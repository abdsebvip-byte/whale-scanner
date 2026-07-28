# full_market_whale_scanner.py - v2.0
# Sessions: Pre-market (2:30-9:30 PM Saudi) | Regular (9:30 PM-4:00 AM) | After-hours (4:00-8:00 AM)
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

EDT = timezone(timedelta(hours=-4))
EST = timezone(timedelta(hours=-5))

def get_current_session():
    now_utc = datetime.now(timezone.utc)
    now_et = now_utc.astimezone(EDT)
    h, m = now_et.hour, now_et.minute
    t = h * 60 + m
    if 390 <= t < 570:
        return "premarket"
    elif 570 <= t < 960:
        return "regular"
    elif 960 <= t < 1200:
        return "afterhours"
    else:
        return "closed"

SESSION_NAMES = {
    "premarket": "جلسة ماقبل التداول (Pre-Market)",
    "regular": "الجلسة الرسمية (Regular)",
    "afterhours": "الجلسة المسائية (After-Hours)",
    "closed": "السوق مغلق",
}

SESSION_TIMES_UTC = {
    "premarket": "6:30 AM - 9:30 AM UTC",
    "regular": "9:30 AM - 4:00 PM UTC",
    "afterhours": "4:00 PM - 8:00 PM UTC",
}

def classify_session():
    now_utc = datetime.now(timezone.utc)
    t = now_utc.hour * 60 + now_utc.minute
    if 390 <= t < 570:
        return "premarket"
    elif 570 <= t < 960:
        return "regular"
    elif 960 <= t < 1200:
        return "afterhours"
    else:
        return "closed"


