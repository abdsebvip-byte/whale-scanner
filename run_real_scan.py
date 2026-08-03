import requests
import json
import yfinance as yf
import pandas as pd
import ta
import time
import pytz
from datetime import datetime, timedelta

MAX_CHANGE_1D = 8.0
MIN_PRICE = 0.10
MAX_PRICE = 10.0
MIN_VOLUME = 200000

def get_stock_list():
    url = "https://scanner.tradingview.com/america/scan"
    payload = {
        "filter": [
            {"left": "close", "operation": "greater", "right": MIN_PRICE},
            {"left": "volume", "operation": "greater", "right": MIN_VOLUME}
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
            stocks = []
            for item in resp.json().get("data", []):
                sym = item.get("s", "").split(":")[-1]
                d = item.get("d", [])
                if sym and len(d) >= 9:
                    if '/' in sym or '.U' in sym or '.W' in sym:
                        continue
                    change = float(d[3] or 0)
                    price = float(d[1] or 0)
                    if price < MIN_PRICE or price > MAX_PRICE:
                        continue
                    if abs(change) > MAX_CHANGE_1D:
                        continue
                    stocks.append({
                        'symbol': sym, 'price': price, 'volume': float(d[2] or 0),
                        'change': change, 'avg_volume_10d': float(d[8] or 0),
                    })
            return stocks
    except Exception as e:
        print(f"[-] TradingView: {e}")
    return []


def _get_short_percent(symbol):
    """Best-effort short interest (fraction of float, e.g. 0.15 = 15%)."""
    try:
        return float(yf.Ticker(symbol).info.get('shortPercentOfFloat') or 0.0)
    except Exception:
        return 0.0


def analyze_stock(symbol):
    try:
        df = yf.download(symbol, period="6mo", progress=False)
        if df is None or len(df) < 30:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        close = df['Close'].astype(float)
        vol = df['Volume'].astype(float)
        high = df['High'].astype(float)
        low = df['Low'].astype(float)
        open_ = df['Open'].astype(float)

        if close.iloc[-1] < MIN_PRICE or close.iloc[-1] > MAX_PRICE:
            return None

        price_at_scan = float(close.iloc[-1])
        gap_pct = float((open_.iloc[-1] - close.iloc[-2]) / close.iloc[-2] * 100) if len(close) >= 2 else 0.0
        short_percent = _get_short_percent(symbol)

        vol_mean = vol.rolling(20).mean().iloc[-1]
        vol_std = vol.rolling(20).std().iloc[-1]
        vol_ratio = float(vol.iloc[-1] / vol_mean) if vol_mean > 0 else 1
        vol_z = float((vol.iloc[-1] - vol_mean) / vol_std) if vol_std > 0 else 0

        chg_1d = float((close.iloc[-1] - close.iloc[-2]) / close.iloc[-2] * 100)
        chg_5d = float((close.iloc[-1] - close.iloc[-5]) / close.iloc[-5] * 100) if len(close) >= 5 else 0

        if abs(chg_1d) > MAX_CHANGE_1D:
            return None

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
        cmf = float(cmf_list[-1]) if cmf_list else 0

        obv = ta.volume.OnBalanceVolumeIndicator(close=close, volume=vol)
        obv_line = obv.on_balance_volume()
        obv_sma = obv_line.rolling(20).mean()
        obv_up = float(obv_line.iloc[-1]) > float(obv_sma.iloc[-1])

        macd = ta.trend.MACD(close)
        macd_diff = float(macd.macd_diff().iloc[-1]) if not pd.isna(macd.macd_diff().iloc[-1]) else 0

        vol_build = 0
        for i in range(len(vol)-1, max(len(vol)-10, 0), -1):
            if vol.iloc[i] > vol_mean * 1.3:
                vol_build += 1
            else:
                break

        price_pos = 0.5
        range_20 = high.tail(20).max() - low.tail(20).min()
        if range_20 > 0:
            price_pos = float((close.iloc[-1] - low.tail(20).min()) / range_20)

        return {
            'symbol': symbol,
            'price': float(close.iloc[-1]),
            'volume': float(vol.iloc[-1]),
            'change_1d': chg_1d,
            'change_5d': chg_5d,
            'volume_ratio': vol_ratio,
            'z_score': vol_z,
            'rsi': rsi_val,
            'cmf': cmf,
            'bollinger_squeeze': squeeze,
            'obv_above_sma': obv_up,
            'macd_diff': macd_diff,
            'volume_build_days': vol_build,
            'price_position': price_pos,
            'price_at_scan': price_at_scan,
            'gap_pct': gap_pct,
            'short_percent': short_percent,
            'ohlcv': df,
        }
    except:
        return None


def score_stock(s):
    score = 0
    chg = abs(s.get('change_1d', 0))
    vol_r = s.get('volume_ratio', 0)
    rsi = s.get('rsi', 50)
    cmf = s.get('cmf', 0)
    squeeze = s.get('bollinger_squeeze', 0)
    obv_up = s.get('obv_above_sma', 0)
    macd = s.get('macd_diff', 0)
    vol_build = s.get('volume_build_days', 0)
    price_pos = s.get('price_position', 0.5)

    if cmf > 0.25: score += 30
    elif cmf > 0.15: score += 22
    elif cmf > 0.08: score += 15
    elif cmf > 0.03: score += 8
    elif cmf < -0.1: score -= 15

    if squeeze: score += 25

    if vol_r > 3 and chg < 2: score += 20
    elif vol_r > 2 and chg < 2: score += 14
    elif vol_r > 1.5 and chg < 1.5: score += 8

    if obv_up and chg < 2: score += 12
    elif obv_up: score += 5

    if 40 <= rsi <= 65: score += 10
    elif 30 <= rsi < 40: score += 6
    elif rsi > 75: score -= 10

    if macd > 0: score += 8
    elif macd > -0.1: score += 4

    if vol_build >= 3: score += 12
    elif vol_build >= 2: score += 7

    if price_pos < 0.3: score += 8
    elif price_pos > 0.85: score -= 5

    return max(0, min(score, 99))


def run():
    try:
        et = pytz.timezone('US/Eastern')
    except:
        et = timezone(timedelta(hours=-4))
    now = datetime.now(et)
    t = now.hour * 60 + now.minute
    if 240 <= t < 570: session, session_name = "premarket", "Pre-Market"
    elif 570 <= t < 960: session, session_name = "regular", "Regular"
    elif 960 <= t < 1200: session, session_name = "afterhours", "After-Hours"
    else: session, session_name = "closed", "Market Closed"

    print("=" * 60)
    print("  Scanner v6.0")
    print(f"  Session: {session_name}")
    print(f"  Time: {now.strftime('%Y-%m-%d %H:%M ET')}")
    print("=" * 60)

    print("\n[1/3] Getting stocks from TradingView...")
    stocks = get_stock_list()
    print(f"  {len(stocks)} stocks (already filtered: change < {MAX_CHANGE_1D}%, price ${MIN_PRICE}-${MAX_PRICE})")

    stocks.sort(key=lambda x: x['volume'], reverse=True)
    stocks = stocks[:200]

    print(f"\n[2/3] Analyzing top {len(stocks)} stocks...")
    results = []
    for i, stock in enumerate(stocks):
        if i % 50 == 0 and i > 0:
            print(f"  ... {i}/{len(stocks)}")
        features = analyze_stock(stock['symbol'])
        if features and abs(features.get('change_1d', 0)) <= MAX_CHANGE_1D:
            features['explosion_probability'] = score_stock(features)
            results.append(features)
        time.sleep(0.1)

    print(f"  {len(results)} stocks analyzed")
    results.sort(key=lambda x: x.get('explosion_probability', 0), reverse=True)

    print(f"\n[3/3] Saving predictions...")
    top = []
    for p in results[:30]:
        top.append({
            'symbol': p['symbol'],
            'price': round(p['price'], 2),
            'explosion_probability': p['explosion_probability'],
            'volume_ratio': round(p['volume_ratio'], 2),
            'z_score': round(p['z_score'], 2),
            'rsi': round(p['rsi'], 1),
            'cmf': round(p['cmf'], 4),
            'bollinger_squeeze': bool(p['bollinger_squeeze']),
            'obv_above_sma': bool(p['obv_above_sma']),
            'change_1d': round(p['change_1d'], 2),
            'change_5d': round(p['change_5d'], 2),
            'atr_ratio': 0,
            'macd_diff': round(p['macd_diff'], 4),
        })

    output = {
        'scan_time': now.isoformat(),
        'session': session,
        'session_name': session_name,
        'total_analyzed': len(results),
        'predictions': top,
        'model_trained': False,
    }

    with open('predictions.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False, default=str)

    print(f"\n{'='*60}")
    print(f"  TOP 15 PREDICTIONS:")
    print(f"{'='*60}")
    print(f"  {'#':>2} {'Sym':<8} {'Prob':>5} {'Price':>8} {'1D%':>7} {'Vol':>6} {'RSI':>5} {'CMF':>7} {'Signals'}")
    print(f"  {'-'*65}")
    for i, p in enumerate(top[:15], 1):
        sigs = []
        if p['bollinger_squeeze']: sigs.append("SQ")
        if p['obv_above_sma']: sigs.append("OBV")
        if p['cmf'] > 0.15: sigs.append("ACC")
        if p['volume_ratio'] > 2: sigs.append("VOL")
        print(f"  {i:>2} {p['symbol']:<8} {p['explosion_probability']:>4}% ${p['price']:>6.2f} {p['change_1d']:>+6.1f}% {p['volume_ratio']:>5.1f}x {p['rsi']:>4.0f} {p['cmf']:>+6.3f} {', '.join(sigs)}")

    print(f"\n  Saved {len(top)} predictions to predictions.json")
    return top


if __name__ == "__main__":
    run()
