import requests
import json
import yfinance as yf
import pandas as pd
import ta
import time

MAX_CHANGE = 8.0
MIN_VOL = 200000

# Step 1: Get stocks from TradingView
url = 'https://scanner.tradingview.com/america/scan'
payload = {
    'filter': [
        {'left': 'close', 'operation': 'greater', 'right': 1.0},
        {'left': 'volume', 'operation': 'greater', 'right': MIN_VOL}
    ],
    'markets': ['america'],
    'symbols': {'query': {'types': ['stock']}, 'tickers': []},
    'columns': ['name', 'close', 'volume', 'change', 'float_shares_outstanding', 'high', 'low', 'open', 'average_volume_10d_calc'],
    'sort': {'sortBy': 'volume', 'sortOrder': 'desc'},
    'range': [0, 50]
}
headers = {'User-Agent': 'Mozilla/5.0', 'Content-Type': 'application/json'}
resp = requests.post(url, json=payload, headers=headers, timeout=15)
data = resp.json()

all_stocks = []
for item in data.get('data', []):
    sym = item.get('s', '').split(':')[-1]
    d = item.get('d', [])
    if sym and len(d) >= 9:
        all_stocks.append({'symbol': sym, 'price': float(d[1] or 0), 'volume': float(d[2] or 0), 'change': float(d[3] or 0)})

print("=" * 70)
print("  PHASE 1: Stock List from TradingView")
print("=" * 70)
print(f"  Total: {len(all_stocks)} stocks")

# Step 2: Filter out already-moved
skipped = []
candidates = []
for s in all_stocks:
    if abs(s['change']) > MAX_CHANGE:
        skipped.append(s)
    else:
        candidates.append(s)

print(f"  SKIPPED (moved > {MAX_CHANGE}%): {len(skipped)} stocks")
for s in skipped[:8]:
    print(f"    X {s['symbol']}: ${s['price']:.2f} change={s['change']:+.1f}% -- ALREADY MOVED")
print(f"  CANDIDATES (change < {MAX_CHANGE}%): {len(candidates)} stocks")
print()

# Step 3: Deep analysis of top 15 candidates
print("=" * 70)
print("  PHASE 2: Deep Technical Analysis (top 15)")
print("=" * 70)

results = []
for i, stock in enumerate(candidates[:15]):
    sym = stock['symbol']
    print(f"\n  [{i+1}/15] Analyzing {sym}...", end=" ")
    try:
        df = yf.download(sym, period='6mo', progress=False)
        if df is None or len(df) < 30:
            print("SKIP (no data)")
            continue
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        close = df['Close'].astype(float)
        vol = df['Volume'].astype(float)
        high = df['High'].astype(float)
        low = df['Low'].astype(float)

        vol_mean = vol.rolling(20).mean().iloc[-1]
        vol_std = vol.rolling(20).std().iloc[-1]
        vol_ratio = float(vol.iloc[-1] / vol_mean) if vol_mean > 0 else 1
        vol_z = float((vol.iloc[-1] - vol_mean) / vol_std) if vol_std > 0 else 0

        chg_1d = float((close.iloc[-1] - close.iloc[-2]) / close.iloc[-2] * 100)
        chg_5d = float((close.iloc[-1] - close.iloc[-5]) / close.iloc[-5] * 100) if len(close) >= 5 else 0

        bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
        bb_width = (bb.bollinger_hband() - bb.bollinger_lband()) / close
        bb_now = float(bb_width.iloc[-1])
        bb_avg = float(bb_width.rolling(20).mean().iloc[-1])
        squeeze = bb_now < bb_avg * 0.7

        rsi_val = float(ta.momentum.RSIIndicator(close, window=14).rsi().iloc[-1])

        ad = ta.volume.AccDistIndexIndicator(high=high, low=low, close=close, volume=vol)
        ad_line = ad.acc_dist_index()
        cmf_list = []
        for j in range(20, len(df)):
            pad = ad_line.iloc[j] - ad_line.iloc[j-20]
            pvol = vol.iloc[j-20:j].sum()
            cmf_list.append(pad / pvol if pvol > 0 else 0)
        cmf = cmf_list[-1] if cmf_list else 0

        obv = ta.volume.OnBalanceVolumeIndicator(close=close, volume=vol)
        obv_line = obv.on_balance_volume()
        obv_sma = obv_line.rolling(20).mean()
        obv_up = float(obv_line.iloc[-1]) > float(obv_sma.iloc[-1])

        # SCORE: only based on PRE-explosion signals
        score = 0
        if chg_1d > MAX_CHANGE:
            print(f"SKIP (change {chg_1d:+.1f}%)")
            continue

        if cmf > 0.15: score += 22
        elif cmf > 0.08: score += 15
        if squeeze: score += 25
        if vol_ratio > 2 and abs(chg_1d) < 2: score += 20
        elif vol_ratio > 1.5 and abs(chg_1d) < 2: score += 10
        if obv_up and abs(chg_1d) < 2: score += 12
        if 40 <= rsi_val <= 65: score += 10
        elif rsi_val > 75: score -= 10

        score = max(0, min(score, 99))

        signals = []
        if squeeze: signals.append("SQUEEZE")
        if obv_up: signals.append("OBV_UP")
        if cmf > 0.15: signals.append("ACCUM")
        if vol_ratio > 2: signals.append("VOL_SPIKE")
        if rsi_val > 75: signals.append("OVERBOUGHT")
        if rsi_val < 30: signals.append("OVERSOLD")

        results.append({
            'symbol': sym, 'price': float(close.iloc[-1]),
            'score': score, 'change_1d': chg_1d, 'change_5d': chg_5d,
            'vol_ratio': vol_ratio, 'rsi': rsi_val, 'cmf': cmf,
            'squeeze': squeeze, 'obv_up': obv_up, 'signals': signals,
        })

        print(f"score={score} chg={chg_1d:+.1f}% vol={vol_ratio:.1f}x rsi={rsi_val:.0f} cmf={cmf:.3f} squeeze={squeeze} signals={signals}")
        time.sleep(0.1)

    except Exception as e:
        print(f"ERROR: {e}")

results.sort(key=lambda x: x['score'], reverse=True)

print()
print("=" * 70)
print("  PHASE 3: Results (sorted by score)")
print("=" * 70)
print(f"  {'Symbol':<8} {'Score':>5} {'Price':>8} {'1D%':>7} {'5D%':>7} {'Vol':>6} {'RSI':>5} {'CMF':>7} {'Squeeze':>7} {'Signals'}")
print("-" * 70)
for r in results:
    print(f"  {r['symbol']:<8} {r['score']:>4}% ${r['price']:>6.2f} {r['change_1d']:>+6.1f}% {r['change_5d']:>+6.1f}% {r['vol_ratio']:>5.1f}x {r['rsi']:>4.0f} {r['cmf']:>+6.3f} {'Yes' if r['squeeze'] else 'No':>7} {', '.join(r['signals'])}")

print()
print("KEY INSIGHT: Stocks with HIGH score but LOW change_1d = accumulation BEFORE explosion")
print("Stocks with HIGH change_1d = already exploded = too late")