def calc_strategy_score(sig):
    score = 0
    reasons = []
    sig_type = sig.get('type', '')
    price = sig.get('price', 0)
    s_score = sig.get('score', 0)

    if sig_type == 'SHORT_SQUEEZE':
        sp = sig.get('short_percent', 0)
        days_cover = sig.get('short_ratio', 0)
        if sp > 0.30:
            score += 35; reasons.append(f"شورت عالي جداً ({sp*100:.0f}%)")
        elif sp > 0.20:
            score += 30; reasons.append(f"شورت عالي ({sp*100:.0f}%)")
        elif sp > 0.15:
            score += 25; reasons.append(f"شورت مرتفع ({sp*100:.0f}%)")
        elif sp > 0.10:
            score += 15; reasons.append(f"شورت متوسط ({sp*100:.0f}%)")
        if days_cover > 7:
            score += 25; reasons.append(f"أيام تغطية طويلة ({days_cover:.1f} يوم)")
        elif days_cover > 5:
            score += 20; reasons.append(f"أيام تغطية كافية ({days_cover:.1f} يوم)")
        elif days_cover > 3:
            score += 10
        if s_score >= 80:
            score += 20; reasons.append("إشارة سكвиз قوية جداً")
        elif s_score >= 60:
            score += 10

    elif sig_type == 'WHALE_ACCUMULATION':
        z = sig.get('zscore', 0)
        rvol = sig.get('rvol', 1)
        if z > 4.0:
            score += 40; reasons.append(f"تجميع حيتان عالي جداً (Z={z:.1f})")
        elif z > 3.0:
            score += 30; reasons.append(f"تجميع حيتان قوي (Z={z:.1f})")
        elif z > 2.0:
            score += 20; reasons.append(f"تجميع حيتان (Z={z:.1f})")
        if rvol > 5:
            score += 15; reasons.append(f"حجم نسبي عالي ({rvol:.1f}x)")

    elif sig_type == 'VOLUME_SPIKE':
        z = sig.get('zscore', 0)
        rvol = sig.get('rvol', 1)
        if z > 5:
            score += 35; reasons.append(f"ارتفاع حجم استثنائي (Z={z:.1f})")
        elif z > 4:
            score += 25; reasons.append(f"ارتفاع حجم كبير جداً (Z={z:.1f})")
        elif z > 3:
            score += 15; reasons.append(f"ارتفاع حجم (Z={z:.1f})")
        if rvol > 8:
            score += 20; reasons.append(f"الحجم النسبي مرتفع جداً ({rvol:.1f}x)")
        elif rvol > 5:
            score += 10

    elif sig_type == 'PRICE_SPIKE':
        if s_score >= 50:
            score += 50; reasons.append(f"اندفاع سعري ضخم ({s_score}%)")
        elif s_score >= 30:
            score += 40; reasons.append(f"اندفاع سعري كبير ({s_score}%)")
        elif s_score >= 20:
            score += 30; reasons.append(f"اندفاع سعري ({s_score}%)")
        elif s_score >= 15:
            score += 20; reasons.append(f"ارتفاع ملحوظ ({s_score}%)")
        else:
            score += 10; reasons.append("حركة سعرية")
        if price < 5:
            score += 15; reasons.append("سهم صغير جداً - حركة قوية")
        elif price < 20:
            score += 10; reasons.append("سهم صغير")
        elif price < 50:
            score += 5

    elif sig_type == 'PRICE_CRASH':
        if s_score < -30:
            score += 25; reasons.append(f"انخفاض حاد ({s_score}%) — فرصة شراء قوية")
        elif s_score < -20:
            score += 20; reasons.append(f"انخفاض كبير ({s_score}%) — فرصة شراء")
        elif s_score < -15:
            score += 15; reasons.append(f"انخفاض ({s_score}%) — مراقبة")
        else:
            score += 5; reasons.append("انخفاض طفيف — مراقبة")
        if price < 5:
            score += 5; reasons.append("سهم صغير — تذبذب عالي")

    elif sig_type == 'INSIDER_CLUSTER':
        score += 35; reasons.append("شراء مسؤولين داخلي — إشارة قوية")
        if price < 30:
            score += 10; reasons.append("مسؤولون يشترون بسعر منخفض")

    # Price range factor
    if 0.5 < price < 2:
        score += 3; reasons.append("سهم بنسات")
    elif 2 <= price < 10:
        score += 5; reasons.append("سهم صغير — فرصة كبيرة")
    elif 10 <= price < 30:
        score += 3
    elif price >= 100:
        score -= 5; reasons.append("سهم كبير — حركة أبطأ")

    score = max(0, min(score, 100))

    if score >= 75:
        action = "شراء فوري"
    elif score >= 55:
        action = "شراء بمراقبة"
    elif score >= 35:
        action = "انتظار"
    else:
        action = "لا تشتري"

    return {
        'strategy_score': score,
        'strategy_action': action,
        'strategy_reasons': reasons,
    }


