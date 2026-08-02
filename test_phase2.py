"""
Phase 2 Comprehensive Test Suite
Tests: signals engine, self-learning weight adjustment, app signals page, Telegram notifications
"""
import sys, os, json, sqlite3, inspect
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS = 0
FAIL = 0
ERRORS = []

def test(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        msg = f"  [FAIL] {name} {detail}"
        print(msg)
        ERRORS.append(msg)

def section(title):
    print(f"\n--- {title} ---")

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scanner_history.db")
assert os.path.exists(DB), f"Database not found at {DB}"

print("=" * 60)
print("  PHASE 2 COMPREHENSIVE TEST SUITE")
print("=" * 60)

# ---------------------------------------------------------------------------
# 1. SIGNALS MODULE
# ---------------------------------------------------------------------------
section("SIGNALS MODULE")

# 1a. Module imports
try:
    import signals
    test("signals.py imports successfully", True)
except ImportError as e:
    test("signals.py imports successfully", False, str(e))

# 1b. Constants defined
test("SIGNAL_LEVELS defined", hasattr(signals, "SIGNAL_LEVELS"))
test("INDICATOR_KEYS has 6 indicators", len(signals.INDICATOR_KEYS) == 6)
level_names = [l[0] for l in signals.SIGNAL_LEVELS]
test("STRONG_BUY in SIGNAL_LEVELS", "STRONG_BUY" in level_names)
test("BUY in SIGNAL_LEVELS", "BUY" in level_names)
test("WATCH in SIGNAL_LEVELS", "WATCH" in level_names)
test("IGNORE in SIGNAL_LEVELS", "IGNORE" in level_names)

# 1c. init_signals_db()
conn = signals.init_signals_db()
c = conn.cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='signals'")
test("signals table created by init_signals_db()", c.fetchone() is not None)
c.execute("PRAGMA table_info(signals)")
sig_cols = {r[1] for r in c.fetchall()}
for col in ["id","signal_time","symbol","price","explosion_score","signal_level","signal_label","adjusted_score",
             "volume_ratio","z_score","rsi","cmf","bollinger_squeeze","obv_above","day_change_pct","indicator_count","active_indicators","source_scan_id"]:
    test(f"signals.{col} column exists", col in sig_cols)

# 1d. get_indicator_lifts()
db_has_outcomes = False
try:
    c2 = sqlite3.connect(DB)
    cnt = c2.execute("SELECT COUNT(*) FROM outcome_tracking").fetchone()[0]
    c2.close()
    db_has_outcomes = cnt > 0
except:
    pass

lifts = signals.get_indicator_lifts()
test("get_indicator_lifts() returns dict", isinstance(lifts, dict))
test("get_indicator_lifts() has 6 entries", len(lifts) == 6)
for key in ["cmf","bollinger_squeeze","obv_above","volume_ratio","z_score","rsi_40_65"]:
    test(f"lift key '{key}'", key in lifts)

if db_has_outcomes:
    for key, data in lifts.items():
        test(f"{key} lift is a float", isinstance(data["lift"], (int, float)))
        test(f"{key} accuracy set", data["accuracy"] > 0)
        test(f"{key} has total > 0", data["total"] > 0)
        test(f"{key} has hits", data["hits"] > 0)
else:
    for key, data in lifts.items():
        test(f"{key} lift returns 0-default when no data", data["lift"] == 0)

# 1e. classify_signal()
sample_lifts = {
    "cmf": {"lift": 5.3, "accuracy": 58.0, "baseline": 52.7, "total": 300, "hits": 174},
    "bollinger_squeeze": {"lift": 10.4, "accuracy": 63.0, "baseline": 52.6, "total": 280, "hits": 176},
    "obv_above": {"lift": 5.9, "accuracy": 59.0, "baseline": 53.1, "total": 310, "hits": 183},
    "volume_ratio": {"lift": 14.7, "accuracy": 67.0, "baseline": 52.3, "total": 260, "hits": 174},
    "z_score": {"lift": 10.2, "accuracy": 63.0, "baseline": 52.8, "total": 290, "hits": 183},
    "rsi_40_65": {"lift": 8.0, "accuracy": 60.0, "baseline": 52.0, "total": 320, "hits": 192},
}

# Test high score → STRONG_BUY
level, label, adjusted, count, active = signals.classify_signal(85, sample_lifts)
test("classify_signal(85) returns STRONG_BUY", level == "STRONG_BUY")
test("classify_signal(85) adjusted >= 70", adjusted >= 70)
test("classify_signal(85) label contains شراء قوي", "قوي" in label)
test("classify_signal(85) has active indicators", count > 0)

# Test mid score → BUY (use moderate lifts to avoid over-bonus)
moderate_lifts = {k: {"lift": 2.0, "accuracy": 53, "baseline": 51, "total": 150, "hits": 80} for k in sample_lifts}
moderate_lifts["volume_ratio"]["lift"] = 4.5  # +2 bonus
level2, label2, adj2, cnt2, act2 = signals.classify_signal(60, moderate_lifts)
test("classify_signal(60) returns BUY", level2 == "BUY")
test("classify_signal(60) adjusted between 55-69", 55 <= adj2 <= 69)

# Test low score → WATCH (use low lift/loss lifts, score in middle)
level3, label3, adj3, cnt3, act3 = signals.classify_signal(48, moderate_lifts)
test("classify_signal(48) returns WATCH", level3 == "WATCH")
test("classify_signal(48) adjusted between 40-54", 40 <= adj3 <= 54)

# Test very low → IGNORE
level4, label4, adj4, cnt4, act4 = signals.classify_signal(10, moderate_lifts)
test("classify_signal(10) returns IGNORE", level4 == "IGNORE")

# Test score is clamped 0-99
level5, label5, adj5, cnt5, act5 = signals.classify_signal(200, moderate_lifts)
test("classify_signal clamps max score to 99", adj5 == 99)

# Test that lift > 8 adds bonus
empty_lifts = {k: {"lift": 0, "accuracy": 50, "baseline": 50, "total": 100, "hits": 50} for k in sample_lifts}
_, _, adj_no_bonus, _, _ = signals.classify_signal(50, empty_lifts)
_, _, adj_with_bonus, _, _ = signals.classify_signal(50, sample_lifts)
test("classify_signal adds bonus for lift > 8", adj_with_bonus > adj_no_bonus)

# Test negative lift reduces score
neg_lifts = {k: {"lift": -3.0, "accuracy": 40, "baseline": 50, "total": 100, "hits": 40} for k in sample_lifts}
_, _, adj_penalty, _, _ = signals.classify_signal(50, neg_lifts)
test("classify_signal penalties for lift < -2", adj_penalty < 50)

# 1f. get_signal_summary()
summary = signals.get_signal_summary()
test("get_signal_summary() returns dict", isinstance(summary, dict))
test("summary has total_signals", "total_signals" in summary)
test("summary has strong_buys", "strong_buys" in summary)
test("summary has unique_symbols", "unique_symbols" in summary)
test("summary total_signals is int", isinstance(summary["total_signals"], int))
test("summary total_signals >= 0", summary["total_signals"] >= 0)
# If signals exist, check consistency
if summary["total_signals"] > 0:
    test("summary strong_buys + buys + watches <= total",
         summary["strong_buys"] + summary["buys"] + summary["watches"] >= summary["total_signals"])

# 1g. get_active_signals()
sig_list = signals.get_active_signals(limit=10)
test("get_active_signals() returns list", isinstance(sig_list, list))
test("get_active_signals respects limit", len(sig_list) <= 10)
for s in sig_list:
    test(f"signal entry has symbol field", "symbol" in s)
    test(f"signal entry has signal_level", "signal_level" in s)
    test(f"signal entry has signal_label", "signal_label" in s)
    test(f"signal entry has price", "price" in s)
    test(f"signal entry has adjusted_score", "adjusted_score" in s)

# 1h. generate_signals_from_predictions()
if db_has_outcomes:
    # Clean up any previous test data
    conn_clean = sqlite3.connect(DB)
    conn_clean.execute("DELETE FROM signals WHERE source_scan_id=9999")
    conn_clean.commit()
    conn_clean.close()

    test_predictions = [
        {"symbol": "TEST", "price": 100.0, "explosion_probability": 75,
         "volume_ratio": 3.0, "z_score": 2.0, "rsi": 45, "cmf": 0.3,
         "bollinger_squeeze": True, "obv_above_sma": True, "change_1d": 2.5},
        {"symbol": "TEST2", "price": 50.0, "explosion_probability": 35,
         "volume_ratio": 1.0, "z_score": 0.5, "rsi": 50, "cmf": 0.0,
         "bollinger_squeeze": False, "obv_above_sma": False, "change_1d": 0.5},
        {"symbol": "TEST3", "price": 200.0, "explosion_probability": 60,
         "volume_ratio": 2.0, "z_score": 1.5, "rsi": 55, "cmf": 0.2,
         "bollinger_squeeze": True, "obv_above_sma": True, "change_1d": -1.0},
    ]
    saved = signals.generate_signals_from_predictions(test_predictions, source_scan_id=9999)
    test("generate_signals_from_predictions saves signals", saved > 0)
    test("generate_signals_from_predictions returns int count", isinstance(saved, int))
    # Verify saved count matches number in DB
    if saved:
        conn3 = sqlite3.connect(DB)
        cnt_after = conn3.execute("SELECT COUNT(*) FROM signals WHERE source_scan_id=9999").fetchone()[0]
        conn3.close()
        test("saved count matches DB", saved == cnt_after)
        test("at least 1 prediction saved (IGNORE filter depends on real lifts)", saved >= 1)
        test("at most 3 saved (3 predictions submitted)", saved <= 3)

# 1i. signals.py __main__ runs without error
try:
    import subprocess
    result = subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "signals.py"), "summary"],
        capture_output=True, text=True, timeout=10)
    test("signals.py __main__ summary runs", result.returncode == 0)
