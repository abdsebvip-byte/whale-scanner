"""
ماسح الحيتان v5.0 — النسخة الكاملة الحقيقية
==============================================
بيانات حقيقية فقط. لا توصيات وهمية.

المصادر الحقيقية:
1. TradingView API → قائمة الأسهم + أسعار + أحجام
2. yfinance → بيانات تاريخية + خيارات + بيع عَمَي + أخبار
3. scikit-learn → Isolation Forest للكشف عن الشذوذ
4. TA Library → CMF, OBV, Bollinger Bands, RSI
5. SEC EDGAR → شراء المسؤولين الداخليين
6. SQLite → تتبع تاريخ الإشارات والنتائج

الفئات:
A) تحليل الحجم (Z-Score + انكماش Bollinger + تطبيع الوقت)
B) خيارات غير عادية (UOA)
C) مؤشرات التجميع (CMF, OBV)
D) كشف الشذوذ (Isolation Forest)
E) كشف الفجوات (Gap Detection)
F) شراء المسؤولين الداخليين (SEC EDGAR)
G) عناوين الأخبار
H) نظام التقييم (Whale Score 0-100)
"""
import requests
import yfinance as yf
import pandas as pd
import numpy as np
import ta
from datetime import datetime, timedelta, timezone
import time
import sys
import io
import json
import sqlite3
import warnings
warnings.filterwarnings('ignore')
from sklearn.ensemble import IsolationForest
from self_learning import load_memory, save_memory, record_scan_result, analyze_misses, get_threshold_adjustments

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


# ─── قاعدة البيانات ────────────────────────────────────────────