def calc_entry_levels(sig):
    price = sig.get('price', 0)
    if price <= 0:
        return {}
    sig_type = sig.get('type', '')
    score = sig.get('strategy_score', 0)

    if sig_type == 'SHORT_SQUEEZE':
        entry = price
        stop_loss = round(price * 0.85, 2)
        target1 = round(price * 1.20, 2)
        target2 = round(price * 1.50, 2)
        risk_reward = round((target1 - entry) / (entry - stop_loss), 1) if entry > stop_loss else 0
    elif sig_type == 'WHALE_ACCUMULATION':
        entry = price
        stop_loss = round(price * 0.90, 2)
        target1 = round(price * 1.15, 2)
        target2 = round(price * 1.35, 2)
        risk_reward = round((target1 - entry) / (entry - stop_loss), 1) if entry > stop_loss else 0
    elif sig_type == 'VOLUME_SPIKE':
        entry = round(price * 0.98, 2)
        stop_loss = round(price * 0.92, 2)
        target1 = round(price * 1.10, 2)
        target2 = round(price * 1.25, 2)
        risk_reward = round((target1 - entry) / (entry - stop_loss), 1) if entry > stop_loss else 0
    elif sig_type == 'PRICE_SPIKE':
        entry = round(price * 0.97, 2)
        stop_loss = round(price * 0.90, 2)
        target1 = round(price * 1.08, 2)
        target2 = round(price * 1.15, 2)
        risk_reward = round((target1 - entry) / (entry - stop_loss), 1) if entry > stop_loss else 0
    elif sig_type == 'PRICE_CRASH':
        entry = round(price * 0.95, 2)
        stop_loss = round(price * 0.88, 2)
        target1 = round(price * 1.10, 2)
        target2 = round(price * 1.20, 2)
        risk_reward = round((target1 - entry) / (entry - stop_loss), 1) if entry > stop_loss else 0
    elif sig_type == 'INSIDER_CLUSTER':
        entry = price
        stop_loss = round(price * 0.88, 2)
        target1 = round(price * 1.20, 2)
        target2 = round(price * 1.40, 2)
        risk_reward = round((target1 - entry) / (entry - stop_loss), 1) if entry > stop_loss else 0
    else:
        entry = price
        stop_loss = round(price * 0.90, 2)
        target1 = round(price * 1.10, 2)
        target2 = round(price * 1.20, 2)
        risk_reward = round((target1 - entry) / (entry - stop_loss), 1) if entry > stop_loss else 0

    return {
        'entry_price': entry,
        'stop_loss': stop_loss,
        'target1': target1,
        'target2': target2,
        'risk_reward': risk_reward,
    }


