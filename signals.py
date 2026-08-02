"""
signals.py — محرك الإشارات الذكي
====================================
يُحول explosion_score + دقة المؤشرات إلى إشارات قابلة للتنفيذ:
STRONG_BUY ≥ 70 | BUY ≥ 55 | WATCH ≥ 40 | IGNORE < 40
"""
import sqlite3
import json
from datetime import datetime

DB_PATH = "scanner_history.db"

SIGNAL_LEVELS = [
    ("STRONG_BUY", 70, "🔴 شراء قوي"),
    ("BUY", 55, "🟠 شراء"),
    ("WATCH", 40, "🟡 مراقبة"),
    ("IGNORE", 0, "⚪ تجاهل"),
]

INDICATOR_KEYS = {
    "cmf": "cmf >= 0.15",
    "bollinger_squeeze": "bollinger_squeeze = 1",
    "obv_above": "obv_above = 1",
    "volume_ratio": "volume_ratio >= 2.0",
    "z_score": "z_score >= 1.5",
    "rsi_40_65": "rsi BETWEEN 40 AND 65",
}


def init_signals_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        signal_time TEXT,
        symbol TEXT,
        price REAL,
        explosion_score INTEGER,
        signal_level TEXT,
        signal_label TEXT,
        adjusted_score INTEGER,
        volume_ratio REAL,
        z_score REAL,
        rsi REAL,
        cmf REAL,
        bollinger_squeeze INTEGER,
        obv_above INTEGER,
        day_change_pct REAL,
        ml_prob REAL,
        indicator_count INTEGER,
        active_indicators TEXT,
        source_scan_id INTEGER
    )''')
    c.execute("PRAGMA table_info(signals)")
    existing_columns = {row[1] for row in c.fetchall()}
    if "ml_prob" not in existing_columns:
        c.execute("ALTER TABLE signals ADD COLUMN ml_prob REAL")
    conn.commit()
    return conn


def get_indicator_lifts():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    lifts = {}
    for key, condition in INDICATOR_KEYS.items():
        try:
            c.execute(f"SELECT COUNT(*) FROM outcome_tracking WHERE {condition}")
            total = c.fetchone()[0]
            c.execute(f"SELECT COUNT(*) FROM outcome_tracking WHERE {condition} AND exploded = 1")
            hits = c.fetchone()[0]
            c.execute(f"SELECT COUNT(*) FROM outcome_tracking WHERE NOT ({condition}) AND exploded = 1")
            hits_without = c.fetchone()[0]
            c.execute(f"SELECT COUNT(*) FROM outcome_tracking WHERE NOT ({condition})")
            total_without = c.fetchone()[0]
            acc = round(hits / total * 100, 1) if total > 0 else 0
            baseline = round(hits_without / total_without * 100, 1) if total_without > 0 else 0
            lifts[key] = {
                "accuracy": acc,
                "baseline": baseline,
                "lift": round(acc - baseline, 1),
                "total": total,
                "hits": hits,
            }
        except:
            lifts[key] = {"accuracy": 0, "baseline": 0, "lift": 0, "total": 0, "hits": 0}
    conn.close()
    return lifts


def classify_signal(score, lifts):
    bonus = 0
    active_count = 0
    active_list = []

    for key, data in lifts.items():
        if data["lift"] > 8:
            bonus += 4
        elif data["lift"] > 4:
            bonus += 2
        elif data["lift"] < -2:
            bonus -= 3
        if data["total"] > 0 and data["accuracy"] > data["baseline"]:
            active_count += 1
            active_list.append(key)

    adjusted = max(0, min(99, score + bonus))

    for level, threshold, label in SIGNAL_LEVELS:
        if adjusted >= threshold:
            return level, label, adjusted, active_count, active_list

    return "IGNORE", "⚪ تجاهل", adjusted, active_count, active_list


def classify_ml_probability(prob):
    score = max(0, min(99, int(round(float(prob) * 100))))

    try:
        from ml_engine import classify_signal as classify_ml_signal
        band = classify_ml_signal(float(prob), dynamic_threshold=False)
    except Exception:
        band = "strong" if prob >= 0.7 else "medium" if prob >= 0.5 else "weak"

    if band == "strong":
        return "STRONG_BUY", "🔴 شراء قوي", score, 0, []
    if band == "medium":
        return "BUY", "🟠 شراء", score, 0, []
    if score >= 40:
        return "WATCH", "🟡 مراقبة", score, 0, []
    return "IGNORE", "⚪ تجاهل", score, 0, []


def generate_signals_from_predictions(predictions, source_scan_id=None):
    if not predictions:
        return []
    lifts = get_indicator_lifts()
    conn = init_signals_db()
    c = conn.cursor()
    now = datetime.now().isoformat()
    saved = 0

    for pred in predictions:
        score = pred.get("explosion_probability", 0)
        ml_prob = pred.get("ml_prob")
        if ml_prob is not None:
            level, label, adjusted, active_cnt, active_list = classify_ml_probability(ml_prob)
        else:
            level, label, adjusted, active_cnt, active_list = classify_signal(score, lifts)

        if level == "IGNORE":
            continue

        try:
            c.execute('''INSERT INTO signals
                (signal_time, symbol, price, explosion_score, signal_level, signal_label,
                 adjusted_score, volume_ratio, z_score, rsi, cmf,
                 bollinger_squeeze, obv_above, day_change_pct,
                 ml_prob, indicator_count, active_indicators, source_scan_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (now, pred.get("symbol", ""), pred.get("price", 0),
                 score, level, label, adjusted,
                 pred.get("volume_ratio", 0), pred.get("z_score", 0),
                 pred.get("rsi", 50), pred.get("cmf", 0),
                 1 if pred.get("bollinger_squeeze") else 0,
                 1 if pred.get("obv_above_sma") else 0,
                 pred.get("change_1d", 0),
                 ml_prob,
                 active_cnt, json.dumps(active_list), source_scan_id))
            conn.commit()
            saved += 1
        except:
            continue

    conn.close()
    return saved


