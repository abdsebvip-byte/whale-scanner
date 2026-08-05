"""
outcome_tracker.py — تتبع نتائج تنبؤات الماسح
================================================
المهمة: مقارنة التنبؤات بالواقع الفعلي.
كل سهم تنبأنا به يتابع سعره بعد (1 يوم، 3 أيام، 5 أيام عمل).
نعرف بالضبط هل انفجر ولا لأ.
"""
import yfinance as yf
import pandas as pd
import numpy as np
import sqlite3
import json
import time
from datetime import datetime, timedelta

DB_PATH = "scanner_history.db"


def init_tracking_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS outcome_tracking (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        prediction_id INTEGER,
        symbol TEXT,
        scan_time TEXT,
        session_type TEXT,
        price_at_scan REAL,
        volume_ratio REAL,
        z_score REAL,
        rsi REAL,
        cmf REAL,
        bollinger_squeeze INTEGER,
        obv_above INTEGER,
        change_pct_at_scan REAL,
        explosion_score INTEGER,
        price_1d REAL,
        price_3d REAL,
        price_5d REAL,
        change_1d REAL,
        change_3d REAL,
        change_5d REAL,
        max_change_5d REAL,
        min_change_5d REAL,
        exploded INTEGER DEFAULT 0,
        touched_stop INTEGER DEFAULT 0,
        last_checked TEXT,
        FOREIGN KEY (prediction_id) REFERENCES session_data(id)
    )''')
    conn.commit()
    return conn


def fetch_current_price(symbol):
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="5d")
        if hist is None or len(hist) == 0:
            return None, None
        if isinstance(hist.columns, pd.MultiIndex):
            hist.columns = hist.columns.get_level_values(0)
        return float(hist['Close'].iloc[-1]), hist['Close'].values
    except:
        return None, None


def fetch_price_at_date(symbol, target_date):
    try:
        start = (target_date - timedelta(days=5)).strftime('%Y-%m-%d')
        end = (target_date + timedelta(days=1)).strftime('%Y-%m-%d')
        ticker = yf.Ticker(symbol)
        hist = ticker.history(start=start, end=end, period="1wk")
        if hist is None or len(hist) == 0:
            return None
        if isinstance(hist.columns, pd.MultiIndex):
            hist.columns = hist.columns.get_level_values(0)
        return float(hist['Close'].iloc[-1])
    except:
        return None


def backfill_outcomes():
    """تتبع نتائج جميع التنبؤات القديمة — يقارن السعر الحالي بسعر التنبؤ"""
    conn = init_tracking_db()
    c = conn.cursor()

    c.execute('''SELECT s.id, s.scan_time, s.session_type, s.symbol,
        s.price, s.volume_ratio, s.z_score, s.rsi, s.cmf,
        s.bollinger_squeeze, s.obv_above, s.change_pct, s.explosion_score
        FROM session_data s
        LEFT JOIN outcome_tracking o ON s.id = o.prediction_id
        WHERE o.id IS NULL''')
    rows = c.fetchall()
    print(f"[+] وجدنا {len(rows)} تنبؤاً قديماً")

    tracked = 0
    for row in rows:
        pred_id, scan_time, session_type, symbol, price_at_scan = row[0], row[1], row[2], row[3], row[4]
        vol_ratio, z_score, rsi, cmf = row[5], row[6], row[7], row[8]
        squeeze, obv, change_pct = row[9], row[10], row[11]
        explosion_score = int(row[12]) if len(row) > 12 and row[12] else 0

        try:
            scan_dt = datetime.fromisoformat(scan_time)
            if scan_dt.tzinfo is not None:
                scan_dt = scan_dt.replace(tzinfo=None)
        except:
            scan_dt = datetime.now()

        current_prices = fetch_current_price(symbol)
        if current_prices[0] is None:
            continue

        current_price, price_array = current_prices
        days_passed = (datetime.now() - scan_dt).days

        change_1d = None
        change_3d = None
        change_5d = None
        price_1d_val = None
        price_3d_val = None
        price_5d_val = None
        max_chg = None
        min_chg = None

        if price_at_scan and price_at_scan > 0:
            if len(price_array) >= 1:
                price_1d_val = float(price_array[min(0, len(price_array)-1)])
                change_1d = round((price_1d_val - price_at_scan) / price_at_scan * 100, 2)
            if len(price_array) >= 3:
                price_3d_val = float(price_array[min(2, len(price_array)-1)])
                change_3d = round((price_3d_val - price_at_scan) / price_at_scan * 100, 2)
            if len(price_array) >= 5:
                price_5d_val = float(price_array[min(4, len(price_array)-1)])
                change_5d = round((price_5d_val - price_at_scan) / price_at_scan * 100, 2)

            changes = [(p - price_at_scan) / price_at_scan * 100 for p in price_array]
            max_chg = round(max(changes), 2) if changes else None
            min_chg = round(min(changes), 2) if changes else None

        best_change = change_5d if change_5d is not None else (change_3d if change_3d is not None else change_1d)
        exploded = 1 if best_change is not None and best_change >= 5.0 else 0
        touched_stop = 1 if min_chg is not None and min_chg <= -5.0 else 0

        try:
            c.execute('''INSERT INTO outcome_tracking
                (prediction_id, symbol, scan_time, session_type,
                 price_at_scan, volume_ratio, z_score, rsi, cmf,
                 bollinger_squeeze, obv_above, change_pct_at_scan, explosion_score,
                 price_1d, price_3d, price_5d,
                 change_1d, change_3d, change_5d,
                 max_change_5d, min_change_5d, exploded, touched_stop, last_checked)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (pred_id, symbol, scan_time, session_type,
                 round(price_at_scan, 2) if price_at_scan else 0,
                 round(vol_ratio, 2) if vol_ratio else 0,
                 round(z_score, 2) if z_score else 0,
                 round(rsi, 1) if rsi else 50,
                 round(cmf, 4) if cmf else 0,
                 squeeze or 0, obv or 0, round(change_pct, 2) if change_pct else 0,
                 explosion_score,
                 price_1d_val, price_3d_val, price_5d_val,
                 change_1d, change_3d, change_5d,
                 max_chg, min_chg, exploded, touched_stop,
                 datetime.now().isoformat()))
            conn.commit()
            tracked += 1
        except Exception as e:
            print(f"  [!] خطأ في تخزين {symbol}: {e}")
            continue

        if tracked % 50 == 0 and tracked > 0:
            print(f"  ... {tracked} / {len(rows)}")

    conn.close()
    print(f"[OK] تتبعنا نتائج {tracked} تنبؤاً")
    return tracked