class FullMarketWhaleScanner:
    def __init__(self):
        self.all_symbols = []
        try:
            import edgar
            edgar.set_identity('WhaleScanner admin@example.com')
        except Exception:
            pass

    @staticmethod
    def _flatten_df(df):
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df

    def fetch_all_market_symbols(self):
        url = "https://scanner.tradingview.com/america/scan"
        payload = {
            "filter": [
                {"left": "close", "operation": "greater", "right": 0.1},
                {"left": "volume", "operation": "greater", "right": 10000}
            ],
            "markets": ["america"],
            "symbols": {"query": {"types": ["stock"]}, "tickers": []},
            "columns": ["name", "close", "volume", "change", "float_shares_outstanding"],
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
                    if sym and len(d) >= 4:
                        price = float(d[1] or 0)
                        volume = float(d[2] or 0)
                        change = float(d[3] or 0)
                        float_shares = float(d[4] or 0) if len(d) > 4 and d[4] else 0

                        if price > 0.1 and volume > 10000:
                            if '/' in sym or '.U' in sym or '.W' in sym or '.R' in sym:
                                continue
                            symbols.append({
                                'symbol': sym,
                                'price': price,
                                'volume': volume,
                                'change': change,
                                'float': float_shares,
                                'rvol': 1.0,
                            })
                self.all_symbols = symbols
                print(f"[+] TradingView: {len(symbols)} active US stocks loaded")
                return symbols
            else:
                print(f"[-] TradingView error: {response.status_code}")
                return []
        except Exception as e:
            print(f"[-] TradingView connection error: {e}")
            return []

    def scan_insider_buying_batch(self, symbols_batch):
        results = []
        for sym in symbols_batch:
            try:
                from edgar import Company
                company = Company(sym)
                filings = company.get_filings(form="4")
                if not filings:
                    continue
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
                                'insider': insider, 'title': title,
                                'shares': shares, 'price': price,
                                'value': value, 'date': date,
                            })
                    except Exception:
                        continue
                if len(purchases) >= 2:
                    unique = set(p['insider'] for p in purchases)
                    total = sum(p['value'] for p in purchases)
                    results.append({
                        'symbol': sym,
                        'type': 'INSIDER_CLUSTER',
                        'score': 40,
                        'detail': f"{len(purchases)} مشتريات من {len(unique)} مسؤولين (${total:,.0f})",
                        'purchases': purchases,
                    })
            except Exception:
                continue
        return results

    def scan_volume_anomaly_detail(self, symbols):
        results = []
        for sym in symbols:
            try:
                df = yf.download(sym, period="1mo", progress=False)
                if df is None or len(df) < 20:
                    continue
                df = self._flatten_df(df)
                vol = df['Volume'].astype(float)
                close = df['Close'].astype(float)

                vol_mean = vol.rolling(20).mean()
                vol_std = vol.rolling(20).std()

                std_val = float(vol_std.iloc[-1]) if not pd.isna(vol_std.iloc[-1]) else 0
                mean_val = float(vol_mean.iloc[-1]) if not pd.isna(vol_mean.iloc[-1]) else 0
                latest_vol = float(vol.iloc[-1])

                if std_val == 0 or mean_val == 0:
                    continue

                z = (latest_vol - mean_val) / std_val
                rvol = latest_vol / mean_val

                close_valid = close.dropna()
                if len(close_valid) < 6:
                    continue
                price_now = float(close_valid.iloc[-1])
                price_5d = float(close_valid.iloc[-5])
                if price_5d == 0:
                    continue
                change_5d = ((price_now - price_5d) / price_5d) * 100

                if z > 2.0 and change_5d < -3.0:
                    results.append({
                        'symbol': sym, 'type': 'WHALE_ACCUMULATION', 'score': 35,
                        'detail': f"Z={z:.1f} + السعر ينخفض ({change_5d:+.1f}%)",
                        'price': price_now, 'zscore': z, 'rvol': rvol,
                    })
                elif z > 2.5:
                    results.append({
                        'symbol': sym, 'type': 'VOLUME_SPIKE', 'score': 20,
                        'detail': f"ارتفاع حجم (Z={z:.1f}، الحجم النسبي={rvol:.1f}x)",
                        'price': price_now, 'zscore': z, 'rvol': rvol,
                    })
            except Exception:
                continue
        return results

    def full_market_scan(self, include_insider=False):
        session = classify_session()
        session_name = SESSION_NAMES.get(session, "غير معروف")

        print("=" * 60)
        print(f"  ماسح الحيتان - فحص السوق الأمريكي")
        print(f"  الجلسة الحالية: {session_name}")
        print("=" * 60)

        print("\n[1/5] جاري جلب قائمة الأسهم من TradingView...")
        all_symbols = self.fetch_all_market_symbols()
        if not all_symbols:
            return []
        print(f"[+] {len(symbols)} سهم تم تحميله")

        all_signals = []

        print("\n[2/5] فحص ارتفاع السعر...")
        for s in all_symbols:
            sym = s['symbol']
            change = s.get('change', 0)
            price = s['price']

            if change > 15:
                if change >= 50:
                    raw_score = 50
                elif change >= 30:
                    raw_score = 40
                elif change >= 20:
                    raw_score = 30
                else:
                    raw_score = 20
                all_signals.append({
                    'symbol': sym, 'type': 'PRICE_SPIKE', 'score': raw_score,
                    'detail': f"ارتفاع {change:+.1f}% اليوم", 'price': price,
                    'session': session,
                })
            elif change < -15:
                if change <= -50:
                    raw_score = 50
                elif change <= -30:
                    raw_score = 40
                elif change <= -20:
                    raw_score = 30
                else:
                    raw_score = 20
                all_signals.append({
                    'symbol': sym, 'type': 'PRICE_CRASH', 'score': raw_score,
                    'detail': f"انخفاض {change:+.1f}% اليوم", 'price': price,
                    'session': session,
                })

        print(f"[+] {len([s for s in all_signals if s['type'] == 'PRICE_SPIKE'])} إشارات ارتفاع")
        print(f"[+] {len([s for s in all_signals if s['type'] == 'PRICE_CRASH'])} إشارات انهيار")

        print("\n[3/5] فحص الحجم المتداولة على 500 سهم...")
        sorted_by_vol = sorted(all_symbols, key=lambda x: x['volume'], reverse=True)
        vol_candidates = sorted_by_vol[:200] + all_symbols[500:2000:5]
        vol_signals = self.scan_volume_anomaly_detail([s['symbol'] for s in vol_candidates])
        for sig in vol_signals:
            sig['session'] = session
        all_signals.extend(vol_signals)
        print(f"[+] {len(vol_signals)} إشارات حجم تم تأكيدها")

        print("\n[4/5] فحص ضغط بائعي الشورت على 200 سهم صغير...")
        squeeze_candidates = [s for s in all_symbols if 0 < s['price'] <= 20][:200]
        squeeze_signals = []
        for s in squeeze_candidates:
            sym = s['symbol']
            price = s['price']
            try:
                ticker = yf.Ticker(sym)
                info = ticker.info
                short_pct = info.get('shortPercentOfFloat', 0) or 0
                short_ratio = info.get('shortRatio', 0) or 0
                float_shares = info.get('floatShares', 0) or 0

                score = 0
                if short_pct > 0.20: score += 40
                elif short_pct > 0.15: score += 30
                elif short_pct > 0.10: score += 20
                if short_ratio > 5: score += 30
                elif short_ratio > 3: score += 20
                if float_shares < 20000000: score += 20

                if score >= 50:
                    squeeze_signals.append({
                        'symbol': sym, 'type': 'SHORT_SQUEEZE', 'score': score,
                        'detail': f"شورت: {short_pct*100:.1f}% | أيام التغطية: {short_ratio:.1f} | العوامة: {float_shares/1e6:.1f}M",
                        'price': price, 'short_percent': short_pct,
                        'short_ratio': short_ratio, 'float_shares': float_shares,
                        'session': session,
                    })
            except Exception:
                continue
        all_signals.extend(squeeze_signals)
        print(f"[+] {len(squeeze_signals)} إشارات ضغط بائعي الشورت")

        if include_insider:
            flagged = set(s['symbol'] for s in all_signals)[:30]
            print(f"\n[5/5] فحص شراء المسؤولين على {len(flagged)} أسهم...")
            for sym in flagged:
                try:
                    sigs = self.scan_insider_buying_batch([sym])
                    for sig in sigs:
                        sig['session'] = session
                    all_signals.extend(sigs)
                    time.sleep(0.5)
                except Exception:
                    continue

        for sig in all_signals:
            strat = calc_strategy_score(sig)
            sig.update(strat)
            levels = calc_entry_levels(sig)
            sig.update(levels)

        all_signals.sort(key=lambda x: x.get('strategy_score', 0), reverse=True)

        print("\n" + "=" * 60)
        print(f"  النتائج: {len(all_signals)} إشارة من {len(all_symbols)} سهم")
        print("=" * 60)

        type_icons = {
            'INSIDER_CLUSTER': '👤',
            'WHALE_ACCUMULATION': '🐋',
            'VOLUME_SPIKE': '📊',
            'SHORT_SQUEEZE': '🔥',
            'PRICE_SPIKE': '🚀',
            'PRICE_CRASH': '📉',
        }

        for i, sig in enumerate(all_signals[:30], 1):
            icon = type_icons.get(sig['type'], '?')
            action = sig.get('strategy_action', '?')
            strat_score = sig.get('strategy_score', 0)
            print(f"\n{i}. {icon} {sig['symbol']} | {action} | نقاط الاستراتيجية: {strat_score}")
            print(f"   السعر: ${sig.get('price', 0):.2f}")
            print(f"   {sig['detail']}")

        return all_signals


if __name__ == "__main__":
    scanner = FullMarketWhaleScanner()
    signals = scanner.full_market_scan(include_insider=False)

    session = classify_session()
    output = {
        'scan_time': datetime.now().isoformat(),
        'session': session,
        'session_name': SESSION_NAMES.get(session, "غير معروف"),
        'total_signals': len(signals),
        'signals': [{k: v for k, v in sig.items() if k != 'purchases'} for sig in signals]
    }
    with open('scan_results.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n[+] النتائج محفوظة في scan_results.json")