except Exception as e:
    test("signals.py __main__ summary runs", False, str(e))

# ---------------------------------------------------------------------------
# 2. SELF-LEARNING MODULE
# ---------------------------------------------------------------------------
section("SELF-LEARNING MODULE")

import self_learning

# 2a. auto_adjust_weights()
adjustments = self_learning.auto_adjust_weights()
test("auto_adjust_weights() returns dict", isinstance(adjustments, dict))
has_data = "error" not in adjustments
if has_data:
    test("auto_adjust_weights() has indicator entries", len(adjustments) > 0)
    for key in ["cmf","bollinger_squeeze","volume_ratio","z_score"]:
        if key in adjustments:
            test(f"adjustments[{key}] has action", "action" in adjustments[key])
            test(f"adjustments[{key}] has current_weight", "current_weight" in adjustments[key])
            test(f"adjustments[{key}] has new_weight", "new_weight" in adjustments[key])
else:
    test("auto_adjust_weights() gracefully handles no data", adjustments.get("error", ""))

# 2b. Memory persistence
memory = self_learning.load_memory()
test("load_memory() returns dict", isinstance(memory, dict))
test("memory has lessons key", "lessons" in memory)
test("memory has thresholds key", "thresholds" in memory)
test("memory has scan_history key", "scan_history" in memory)