def get_active_signals(limit=30, min_level="WATCH"):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    min_threshold = next((t for l, t, _ in SIGNAL_LEVELS if l == min_level), 0)
    levels = [l[0] for l in SIGNAL_LEVELS if l[1] >= min_threshold]
    placeholders = ",".join(f"'{l}'" for l in levels if l != "IGNORE")
    try:
        c.execute(f'''SELECT signal_time, symbol, price, explosion_score, signal_level,
             signal_label, adjusted_score, volume_ratio, z_score, rsi,
             cmf, bollinger_squeeze, obv_above, day_change_pct, ml_prob,
             indicator_count, active_indicators
             FROM signals WHERE signal_level IN ({placeholders})
             ORDER BY adjusted_score DESC, signal_time DESC LIMIT ?''', (limit,))
        rows = c.fetchall()
    except:
        rows = []
    conn.close()

    signals = []
    for r in rows:
        signals.append({
            "time": r[0], "symbol": r[1], "price": r[2],
            "explosion_score": r[3], "signal_level": r[4],
            "signal_label": r[5], "adjusted_score": r[6],
            "volume_ratio": r[7], "z_score": r[8],
            "rsi": r[9], "cmf": r[10],
            "bollinger_squeeze": bool(r[11]), "obv_above": bool(r[12]),
            "day_change_pct": r[13], "ml_prob": r[14], "indicator_count": r[15],
            "active_indicators": json.loads(r[16]) if r[16] else [],
        })
    return signals


def get_signal_summary():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("SELECT COUNT(*) FROM signals")
        total = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM signals WHERE signal_level = 'STRONG_BUY'")
        strong = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM signals WHERE signal_level = 'BUY'")
        buys = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM signals WHERE signal_level = 'WATCH'")
        watches = c.fetchone()[0]
        c.execute("SELECT COUNT(DISTINCT symbol) FROM signals")
        unique = c.fetchone()[0]
        c.execute('''SELECT signal_time FROM signals ORDER BY signal_time DESC LIMIT 1''')
        last = c.fetchone()
    except:
        total = strong = buys = watches = unique = 0
        last = None
    conn.close()
    return {
        "total_signals": total,
        "strong_buys": strong,
        "buys": buys,
        "watches": watches,
        "unique_symbols": unique,
        "last_signal_time": last[0] if last else None,
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "summary":
        s = get_signal_summary()
        print(f"\nإجمالي الإشارات: {s['total_signals']}")
        print(f"  STRONG_BUY: {s['strong_buys']}")
        print(f"  BUY:        {s['buys']}")
        print(f"  WATCH:      {s['watches']}")
        print(f"  رموز فريدة: {s['unique_symbols']}")
    elif len(sys.argv) > 1 and sys.argv[1] == "active":
        signals = get_active_signals(limit=10)
        print(f"\nآخر {len(signals)} إشارة:")
        for s in signals:
            print(f"  {s['signal_label']:16s} {s['symbol']:6s} ${s['price']:<8.2f} adjusted={s['adjusted_score']}")
    else:
        lifts = get_indicator_lifts()
        print("\nأوزان المؤشرات الحالية (من النتائج الفعلية):")
        print(f"  {'المؤشر':<20} {'دقة':<8} {'أساس':<8} {'Lift':<8}")
        print("-" * 50)
        for k, v in sorted(lifts.items(), key=lambda x: -x[1]["lift"]):
            print(f"  {k:<20} {v['accuracy']:<8.1f} {v['baseline']:<8.1f} {v['lift']:<+8.1f}")
