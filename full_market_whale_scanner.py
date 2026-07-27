# full_market_whale_scanner.py - OPTIMIZED VERSION
# Uses TradingView for bulk screening (instant), yfinance only for detailed analysis
import requests
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import sys
import io
import json

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

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
                            # Skip invalid symbols (preferred stocks, unit shares)
                            if '/' in sym or '.U' in sym or '.W' in sym or '.R' in sym:
                                continue
                            # Calculate RVOL proxy from TradingView data
                            # Use volume vs a rough average (we'll use 2x as baseline)
                            rvol_proxy = 1.0  # Will be refined in Phase 3
                            symbols.append({
                                'symbol': sym,
                                'price': price,
                                'volume': volume,
                                'change': change,
                                'float': float_shares,
                                'rvol': rvol_proxy,
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
                        'detail': f"{len(purchases)} purchases by {len(unique)} insiders (${total:,.0f})",
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
                        'detail': f"Z={z:.1f} + price dropping ({change_5d:+.1f}%)",
                        'price': price_now, 'zscore': z, 'rvol': rvol,
                    })
                elif z > 2.5:
                    results.append({
                        'symbol': sym, 'type': 'VOLUME_SPIKE', 'score': 20,
                        'detail': f"Volume spike (Z={z:.1f}, RVOL={rvol:.1f}x)",
                        'price': price_now, 'zscore': z, 'rvol': rvol,
                    })
            except Exception:
                continue
        return results

    def full_market_scan(self, include_insider=False):
        print("=" * 60)
        print(" WHALE SCANNER - Full US Market Scan (Optimized)")
        print("=" * 60)

        # Phase 1: Get all stocks + screening data from TradingView (instant)
        print("\n[Phase 1] Fetching stock list from TradingView...")
        all_symbols = self.fetch_all_market_symbols()
        if not all_symbols:
            return []
        print(f"[+] {len(all_symbols)} stocks loaded")

        all_signals = []

        # Phase 2: Screen using TradingView data
        # Select a MIX of stocks for volume analysis: top vol + random small/mid caps
        print("\n[Phase 2] Selecting candidates for deep analysis...")
        
        # Top 200 by volume (big caps with unusual activity)
        sorted_by_vol = sorted(all_symbols, key=lambda x: x['volume'], reverse=True)
        vol_candidates_big = sorted_by_vol[:200]
        
        # Random 300 from middle of list (mid/small caps more likely to spike)
        vol_candidates_small = all_symbols[500:2000:5]  # Every 5th stock = 300
        
        vol_candidates = vol_candidates_big + vol_candidates_small

        all_signals = []
        for s in all_symbols:
            sym = s['symbol']
            change = s.get('change', 0)
            price = s['price']

            # Price spike signals (from TradingView, instant)
            if change > 15:
                all_signals.append({
                    'symbol': sym, 'type': 'PRICE_SPIKE', 'score': 15,
                    'detail': f"Up {change:+.1f}% today", 'price': price,
                })
            elif change < -15:
                all_signals.append({
                    'symbol': sym, 'type': 'PRICE_CRASH', 'score': 10,
                    'detail': f"Down {change:+.1f}% today", 'price': price,
                })

        # Small caps for squeeze
        squeeze_candidates = [s for s in all_symbols if 0 < s['price'] <= 20][:300]

        print(f"[+] {len(vol_candidates)} volume candidates for deep analysis")
        print(f"[+] {len(squeeze_candidates)} small cap candidates")
        print(f"[+] {len([s for s in all_signals if s['type'] == 'PRICE_SPIKE'])} price spike signals")
        print(f"[+] {len([s for s in all_signals if s['type'] == 'PRICE_CRASH'])} price crash signals")

        # Phase 3: Deep volume analysis on candidates only (yfinance)
        print(f"\n[Phase 3] Deep volume analysis on {len(vol_candidates)} candidates...")
        vol_signals = self.scan_volume_anomaly_detail([s['symbol'] for s in vol_candidates])
        all_signals.extend(vol_signals)
        print(f"[+] Volume signals confirmed: {len(vol_signals)}")

        # Phase 4: Short squeeze analysis on candidates
        squeeze_candidates = squeeze_candidates[:200]  # Cap at 200
        print(f"\n[Phase 4] Short squeeze analysis on {len(squeeze_candidates)} small caps...")
        squeeze_signals = []
        batch_size = 20
        for i in range(0, len(squeeze_candidates), batch_size):
            batch = squeeze_candidates[i:i+batch_size]
            if (i // batch_size + 1) % 5 == 0:
                print(f"  ... scanned {i}/{len(squeeze_candidates)}")
            for s in batch:
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
                            'detail': f"Short: {short_pct*100:.1f}% | Days Cover: {short_ratio:.1f} | Float: {float_shares/1e6:.1f}M",
                            'price': price, 'short_percent': short_pct,
                        })
                except Exception:
                    continue

        all_signals.extend(squeeze_signals)
        print(f"[+] Squeeze signals: {len(squeeze_signals)}")

        # Phase 5: Insider buying (optional, on flagged stocks only)
        insider_signals = []
        if include_insider:
            flagged = set(s['symbol'] for s in all_signals)
            flagged_list = list(flagged)[:30]
            print(f"\n[Phase 5] Insider buying on {len(flagged_list)} flagged stocks...")
            for sym in flagged_list:
                try:
                    sigs = self.scan_insider_buying_batch([sym])
                    insider_signals.extend(sigs)
                    time.sleep(0.5)
                except Exception:
                    continue

        all_signals.extend(insider_signals)
        print(f"[+] Insider signals: {len(insider_signals)}")

        # Sort and display
        all_signals.sort(key=lambda x: x['score'], reverse=True)

        print("\n" + "=" * 60)
        print(f" RESULTS: {len(all_signals)} signals from {len(all_symbols)} stocks")
        print("=" * 60)

        for i, sig in enumerate(all_signals[:30], 1):
            icon = {
                'INSIDER_CLUSTER': '[INSIDER]',
                'WHALE_ACCUMULATION': '[WHALE]',
                'VOLUME_SPIKE': '[VOL+]',
                'SHORT_SQUEEZE': '[SQUEEZE]',
                'PRICE_SPIKE': '[SPIKE+]',
                'PRICE_CRASH': '[SPIKE-]',
            }.get(sig['type'], '[?]')

            print(f"\n{i}. {icon} {sig['symbol']} -- Score: {sig['score']}")
            print(f"   Price: ${sig.get('price', 0):.2f}")
            print(f"   Detail: {sig['detail']}")

        return all_signals


if __name__ == "__main__":
    scanner = FullMarketWhaleScanner()
    signals = scanner.full_market_scan(include_insider=False)

    # Save results
    output = {
        'scan_time': datetime.now().isoformat(),
        'total_signals': len(signals),
        'signals': [{k: v for k, v in sig.items() if k != 'purchases'} for sig in signals]
    }
    with open('scan_results.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n[+] Results saved to scan_results.json")