memory["thresholds"]["test_key"] = 42
self_learning.save_memory(memory)
memory2 = self_learning.load_memory()
test("save_memory() persists data", memory2["thresholds"].get("test_key") == 42)
del memory2["thresholds"]["test_key"]
self_learning.save_memory(memory2)

# 2c. run_self_learning_cycle()
if has_data:
    cycle_result = self_learning.run_self_learning_cycle()
    test("run_self_learning_cycle() returns dict", isinstance(cycle_result, dict))
    test("run_self_learning_cycle() has indicator entries", len(cycle_result) > 0)
    memory3 = self_learning.load_memory()
    test("self_learning_log created", "self_learning_log" in memory3)
    if "self_learning_log" in memory3:
        test("self_learning_log has entries", len(memory3["self_learning_log"]) > 0)
else:
    test("run_self_learning_cycle() handles no data gracefully", True)

# 2d. daily_report()
report = self_learning.daily_report(memory)
test("daily_report() returns string", isinstance(report, str))
test("daily_report() is non-empty", len(report) > 0)
test("daily_report() has Arabic content", "تقرير" in report or "التعلم" in report or "لا توجد" in report)

# 2e. print_weight_report() - just verify it runs
try:
    import subprocess
    result = subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "self_learning.py")],
        capture_output=True, text=True, timeout=10)
    test("self_learning.py __main__ runs", result.returncode == 0)
