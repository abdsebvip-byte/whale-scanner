import json
import os
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta


MEMORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scanner_memory.json")


def load_memory():
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"lessons": [], "thresholds": {}, "scan_history": []}


def save_memory(memory):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory, f, indent=2, ensure_ascii=False)


def record_scan_result(memory, signals):
    entry = {
        "time": datetime.now().isoformat(),
        "count": len(signals),
        "symbols": [s["symbol"] for s in signals],
    }
    memory["scan_history"].append(entry)
    if len(memory["scan_history"]) > 30:
        memory["scan_history"] = memory["scan_history"][-30:]
    return memory


def analyze_misses(memory, top_movers_pct=5.0):
    """
    After market close, fetch top movers.
    Compare with what we scanned earlier.
    Identify stocks that moved significantly but were NOT in our signals.
    """
    history = memory.get("scan_history", [])
    if not history:
        return [], []

    last_scan = history[-1]
    scanned_symbols = set(last_scan.get("symbols", []))

    try:
        screener = yf.Screner()
        gainers = screener.get_day_gainers()
        losers = screener.get_day_losers()
    except Exception:
        try:
            url = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?scrIds=day_gainers&count=25"
            gainers_resp = yf.utils.get_json(url)
            gainers = []
        except Exception:
            return [], []

    big_movers = []
    try:
        if gainers is not None and hasattr(gainers, 'rows'):
            for row in gainers.rows[:25]:
                if hasattr(row, 'symbol') and hasattr(row, 'regular_market_change_percent'):
                    if abs(row.regular_market_change_percent) > top_movers_pct:
                        big_movers.append({
                            "symbol": row.symbol,
                            "change_pct": row.regular_market_change_percent,
                            "price": getattr(row, 'regular_market_price', 0),
                        })
    except Exception:
        pass

    if not big_movers:
        return [], []

    missed = [m for m in big_movers if m["symbol"] not in scanned_symbols]
    hit = [m for m in big_movers if m["symbol"] in scanned_symbols]

    lessons = []
    for stock in missed:
        sym = stock["symbol"]
        try:
            data = yf.download(sym, period="1mo", progress=False)
            if data is None or len(data) < 5:
                continue
            if hasattr(data.columns, 'get_level_values'):
                data.columns = data.columns.get_level_values(0)

            vol_now = data['Volume'].iloc[-1] if 'Volume' in data.columns else 0
            vol_avg = data['Volume'].iloc[-20:].mean() if len(data) >= 20 else data['Volume'].mean()
            vol_ratio = vol_now / vol_avg if vol_avg > 0 else 0

            close = data['Close']
            rsi = 50
            if len(close) >= 15:
                delta = close.diff()
                gain = delta.clip(lower=0).rolling(14).mean()
                loss = (-delta.clip(upper=0)).rolling(14).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs))
                rsi = float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50

            lesson = {
                "symbol": sym,
                "missed_at": datetime.now().isoformat(),
                "actual_change_pct": stock["change_pct"],
                "volume_ratio": round(vol_ratio, 2),
                "rsi_at_scan": round(float(rsi), 1),
                "volume_5d_avg": round(float(vol_avg), 0),
                "price": float(stock["price"]),
                "reason_we_missed": [],
            }

            if vol_ratio > 2.5:
                lesson["reason_we_missed"].append("volume_spike_missed")
            if rsi < 30:
                lesson["reason_we_missed"].append("oversold_bounce_missed")
            if rsi > 70:
                lesson["reason_we_missed"].append("strong_momentum_continued")

            lessons.append(lesson)

        except Exception:
            continue

    memory["lessons"].extend(lessons)
    if len(memory["lessons"]) > 100:
        memory["lessons"] = memory["lessons"][-100:]

    return hit, missed


def get_threshold_adjustments(memory):
    lessons = memory.get("lessons", [])
    if len(lessons) < 5:
        return {}

    vol_misses = [l for l in lessons if "volume_spike_missed" in l.get("reason_we_missed", [])]
    rsi_misses = [l for l in lessons if "oversold_bounce_missed" in l.get("reason_we_missed", [])]

    adjustments = {}
    if len(vol_misses) > 3:
        avg_vol_ratio = sum(l["volume_ratio"] for l in vol_misses) / len(vol_misses)
        adjustments["min_volume_ratio"] = max(1.5, avg_vol_ratio * 0.8)
        adjustments["note"] = f"Lowered volume threshold — missed {len(vol_misses)} stocks with avg vol ratio {avg_vol_ratio:.1f}x"

    if len(rsi_misses) > 3:
        adjustments["rsi_oversold"] = 35
        adjustments["note_rsi"] = f"Added oversold detection — missed {len(rsi_misses)} bounces"

    return adjustments


def daily_report(memory):
    lessons = memory.get("lessons", [])
    if not lessons:
        return "لا توجد بيانات تعلم بعد."

    reason_counts = {}
    for l in lessons:
        for r in l.get("reason_we_missed", []):
            reason_counts[r] = reason_counts.get(r, 0) + 1

    report = f"**تقرير التعلم الذاتي** ({len(lessons)} أسهم فُقدت)\n\n"
    report += "أسباب الفقد:\n"
    for reason, count in sorted(reason_counts.items(), key=lambda x: -x[1]):
        report += f"- {reason}: {count} مرة\n"

    if lessons:
        avg_miss = sum(abs(l.get("actual_change_pct", 0)) for l in lessons) / len(lessons)
        report += f"\nمتوسط التغيير للأسهم المفقودة: {avg_miss:.1f}%"

    return report
