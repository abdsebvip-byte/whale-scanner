"""
run_quick_scan.py — ماسح Track 2 (انحدار على أقصى صعود 5 أيام)
================================================================
- يسحب قائمة الأسهم من TradingView (نفس run_real_scan)
- يحلل كل سهم بـ analyze_stock (يجلب OHLCV خام + حقول المحرك)
- يبني 27 ميزة: 23 من feature_pipeline.extract_features + 4 من المحرك
- يدرب انحدار quick_scan على training_matrix_band.csv
- يمرر بوابة الصدق (backtest_honesty_gate) ثم يرتب الكون
- يكتب predictions.json بشكل متوافق مع app.load_predictions
- يضمن الجداول ويُدرج كل تنبؤ في session_data ثم outcome_tracking
"""
import json
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from run_real_scan import analyze_stock, get_stock_list as tv_get_stock_list
from feature_pipeline import extract_features, FEATURE_COLUMNS
from quick_scan import (
    load_training_matrix,
    train_regressor,
    backtest_honesty_gate,
    rank_universe,
    quick_scan,
    FEATURE_COLUMNS_FULL,
    TOP_N_OUTPUT,
)
import predictive_scanner
import outcome_tracker

DB_PATH = "scanner_history.db"
PREDICTIONS_PATH = "predictions.json"


def _build_feature_row(features: dict) -> list | None:
    """اجمع 27 ميزة من آخر صف features + حقول المحرك الأربعة."""
    try:
        raw = features.get("ohlcv")
        if raw is None or len(raw) < 60:
            return None
        feats = extract_features(raw)
        if feats is None or feats.empty:
            return None
        last = feats.iloc[-1]
        if last.isna().any():
            return None
        engine = [
            float(features.get("price_at_scan", 0.0) or 0.0),
            float(features.get("volume_ratio", 1.0) or 1.0),
            float(features.get("gap_pct", 0.0) or 0.0),
            float(features.get("short_percent", 0.0) or 0.0),
        ]
        row = [float(x) for x in last.tolist()] + engine
        if not all(np.isfinite(float(x)) for x in row):
            return None
        return row
    except Exception:
        return None


def _keep_previous_predictions(path: str = PREDICTIONS_PATH) -> bool:
    """Return True if an empty run should preserve an existing predictions file."""
    if not os.path.exists(path):
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            prev = json.load(f)
    except Exception:
        return False
    return bool(prev.get("predictions"))


def _session_label(now: datetime) -> tuple[str, str]:
    t = now.hour * 60 + now.minute
    if 240 <= t < 570:
        return "premarket", "Pre-Market"
    if 570 <= t < 960:
        return "regular", "Regular"
    if 960 <= t < 1200:
        return "afterhours", "After-Hours"
    return "closed", "Market Closed"


