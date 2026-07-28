"""
predictive_scanner.py — الماسح التنبؤي
========================================
يُشغّل بعد نهاية كل جلسة ويحلل:
1. أي أسهم تحركت بشكل غير عادي خلال الجلسة
2. أي أنماط سابقة تُشير لانفجار قادم
3. يتنبأ بالأسهم الأعلى احتمالاً للانفجار في الجلسة القادمة

يعمل بـ3 مراحل:
1. جمع بيانات الجلسة المنقضية
2. مقارنة مع أنماط الانفجار التاريخية
3. توليد تنبؤات مرجّحة
"""
import yfinance as yf
import pandas as pd
import numpy as np
import ta
import requests
import json
import sqlite3
import os
import time
import sys
import io
from datetime import datetime, timedelta, timezone
import warnings
warnings.filterwarnings('ignore')
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
import pickle

DB_PATH = "scanner_history.db"
MODEL_PATH = "explosion_model.pkl"
PREDICTIONS_PATH = "predictions.json"

# ─── قاعدة البيانات ────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS session_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scan_time TEXT,
        session_type TEXT,
        symbol TEXT,
        price REAL,
        volume REAL,
        volume_ratio REAL,
        z_score REAL,
        change_pct REAL,
        rsi REAL,
        cmf REAL,
        obv_above INTEGER,
        bollinger_squeeze INTEGER,
        anomaly_score REAL,
        gap_pct REAL,
        float_shares REAL,
        short_percent REAL,
        -- what happened NEXT session
        next_session_change REAL,
        exploded INTEGER
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS explosions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT,
        date TEXT,
        session_type TEXT,
        pre_explosion_signals TEXT,
        price_before REAL,
        price_after_1d REAL,
        price_after_3d REAL,
        change_1d REAL,
        change_3d REAL
    )''')
    conn.commit()
    return conn


# ─── جمع بيانات الجلسة ────────────────────────────────────────

def get_all_stocks_from_tradingview(min_volume=50000):
    """جلب كل الأسهم من TradingView مع أحجامها الحالية"""
    url = "https://scanner.tradingview.com/america/scan"
    payload = {
        "filter": [
            {"left": "close", "operation": "greater", "right": 0.5},
            {"left": "volume", "operation": "greater", "right": min_volume}
        ],
        "markets": ["america"],
        "symbols": {"query": {"types": ["stock"]}, "tickers": []},
        "columns": ["name", "close", "volume", "change", "float_shares_outstanding",
                     "high", "low", "open", "average_volume_10d_calc"],
        "sort": {"sortBy": "volume", "sortOrder": "desc"},
        "range": [0, 6000]
    }
    headers = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            stocks = []
            for item in data.get("data", []):
                sym = item.get("s", "").split(":")[-1]
                d = item.get("d", [])
                if sym and len(d) >= 9:
                    if '/' in sym or '.U' in sym or '.W' in sym:
                        continue
                    stocks.append({
                        'symbol': sym,
                        'price': float(d[1] or 0),
                        'volume': float(d[2] or 0),
                        'change': float(d[3] or 0),
                        'float': float(d[4] or 0),
                        'high': float(d[5] or 0),
                        'low': float(d[6] or 0),
                        'open': float(d[7] or 0),
                        'avg_volume_10d': float(d[8] or 0),
                    })
            return stocks
    except Exception as e:
        print(f"[-] TradingView error: {e}")
    return []


def analyze_stock_for_prediction(symbol):
    """
    تحليل سهم واحد — استخراج الميزات للتنبؤ
    يرجع ميزات حقيقية من بيانات yfinance
    """
    try:
        df = yf.download(symbol, period="6mo", progress=False)
        if df is None or len(df) < 30:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        close = df['Close'].astype(float)
        volume = df['Volume'].astype(float)
        high = df['High'].astype(float)
        low = df['Low'].astype(float)
        open_price = df['Open'].astype(float)

        features = {}

        # === الحجم ===
        vol_mean_20 = volume.rolling(20).mean().iloc[-1]
        vol_std_20 = volume.rolling(20).std().iloc[-1]
        today_vol = float(volume.iloc[-1])

        if vol_std_20 > 0 and vol_mean_20 > 0:
            features['volume_z_score'] = (today_vol - vol_mean_20) / vol_std_20
            features['volume_ratio'] = today_vol / vol_mean_20
        else:
            features['volume_z_score'] = 0
            features['volume_ratio'] = 1

        # حجم 5 أيام
        vol_5d = volume.tail(5)
        features['volume_5d_avg_ratio'] = float(vol_5d.mean() / vol_mean_20) if vol_mean_20 > 0 else 1
        features['high_volume_days'] = sum(1 for z in (volume - vol_mean_20) / vol_std_20 if z > 2) if vol_std_20 > 0 else 0

        # === السعر ===
        features['change_1d'] = float((close.iloc[-1] - close.iloc[-2]) / close.iloc[-2] * 100) if len(close) >= 2 else 0
        features['change_5d'] = float((close.iloc[-1] - close.iloc[-5]) / close.iloc[-5] * 100) if len(close) >= 5 else 0
        features['change_20d'] = float((close.iloc[-1] - close.iloc[-20]) / close.iloc[-20] * 100) if len(close) >= 20 else 0

        # === Bollinger Bands ===
        bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
        bb_width = (bb.bollinger_hband() - bb.bollinger_lband()) / close
        bb_width_now = float(bb_width.iloc[-1])
        bb_width_avg = float(bb_width.rolling(20).mean().iloc[-1])
        features['bollinger_width'] = bb_width_now
        features['bollinger_squeeze'] = 1 if (bb_width_now < bb_width_avg * 0.7 and bb_width_avg > 0) else 0
        features['bollinger_pct'] = float(bb.bollinger_pband().iloc[-1]) if not pd.isna(bb.bollinger_pband().iloc[-1]) else 0.5

        # === RSI ===
        rsi = ta.momentum.RSIIndicator(close, window=14)
        features['rsi'] = float(rsi.rsi().iloc[-1]) if not pd.isna(rsi.rsi().iloc[-1]) else 50

        # === CMF ===
        try:
            ad = ta.volume.AccDistIndexIndicator(high=high, low=low, close=close, volume=volume)
            ad_line = ad.acc_dist_index()
            cmf_vals = []
            for i in range(20, len(df)):
                pad = ad_line.iloc[i] - ad_line.iloc[i-20]
                pvol = volume.iloc[i-20:i].sum()
                cmf_vals.append(pad / pvol if pvol > 0 else 0)
            features['cmf'] = cmf_vals[-1] if cmf_vals else 0
        except:
            features['cmf'] = 0

        # === OBV ===
        try:
            obv = ta.volume.OnBalanceVolumeIndicator(close=close, volume=volume)
            obv_line = obv.on_balance_volume()
            obv_sma = obv_line.rolling(20).mean()
            features['obv_above_sma'] = 1 if float(obv_line.iloc[-1]) > float(obv_sma.iloc[-1]) else 0
        except:
            features['obv_above_sma'] = 0

        # === ATR ===
        try:
            atr = ta.volatility.AverageTrueRange(high=high, low=low, close=close, window=14)
            features['atr_ratio'] = float(atr.average_true_range().iloc[-1] / close.iloc[-1]) if close.iloc[-1] > 0 else 0
        except:
            features['atr_ratio'] = 0

        # === MACD ===
        try:
            macd = ta.trend.MACD(close)
            features['macd_diff'] = float(macd.macd_diff().iloc[-1]) if not pd.isna(macd.macd_diff().iloc[-1]) else 0
        except:
            features['macd_diff'] = 0

        # === Distance from 52w high/low ===
        features['dist_from_52w_high'] = float((close.iloc[-1] - close.max()) / close.max() * 100)
        features['dist_from_52w_low'] = float((close.iloc[-1] - close.min()) / close.min() * 100)

        # === Price position in range ===
        range_20 = high.tail(20).max() - low.tail(20).min()
        if range_20 > 0:
            features['price_position'] = float((close.iloc[-1] - low.tail(20).min()) / range_20)
        else:
            features['price_position'] = 0.5

        # === Gap from open ===
        today_open = float(open_price.iloc[-1])
        today_close = float(close.iloc[-1])
        if today_open > 0:
            features['gap_from_open'] = (today_close - today_open) / today_open * 100
        else:
            features['gap_from_open'] = 0

        features['symbol'] = symbol
        features['price'] = float(close.iloc[-1])
        features['volume'] = today_vol

        return features

    except Exception as e:
        return None


# ─── كشف أنماط الانفجار التاريخية ─────────────────────────────

def find_explosion_patterns(conn):
    """
    يبحث في التاريخ عن أنماط السباق للانفجارات
    انفجار = سهم صعد >8% في يوم واحد بعد جلسة معينة
    """
    c = conn.cursor()
    c.execute('''
        SELECT symbol, scan_time, session_type, price, volume_ratio, z_score,
               change_pct, rsi, cmf, obv_above, bollinger_squeeze,
               next_session_change, exploded
        FROM session_data
        WHERE exploded = 1
        ORDER BY scan_time DESC
        LIMIT 200
    ''')
    rows = c.fetchall()
    patterns = []
    for row in rows:
        patterns.append({
            'symbol': row[0], 'time': row[1], 'session': row[2],
            'price': row[3], 'volume_ratio': row[4], 'z_score': row[5],
            'change_pct': row[6], 'rsi': row[7], 'cmf': row[8],
            'obv_above': row[9], 'squeeze': row[10],
            'next_change': row[11], 'exploded': row[12],
        })
    return patterns


def build_training_data(conn):
    """
    بناء بيانات التدريب من التاريخ
    positives: أسهم انفجرت بعد جلسة
    negatives: أسهم ما انفجرت
    """
    c = conn.cursor()

    # إيجابيات — أسهم انفجرت
    c.execute('''
        SELECT volume_ratio, z_score, change_pct, rsi, cmf, obv_above,
               bollinger_squeeze, gap_pct, float_shares, short_percent,
               next_session_change
        FROM session_data
        WHERE exploded = 1 AND next_session_change IS NOT NULL
    ''')
    positives = c.fetchall()

    # سلبيات — أسهم ما انفجرت
    c.execute('''
        SELECT volume_ratio, z_score, change_pct, rsi, cmf, obv_above,
               bollinger_squeeze, gap_pct, float_shares, short_percent,
               next_session_change
        FROM session_data
        WHERE exploded = 0 AND next_session_change IS NOT NULL
    ''')
    negatives = c.fetchall()

    if len(positives) < 10 or len(negatives) < 10:
        return None, None, None

    feature_names = ['volume_ratio', 'z_score', 'change_pct', 'rsi', 'cmf',
                     'obv_above', 'bollinger_squeeze', 'gap_pct', 'float_shares',
                     'short_percent', 'next_session_change']

    X_pos = np.array([[r[i] for i in range(len(r)-1)] for r in positives])
    X_neg = np.array([[r[i] for i in range(len(r)-1)] for r in negatives])

    X = np.vstack([X_pos, X_neg])
    y = np.array([1]*len(positives) + [0]*len(negatives))

    # Replace NaN
    X = np.nan_to_num(X, nan=0)

    return X, y, feature_names


# ─── النموذج ──────────────────────────────────────────────────

def train_model(conn):
    """تدريب نموذج التنبؤ"""
    X, y, feature_names = build_training_data(conn)
    if X is None:
        print("[-] لا توجد بيانات كافية للتدريب (تحتاج 10+ انفجارات و10+ سلبيات)")
        return None

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    model = GradientBoostingClassifier(
        n_estimators=100, max_depth=4, learning_rate=0.1,
        random_state=42
    )
    model.fit(X_scaled, y)

    # حفظ النموذج
    with open(MODEL_PATH, 'wb') as f:
        pickle.dump({'model': model, 'scaler': scaler, 'features': feature_names}, f)

    accuracy = model.score(X_scaled, y)
    print(f"[+] النموذج مدرب — دقة: {accuracy:.1%}")
    print(f"   ميزات: {feature_names}")
    print(f"   أهمية: {dict(zip(feature_names, [round(x,3) for x in model.feature_importances_]))}")

    return {'model': model, 'scaler': scaler, 'features': feature_names}


def load_model():
    if os.path.exists(MODEL_PATH):
        with open(MODEL_PATH, 'rb') as f:
            return pickle.load(f)
    return None


# ─── التنبؤ ────────────────────────────────────────────────────

def predict_explosions(stocks_to_analyze, model_data=None):
    """
    التنبؤ بالأسهم اللي ممكن تنفجر الجلسة القادمة
    """
    print(f"\n[تنبؤ] تحليل {len(stocks_to_analyze)} سهم...")

    analyzed = []
    for i, stock in enumerate(stocks_to_analyze):
        if i % 50 == 0 and i > 0:
            print(f"  ... {i}/{len(stocks_to_analyze)}")
        features = analyze_stock_for_prediction(stock['symbol'])
        if features:
            analyzed.append(features)
        time.sleep(0.1)

    print(f"[+] {len(analyzed)} سهم محلل")

    if not analyzed:
        return []

    predictions = []

    if model_data:
        # استخدام النموذج المدرب
        feature_names = model_data['features']
        model = model_data['model']
        scaler = model_data['scaler']

        for stock in analyzed:
            try:
                X = np.array([[stock.get(f, 0) for f in feature_names]])
                X = np.nan_to_num(X, nan=0)
                X_scaled = scaler.transform(X)
                prob = model.predict_proba(X_scaled)[0][1]
                stock['explosion_probability'] = round(prob * 100, 1)
                predictions.append(stock)
            except Exception:
                stock['explosion_probability'] = 0
                predictions.append(stock)
    else:
        # بدون نموذج — قواعد بسيطة مبنية على الأنماط المعروفة
        for stock in analyzed:
            score = 0

            # حجم مرتفع + انكماش = احتمال انفجار
            if stock.get('volume_ratio', 0) > 2.0:
                score += 20
            if stock.get('volume_z_score', 0) > 2.5:
                score += 15

            # انكماش Bollinger = السعر يجهز لحركة
            if stock.get('bollinger_squeeze', 0) == 1:
                score += 25

            # CMF إيجابي = تجميع
            if stock.get('cmf', 0) > 0.1:
                score += 15

            # RSI معتدل (30-70) = في مجال للحركة
            rsi = stock.get('rsi', 50)
            if 30 <= rsi <= 70:
                score += 10
            elif rsi < 30:
                score += 5  # oversold bounce potential

            # OBV صاعد = ضغط شرائي
            if stock.get('obv_above_sma', 0) == 1:
                score += 10

            # MACD إيجابي
            if stock.get('macd_diff', 0) > 0:
                score += 5

            stock['explosion_probability'] = min(score, 99)
            predictions.append(stock)

    predictions.sort(key=lambda x: x.get('explosion_probability', 0), reverse=True)
    return predictions


# ─── المنسّق الرئيسي ──────────────────────────────────────────

def run_post_session_scan():
    """
    المسح التنبؤي — يُشغّل بعد نهاية كل جلسة
    """
    EDT = timezone(timedelta(hours=-4))
    now = datetime.now(EDT)
    t = now.hour * 60 + now.minute

    if 390 <= t < 570:
        session = "premarket"
        session_name = "ما قبل التداول"
    elif 570 <= t < 960:
        session = "regular"
        session_name = "الجلسة الرسمية"
    elif 960 <= t < 1200:
        session = "afterhours"
        session_name = "الجلسة المسائية"
    else:
        session = "closed"
        session_name = "السوق مغلق"

    print("=" * 60)
    print("  🔮 الماسح التنبؤي v5.0")
    print(f"  الجلسة: {session_name}")
    print(f"  الوقت: {now.strftime('%Y-%m-%d %H:%M ET')}")
    print("=" * 60)

    conn = init_db()

    # الخطوة 1: جلب الأسهم
    print("\n[1/4] جلب قائمة الأسهم...")
    all_stocks = get_all_stocks_from_tradingview(min_volume=100000)
    if not all_stocks:
        print("[-] فشل جلب الأسهم")
        return []
    print(f"[+] {len(all_stocks)} سهم")

    # الخطوة 2: تحليل الأفضل
    print(f"\n[2/4] تحليل أفضل 400 سهم...")
    sorted_by_vol = sorted(all_stocks, key=lambda x: x['volume'], reverse=True)
    candidates = sorted_by_vol[:300] + all_stocks[600:2000:5]
    candidates = candidates[:400]

    # الخطوة 3: التنبؤ
    print(f"\n[3/4] التنبؤ بالانفجارات...")
    model_data = load_model()
    if model_data:
        print("[+] تم تحميل النموذج المدرب")
    else:
        print("[-] لا يوجد نموذج — استخدام القواعد")

    predictions = predict_explosions(candidates, model_data)

    # حفظ في قاعدة البيانات
    print(f"\n[4/4] حفظ البيانات...")
    c = conn.cursor()
    for p in predictions:
        try:
            # التحقق إذا انفجر هذا السهم في الجلسة القادمة (للتاريخ)
            c.execute('''INSERT INTO session_data
                (scan_time, session_type, symbol, price, volume, volume_ratio,
                 z_score, change_pct, rsi, cmf, obv_above, bollinger_squeeze,
                 anomaly_score, gap_pct, float_shares, short_percent,
                 next_session_change, exploded)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (now.isoformat(), session, p.get('symbol', ''),
                 p.get('price', 0), p.get('volume', 0),
                 p.get('volume_ratio', 0), p.get('volume_z_score', 0),
                 p.get('change_1d', 0), p.get('rsi', 50),
                 p.get('cmf', 0), p.get('obv_above_sma', 0),
                 p.get('bollinger_squeeze', 0), 0, 0,
                 0, 0, None, 0))
        except Exception:
            continue
    conn.commit()

    # حفظ التنبؤات
    top_predictions = []
    for p in predictions[:30]:
        top_predictions.append({
            'symbol': p.get('symbol', ''),
            'price': round(p.get('price', 0), 2),
            'explosion_probability': p.get('explosion_probability', 0),
            'volume_ratio': round(p.get('volume_ratio', 0), 2),
            'z_score': round(p.get('volume_z_score', 0), 2),
            'rsi': round(p.get('rsi', 50), 1),
            'cmf': round(p.get('cmf', 0), 4),
            'bollinger_squeeze': bool(p.get('bollinger_squeeze', 0)),
            'obv_above_sma': bool(p.get('obv_above_sma', 0)),
            'change_1d': round(p.get('change_1d', 0), 2),
            'change_5d': round(p.get('change_5d', 0), 2),
            'atr_ratio': round(p.get('atr_ratio', 0), 4),
            'macd_diff': round(p.get('macd_diff', 0), 4),
        })

    output = {
        'scan_time': now.isoformat(),
        'session': session,
        'session_name': session_name,
        'total_analyzed': len(predictions),
        'predictions': top_predictions,
        'model_trained': model_data is not None,
    }

    with open(PREDICTIONS_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False, default=str)

    # print top predictions
    print("\n" + "=" * 60)
    print(f"  🔮 أفضل 10 تنبؤات للجلسة القادمة:")
    print("=" * 60)
    for i, p in enumerate(top_predictions[:10], 1):
        prob = p['explosion_probability']
        icon = "🔴" if prob >= 70 else "🟡" if prob >= 40 else "🟢"
        print(f"\n{i}. {icon} {p['symbol']} — ${p['price']}")
        print(f"   احتمال الانفجار: {prob}%")
        print(f"   حجم={p['volume_ratio']}x | Z={p['z_score']} | RSI={p['rsi']}")
        print(f"   قوة التجميع={p['cmf']} | انكماش={'نعم' if p['bollinger_squeeze'] else 'لا'} | OBV={'صاعد' if p['obv_above_sma'] else 'هابط'}")

    conn.close()
    print(f"\n[✓] محفوظ في {PREDICTIONS_PATH}")
    return top_predictions


if __name__ == "__main__":
    run_post_session_scan()