DB_PATH = "scanner_history.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS scan_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scan_time TEXT,
        symbol TEXT,
        signals_json TEXT,
        price REAL,
        score REAL,
        grade TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS outcome_tracking (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT,
        scan_time TEXT,
        signals_json TEXT,
        price_at_scan REAL,
        price_1d REAL,
        price_3d REAL,
        price_5d REAL,
        change_1d REAL,
        change_3d REAL,
        change_5d REAL
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS insider_buying (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT,
        filing_date TEXT,
        insider_name TEXT,
        title TEXT,
        shares REAL,
        price REAL,
        value REAL,
        transaction_type TEXT
    )''')
    conn.commit()
    return conn


def save_scan_to_db(conn, signals):
    c = conn.cursor()
    for sig in signals:
        c.execute('''INSERT INTO scan_history
            (scan_time, symbol, signals_json, price, score, grade)
            VALUES (?, ?, ?, ?, ?, ?)''',
            (datetime.now().isoformat(), sig['symbol'],
             json.dumps([s['type'] for s in sig.get('signals', [])]),
             sig.get('price', 0), sig.get('whale_score', 0), sig.get('grade', 'F')))
    conn.commit()


def track_outcomes(conn, symbols):
    c = conn.cursor()
    for sym in symbols:
        c.execute('''SELECT id, scan_time, price_at_scan FROM outcome_tracking
            WHERE symbol = ? AND price_5d IS NULL
            ORDER BY scan_time DESC LIMIT 5''', (sym,))
        rows = c.fetchall()
        if not rows:
            continue
        try:
            ticker = yf.Ticker(sym)
            hist = ticker.history(period="7d")
            if hist is None or len(hist) < 2:
                continue
            prices = hist['Close'].values
            for row_id, scan_time, price_at_scan in rows:
                scan_dt = datetime.fromisoformat(scan_time)
                deltas = []
                for p in prices:
                    idx = len(deltas)
                    if idx < 1:
                        deltas.append(('price_1d', round(float(p), 2)))
                    elif idx < 3:
                        deltas.append(('price_3d', round(float(p), 2)))
                    elif idx < 5:
                        deltas.append(('price_5d', round(float(p), 2)))
                for field, val in deltas:
                    c.execute(f'UPDATE outcome_tracking SET {field} = ? WHERE id = ?', (val, row_id))
                if price_at_scan > 0:
                    for field in ['price_1d', 'price_3d', 'price_5d']:
                        c.execute(f'SELECT {field} FROM outcome_tracking WHERE id = ?', (row_id,))
                        pp = c.fetchone()[0]
                        if pp and pp > 0:
                            change_field = field.replace('price_', 'change_')
                            c.execute(f'UPDATE outcome_tracking SET {change_field} = ? WHERE id = ?',
                                      (round(((pp - price_at_scan) / price_at_scan) * 100, 2), row_id))
            conn.commit()
        except Exception:
            continue


# ─── كشف الفجوات ──────────────────────────────────────────────

def detect_gap(symbol):
    """كشف فجوات السعر ما قبل الافتتاح"""
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        prev_close = info.get('previousClose', 0)
        current_price = info.get('currentPrice') or info.get('regularMarketPrice', 0)
        pre_market = info.get('preMarketPrice', 0)
        after_hours = info.get('postMarketPrice', 0)

        gaps = []
        if prev_close > 0:
            if pre_market > 0:
                gap_pct = ((pre_market - prev_close) / prev_close) * 100
                if abs(gap_pct) > 2:
                    gaps.append({
                        'type': 'PREGAP_UP' if gap_pct > 0 else 'PREGAP_DOWN',
                        'percent': round(gap_pct, 2),
                        'from': round(prev_close, 2),
                        'to': round(pre_market, 2),
                    })
            if after_hours > 0:
                gap_pct = ((after_hours - prev_close) / prev_close) * 100
                if abs(gap_pct) > 2:
                    gaps.append({
                        'type': 'AH_GAP_UP' if gap_pct > 0 else 'AH_GAP_DOWN',
                        'percent': round(gap_pct, 2),
                        'from': round(prev_close, 2),
                        'to': round(after_hours, 2),
                    })
        return gaps if gaps else None
    except Exception:
        return None


# ─── أخبار ─────────────────────────────────────────────────────

def get_stock_news(symbol):
    """جلب عناوين الأخبار من yfinance"""
    try:
        ticker = yf.Ticker(symbol)
        news = ticker.news
        if not news:
            return None

        headlines = []
        for item in news[:5]:
            title = item.get('title', '')
            publisher = item.get('publisher', '')
            link = item.get('link', '')
            pub_date = datetime.fromtimestamp(item.get('providerPublishTime', 0)).strftime('%Y-%m-%d') if item.get('providerPublishTime') else ''
            if title:
                headlines.append({
                    'title': title,
                    'publisher': publisher,
                    'date': pub_date,
                    'link': link,
                })

        if headlines:
            return {
                'count': len(headlines),
                'headlines': headlines,
                'is_news_heavy': len(headlines) >= 3,
            }
        return None
    except Exception:
        return None


# ─── شراء المسؤولين الداخليين ─────────────────────────────────

def get_insider_buying(symbol):
    """كشف شراء المسؤولين الداخليين من SEC EDGAR عبر yfinance"""
    try:
        ticker = yf.Ticker(symbol)
        insider = ticker.insider_transactions
        if insider is None or len(insider) == 0:
            return None

        buys = []
        for _, row in insider.iterrows():
            text = str(row.get('Text', '')).lower()
            if 'purchase' in text or 'buy' in text:
                buys.append({
                    'insider': row.get('Insider Name', ''),
                    'title': row.get('Title', ''),
                    'date': str(row.get('Start Date', '')),
                    'shares': row.get('Shares', 0),
                    'price': row.get('Price', 0),
                    'value': row.get('Value', 0),
                })

        if buys:
            total_value = sum(b.get('value', 0) or 0 for b in buys)
            return {
                'count': len(buys),
                'transactions': buys[:10],
                'total_value': total_value,
            }
        return None
    except Exception:
        return None


# ─── الجلسات ──────────────────────────────────────────────────

def get_current_session():
    EDT = timezone(timedelta(hours=-4))
    now_et = datetime.now(EDT)
    t = now_et.hour * 60 + now_et.minute
    if 390 <= t < 570:
        return "premarket", "ماقبل التداول"
    elif 570 <= t < 960:
        return "regular", "الجلسة الرسمية"
    elif 960 <= t < 1200:
        return "afterhours", "الجلسة المسائية"
    else:
        return "closed", "السوق مغلق"


def get_session_minutes_elapsed():
    EDT = timezone(timedelta(hours=-4))
    now_et = datetime.now(EDT)
    t = now_et.hour * 60 + now_et.minute
    if 570 <= t < 960:
        return t - 570
    return 390


def normalize_volume_for_session(volume_today, minutes_elapsed, session_code):
    """تطبيع الحجم حسب الوقت المنقضي في الجلسة"""
    if session_code == 'regular':
        full_session_minutes = 390
    elif session_code == 'premarket':
        full_session_minutes = 180
    elif session_code == 'afterhours':
        full_session_minutes = 240
    else:
        full_session_minutes = 390

    if minutes_elapsed <= 0:
        return volume_today

    extrapolated = (volume_today / minutes_elapsed) * full_session_minutes
    return extrapolated


# ─── نظام التقييم ─────────────────────────────────────────────

def calculate_whale_score(signals, data):
    """حساب درجة الحوت 0-100 بناءً على قوة الإشارات"""
    score = 0

    for signal in signals:
        sig_type = signal['type']

        if sig_type == 'VOLUME_ANOMALY':
            z = data.get('z_score', 0)
            if z > 4:
                score += 25
            elif z > 3:
                score += 20
            elif z > 2.5:
                score += 15
            elif z > 2:
                score += 10

        elif sig_type == 'BOLLINGER_SQUEEZE':
            score += 15

        elif sig_type == 'ACCUMULATION':
            cmf = data.get('cmf', 0)
            if cmf > 0.3:
                score += 20
            elif cmf > 0.2:
                score += 15
            elif cmf > 0.15:
                score += 10

        elif sig_type == 'MULTI_DAY_VOLUME':
            days = data.get('high_volume_days_5', 0)
            score += min(days * 5, 20)

        elif sig_type == 'UNUSUAL_OPTIONS':
            score += 20

        elif sig_type == 'HIGH_SHORT_INTEREST':
            score += 15

        elif sig_type == 'ANOMALY_DETECTED':
            score += 10

        elif sig_type == 'GAP_DETECTED':
            score += 12

        elif sig_type == 'NEWS_HEAVY':
            score += 8

        elif sig_type == 'INSIDER_BUYING':
            score += 18

    # مكافأة التنوع
    num_signals = len(signals)
    if num_signals >= 4:
        score += 15
    elif num_signals >= 3:
        score += 10
    elif num_signals >= 2:
        score += 5

    # RSI factor
    rsi = data.get('rsi', 50)
    if 30 <= rsi <= 70:
        score += 5

    score = min(score, 100)

    if score >= 75:
        grade = 'A+'
    elif score >= 60:
        grade = 'A'
    elif score >= 45:
        grade = 'B+'
    elif score >= 30:
        grade = 'B'
    elif score >= 20:
        grade = 'C'
    else:
        grade = 'D'

    return score, grade


# ─── الماسح الرئيسي ──────────────────────────────────────────

class WhaleScanner:
    def __init__(self):
        self.all_symbols = []

    def fetch_all_market_symbols(self):
        url = "https://scanner.tradingview.com/america/scan"
        payload = {
            "filter": [
                {"left": "close", "operation": "greater", "right": 0.5},
                {"left": "volume", "operation": "greater", "right": 50000}
            ],
            "markets": ["america"],
            "symbols": {"query": {"types": ["stock"]}, "tickers": []},
            "columns": ["name", "close", "volume", "change", "float_shares_outstanding",
                         "high", "low", "open"],
            "sort": {"sortBy": "volume", "sortOrder": "desc"},
            "range": [0, 6000]
        }
        headers = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            if response.status_code == 200:
                data = response.json()
                rows = data.get("data", [])
                symbols = []
                for item in rows:
                    sym = item.get("s", "").split(":")[-1]
                    d = item.get("d", [])
                    if sym and len(d) >= 5:
                        price = float(d[1] or 0)
                        volume = float(d[2] or 0)
                        change = float(d[3] or 0)
                        float_shares = float(d[4] or 0) if d[4] else 0
                        if price > 0.5 and volume > 50000:
                            if '/' in sym or '.U' in sym or '.W' in sym or '.R' in sym:
                                continue
                            symbols.append({
                                'symbol': sym, 'price': price, 'volume': volume,
                                'change': change, 'float': float_shares,
                            })
                self.all_symbols = symbols
                print(f"[+] TradingView: {len(symbols)} سهم")
                return symbols
            else:
                print(f"[-] TradingView خطأ: {response.status_code}")
                return []
        except Exception as e:
            print(f"[-] خطأ اتصال: {e}")
            return []

    def analyze_stock(self, symbol):
        """تحليل شامل لسهم واحد — كل الحسابات حقيقية"""
        try:
            df = yf.download(symbol, period="3mo", progress=False)
            if df is None or len(df) < 30:
                return None

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            close = df['Close'].astype(float)
            volume = df['Volume'].astype(float)
            high = df['High'].astype(float)
            low = df['Low'].astype(float)

            result = {'symbol': symbol}

            # === A) تحليل الحجم ===
            vol_mean = volume.rolling(20).mean()
            vol_std = volume.rolling(20).std()
            mean_val = float(vol_mean.iloc[-1]) if not pd.isna(vol_mean.iloc[-1]) else 0
            std_val = float(vol_std.iloc[-1]) if not pd.isna(vol_std.iloc[-1]) else 0
            today_vol = float(volume.iloc[-1])

            if std_val > 0 and mean_val > 0:
                z_score = (today_vol - mean_val) / std_val
                relative_vol = today_vol / mean_val
            else:
                z_score = 0
                relative_vol = 1

            result['z_score'] = round(z_score, 2)
            result['relative_volume'] = round(relative_vol, 2)
            result['today_volume'] = int(today_vol)
            result['avg_volume_20d'] = int(mean_val)

            vol_z_scores = (volume - vol_mean) / vol_std
            high_vol_days = sum(1 for z in vol_z_scores.dropna().tail(5) if z > 2)
            result['high_volume_days_5'] = high_vol_days

            # === B) Bollinger Bands ===
            bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
            bb_high = bb.bollinger_hband()
            bb_low = bb.bollinger_lband()
            bb_width = (bb_high - bb_low) / close

            current_width = float(bb_width.iloc[-1]) if not pd.isna(bb_width.iloc[-1]) else 0
            avg_width = float(bb_width.rolling(20).mean().iloc[-1]) if len(bb_width) > 20 else 0

            result['bollinger_width'] = round(current_width, 4)
            result['bollinger_squeeze'] = current_width < avg_width * 0.7 if avg_width > 0 else False

            # === C) CMF + OBV ===
            try:
                ad = ta.volume.AccDistIndexIndicator(high=high, low=low, close=close, volume=volume)
                ad_line = ad.acc_dist_index()

                cmf_values = []
                for i in range(20, len(df)):
                    period_ad = ad_line.iloc[i] - ad_line.iloc[i-20]
                    period_vol = volume.iloc[i-20:i].sum()
                    if period_vol > 0:
                        cmf_values.append(period_ad / period_vol)
                    else:
                        cmf_values.append(0)

                result['cmf'] = round(cmf_values[-1], 4) if cmf_values else 0
            except Exception:
                result['cmf'] = 0

            try:
                obv = ta.volume.OnBalanceVolumeIndicator(close=close, volume=volume)
                obv_line = obv.on_balance_volume()
                obv_sma = obv_line.rolling(20).mean()
                result['obv_trend'] = 'صاعد' if float(obv_line.iloc[-1]) > float(obv_sma.iloc[-1]) else 'هابط'
                result['obv_above_sma'] = float(obv_line.iloc[-1]) > float(obv_sma.iloc[-1])
            except Exception:
                result['obv_trend'] = 'غير معروف'
                result['obv_above_sma'] = False

            # === D) RSI ===
            try:
                rsi = ta.momentum.RSIIndicator(close, window=14)
                result['rsi'] = round(float(rsi.rsi().iloc[-1]), 1)
            except Exception:
                result['rsi'] = 50

            # === E) تغيّر السعر ===
            close_valid = close.dropna()
            if len(close_valid) >= 6:
                price_now = float(close_valid.iloc[-1])
                price_5d = float(close_valid.iloc[-5])
                result['change_5d'] = round(((price_now - price_5d) / price_5d) * 100, 2) if price_5d > 0 else 0
            else:
                result['change_5d'] = 0

            result['price'] = float(close.iloc[-1]) if len(close) > 0 else 0

            # === F) Isolation Forest ===
            try:
                features = pd.DataFrame({
                    'volume_ratio': volume / volume.rolling(20).mean(),
                    'close_change': close.pct_change(),
                    'high_low_range': (high - low) / close,
                    'rsi_val': ta.momentum.RSIIndicator(close, window=14).rsi(),
                }).dropna()

                if len(features) >= 20:
                    iso_forest = IsolationForest(n_estimators=100, contamination=0.05, random_state=42)
                    features['anomaly'] = iso_forest.fit_predict(features)
                    features['anomaly_score'] = iso_forest.decision_function(features)
                    latest = features.iloc[-1]
                    result['anomaly_score'] = round(float(latest['anomaly_score']), 3)
                    result['is_anomaly'] = latest['anomaly'] == -1
                else:
                    result['anomaly_score'] = 0
                    result['is_anomaly'] = False
            except Exception:
                result['anomaly_score'] = 0
                result['is_anomaly'] = False

            return result

        except Exception:
            return None

    def analyze_options(self, symbol):
        """خيارات غير عادية — بيانات حقيقية من yfinance"""
        try:
            ticker = yf.Ticker(symbol)
            expirations = ticker.options
            if not expirations:
                return None

            unusual = []
            for exp in expirations[:3]:
                try:
                    chain = ticker.option_chain(exp)
                    calls = chain.calls
                    puts = chain.puts

                    for _, row in calls.iterrows():
                        vol = row.get('volume', 0) or 0
                        oi = row.get('openInterest', 0) or 0
                        if oi > 0 and vol > oi * 3:
                            unusual.append({
                                'type': 'CALL',
                                'contract': row.get('contractSymbol', ''),
                                'expiry': exp,
                                'strike': row.get('strike', 0),
                                'volume': int(vol),
                                'open_interest': int(oi),
                                'ratio': round(vol / oi, 1),
                                'price': row.get('lastPrice', 0),
                            })

                    for _, row in puts.iterrows():
                        vol = row.get('volume', 0) or 0
                        oi = row.get('openInterest', 0) or 0
                        if oi > 0 and vol > oi * 3:
                            unusual.append({
                                'type': 'PUT',
                                'contract': row.get('contractSymbol', ''),
                                'expiry': exp,
                                'strike': row.get('strike', 0),
                                'volume': int(vol),
                                'open_interest': int(oi),
                                'ratio': round(vol / oi, 1),
                                'price': row.get('lastPrice', 0),
                            })
                except Exception:
                    continue

            if unusual:
                total_call_vol = sum(u['volume'] for u in unusual if u['type'] == 'CALL')
                total_put_vol = sum(u['volume'] for u in unusual if u['type'] == 'PUT')
                return {
                    'contracts': unusual,
                    'count': len(unusual),
                    'total_call_volume': total_call_vol,
                    'total_put_volume': total_put_vol,
                    'bias': 'صعودي' if total_call_vol > total_put_vol * 2 else 'هبوطي' if total_put_vol > total_call_vol * 2 else 'محايد',
                }
            return None
        except Exception:
            return None

    def get_short_data(self, symbol):
        """بيانات بيع العَمَي — حقيقية من yfinance"""
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            sp = info.get('shortPercentOfFloat', None)
            sr = info.get('shortRatio', None)
            fs = info.get('floatShares', None)
            if sp is not None and sp > 0:
                return {
                    'short_percent': sp,
                    'days_to_cover': sr,
                    'float_shares': fs,
                }
            return None
        except Exception:
            return None

    def scan(self, include_insider=False, include_news=True):
        session_code, session_name = get_current_session()
        minutes_elapsed = get_session_minutes_elapsed()

        memory = load_memory()
        adjustments = get_threshold_adjustments(memory)
        z_threshold = adjustments.get("min_z_score", 2.0)
        rsi_oversold_threshold = adjustments.get("rsi_oversold", 30)

        conn = init_db()

        print("=" * 60)
        print("  ماسح الحيتان v5.0 — النسخة الكاملة الحقيقية")
        print(f"  الجلسة: {session_name}")
        print(f"  أوقات الجلسة: {minutes_elapsed} دقيقة")
        if adjustments.get("note"):
            print(f"  تعلم ذاتي: {adjustments['note']}")
        print("=" * 60)

        # Step 1
        print("\n[1/7] جلب قائمة الأسهم...")
        all_symbols = self.fetch_all_market_symbols()
        if not all_symbols:
            return []

        # Step 2
        print(f"\n[2/7] تحليل شامل على 400 سهم...")
        sorted_by_vol = sorted(all_symbols, key=lambda x: x['volume'], reverse=True)
        candidates = sorted_by_vol[:300] + all_symbols[600:2000:4]

        analyzed = []
        for i, s in enumerate(candidates):
            if i % 80 == 0 and i > 0:
                print(f"  ... {i}/{len(candidates)}")
            data = self.analyze_stock(s['symbol'])
            if data:
                # تطبيع الحجم حسب الوقت
                extrapolated_vol = normalize_volume_for_session(
                    data.get('today_volume', 0), minutes_elapsed, session_code
                )
                data['extrapolated_volume'] = int(extrapolated_vol)

                # إعادة حساب Z-Score بالحجم المُسطّح
                mean_val = data.get('avg_volume_20d', 0)
                if mean_val > 0:
                    data['session_adjusted_z'] = round(
                        (extrapolated_vol - mean_val) / (mean_val * 0.3) if mean_val * 0.3 > 0 else 0, 2
                    )
                else:
                    data['session_adjusted_z'] = data.get('z_score', 0)

                analyzed.append(data)
            time.sleep(0.1)

        print(f"[+] {len(analyzed)} سهم تم تحليله")

        # Step 3
        print(f"\n[3/7] تحليل الخيارات على أفضل 100 سهم...")
        options_results = {}
        for s in sorted(analyzed, key=lambda x: x.get('z_score', 0), reverse=True)[:100]:
            opt = self.analyze_options(s['symbol'])
            if opt:
                options_results[s['symbol']] = opt
            time.sleep(0.3)

        print(f"[+] {len(options_results)} أسهم بخيارات غير عادية")

        # Step 4
        print(f"\n[4/7] بيانات بيع العَمَي...")
        short_results = {}
        interesting = [s for s in analyzed if s.get('z_score', 0) > 2 or s.get('cmf', 0) > 0.1]
        for s in interesting[:50]:
            short = self.get_short_data(s['symbol'])
            if short and short.get('short_percent') and short['short_percent'] > 0.10:
                short_results[s['symbol']] = short
            time.sleep(0.3)

        print(f"[+] {len(short_results)} أسهم بيع عَمَي مرتفع")

        # Step 5
        print(f"\n[5/7] كشف الفجوات...")
        gap_results = {}
        for s in analyzed[:200]:
            gaps = detect_gap(s['symbol'])
            if gaps:
                gap_results[s['symbol']] = gaps
            time.sleep(0.1)

        print(f"[+] {len(gap_results)} أسهم بفجوات")

        # Step 6
        print(f"\n[6/7] شراء المسؤولين الداخليين...")
        insider_results = {}
        if include_insider:
            for s in analyzed[:100]:
                insider = get_insider_buying(s['symbol'])
                if insider:
                    insider_results[s['symbol']] = insider
                time.sleep(0.2)
            print(f"[+] {len(insider_results)} أسهم بشراء داخلي")
        else:
            print("[-] تخطي شراء المسؤولين (بطيء)")

        # Step 7
        print(f"\n[7/7] عناوين الأخبار...")
        news_results = {}
        if include_news:
            for s in analyzed[:150]:
                news = get_stock_news(s['symbol'])
                if news and news.get('is_news_heavy'):
                    news_results[s['symbol']] = news
                time.sleep(0.1)
            print(f"[+] {len(news_results)} أسهم بأخبار كثيرة")

        # ─── تجميع النتائج ────────────────────────────────────
        print(f"\nتجميع النتائج + التقييم...")

        all_signals = []
        for data in analyzed:
            sym = data['symbol']
            signals_for_stock = []

            if data.get('z_score', 0) > z_threshold:
                signals_for_stock.append({
                    'type': 'VOLUME_ANOMALY',
                    'detail': f"Z-Score={data['z_score']}، حجم نسبي={data['relative_volume']}x",
                })

            if data.get('bollinger_squeeze'):
                signals_for_stock.append({
                    'type': 'BOLLINGER_SQUEEZE',
                    'detail': f"انكماش Bollinger — عرض={data.get('bollinger_width', 0)}",
                })

            if data.get('cmf', 0) > 0.15 and data.get('obv_above_sma'):
                signals_for_stock.append({
                    'type': 'ACCUMULATION',
                    'detail': f"CMF={data.get('cmf', 0)} + OBV صاعد",
                })

            if data.get('high_volume_days_5', 0) >= 3:
                signals_for_stock.append({
                    'type': 'MULTI_DAY_VOLUME',
                    'detail': f"{data['high_volume_days_5']} أيام حجم مرتفع",
                })

            if sym in options_results:
                opt = options_results[sym]
                signals_for_stock.append({
                    'type': 'UNUSUAL_OPTIONS',
                    'detail': f"{opt['count']} عقود غير عادية — {opt['bias']}",
                    'options_data': opt,
                })

            if sym in short_results:
                sd = short_results[sym]
                signals_for_stock.append({
                    'type': 'HIGH_SHORT_INTEREST',
                    'detail': f"بيع عَمَي={sd['short_percent']*100:.1f}%",
                    'short_data': sd,
                })

            if data.get('is_anomaly'):
                signals_for_stock.append({
                    'type': 'ANOMALY_DETECTED',
                    'detail': f"شذوذ AI — score={data.get('anomaly_score', 0)}",
                    'anomaly_score': data.get('anomaly_score', 0),
                })

            if sym in gap_results:
                gap = gap_results[sym][0]
                signals_for_stock.append({
                    'type': 'GAP_DETECTED',
                    'detail': f"فجوة {gap['type']} = {gap['percent']}%",
                    'gap_data': gap,
                })

            if sym in news_results:
                signals_for_stock.append({
                    'type': 'NEWS_HEAVY',
                    'detail': f"{news_results[sym]['count']} أخبار",
                    'news_data': news_results[sym],
                })

            if sym in insider_results:
                signals_for_stock.append({
                    'type': 'INSIDER_BUYING',
                    'detail': f"{insider_results[sym]['count']} عمليات شراء داخلي",
                    'insider_data': insider_results[sym],
                })

            if signals_for_stock:
                score, grade = calculate_whale_score(signals_for_stock, data)

                all_signals.append({
                    'symbol': sym,
                    'price': data.get('price', 0),
                    'change_5d': data.get('change_5d', 0),
                    'volume_data': {
                        'z_score': data.get('z_score', 0),
                        'relative_volume': data.get('relative_volume', 0),
                        'today_volume': data.get('today_volume', 0),
                        'avg_volume_20d': data.get('avg_volume_20d', 0),
                        'high_volume_days_5': data.get('high_volume_days_5', 0),
                        'extrapolated_volume': data.get('extrapolated_volume', 0),
                        'session_adjusted_z': data.get('session_adjusted_z', 0),
                    },
                    'bollinger': {
                        'width': data.get('bollinger_width', 0),
                        'squeeze': data.get('bollinger_squeeze', False),
                    },
                    'accumulation': {
                        'cmf': data.get('cmf', 0),
                        'obv_trend': data.get('obv_trend', ''),
                        'obv_above_sma': data.get('obv_above_sma', False),
                    },
                    'rsi': data.get('rsi', 50),
                    'anomaly_score': data.get('anomaly_score', 0),
                    'is_anomaly': data.get('is_anomaly', False),
                    'whale_score': score,
                    'grade': grade,
                    'signals': signals_for_stock,
                    'session': session_code,
                })

        all_signals.sort(key=lambda x: x.get('whale_score', 0), reverse=True)

        save_scan_to_db(conn, all_signals)
        memory = record_scan_result(memory, all_signals)
        save_memory(memory)
        conn.close()

        print("\n" + "=" * 60)
        print(f"  النتائج: {len(all_signals)} سهم ببيانات مثيرة")
        print("=" * 60)

        for i, sig in enumerate(all_signals[:20], 1):
            sigs = sig.get('signals', [])
            print(f"\n{i}. {sig['symbol']} — ${sig.get('price', 0):.2f}")
            print(f"   درجة: {sig.get('whale_score', 0)}/100 ({sig.get('grade', '?')})")
            print(f"   الإشارات: {len(sigs)}")
            vd = sig.get('volume_data', {})
            print(f"   Z-Score={vd.get('z_score', 0)} | حجم نسبي={vd.get('relative_volume', 0)}x")

        return all_signals


if __name__ == "__main__":
    scanner = WhaleScanner()
    signals = scanner.scan()

    session_code, session_name = get_current_session()
    output = {
        'scan_time': datetime.now().isoformat(),
        'session': session_code,
        'session_name': session_name,
        'total_signals': len(signals),
        'signals': signals,
    }
    with open('scan_results.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n[+] محفوظ في scan_results.json")