def _insert_prediction(
    conn: sqlite3.Connection,
    prediction: dict,
    features: dict,
    session: str,
    scan_time: str,
) -> int:
    """أدرج في session_data وأعد prediction_id ثم أدرج في outcome_tracking."""
    cur = conn.cursor()
    price = float(features.get("price", 0.0) or 0.0)
    volume_ratio = float(features.get("volume_ratio", 1.0) or 1.0)
    z_score = float(features.get("z_score", 0.0) or 0.0)
    change_pct = float(features.get("change_1d", 0.0) or 0.0)
    rsi = float(features.get("rsi", 50.0) or 50.0)
    cmf = float(features.get("cmf", 0.0) or 0.0)
    obv = 1 if features.get("obv_above_sma") else 0
    squeeze = 1 if features.get("bollinger_squeeze") else 0
    gap_pct = float(features.get("gap_pct", 0.0) or 0.0)
    short_percent = float(features.get("short_percent", 0.0) or 0.0)
    upside = float(prediction.get("predicted_upside", 0.0) or 0.0)
    volume = float(features.get("volume", 0.0) or 0.0)

    cur.execute(
        """
        INSERT INTO session_data (
            scan_time, session_type, symbol, price, volume, volume_ratio,
            z_score, change_pct, rsi, cmf, obv_above, bollinger_squeeze,
            explosion_score, gap_pct, float_shares, short_percent,
            next_session_change, exploded
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            scan_time,
            session,
            prediction["symbol"],
            price,
            volume,
            volume_ratio,
            z_score,
            change_pct,
            rsi,
            cmf,
            obv,
            squeeze,
            round(upside, 2),
            gap_pct,
            0.0,
            short_percent,
            None,
            0,
        ),
    )
    prediction_id = int(cur.lastrowid)

    cur.execute(
        """
        INSERT INTO outcome_tracking (
            prediction_id, symbol, scan_time, session_type, price_at_scan,
            volume_ratio, z_score, rsi, cmf, bollinger_squeeze, obv_above,
            change_pct_at_scan, explosion_score, price_1d, price_3d,
            price_5d, change_1d, change_3d, change_5d, max_change_5d,
            min_change_5d, exploded, touched_stop, last_checked
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            prediction_id,
            prediction["symbol"],
            scan_time,
            session,
            price,
            volume_ratio,
            z_score,
            rsi,
            cmf,
            squeeze,
            obv,
            change_pct,
            int(round(upside)),
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            0,
            0,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    return prediction_id


def _prediction_entry(meta: dict, pred: dict) -> dict:
    symbol = meta.get("symbol", pred.get("symbol", ""))
    upside = float(pred.get("predicted_upside", 0.0) or 0.0)
    return {
        "symbol": symbol,
        "price": round(float(meta.get("price", 0.0) or 0.0), 2),
        "explosion_probability": round(min(99.0, max(0.0, upside)), 1),
        "predicted_upside": round(upside, 2),
        "volume_ratio": round(float(meta.get("volume_ratio", 1.0) or 1.0), 2),
        "z_score": round(float(meta.get("z_score", 0.0) or 0.0), 2),
        "rsi": round(float(meta.get("rsi", 50.0) or 50.0), 1),
        "cmf": round(float(meta.get("cmf", 0.0) or 0.0), 4),
        "bollinger_squeeze": bool(meta.get("bollinger_squeeze")),
        "obv_above_sma": bool(meta.get("obv_above_sma")),
        "change_1d": round(float(meta.get("change_1d", 0.0) or 0.0), 2),
        "change_5d": round(float(meta.get("change_5d", 0.0) or 0.0), 2),
        "atr_ratio": 0,
        "gap_pct": round(float(meta.get("gap_pct", 0.0) or 0.0), 2),
        "short_percent": round(float(meta.get("short_percent", 0.0) or 0.0), 4),
    }


def run(max_stocks: int = 200, top_n: int | None = None, seed: int = 42, do_log: bool = True):
    try:
        import pytz

        et = pytz.timezone("US/Eastern")
    except Exception:
        et = timezone(timedelta(hours=-4))
    now = datetime.now(et)
    session, session_name = _session_label(now)
    scan_time = now.isoformat()

    print("=" * 60)
    print("  Quick Scan v7.0 (Track 2 regression)")
    print(f"  Session: {session_name}")
    print(f"  Time: {now.strftime('%Y-%m-%d %H:%M ET')}")
    print("=" * 60)

    print("\n[1/4] Getting stocks from TradingView...")
    stocks = tv_get_stock_list()
    print(f"  {len(stocks)} stocks (price ${0.10}-$10.0, |change| <= 8%)")

    stocks.sort(key=lambda x: x.get("volume", 0) or 0, reverse=True)
    stocks = stocks[:max_stocks]

    print(f"\n[2/4] Analyzing top {len(stocks)} stocks...")
    universe_meta = []
    universe_rows = []
    for i, stock in enumerate(stocks):
        if i % 50 == 0 and i > 0:
            print(f"  ... {i}/{len(stocks)}")
        features = analyze_stock(stock["symbol"])
        if not features:
            continue
        row = _build_feature_row(features)
        if row is None:
            continue
        universe_meta.append(features)
        universe_rows.append(row)
        time.sleep(0.05)

    print(f"  {len(universe_rows)} stocks with full feature rows")
    symbols = [m.get("symbol") for m in universe_meta]

    output = {
        "scan_time": scan_time,
        "session": session,
        "session_name": session_name,
        "total_analyzed": len(universe_rows),
        "model_trained": True,
        "gate": {"passed": False},
        "predictions": [],
    }

    if len(universe_rows) < 5:
        print("\n[-] Universe too small; skipping gate and ranking.")
    else:
        print("\n[3/4] Training regressor + honesty gate...")
        X_train, y_train, _names = load_training_matrix()
        regressor = train_regressor(X_train, y_train)
        gate = backtest_honesty_gate(X_train, y_train, regressor, random_state=seed)
        output["gate"] = gate
        print(
            f"  gate: top10_avg={gate['top10_avg']:.2f}% "
            f"random_avg={gate['random_avg']:.2f}% "
            f"ratio={gate['ratio']:.2f} passed={gate['passed']}"
        )

        print("\n[4/4] Ranking universe...")
        X_new = np.asarray(universe_rows, dtype=np.float64)
        ranked = rank_universe(X_new, symbols, regressor)
        top = quick_scan(X_new, symbols, regressor, top_n=top_n or TOP_N_OUTPUT)
        top_symbols = {t["symbol"] for t in top}
        meta_by_symbol = {m.get("symbol"): m for m in universe_meta}
        preds = []
        for p in ranked:
            if p["symbol"] not in top_symbols:
                continue
            meta = meta_by_symbol.get(p["symbol"])
            if meta is None:
                continue
            preds.append(_prediction_entry(meta, p))
        preds.sort(key=lambda x: x.get("predicted_upside", 0.0), reverse=True)
        output["predictions"] = preds
        print(f"  Top {len(preds)} ranked")

    if len(output["predictions"]) == 0 and _keep_previous_predictions():
        print("  Empty run; keeping previous predictions.json")
        with open(PREDICTIONS_PATH, "r", encoding="utf-8") as f:
            output = json.load(f)
    with open(PREDICTIONS_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False, default=str)

    print("\nPersisting predictions to DB...")
    if do_log:
        predictive_scanner.init_db()
        outcome_tracker.init_tracking_db()
        conn = sqlite3.connect(DB_PATH)
        try:
            for pred in output["predictions"]:
                meta = next((m for m in universe_meta if m.get("symbol") == pred["symbol"]), None)
                if meta is None:
                    continue
                _insert_prediction(conn, pred, meta, session, scan_time)
            conn.commit()
        finally:
            conn.close()
        print(f"  Inserted {len(output['predictions'])} rows into session_data + outcome_tracking")
    else:
        print("  --no-log: skipping DB write")

    shown = min(len(output["predictions"]), 15)
    print(f"\n{'='*60}")
    print(f"  TOP {shown} PREDICTIONS:")
    print(f"{'='*60}")
    print(f"  {'#':>2} {'Sym':<8} {'Upside%':>8} {'Price':>8} {'1D%':>7} {'Vol':>6} {'RSI':>5} {'CMF':>7}")
    print(f"  {'-'*65}")
    for i, p in enumerate(output["predictions"][:15], 1):
        up = p.get("predicted_upside") if p.get("predicted_upside") is not None else p.get("explosion_probability", 0)
        print(
            f"  {i:>2} {p.get('symbol',''):<8} {up:>7.1f} "
            f"${p.get('price',0):>6.2f} {p.get('change_1d',0):>+6.1f}% "
            f"{p.get('volume_ratio',0):>5.1f}x {p.get('rsi',50):>4.0f} {p.get('cmf',0):>+6.3f}"
        )

    print(f"\n  Saved {len(output['predictions'])} predictions to {PREDICTIONS_PATH}")
    return output["predictions"]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Quick-scan runtime (Track 2 daily loop)")
    parser.add_argument("--limit", type=int, default=200, help="cap universe size for smoke tests")
    parser.add_argument("--no-log", action="store_true", help="skip outcome_tracker DB write")
    parser.add_argument("--seed", type=int, default=42, help="random_state for the honesty gate")
    args = parser.parse_args()
    run(max_stocks=args.limit, seed=args.seed, do_log=not args.no_log)
