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

# النضوج يتطلب 5 أيام تداول (~7 أيام تقويمية). الصفوف الأحدث من هذا الحد
# لا يمكن نضوجها بعد — نتجاوزها دون جلب شبكي حتى تستحق التحديث.
MATURITY_CUTOFF_DAYS = 7


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
        macd REAL,
        vol_build INTEGER,
        price_pos REAL,
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
    # ترحيل القواعد القديمة: إعادة تسمية anomaly_score -> explosion_score (آمن إن لم يوجد)
    try:
        cols = [r[1] for r in c.execute("PRAGMA table_info(session_data)").fetchall()]
        if 'anomaly_score' in cols and 'explosion_score' not in cols:
            c.execute("ALTER TABLE session_data RENAME COLUMN anomaly_score TO explosion_score")
    except Exception:
        pass
    # ترحيل إضافي: أعمدة المكوّنات الثمانية في outcome_tracking (macd / vol_build / price_pos)
    try:
        cols = [r[1] for r in c.execute("PRAGMA table_info(outcome_tracking)").fetchall()]
        if 'macd' not in cols:
            c.execute("ALTER TABLE outcome_tracking ADD COLUMN macd REAL")
        if 'vol_build' not in cols:
            c.execute("ALTER TABLE outcome_tracking ADD COLUMN vol_build INTEGER")
        if 'price_pos' not in cols:
            c.execute("ALTER TABLE outcome_tracking ADD COLUMN price_pos REAL")
    except Exception:
        pass
    # ترحيل إضافي: أعمدة المكوّنات الثمانية في session_data (macd / vol_build / price_pos)
    # مطلوبة لأن backfill_outcomes يقرأها في SELECT — يجب أن تكون موجودة على القاعدة الفعلية.
    try:
        cols = [r[1] for r in c.execute("PRAGMA table_info(session_data)").fetchall()]
        if 'macd' not in cols:
            c.execute("ALTER TABLE session_data ADD COLUMN macd REAL")
        if 'vol_build' not in cols:
            c.execute("ALTER TABLE session_data ADD COLUMN vol_build INTEGER")
        if 'price_pos' not in cols:
            c.execute("ALTER TABLE session_data ADD COLUMN price_pos REAL")
    except Exception:
        pass
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


def fetch_price_history(symbol, start_date):
    """يعيد [(date, close), ...] تصاعديًا من start_date حتى اليوم."""
    try:
        start = (start_date - timedelta(days=1)).strftime('%Y-%m-%d')
        end = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        ticker = yf.Ticker(symbol)
        hist = ticker.history(start=start, end=end, interval='1d')
        if hist is None or len(hist) == 0:
            return []
        if isinstance(hist.columns, pd.MultiIndex):
            hist.columns = hist.columns.get_level_values(0)
        out = []
        for idx, row in hist.iterrows():
            d = idx.date() if hasattr(idx, 'date') else idx
            out.append((d, float(row['Close'])))
        return out
    except:
        return []


def compute_outcome(price_at_scan, hist_pairs):
    """حساب النتائج بعد 1/3/5 أيام تداول من تاريخ المسح.
    hist_pairs: [(date, close)] تصاعدي يبدأ من أول إغلاق بعد يوم المسح.
    الانفجار (exploded) يُحتسب فقط عند نضوج 5 أيام تداول كاملة — لا fallback على يوم واحد."""
    result = dict(price_1d=None, price_3d=None, price_5d=None,
                  change_1d=None, change_3d=None, change_5d=None,
                  max_chg=None, min_chg=None,
                  best_change=None, is_mature=False, exploded=0, touched_stop=0)
    if not price_at_scan or price_at_scan <= 0 or not hist_pairs:
        return result
    closes = [c for _, c in hist_pairs]
    if len(closes) >= 1:
        result['price_1d'] = round(closes[0], 2)
        result['change_1d'] = round((closes[0] - price_at_scan) / price_at_scan * 100, 2)
    if len(closes) >= 3:
        result['price_3d'] = round(closes[2], 2)
        result['change_3d'] = round((closes[2] - price_at_scan) / price_at_scan * 100, 2)
    if len(closes) >= 5:
        result['price_5d'] = round(closes[4], 2)
        result['change_5d'] = round((closes[4] - price_at_scan) / price_at_scan * 100, 2)
    if closes:
        chgs = [(c - price_at_scan) / price_at_scan * 100 for c in closes]
        result['max_chg'] = round(max(chgs), 2)
        result['min_chg'] = round(min(chgs), 2)
    result['is_mature'] = len(closes) >= 5
    if result['is_mature']:
        best = result['change_5d']
        result['best_change'] = best
        result['exploded'] = 1 if best is not None and best >= 5.0 else 0
        result['touched_stop'] = 1 if result['min_chg'] is not None and result['min_chg'] <= -5.0 else 0
    return result