def generate_accuracy_report():
    """تقرير دقة الماسح — نسب نجاح حقيقية"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute('''SELECT COUNT(*) FROM outcome_tracking WHERE exploded = 1''')
    hits = c.fetchone()[0]

    c.execute('''SELECT COUNT(*) FROM outcome_tracking''')
    total = c.fetchone()[0]

    c.execute('''SELECT AVG(change_1d) FROM outcome_tracking WHERE change_1d IS NOT NULL''')
    avg_1d = c.fetchone()[0]

    c.execute('''SELECT AVG(change_3d) FROM outcome_tracking WHERE change_3d IS NOT NULL''')
    avg_3d = c.fetchone()[0]

    c.execute('''SELECT AVG(change_5d) FROM outcome_tracking WHERE change_5d IS NOT NULL''')
    avg_5d = c.fetchone()[0]

    c.execute('''SELECT AVG(max_change_5d) FROM outcome_tracking WHERE max_change_5d IS NOT NULL''')
    avg_max = c.fetchone()[0]

    c.execute('''SELECT AVG(min_change_5d) FROM outcome_tracking WHERE min_change_5d IS NOT NULL''')
    avg_min = c.fetchone()[0]

    c.execute('''SELECT symbol, change_5d FROM outcome_tracking 
        WHERE change_5d IS NOT NULL ORDER BY change_5d DESC LIMIT 5''')
    best = c.fetchall()

    c.execute('''SELECT symbol, change_5d FROM outcome_tracking 
        WHERE change_5d IS NOT NULL ORDER BY change_5d ASC LIMIT 5''')
    worst = c.fetchall()

    conn.close()

    if total == 0:
        return {
            'total_tracked': 0,
            'hits': 0,
            'accuracy': 0,
            'avg_return_1d': 0,
            'avg_return_3d': 0,
            'avg_return_5d': 0,
            'avg_max_upside': 0,
            'avg_max_drawdown': 0,
            'best_performers': [],
            'worst_performers': [],
        }

    report = {
        'total_tracked': total,
        'hits': hits,
        'accuracy': round(hits / total * 100, 2),
        'accuracy_pct': f"{round(hits / total * 100, 1)}%",
        'avg_return_1d': round(avg_1d, 2) if avg_1d else 0,
        'avg_return_3d': round(avg_3d, 2) if avg_3d else 0,
        'avg_return_5d': round(avg_5d, 2) if avg_5d else 0,
        'avg_max_upside': round(avg_max, 2) if avg_max else 0,
        'avg_max_drawdown': round(avg_min, 2) if avg_min else 0,
        'best_performers': [{'symbol': r[0], 'return': round(r[1], 2)} for r in best],
        'worst_performers': [{'symbol': r[0], 'return': round(r[1], 2)} for r in worst],
    }
    return report


def get_indicator_breakdown():
    """تحليل دقة كل مؤشر على حدة — وش المؤشرات اللي فعلاً تنبئ بالانفجار؟"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    report = {}
    indicators = [
        ('cmf', 'CMF > 0.15', 'cmf >= 0.15'),
        ('bollinger_squeeze', 'Bollinger Squeeze', 'bollinger_squeeze = 1'),
        ('obv_above', 'OBV صاعد', 'obv_above = 1'),
        ('volume_ratio', 'حجم > 2x', 'volume_ratio >= 2.0'),
        ('rsi_40_65', 'RSI 40-65', 'rsi BETWEEN 40 AND 65'),
        ('rsi_30_40', 'RSI 30-40', 'rsi BETWEEN 30 AND 40'),
        ('z_score', 'Z-Score > 1.5', 'z_score >= 1.5'),
    ]

    for key, name, condition in indicators:
        try:
            c.execute(f'''SELECT COUNT(*) FROM outcome_tracking WHERE {condition}''')
            total_with_indicator = c.fetchone()[0]
            c.execute(f'''SELECT COUNT(*) FROM outcome_tracking 
                WHERE {condition} AND exploded = 1''')
            hits_with_indicator = c.fetchone()[0]

            c.execute(f'''SELECT COUNT(*) FROM outcome_tracking 
                WHERE NOT ({condition}) AND exploded = 1''')
            hits_without = c.fetchone()[0]
            c.execute(f'''SELECT COUNT(*) FROM outcome_tracking 
                WHERE NOT ({condition})''')
            total_without = c.fetchone()[0]

            acc_with = round(hits_with_indicator / total_with_indicator * 100, 1) if total_with_indicator > 0 else 0
            acc_without = round(hits_without / total_without * 100, 1) if total_without > 0 else 0

            report[key] = {
                'name': name,
                'total': total_with_indicator,
                'hits': hits_with_indicator,
                'accuracy': acc_with,
                'accuracy_pct': f"{acc_with}%",
                'baseline': acc_without,
                'lift': round(acc_with - acc_without, 1),
            }
        except:
            continue

    conn.close()
    return report


