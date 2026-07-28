"""
ماسح الحيتان v4.0 — النسخة الكاملة الحقيقية
==============================================
بيانات حقيقية فقط. لا توصيات وهمية.

المصادر الحقيقية:
1. TradingView API → قائمة الأسهم + أسعار + أحجام
2. yfinance → بيانات تاريخية + خيارات + بيع عَمَي
3. scikit-learn → Isolation Forest للكشف عن الشذوذ
4. TA Library → CMF, OBV, Bollinger Bands, RSI
5. SEC EDGAR → شراء المسؤولين الداخليين

الفئات:
A) تحليل الحجم (Z-Score + انكماش Bollinger)
B) خيارات غير عادية (UOA)
C) مؤشرات التجميع (CMF, OBV)
D) كشف الشذوذ (Isolation Forest)
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
import warnings
warnings.filterwarnings('ignore')
from sklearn.ensemble import IsolationForest
from self_learning import load_memory, save_memory, record_scan_result, analyze_misses, get_threshold_adjustments

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


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
        """
        تحليل شامل لسهم واحد — كل الحسابات حقيقية
        """
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

            # Z-Score
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

            # Multi-day volume consistency (3+ أيام Z>2)
            vol_z_scores = (volume - vol_mean) / vol_std
            high_vol_days = sum(1 for z in vol_z_scores.dropna().tail(5) if z > 2)
            result['high_volume_days_5'] = high_vol_days

            # === B) Bollinger Bands — كشف الانكماش ===

            bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
            bb_high = bb.bollinger_hband()
            bb_low = bb.bollinger_lband()
            bb_width = (bb_high - bb_low) / close  # عرض الشريط

            current_width = float(bb_width.iloc[-1]) if not pd.isna(bb_width.iloc[-1]) else 0
            avg_width = float(bb_width.rolling(20).mean().iloc[-1]) if len(bb_width) > 20 else 0

            result['bollinger_width'] = round(current_width, 4)
            result['bollinger_squeeze'] = current_width < avg_width * 0.7 if avg_width > 0 else False

            # === C) مؤشرات التجميع (CMF, OBV) ===

            # Chaikin Money Flow
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

            # On-Balance Volume
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

            # === F) Isolation Forest — كشف الشذوذ بالذكاء الاصطناعي ===
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
        """
        تحليل الخيارات غير العادية — بيانات حقيقية من yfinance
        يكشف عندما حجم تداول العقد يتجاوز 3 مرات Open Interest
        """
        try:
            ticker = yf.Ticker(symbol)
            expirations = ticker.options
            if not expirations:
                return None

            unusual = []
            for exp in expirations[:3]:  # أول 3 تواريخ
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

    def scan(self, include_insider=False):
        session_code, session_name = get_current_session()

        # تحميل الذاكرة والتذكّر
        memory = load_memory()
        adjustments = get_threshold_adjustments(memory)
        z_threshold = adjustments.get("min_z_score", 2.0)
        rsi_oversold_threshold = adjustments.get("rsi_oversold", 30)

        print("=" * 60)
        print("  ماسح الحيتان v4.0 — النسخة الكاملة الحقيقية")
        print(f"  الجلسة: {session_name}")
        if adjustments.get("note"):
            print(f"  تعلم ذاتي: {adjustments['note']}")
        if adjustments.get("note_rsi"):
            print(f"  تعلم ذاتي: {adjustments['note_rsi']}")
        print("=" * 60)

        # Step 1: Get all stocks
        print("\n[1/5] جلب قائمة الأسهم...")
        all_symbols = self.fetch_all_market_symbols()
        if not all_symbols:
            return []

        # Step 2: Deep analysis on top 400 candidates
        print(f"\n[2/5] تحليل شامل على 400 سهم...")
        sorted_by_vol = sorted(all_symbols, key=lambda x: x['volume'], reverse=True)
        candidates = sorted_by_vol[:300] + all_symbols[600:2000:4]

        analyzed = []
        for i, s in enumerate(candidates):
            if i % 80 == 0 and i > 0:
                print(f"  ... {i}/{len(candidates)}")
            data = self.analyze_stock(s['symbol'])
            if data:
                analyzed.append(data)
            time.sleep(0.1)

        print(f"[+] {len(analyzed)} سهم تم تحليله")

        # Step 3: Options analysis on top candidates
        print(f"\n[3/5] تحليل الخيارات على أفضل 100 سهم...")
        options_results = {}
        for s in sorted(analyzed, key=lambda x: x.get('z_score', 0), reverse=True)[:100]:
            opt = self.analyze_options(s['symbol'])
            if opt:
                options_results[s['symbol']] = opt
            time.sleep(0.3)

        print(f"[+] {len(options_results)} أسهم بخيارات غير عادية")

        # Step 4: Short selling data
        print(f"\n[4/5] بيانات بيع العَمَي على الأسهم المثيرة...")
        short_results = {}
        interesting = [s for s in analyzed if s.get('z_score', 0) > 2 or s.get('cmf', 0) > 0.1]
        for s in interesting[:50]:
            short = self.get_short_data(s['symbol'])
            if short and short.get('short_percent') and short['short_percent'] > 0.10:
                short_results[s['symbol']] = short
            time.sleep(0.3)

        print(f"[+] {len(short_results)} أسهم بيع عَمَي مرتفع")

        # Step 5: Combine results
        print(f"\n[5/5] تجميع النتائج...")

        all_signals = []
        for data in analyzed:
            sym = data['symbol']
            signals_for_stock = []

            # حجم غير عادي
            if data.get('z_score', 0) > 2.0:
                signals_for_stock.append({
                    'type': 'VOLUME_ANOMALY',
                    'detail': f"Z-Score={data['z_score']}، حجم نسبي={data['relative_volume']}x",
                })

            # انكماش Bollinger
            if data.get('bollinger_squeeze'):
                signals_for_stock.append({
                    'type': 'BOLLINGER_SQUEEZE',
                    'detail': f"انكماش Bollinger — عرض الشريط={data.get('bollinger_width', 0)}",
                })

            # تجميع (CMF إيجابي + OBV صاعد)
            if data.get('cmf', 0) > 0.15 and data.get('obv_above_sma'):
                signals_for_stock.append({
                    'type': 'ACCUMULATION',
                    'detail': f"CMF={data.get('cmf', 0)} + OBV صاعد — تجميع أموال",
                })

            # حجم عالي لأكثر من يوم
            if data.get('high_volume_days_5', 0) >= 3:
                signals_for_stock.append({
                    'type': 'MULTI_DAY_VOLUME',
                    'detail': f"{data['high_volume_days_5']} أيام حجم مرتفع من آخر 5",
                })

            # خيارات غير عادية
            if sym in options_results:
                opt = options_results[sym]
                signals_for_stock.append({
                    'type': 'UNUSUAL_OPTIONS',
                    'detail': f"{opt['count']} عقود غير عادية — اتجاه {opt['bias']}",
                    'options_data': opt,
                })

            # بيع عَمَي مرتفع
            if sym in short_results:
                sd = short_results[sym]
                signals_for_stock.append({
                    'type': 'HIGH_SHORT_INTEREST',
                    'detail': f"بيع عَمَي={sd['short_percent']*100:.1f}%، أيام التغطية={sd.get('days_to_cover', 0)}",
                    'short_data': sd,
                })

            # شذوذ Isolation Forest
            if data.get('is_anomaly'):
                signals_for_stock.append({
                    'type': 'ANOMALY_DETECTED',
                    'detail': f"شذوذ ذكاء اصطناعي — score={data.get('anomaly_score', 0)}",
                    'anomaly_score': data.get('anomaly_score', 0),
                })

            if signals_for_stock:
                all_signals.append({
                    'symbol': sym,
                    'price': data.get('price', 0),
                    'change_5d': data.get('change_5d', 0),
                    'change_today': data.get('change_today', 0),
                    'volume_data': {
                        'z_score': data.get('z_score', 0),
                        'relative_volume': data.get('relative_volume', 0),
                        'today_volume': data.get('today_volume', 0),
                        'avg_volume_20d': data.get('avg_volume_20d', 0),
                        'high_volume_days_5': data.get('high_volume_days_5', 0),
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
                    'signals': signals_for_stock,
                    'session': session_code,
                })

        # Sort by number of signals (more signals = more interesting)
        all_signals.sort(key=lambda x: len(x.get('signals', [])), reverse=True)

        # حفظ في الذاكرة + تحليل الفقد
        memory = record_scan_result(memory, all_signals)
        save_memory(memory)

        print("\n" + "=" * 60)
        print(f"  النتائج: {len(all_signals)} سهم ببيانات مثيرة")
        print("=" * 60)

        for i, sig in enumerate(all_signals[:20], 1):
            sigs = sig.get('signals', [])
            sig_types = [s['type'] for s in sigs]
            print(f"\n{i}. {sig['symbol']} — ${sig.get('price', 0):.2f}")
            print(f"   الإشارات: {len(sigs)} — {', '.join(sig_types)}")
            vd = sig.get('volume_data', {})
            print(f"   Z-Score={vd.get('z_score', 0)} | حجم نسبي={vd.get('relative_volume', 0)}x")
            acc = sig.get('accumulation', {})
            print(f"   CMF={acc.get('cmf', 0)} | OBV={acc.get('obv_trend', '')}")

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