def backfill_outcomes():
    """تتبع نتائج جميع التنبؤات — إدراج الجديد وتحديث غير الناضج حتى يكتمل 5 أيام تداول.
    السعر يُجلب من تاريخ المسح نفسه، لا من آخر 5 أيام قبل الآن."""
    conn = init_tracking_db()
    c = conn.cursor()

    # حد النضوج: صف أحدث من هذا الحد لا يمكن أن يكتمل فيه 5 أيام تداول بعد،
    # فلا نكلف جلب شبكي له. يُحسب مرة واحدة هنا.
    maturity_cutoff = datetime.now() - timedelta(days=MATURITY_CUTOFF_DAYS)

    c.execute('''SELECT symbol, MIN(scan_time) FROM session_data GROUP BY symbol''')
    oldest_by_symbol = {}
    for sym, st in c.fetchall():
        try:
            dt = datetime.fromisoformat(st)
            if dt.tzinfo is not None:
                dt = dt.replace(tzinfo=None)
        except:
            dt = datetime.now()
        oldest_by_symbol[sym] = dt

    history_cache = {}

    def get_history(symbol, scan_dt):
        if symbol not in history_cache:
            start = oldest_by_symbol.get(symbol, scan_dt)
            history_cache[symbol] = fetch_price_history(symbol, start)
        return history_cache[symbol]

    def parse_scan(scan_time):
        try:
            dt = datetime.fromisoformat(scan_time)
            if dt.tzinfo is not None:
                dt = dt.replace(tzinfo=None)
            return dt
        except:
            return datetime.now()

    # 1) إدراج الصفوف الجديدة (غير المتتبعة)
    c.execute('''SELECT s.id, s.scan_time, s.session_type, s.symbol,
        s.price, s.volume_ratio, s.z_score, s.rsi, s.cmf,
        s.bollinger_squeeze, s.obv_above, s.change_pct, s.explosion_score,
        s.macd, s.vol_build, s.price_pos
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
        macd = row[13] if len(row) > 13 else None
        vol_build = row[14] if len(row) > 14 else None
        price_pos = row[15] if len(row) > 15 else None

        scan_dt = parse_scan(scan_time)
        if scan_dt > maturity_cutoff:
            continue
        hist_pairs = get_history(symbol, scan_dt)
        if not hist_pairs:
            continue
        after = [p for p in hist_pairs if p[0] > scan_dt.date()]
        o = compute_outcome(price_at_scan, after)
        if o['change_1d'] is None:
            continue

        exploded = o['exploded']
        touched_stop = o['touched_stop']

        try:
            c.execute('''INSERT INTO outcome_tracking
                (prediction_id, symbol, scan_time, session_type,
                 price_at_scan, volume_ratio, z_score, rsi, cmf,
                 bollinger_squeeze, obv_above, change_pct_at_scan, explosion_score,
                 macd, vol_build, price_pos,
                 price_1d, price_3d, price_5d,
                 change_1d, change_3d, change_5d,
                 max_change_5d, min_change_5d, exploded, touched_stop, last_checked)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (pred_id, symbol, scan_time, session_type,
                 round(price_at_scan, 2) if price_at_scan else 0,
                 round(vol_ratio, 2) if vol_ratio else 0,
                 round(z_score, 2) if z_score else 0,
                 round(rsi, 1) if rsi else 50,
                 round(cmf, 4) if cmf else 0,
                 squeeze or 0, obv or 0, round(change_pct, 2) if change_pct else 0,
                 explosion_score,
                 round(macd, 4) if macd else 0,
                 int(vol_build) if vol_build else 0,
                 round(price_pos, 4) if price_pos else 0,
                 o['price_1d'], o['price_3d'], o['price_5d'],
                 o['change_1d'], o['change_3d'], o['change_5d'],
                 o['max_chg'], o['min_chg'], exploded, touched_stop,
                 datetime.now().isoformat()))
            conn.commit()
            tracked += 1
        except Exception as e:
            print(f"  [!] خطأ في تخزين {symbol}: {e}")
            continue

        if tracked % 50 == 0 and tracked > 0:
            print(f"  ... {tracked} / {len(rows)}")

    # 2) تحديث الصفوف المتتبعة غير المكتملة (change_5d لم يُحسب بعد) — مع تجاهل
    #    الصفوف الأحدث من حد النضوج. ملاحظة مهمة: change_5d = 0 نتيجة حقيقية
    #    (السعر لم يتحرك)، ليست نقص بيانات، فلا تُعاد معالجتها أبداً.
    c.execute('''SELECT id, symbol, scan_time, price_at_scan
        FROM outcome_tracking
        WHERE change_5d IS NULL''')
    pending = [row for row in c.fetchall() if parse_scan(row[2]) <= maturity_cutoff]
    print(f"[+] {len(pending)} صف متتبع غير مكتمل وناضج — نحدّثها")

    updated = 0
    for pid, symbol, scan_time, price_at_scan in pending:
        scan_dt = parse_scan(scan_time)
        hist_pairs = get_history(symbol, scan_dt)
        if not hist_pairs:
            continue
        after = [p for p in hist_pairs if p[0] > scan_dt.date()]
        o = compute_outcome(price_at_scan, after)
        if o['change_1d'] is None:
            continue
        exploded = o['exploded']
        touched_stop = o['touched_stop']
        try:
            c.execute('''UPDATE outcome_tracking SET
                price_1d=?, price_3d=?, price_5d=?,
                change_1d=?, change_3d=?, change_5d=?,
                max_change_5d=?, min_change_5d=?,
                exploded=?, touched_stop=?, last_checked=?
                WHERE id=?''',
                (o['price_1d'], o['price_3d'], o['price_5d'],
                 o['change_1d'], o['change_3d'], o['change_5d'],
                 o['max_chg'], o['min_chg'],
                 exploded, touched_stop, datetime.now().isoformat(), pid))
            conn.commit()
            updated += 1
        except Exception as e:
            print(f"  [!] خطأ في تحديث {symbol}: {e}")
            continue

    conn.close()
    print(f"[OK] أُدرج {tracked} جديداً وحُدّث {updated} غير مكتمل")
    return tracked


def generate_accuracy_report():
    """تقرير دقة الماسح — نسب نجاح حقيقية"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute('''SELECT COUNT(*) FROM outcome_tracking WHERE exploded = 1''')
    hits = c.fetchone()[0]

    c.execute('''SELECT COUNT(*) FROM outcome_tracking WHERE change_5d IS NOT NULL''')
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
        ('squeeze_volume', 'Squeeze + حجم >= 2x', 'bollinger_squeeze = 1 AND volume_ratio >= 2.0'),
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