def print_report():
    report = generate_accuracy_report()
    if report['total_tracked'] == 0:
        print("\nلا توجد نتائج متتبعة بعد. شغّل backfill_outcomes() أولاً.")
        return

    print("\n" + "=" * 65)
    print("  تقرير دقة الماسح — OutCome Tracker")
    print("=" * 65)
    print(f"  إجمالي التنبؤات المتتبعة: {report['total_tracked']}")
    print(f"  الانفجارات المحققة:        {report['hits']}")
    print(f"  نسبة الدقة:                {report['accuracy_pct']}")
    print(f"\n  متوسط العائد:")
    print(f"  بعد يوم:   {report['avg_return_1d']:+.1f}%")
    print(f"  بعد 3 أيام: {report['avg_return_3d']:+.1f}%")
    print(f"  بعد 5 أيام: {report['avg_return_5d']:+.1f}%")
    print(f"\n  متوسط أقصى صعود:  {report['avg_max_upside']:+.1f}%")
    print(f"  متوسط أقصى هبوط:  {report['avg_max_drawdown']:+.1f}%")

    if report['best_performers']:
        print("\n  أفضل 5:")
        for s in report['best_performers']:
            print(f"    {s['symbol']}: {s['return']:+.1f}%")
    if report['worst_performers']:
        print("\n  أسوأ 5:")
        for s in report['worst_performers']:
            print(f"    {s['symbol']}: {s['return']:+.1f}%")

    indicators = get_indicator_breakdown()
    if indicators:
        print("\n" + "-" * 65)
        print("  دقة كل مؤشر:")
        print("-" * 65)
        print(f"  {'المؤشر':<25} {'حجم':<8} {'دقة':<8} {'أساس':<8} {'الفرق':<8}")
        print("-" * 65)
        for k, v in indicators.items():
            print(f"  {v['name']:<25} {v['total']:<8} {v['accuracy_pct']:<8} {v['baseline']:<8.1f} {v['lift']:<+7.1f}%")

    print("\n" + "=" * 65)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "report":
        print_report()
    else:
        backfill_outcomes()
        print_report()
