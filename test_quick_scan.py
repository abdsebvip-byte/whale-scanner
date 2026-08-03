"""
Quick-scan (Track 2) test suite — Approach 1 direct regression on max upside.
Matches the lightweight PASS/FAIL style already used in this repository.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

import feature_pipeline
import quick_scan

PASS = 0
FAIL = 0
ERRORS: list[str] = []


def test(name: str, condition: bool, detail: str = "") -> None:
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


def run_tests() -> tuple[int, int, list[str]]:
    global PASS, FAIL, ERRORS
    PASS = 0
    FAIL = 0
    ERRORS = []

    print("=" * 60)
    print("  QUICK SCAN TEST SUITE (TRACK 2)")
    print("=" * 60)

    section("SCAN BAND CONSTANTS")
    test("MIN_PRICE == 0.10", quick_scan.MIN_PRICE == 0.10)
    test("MAX_PRICE == 10.00", quick_scan.MAX_PRICE == 10.0)
    test("scan band matches predictive_scanner constants", (quick_scan.MIN_PRICE, quick_scan.MAX_PRICE) == (0.10, 10.0))

    section("HONESTY GATE CONSTANTS")
    test("gate top-N == 10", quick_scan.TOP_N_GATE == 10)
    test("min upside ratio == 3.0 (3-5x design)", quick_scan.MIN_UPSIDE_RATIO == 3.0)
    test("surface top-N == 20", quick_scan.TOP_N_OUTPUT == 20)

    section("TRAINING MATRIX LOADER")
    test("TRAINING_MATRIX_PATH points to band csv", os.path.basename(str(quick_scan.TRAINING_MATRIX_PATH)) == "training_matrix_band.csv")
    test("training matrix exists on disk", os.path.exists(str(quick_scan.TRAINING_MATRIX_PATH)))

    X, y, feature_names = quick_scan.load_training_matrix()
    test("X is 2D numeric", isinstance(X, np.ndarray) and X.ndim == 2 and np.issubdtype(X.dtype, np.number))
    test("y is 1D numeric", isinstance(y, np.ndarray) and y.ndim == 1 and np.issubdtype(y.dtype, np.number))
    test("X has 126 in-band rows", X.shape[0] == 126)
    test("X has 27 features (23 canonical + 4 engine)", X.shape[1] == 27)
    test("y has one label per row", y.shape[0] == 126)
    test("feature_names length == 27", len(feature_names) == 27)
    test("first 23 features are canonical FEATURE_COLUMNS", list(feature_names[:23]) == list(feature_pipeline.FEATURE_COLUMNS))
    test("engine features appended in order", list(feature_names[23:]) == ["price_at_scan", "volume_ratio", "gap_pct", "short_percent"])
    test("no NaN in feature matrix", np.isnan(X).sum() == 0)
    test("no NaN in targets", np.isnan(y).sum() == 0)
    test("explosive rows present (max >= 50%)", float(y.max()) >= 50.0)
    test("exactly 5 in-band rows reach >= 50%", int((y >= 50).sum()) == 5)
    test("targets stay in percent range", float(y.min()) >= -1.0)

    section("REGRESSION TRAINER")
    test("train_regressor exists", hasattr(quick_scan, "train_regressor"))
    regressor = None
    train_fn = getattr(quick_scan, "train_regressor", None)
    if train_fn is not None:
        regressor = train_fn(X, y)
        test("train_regressor returns a fitted object", regressor is not None and hasattr(regressor, "predict"))
        predicted = np.asarray(regressor.predict(X), dtype=float)
        test("predictions are 1D with one value per row", predicted.ndim == 1 and predicted.shape[0] == X.shape[0])
        test("predictions are finite", bool(np.isfinite(predicted).all()))
        test("predictions are not constant", float(np.std(predicted)) > 0.0)
        rank_corr = float(np.corrcoef(np.argsort(np.argsort(y)), np.argsort(np.argsort(predicted)))[0, 1])
        test("rank correlation with outcome is positive (model learned)", rank_corr > 0.0, detail=f"corr={rank_corr:.3f}")

    section("HONESTY GATE")
    test("backtest_honesty_gate exists", hasattr(quick_scan, "backtest_honesty_gate"))
    gate_fn = getattr(quick_scan, "backtest_honesty_gate", None)
    if gate_fn is not None and regressor is not None:
        gate = gate_fn(X, y, regressor)
        for key in ("top10_avg", "random_avg", "ratio", "passed"):
            test(f"gate returns '{key}'", isinstance(gate, dict) and key in gate)
        test("gate ratio equals top10_avg / random_avg", abs(gate["ratio"] - gate["top10_avg"] / gate["random_avg"]) < 1e-9)
        test("gate 'passed' is a bool", isinstance(gate["passed"], bool))
        test("gate 'passed' matches ratio threshold", gate["passed"] == (gate["ratio"] >= quick_scan.MIN_UPSIDE_RATIO))
        test("gate ratio is finite and non-negative", bool(np.isfinite(gate["ratio"])) and gate["ratio"] >= 0.0)
        gate_again = gate_fn(X, y, regressor, random_state=42)
        test("gate is deterministic for a fixed seed", gate_again["ratio"] == gate["ratio"])
    else:
        if regressor is None:
            test("gate requires a trained regressor", False)

    section("QUICK SCAN RANKING")
    test("rank_universe exists", hasattr(quick_scan, "rank_universe"))
    symbols = [f"TICKER{i}" for i in range(X.shape[0])]
    ranked = None
    rank_fn = getattr(quick_scan, "rank_universe", None)
    if rank_fn is not None and regressor is not None:
        ranked = rank_fn(X, symbols, regressor)
        test("rank_universe returns a list", isinstance(ranked, list))
        test("rank_universe ranks every symbol", isinstance(ranked, list) and len(ranked) == X.shape[0])
        if isinstance(ranked, list) and len(ranked) > 1:
            test("every entry has symbol + predicted_upside",
                 all(isinstance(e, dict) and "symbol" in e and "predicted_upside" in e for e in ranked))
            values = [float(e["predicted_upside"]) for e in ranked]
            test("ranking is descending by predicted_upside", all(values[i] >= values[i + 1] for i in range(len(values) - 1)))
    else:
        if regressor is None:
            test("rank_universe requires a trained regressor", False)

    section("QUICK SCAN ENTRY")
    test("quick_scan exists", hasattr(quick_scan, "quick_scan"))
    scan_fn = getattr(quick_scan, "quick_scan", None)
    if scan_fn is not None and regressor is not None:
        top = scan_fn(X, symbols, regressor)
        test("quick_scan surfaces TOP_N_OUTPUT entries", isinstance(top, list) and len(top) == quick_scan.TOP_N_OUTPUT)
        test("quick_scan entries are the top ranked",
             isinstance(top, list) and ranked is not None and top == ranked[: quick_scan.TOP_N_OUTPUT])
    else:
        if regressor is None:
            test("quick_scan requires a trained regressor", False)

    print("\n" + "=" * 60)
    print(f"RESULT: {PASS} passed, {FAIL} failed")
    print("=" * 60)
    return PASS, FAIL, ERRORS


if __name__ == "__main__":
    _, fail, _ = run_tests()
    raise SystemExit(1 if fail else 0)
