"""
ماسح الحيتان — النسخة الصادقة v3.0
====================================
يحضر بيانات حقيقية من البورصة فقط.
لا يخترع توصيات شراء أو بيع.
يعرض ما وجدته البيانات ويترك القرار لك.

مصادر البيانات الحقيقية:
1. TradingView Scanner API → قائمة الأسهم + أسعار + أحجام (فوري)
2. yfinance → بيانات تاريخية + Z-Score + بيع عَمَي
3. SEC EDGAR → شراء المسؤولين الداخليين (اختياري)
"""
import requests
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
import time
import sys
import io
import json

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


def get_current_session():
    EDT = timezone(timedelta(hours=-4))
    now_et = datetime.now(EDT)
    t = now_et.hour * 60 + now_et.minute
    if 390 <= t < 570:
        return "premarket", "ماقبل التداول (2:30-9:30 مساءً السعودية)"
    elif 570 <= t < 960:
        return "regular", "الجلسة الرسمية (9:30 مساءً-4:00 صباحاً)"
    elif 960 <= t < 1200:
        return "afterhours", "الجلسة المسائية (4:00-8:00 صباحاً)"
    else:
        return "closed", "السوق مغلق"


class WhaleScanner:
    def __init__(self):
        self.all_symbols = []

    def fetch_all_market_symbols(self):
        url = "https://scanner.tradingview.com/america/scan"
        payload = {
            "filter": [
                {"left": "close", "operation": "greater", "right": 0.1},
                {"left": "volume", "operation": "greater", "right": 10000}
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
                        float_shares = float(d[4] or 0) if len(d) > 4 and d[4] else 0
                        high = float(d[5] or 0) if len(d) > 5 and d[5] else 0
                        low = float(d[6] or 0) if len(d) > 6 and d[6] else 0
                        open_p = float(d[7] or 0) if len(d) > 7 and d[7] else 0

                        if price > 0.1 and volume > 10000:
                            if '/' in sym or '.U' in sym or '.W' in sym or '.R' in sym:
                                continue
                            symbols.append({
                                'symbol': sym,
                                'price': price,
                                'volume': volume,
                                'change_pct': change,
                                'float': float_shares,
                                'high': high,
                                'low': low,
                                'open': open_p,
                            })
                self.all_symbols = symbols
                print(f"[+] تم جلب {len(symbols)} سهم")
                return symbols
            else:
                print(f"[-] خطأ TradingView: {response.status_code}")
                return []
        except Exception as e:
            print(f"[-] خطأ اتصال: {e}")
            return []

    def analyze_volume(self, symbol):
        """
        تحليل الحجم — حساب إحصائي حقيقي
        Z-Score = (الحجم اليوم - المتوسط) / الانحراف المعياري
        هذا حساب رياضي حقيقي وموثق
        """
        try:
            df = yf.download(symbol, period="1mo", progress=False)
            if df is None or len(df) < 20:
                return None
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            vol = df['Volume'].astype(float)
            close = df['Close'].astype(float)

            vol_mean = vol.rolling(20).mean()
            vol_std = vol.rolling(20).std()

            mean_val = float(vol_mean.iloc[-1]) if not pd.isna(vol_mean.iloc[-1]) else 0
            std_val = float(vol_std.iloc[-1]) if not pd.isna(vol_std.iloc[-1]) else 0
            latest_vol = float(vol.iloc[-1])

            if std_val == 0 or mean_val == 0:
                return None

            z_score = (latest_vol - mean_val) / std_val
            relative_volume = latest_vol / mean_val

            close_valid = close.dropna()
            change_5d = 0
            change_1d = 0
            if len(close_valid) >= 6:
                price_now = float(close_valid.iloc[-1])
                price_5d = float(close_valid.iloc[-5])
                price_1d = float(close_valid.iloc[-2]) if len(close_valid) >= 2 else price_now
                change_5d = ((price_now - price_5d) / price_5d) * 100 if price_5d != 0 else 0
                change_1d = ((price_now - price_1d) / price_1d) * 100 if price_1d != 0 else 0
            else:
                price_now = float(close_valid.iloc[-1]) if len(close_valid) > 0 else 0

            return {
                'z_score': round(z_score, 2),
                'relative_volume': round(relative_volume, 2),
                'avg_volume_20d': int(mean_val),
                'today_volume': int(latest_vol),
                'change_5d': round(change_5d, 2),
                'change_1d': round(change_1d, 2),
                'price_from_52w_high': 0,
                'price_from_52w_low': 0,
            }
        except Exception:
            return None

    def get_short_data(self, symbol):
        """بيانات بيع عَمَي — من yfinance (بيانات حقيقية من البورصة)"""
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            short_pct = info.get('shortPercentOfFloat', None)
            short_ratio = info.get('shortRatio', None)
            float_shares = info.get('floatShares', None)
            return {
                'short_percent': short_pct,
                'days_to_cover': short_ratio,
                'float_shares': float_shares,
            }
        except Exception:
            return None

    def get_insider_buying(self, symbol):
        """شراء المسؤولين — من SEC filings (بيانات حكومية حقيقية)"""
        try:
            from edgar import Company
            company = Company(symbol)
            filings = company.get_filings(form="4")
            if not filings:
                return None

            purchases = []
            for filing in filings.latest(10):
                try:
                    obj = filing.obj()
                    df = obj.to_dataframe()
                    if df is None or len(df) == 0:
                        continue
                    for _, row in df.iterrows():
                        code = str(row.get('Code', ''))
                        if code != 'P':
                            continue
                        shares = float(row.get('Shares', 0) or 0)
                        price = float(row.get('Price', 0) or 0)
                        insider = str(row.get('Insider', ''))
                        title = str(row.get('Position', ''))
                        date = str(row.get('Date', ''))
                        value = shares * price
                        if value < 25000:
                            continue
                        purchases.append({
                            'insider': insider,
                            'title': title,
                            'shares': shares,
                            'price': price,
                            'value': value,
                            'date': date,
                        })
                except Exception:
                    continue

            if len(purchases) >= 2:
                unique = set(p['insider'] for p in purchases)
                total = sum(p['value'] for p in purchases)
                return {
                    'count': len(purchases),
                    'unique_insiders': len(unique),
                    'total_value': total,
                    'purchases': purchases,
                }
            return None
        except Exception:
            return None

    def scan(self, include_insider=False):
        session_code, session_name = get_current_session()

        print("=" * 60)
        print("  ماسح الحيتان — النسخة الصادقة")
        print(f"  الجلسة: {session_name}")
        print("=" * 60)

        # Step 1: Get all stocks
        print("\n[1/3] جلب قائمة الأسهم...")
        all_symbols = self.fetch_all_market_symbols()
        if not all_symbols:
            return []

        # Step 2: Volume analysis on top 500 candidates
        print(f"\n[2/3] تحليل حجم التداول على 500 سهم...")
        sorted_by_vol = sorted(all_symbols, key=lambda x: x['volume'], reverse=True)
        candidates = sorted_by_vol[:200] + all_symbols[500:2000:5]

        volume_results = []
        for i, s in enumerate(candidates):
            sym = s['symbol']
            if i % 100 == 0 and i > 0:
                print(f"  ... {i}/{len(candidates)}")
            vol = self.analyze_volume(sym)
            if vol and vol['z_score'] > 2.0:
                volume_results.append({
                    'symbol': sym,
                    'price': s['price'],
                    'change_today': s['change_pct'],
                    'volume_data': vol,
                })

        print(f"[+] {len(volume_results)} أسهم بحجم غير عادي")

        # Step 3: Short selling on volume anomalies
        print(f"\n[3/3] فحص بيع العَمَي...")
        short_results = []
        for sig in volume_results:
            short = self.get_short_data(sig['symbol'])
            if short and short.get('short_percent') and short['short_percent'] > 0.15:
                sig['short_data'] = short
                short_results.append(sig)
            time.sleep(0.3)

        print(f"[+] {len(short_results)} أسهم بيع عَمَي مرتفع (>15%)")

        # Insider buying (optional)
        insider_results = []
        if include_insider:
            flagged = list(set(s['symbol'] for s in volume_results))[:20]
            print(f"\n  فحص شراء المسؤولين على {len(flagged)} أسهم...")
            for sym in flagged:
                insider = self.get_insider_buying(sym)
                if insider:
                    insider_results.append({
                        'symbol': sym,
                        'insider_data': insider,
                    })
                time.sleep(0.5)

        # Combine and deduplicate
        all_results = volume_results + short_results + insider_results
        seen = {}
        for r in all_results:
            sym = r['symbol']
            if sym not in seen or len(r) > len(seen[sym]):
                seen[sym] = r
        all_results = list(seen.values())

        # Print results
        print("\n" + "=" * 60)
        print(f"  النتائج: {len(all_results)} سهم ببيانات مثيرة")
        print("=" * 60)

        for i, r in enumerate(all_results[:30], 1):
            vd = r.get('volume_data', {})
            sd = r.get('short_data', {})
            print(f"\n{i}. {r['symbol']} — ${r.get('price', 0):.2f}")
            print(f"   Z-Score: {vd.get('z_score', 0)} | حجم نسبي: {vd.get('relative_volume', 0)}x")
            print(f"   تغيّر 5 أيام: {vd.get('change_5d', 0):+.1f}%")
            if sd.get('short_percent'):
                print(f"   بيع عَمَي: {sd['short_percent']*100:.1f}%")

        return all_results


if __name__ == "__main__":
    scanner = WhaleScanner()
    signals = scanner.scan(include_insider=False)

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
