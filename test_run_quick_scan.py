"""
test_run_quick_scan.py — test suite for the Track 2 runtime wrapper.
Matches the lightweight PASS/FAIL style used across this repository.

The network-bound run() path is NOT exercised here (would hit TradingView +
yfinance); we verify the pure helpers, the DB insert contract, and the
composed prediction output shape instead.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile

import numpy as np
import pandas as pd

import feature_pipeline
import run_quick_scan

PASS = 0
FAIL = 0
ERRORS: list[str] = []


def check_condition(name: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL, ERRORS
    if condition:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        message = f"FAIL  {name}"
        if detail:
            message += f"  [{detail}]"
        print(f"  {message}")
        ERRORS.append(name)


def section(title: str) -> None:
    print("")
    print(title)
    print("-" * len(title))


def make_ohlcv(n: int = 80, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-01-01", periods=n, freq="B")
    close = 5.0 + np.cumsum(rng.normal(0.01, 0.1, n))
    open_ = close + rng.normal(0, 0.02, n)
    high = np.maximum(open_, close) + rng.uniform(0.01, 0.2, n)
    low = np.minimum(open_, close) - rng.uniform(0.01, 0.2, n)
    volume = rng.uniform(300_000, 900_000, n)
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=idx,
    )


def run_tests() -> tuple[int, int, list[str]]:
    global PASS, FAIL, ERRORS
    PASS = 0
    FAIL = 0
    ERRORS = []

    print("=" * 60)
    print("  RUN QUICK SCAN TEST SUITE (TRACK 2 RUNTIME)")
    print("=" * 60)

    section("IMPORTS & COMPOSITION")
    check_condition("module imports cleanly", run_quick_scan is not None)
    check_condition("pulls analyze_stock from run_real_scan", callable(run_quick_scan.analyze_stock))
    check_condition("pulls get_stock_list from run_real_scan", callable(run_quick_scan.tv_get_stock_list))
    check_condition("pulls extract_features from feature_pipeline", callable(run_quick_scan.extract_features))
    check_condition("pulls quick_scan training/ranking helpers", all(callable(getattr(run_quick_scan, fn, None)) for fn in (
        "load_training_matrix", "train_regressor", "backtest_honesty_gate",
        "rank_universe", "quick_scan",
    )))
    check_condition("DB_PATH points at scanner_history.db", run_quick_scan.DB_PATH == "scanner_history.db")
    check_condition("DB_PATH matches predictive_scanner", run_quick_scan.DB_PATH == __import__("predictive_scanner").DB_PATH)
    check_condition("DB_PATH matches outcome_tracker", run_quick_scan.DB_PATH == __import__("outcome_tracker").DB_PATH)

    section("FEATURE ROW BUILDING")
    df = make_ohlcv()
    features = {
        "symbol": "TEST",
        "price": 5.5,
        "volume": 500_000,
        "change_1d": 1.2,
        "change_5d": 3.0,
        "volume_ratio": 1.8,
        "z_score": 0.5,
        "rsi": 55.0,
        "cmf": 0.1,
        "bollinger_squeeze": True,
        "obv_above_sma": True,
        "gap_pct": 0.7,
        "short_percent": 0.15,
        "price_at_scan": 5.5,
        "ohlcv": df,
    }
    row = run_quick_scan._build_feature_row(features)
    check_condition("builds a 27-dim feature row", isinstance(row, list) and len(row) == 27)
    if isinstance(row, list):
        check_condition("row is all finite floats", len(row) == 27 and all(np.isfinite(float(v)) for v in row))
    short = dict(features, ohlcv=make_ohlcv(n=20))
    check_condition("rejects too-short OHLCV", run_quick_scan._build_feature_row(short) is None)
    check_condition("rejects missing OHLCV", run_quick_scan._build_feature_row(dict(features, ohlcv=None)) is None)
    bad = dict(features, volume_ratio=float("inf"))
    check_condition("rejects non-finite engine value", run_quick_scan._build_feature_row(bad) is None)
    bad_ohlcv = make_ohlcv(n=80)
    bad_ohlcv.loc[bad_ohlcv.index[-1], "high"] = float("inf")
    check_condition("rejects non-finite OHLCV tail", run_quick_scan._build_feature_row(dict(features, ohlcv=bad_ohlcv)) is None)

    section("SESSION LABELLING")
    def label(h: int, m: int) -> tuple[str, str]:
        return run_quick_scan._session_label(pd.Timestamp("2026-08-03", tz="US/Eastern").tz_localize(None).replace(hour=h, minute=m).tz_localize("US/Eastern"))
    check_condition("premarket 08:00", label(8, 0)[0] == "premarket")
    check_condition("regular 10:00", label(10, 0)[0] == "regular")
    check_condition("afterhours 16:30", label(16, 30)[0] == "afterhours")
    check_condition("closed 01:00", label(1, 0)[0] == "closed")

    section("CLI FLAGS & RUN SIGNATURE")
    check_condition("run() accepts max_stocks", run_quick_scan.run.__code__.co_varnames[:4] == ("max_stocks", "top_n", "seed", "do_log"))
    check_condition("run() has defaults for limit/seed/log",
         run_quick_scan.run.__defaults__ == (200, None, 42, True))
    with open(run_quick_scan.__file__, "r", encoding="utf-8") as f:
        rqs_source = f.read()
    check_condition("run() routes seed to backtest_honesty_gate", "random_state=seed" in rqs_source)
    check_condition("run() guards DB write with do_log", "if do_log:" in rqs_source)
    check_condition("_keep_previous_predictions exists", callable(run_quick_scan._keep_previous_predictions))

    section("EMPTY-RUN GUARD")
    empty_path = os.path.join(tempfile.gettempdir(), "predictions_guard_test.json")
    if os.path.exists(empty_path):
        os.remove(empty_path)
    check_condition("guard returns False when file missing", run_quick_scan._keep_previous_predictions(empty_path) is False)
    with open(empty_path, "w", encoding="utf-8") as f:
        json.dump({"predictions": []}, f)
    check_condition("guard returns False when prev empty", run_quick_scan._keep_previous_predictions(empty_path) is False)
    with open(empty_path, "w", encoding="utf-8") as f:
        json.dump({"predictions": [{"symbol": "X"}]}, f)
    check_condition("guard returns True when prev has preds", run_quick_scan._keep_previous_predictions(empty_path) is True)
    with open(empty_path, "w", encoding="utf-8") as f:
        f.write("{broken json")
    check_condition("guard returns False on corrupt file", run_quick_scan._keep_previous_predictions(empty_path) is False)
    os.remove(empty_path)

    section("PREDICTION ENTRY SHAPE")
    meta = dict(features)
    entry = run_quick_scan._prediction_entry(meta, {"symbol": "TEST", "predicted_upside": 12.34})
    check_condition("entry carries symbol", entry.get("symbol") == "TEST")
    check_condition("entry carries predicted_upside", abs(entry.get("predicted_upside", 0) - 12.34) < 1e-6)
    check_condition("entry carries explosion_probability (clamped 0-99)", 0 <= entry.get("explosion_probability", -1) <= 99)
    check_condition("entry carries app-facing keys",
         all(k in entry for k in ("price", "volume_ratio", "z_score", "rsi", "cmf",
                                  "bollinger_squeeze", "obv_above_sma", "change_1d", "change_5d")))

    section("DB INSERTION CONTRACT")
    conn = None
    try:
        tmp = os.path.join(tempfile.gettempdir(), "run_quick_scan_test.db")
        if os.path.exists(tmp):
            os.remove(tmp)
        conn = sqlite3.connect(tmp)
        conn.execute(
            """
            CREATE TABLE session_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_time TEXT, session_type TEXT, symbol TEXT, price REAL,
                volume REAL, volume_ratio REAL, z_score REAL, change_pct REAL,
                rsi REAL, cmf REAL, obv_above INTEGER, bollinger_squeeze INTEGER,
                anomaly_score REAL, gap_pct REAL, float_shares REAL,
                short_percent REAL, next_session_change REAL, exploded INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE outcome_tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prediction_id INTEGER, symbol TEXT, scan_time TEXT,
                session_type TEXT, price_at_scan REAL, volume_ratio REAL,
                z_score REAL, rsi REAL, cmf REAL, bollinger_squeeze INTEGER,
                obv_above INTEGER, change_pct_at_scan REAL, explosion_score REAL,
                price_1d REAL, price_3d REAL, price_5d REAL, change_1d REAL,
                change_3d REAL, change_5d REAL, max_change_5d REAL,
                min_change_5d REAL, exploded INTEGER, touched_stop INTEGER,
                last_checked TEXT
            )
            """
        )
        pred_id = run_quick_scan._insert_prediction(
            conn,
            {"symbol": "TEST", "predicted_upside": 12.34},
            meta,
            "regular",
            "2026-08-03T15:00:00",
        )
        sid = conn.execute("SELECT id FROM session_data WHERE symbol='TEST'").fetchone()
        ot = conn.execute("SELECT prediction_id FROM outcome_tracking WHERE symbol='TEST'").fetchone()
        check_condition("insert returns positive id", isinstance(pred_id, int) and pred_id > 0)
        check_condition("session_data row written", sid is not None and sid[0] == pred_id)
        check_condition("outcome_tracking row linked", ot is not None and ot[0] == pred_id)
        if sid is not None:
            row_s = conn.execute("SELECT * FROM session_data WHERE id=?", (pred_id,)).fetchone()
            cols_s = [c[0] for c in conn.execute("SELECT * FROM session_data").description]
            check_condition("session_data columns align with predictive_scanner schema",
                 set(cols_s) >= {"scan_time", "session_type", "symbol", "price", "volume",
                                 "volume_ratio", "z_score", "change_pct", "rsi", "cmf",
                                 "obv_above", "bollinger_squeeze", "anomaly_score", "gap_pct",
                                 "float_shares", "short_percent", "next_session_change", "exploded"})
        if ot is not None:
            row_o = conn.execute("SELECT * FROM outcome_tracking WHERE prediction_id=?", (pred_id,)).fetchone()
            cols_o = [c[0] for c in conn.execute("SELECT * FROM outcome_tracking").description]
            check_condition("outcome_tracking columns align with outcome_tracker schema",
                 set(cols_o) >= {"prediction_id", "symbol", "scan_time", "session_type",
                                 "price_at_scan", "explosion_score", "max_change_5d",
                                 "min_change_5d", "exploded", "touched_stop", "last_checked"})
    except Exception as exc:
        check_condition("db insert ran without exception", False, detail=str(exc))
    finally:
        if conn is not None:
            conn.close()

    print("\n" + "=" * 60)
    print(f"RESULT: {PASS} passed, {FAIL} failed")
    print("=" * 60)
    return PASS, FAIL, ERRORS


if __name__ == "__main__":
    _, fail, _ = run_tests()
    raise SystemExit(1 if fail else 0)