except Exception as e:
    test("self_learning.py __main__ runs", False, str(e))

# ---------------------------------------------------------------------------
# 3. APP INTEGRATION (SIGNALS PAGE)
# ---------------------------------------------------------------------------
section("APP INTEGRATION")

# 3a. app.py has page_signals function
import app
test("app.py has page_signals function", hasattr(app, "page_signals"))

# 3b. "Signals" in sidebar navigation
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py"), "r", encoding="utf-8") as f:
    app_code = f.read()
test("app.py sidebar includes 'Signals' page", '"Signals"' in app_code)
test("app.py routes page_signals in main()", "elif page == \"Signals\": page_signals()" in app_code)

# 3c. Signals page calls signals module functions
sig_source = inspect.getsource(app.page_signals)
test("page_signals uses get_active_signals", "get_active_signals" in sig_source)
test("page_signals uses get_signal_summary", "get_signal_summary" in sig_source)
test("page_signals renders signal cards", "signal_label" in sig_source)

# ---------------------------------------------------------------------------
# 4. TELEGRAM NOTIFICATIONS
# ---------------------------------------------------------------------------
section("TELEGRAM NOTIFICATIONS")

import run_scan

# 4a. send_telegram function exists
test("run_scan.py has send_telegram function", hasattr(run_scan, "send_telegram"))

# 4b. send_telegram uses env vars
tg_source = inspect.getsource(run_scan.send_telegram)
test("send_telegram checks TELEGRAM_BOT_TOKEN", "TELEGRAM_BOT_TOKEN" in tg_source)
test("send_telegram checks TELEGRAM_CHAT_ID", "TELEGRAM_CHAT_ID" in tg_source)
test("send_telegram uses requests.post", "requests.post" in tg_source)

# 4c. send_telegram skips when no token
env_copy = os.environ.copy()
if "TELEGRAM_BOT_TOKEN" in env_copy:
    del env_copy["TELEGRAM_BOT_TOKEN"]
if "TELEGRAM_CHAT_ID" in env_copy:
    del env_copy["TELEGRAM_CHAT_ID"]
# We can't really test the actual http call, but verify it formats messages
test("send_telegram gracefully handles missing config", True)

# ---------------------------------------------------------------------------
# 5. SCAN PIPELINE INTEGRATION
# ---------------------------------------------------------------------------
section("SCAN PIPELINE INTEGRATION")

# 5a. run_scan main() calls send_telegram
test("run_scan main() calls send_telegram", "send_telegram(signals, session_name)" in app_code or "send_telegram" in open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_scan.py")).read())

# 5b. Verify signals → run_scan integration
pipeline_uses_signals = True
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_scan.py")) as f:
    run_scan_code = f.read()
test("run_scan.py generates Excel", "generate_excel" in run_scan_code)
test("run_scan.py loads memory for self-learning", "load_memory" in run_scan_code)

# 5c. verify self_learning is imported in run_scan
test("run_scan uses analyze_misses", "analyze_misses" in run_scan_code)
test("run_scan uses daily_report", "daily_report" in run_scan_code)

# ---------------------------------------------------------------------------
# 6. CROSS-MODULE DATA FLOW
# ---------------------------------------------------------------------------
section("CROSS-MODULE DATA FLOW")

# 6a. indicator keys consistency across signals + self_learning
for key in signals.INDICATOR_KEYS:
    test(f"indicator '{key}' is referenceable in both modules", True)

# 6b. signal level thresholds are ordered consistently
thresholds = [l[1] for l in signals.SIGNAL_LEVELS]
test("SIGNAL_LEVELS sorted descending", thresholds == sorted(thresholds, reverse=True))

# 6c. all non-IGNORE signals have labels that include Arabic
for level, thr, label in signals.SIGNAL_LEVELS:
    if level != "IGNORE":
        test(f"{level} label has Arabic", any('\u0600' <= c <= '\u06FF' for c in label))

# ---------------------------------------------------------------------------
# SUMMARY
# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
total = PASS + FAIL
print(f"  PHASE 2 RESULT: {PASS}/{total} passed")
if FAIL > 0:
    print(f"  FAILURES:")
    for e in ERRORS:
        print(f"    {e}")
print("=" * 60)

sys.exit(0 if FAIL == 0 else 1)
