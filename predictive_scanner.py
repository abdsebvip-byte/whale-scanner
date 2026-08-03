"""
predictive_scanner.py — الماسح التنبؤي v6.0
=============================================
فكرة حقيقية:
- يبحث عن أسهم تُراكم بقوة (CMF مرتفع) لكن سعرها ما تحرك بعد
- يبحث عن انكماش سعري (Bollinger Squeeze) = طاقة متراكمة
- يبحث عن ضغط شرائي (OBV صاعد مع سعر ثابت)
- يُستبعد الأسهم اللي انفجرت فعلاً (change > 5%)
- الهدف: كشف الأسهم قبل ما تنفجر، مو بعد ما تنفجر
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
import pickle

DB_PATH = "scanner_history.db"
MODEL_PATH = "explosion_model.pkl"
PREDICTIONS_PATH = "predictions.json"

MAX_CHANGE_1D = 8.0
MIN_PRICE = 0.10
MAX_PRICE = 10.0
MIN_VOLUME = 200000

_ENSEMBLE_PREDICTOR = None


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
        next_session_change REAL,
        exploded INTEGER
    )''')
    conn.commit()
    return conn


def get_stock_list(min_volume=100000):
    url = "https://scanner.tradingview.com/america/scan"
    payload = {
        "filter": [
            {"left": "close", "operation": "greater", "right": MIN_PRICE},
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
        print(f"[-] TradingView: {e}")
    return []


def analyze_stock(symbol):
    """تحليل سهم واحد — استخراج ميزات حقيقية"""
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

        if close.iloc[-1] < MIN_PRICE or close.iloc[-1] > MAX_PRICE:
            return None

        features = {}

        # === تغيير السعر — هذا أهم شي ===
        features['change_1d'] = float((close.iloc[-1] - close.iloc[-2]) / close.iloc[-2] * 100) if len(close) >= 2 else 0
        features['change_5d'] = float((close.iloc[-1] - close.iloc[-5]) / close.iloc[-5] * 100) if len(close) >= 5 else 0

        # === الحجم ===
        vol_mean_20 = volume.rolling(20).mean().iloc[-1]
        vol_std_20 = volume.rolling(20).std().iloc[-1]
        today_vol = float(volume.iloc[-1])

        if vol_std_20 > 0 and vol_mean_20 > 0:
            features['volume_z_score'] = float((today_vol - vol_mean_20) / vol_std_20)
            features['volume_ratio'] = float(today_vol / vol_mean_20)
        else:
            features['volume_z_score'] = 0
            features['volume_ratio'] = 1

        vol_5d = volume.tail(5)
        features['volume_5d_avg_ratio'] = float(vol_5d.mean() / vol_mean_20) if vol_mean_20 > 0 else 1

        # === Bollinger Bands ===
        bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
        bb_width = (bb.bollinger_hband() - bb.bollinger_lband()) / close
        bb_width_now = float(bb_width.iloc[-1])
        bb_width_avg = float(bb_width.rolling(20).mean().iloc[-1])
        features['bollinger_width'] = bb_width_now
        features['bollinger_squeeze'] = 1 if (bb_width_now < bb_width_avg * 0.7 and bb_width_avg > 0) else 0

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
            features['cmf'] = float(cmf_vals[-1]) if cmf_vals else 0
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

        # === Price position in 20-day range ===
        range_20 = high.tail(20).max() - low.tail(20).min()
        if range_20 > 0:
            features['price_position'] = float((close.iloc[-1] - low.tail(20).min()) / range_20)
        else:
            features['price_position'] = 0.5

        # === Days since volume started building ===
        vol_build_days = 0
        for i in range(len(volume)-1, max(len(volume)-10, 0), -1):
            if volume.iloc[i] > vol_mean_20 * 1.3:
                vol_build_days += 1
            else:
                break
        features['volume_build_days'] = vol_build_days

        features['symbol'] = symbol
        features['price'] = float(close.iloc[-1])
        features['volume'] = today_vol

        try:
            from feature_pipeline import extract_features

            ohlcv = pd.DataFrame({
                'open': open_price,
                'high': high,
                'low': low,
                'close': close,
                'volume': volume,
            }, index=df.index)
            ml_features = extract_features(ohlcv)
            valid_rows = ml_features.dropna()
            if not valid_rows.empty:
                features['ml_feature_vector'] = [float(v) for v in valid_rows.iloc[-1].tolist()]
        except Exception:
            pass

        return features

    except Exception as e:
        return None


def calculate_explosion_score(stock):
    """
    حساب احتمالية الانفجار — الإصدار المحسّن v2.0
    الأوزان مبنية على تحليل حقيقي لـ 400 تنبؤ سابق.
    """
    ml_prob = _predict_with_ensemble(stock)
    if ml_prob is not None:
        stock['ml_prob'] = ml_prob
        return max(0, min(99, int(round(ml_prob * 100))))

    score = 0

    change_1d = abs(stock.get('change_1d', 0))
    volume_ratio = stock.get('volume_ratio', 0)
    rsi = stock.get('rsi', 50)
    cmf = stock.get('cmf', 0)
    squeeze = stock.get('bollinger_squeeze', 0)
    obv_up = stock.get('obv_above_sma', 0)
    z = stock.get('volume_z_score', 0)
    macd = stock.get('macd_diff', 0)
    vol_build = stock.get('volume_build_days', 0)
    price_pos = stock.get('price_position', 0.5)

    # ─── عقوبة حادة للأسهم اللي انفجرت فعلاً ───
    if change_1d > MAX_CHANGE_1D:
        return 0
    if change_1d > 5:
        return 0
    if change_1d > 3:
        score -= 15

    # ─── حجم مرتفع مع سعر ثابت = أقوى مؤشر (26.1% دقة) ───
    if volume_ratio > 3 and change_1d < 2:
        score += 25
    elif volume_ratio > 2 and change_1d < 2:
        score += 20
    elif volume_ratio > 1.5 and change_1d < 1.5:
        score += 10

    # ─── Z-Score حجم شاذ — مؤشر قوي جداً (21.4% دقة) ───
    if z > 2.0:
        score += 18
    elif z > 1.5:
        score += 14
    elif z > 1.0:
        score += 8

    # ─── انكماش Bollinger — طاقة متراكمة (20.2% دقة) ───
    if squeeze:
        score += 25

    # ─── تجميع (CMF) — دقة متوسطة (17.1%) ───
    if cmf > 0.25:
        score += 20
    elif cmf > 0.15:
        score += 15
    elif cmf > 0.08:
        score += 10
    elif cmf > 0.03:
        score += 5
    elif cmf < -0.1:
        score -= 15

    # ─── OBV صاعد مع سعر ثابت (15.5% دقة) ───
    if obv_up and change_1d < 2:
        score += 12
    elif obv_up:
        score += 5

    # ─── RSI — المجال 40-65 جيد (15.1%)، 30-40 سيء (2.4%) ───
    if 40 <= rsi <= 65:
        score += 12
    elif rsi > 75:
        score -= 10
    elif rsi < 25:
        score -= 5

    # ─── MACD يتحول إيجابي ───
    if macd > 0:
        score += 8
    elif macd > -0.1:
        score += 4

    # ─── بناء الحجم على مدار أيام ───
    if vol_build >= 3:
        score += 12
    elif vol_build >= 2:
        score += 7

    # ─── السعر قريب من قاع النطاق = فرص صعود ───
    if price_pos < 0.3:
        score += 8
    elif price_pos > 0.85:
        score -= 5

    score = max(0, min(score, 99))
    return score


def _predict_with_ensemble(stock):
    global _ENSEMBLE_PREDICTOR

    feature_vector = stock.get('ml_feature_vector')
    if not feature_vector:
        return None

    try:
        if _ENSEMBLE_PREDICTOR is None:
            from ml_engine import EnsemblePredictor

            _ENSEMBLE_PREDICTOR = EnsemblePredictor(model_path=MODEL_PATH)

        if not _ENSEMBLE_PREDICTOR.is_ready():
            return None

        return float(_ENSEMBLE_PREDICTOR.predict_proba(feature_vector))
    except Exception:
        return None


def run_post_session_scan():
    """المسح التنبؤي الرئيسي"""
    import pytz
    try:
        et = pytz.timezone('US/Eastern')
    except:
        et = timezone(timedelta(hours=-4))
    now = datetime.now(et)
    t = now.hour * 60 + now.minute

    if 240 <= t < 570:
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
    print("  الماسح التنبؤي v6.0")
    print(f"  الجلسة: {session_name}")
    print(f"  الوقت: {now.strftime('%Y-%m-%d %H:%M ET')}")
    print("=" * 60)

    conn = init_db()

    print("\n[1/3] جلب الأسهم...")
    all_stocks = get_stock_list(min_volume=MIN_VOLUME)
    if not all_stocks:
        print("[-] فشل جلب الأسهم")
        return []

    # فلترة أولية — إزالة اللي انفجر فعلاً
    candidates = [s for s in all_stocks if abs(s['change']) <= MAX_CHANGE_1D and MIN_PRICE <= s['price'] <= MAX_PRICE]
    print(f"[+] {len(all_stocks)} سهم، {len(candidates)} بعد الفلترة (تغيير < {MAX_CHANGE_1D}%)")

    # ترتيب بالحجم و lấy أفضل
    candidates.sort(key=lambda x: x['volume'], reverse=True)
    candidates = candidates[:500]

    print(f"\n[2/3] تحليل {len(candidates)} سهم...")
    analyzed = []
    for i, stock in enumerate(candidates):
        if i % 50 == 0 and i > 0:
            print(f"  ... {i}/{len(candidates)}")
        features = analyze_stock(stock['symbol'])
        if features:
            # فلترة ثانية — إزالة اللي تحرك بعدين
            if abs(features.get('change_1d', 0)) <= MAX_CHANGE_1D:
                analyzed.append(features)
        time.sleep(0.1)

    print(f"[+] {len(analyzed)} سهم محلل")

    print(f"\n[3/3] حساب الاحتمالات...")
    for stock in analyzed:
        stock['explosion_probability'] = calculate_explosion_score(stock)

    analyzed.sort(key=lambda x: x.get('explosion_probability', 0), reverse=True)

    # حفظ في قاعدة البيانات
    c = conn.cursor()
    for p in analyzed:
        try:
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
                 p.get('bollinger_squeeze', 0),
                 p.get('explosion_probability', 0), 0,
                 0, 0, None, 0))
        except Exception:
            continue
    conn.commit()

    top_predictions = []
    ml_used = False
    for p in analyzed[:30]:
        prediction = {
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
        }
        if p.get('ml_prob') is not None:
            prediction['ml_prob'] = round(p.get('ml_prob', 0), 6)
            ml_used = True
        top_predictions.append(prediction)

    # حفظ الإشارات في جدول signals (يتضمّن ml_prob عند توفّره)
    if top_predictions:
        try:
            from signals import generate_signals_from_predictions
            saved = generate_signals_from_predictions(top_predictions, source_scan_id=None)
            print(f"[+] إشارات: {saved} سجل في جدول signals (ml_prob={'نشط' if ml_used else 'غير متاح'})")
        except Exception as e:
            print(f"  [!] فشل حفظ الإشارات: {e}")

    output = {
        'scan_time': now.isoformat(),
        'session': session,
        'session_name': session_name,
        'total_analyzed': len(analyzed),
        'predictions': top_predictions,
        'model_trained': ml_used,
    }

    with open(PREDICTIONS_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False, default=str)

    print("\n" + "=" * 60)
    print("  أفضل 10 تنبؤات:")
    print("=" * 60)
    for i, p in enumerate(top_predictions[:10], 1):
        prob = p['explosion_probability']
        icon = "!!!" if prob >= 60 else "!" if prob >= 40 else "."
        print(f"\n{i}. {icon} {p['symbol']} — ${p['price']} — {prob}%")
        print(f"   حجم={p['volume_ratio']}x | RSI={p['rsi']} | CMF={p['cmf']}")
        print(f"   تغيير يوم={p['change_1d']:+.1f}% | انكماش={'نعم' if p['bollinger_squeeze'] else 'لا'} | OBV={'صاعد' if p['obv_above_sma'] else 'هابط'}")

    conn.close()
    print(f"\n[OK] محفوظ — {len(top_predictions)} تنبؤ")

    try:
        from outcome_tracker import backfill_outcomes, print_report
        backfill_outcomes()
        print_report()
    except ImportError:
        pass
    except Exception as e:
        print(f"  [!] فشل تتبع النتائج: {e}")

    return top_predictions


if __name__ == "__main__":
    run_post_session_scan()
