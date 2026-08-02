"""
Feature pipeline test suite.
Matches the lightweight PASS/FAIL style already used in this repository.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

import numpy as np
import pandas as pd

import feature_pipeline

PASS = 0
FAIL = 0
ERRORS: list[str] = []


def test(name: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        msg = f"  [FAIL] {name} {detail}".rstrip()
        print(msg)
        ERRORS.append(msg)


def section(title: str) -> None:
    print(f"\n--- {title} ---")


def make_ohlcv(
    rows: int = 120,
    slope: float = 0.2,
    start_price: float = 10.0,
    volume_base: float = 100_000.0,
) -> pd.DataFrame:
    idx = pd.bdate_range("2026-01-05", periods=rows)
    trend = start_price + np.arange(rows) * slope
    seasonal = np.sin(np.arange(rows) / 7.0) * 0.15
    close = trend + seasonal
    open_ = close - 0.05
    high = close + 0.25
    low = close - 0.25
    volume = np.full(rows, volume_base, dtype=float)
    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
        index=idx,
    )


def run_tests() -> tuple[int, int, list[str]]:
    global PASS, FAIL, ERRORS
    PASS = 0
    FAIL = 0
    ERRORS = []

    print("=" * 60)
    print("  FEATURE PIPELINE TEST SUITE")
    print("=" * 60)

    section("FEATURE EXTRACTION")

    source = make_ohlcv()
    snapshot = source.copy(deep=True)
    extracted = feature_pipeline.extract_features(source)

    test("extract_features returns DataFrame", isinstance(extracted, pd.DataFrame))
    test("row count matches input", len(extracted) == len(source))
    test("input DataFrame not mutated", source.equals(snapshot))
    test("feature count matches canonical list", len(feature_pipeline.FEATURE_COLUMNS) == 23)
    test("N_FEATURES is dynamic", feature_pipeline.N_FEATURES == len(feature_pipeline.FEATURE_COLUMNS))
    for column in feature_pipeline.FEATURE_COLUMNS:
        test(f"feature column exists: {column}", column in extracted.columns)

    test(
        "warm-up rows contain NaN values",
        extracted.head(50).isna().sum().sum() > 0,
    )

    constant = make_ohlcv(rows=120, slope=0.0)
    constant[["open", "high", "low", "close"]] = 15.0
    constant_features = feature_pipeline.extract_features(constant)
    const_last = constant_features.iloc[-1]
    test("constant volatility ~= 0", abs(float(const_last["volatility"])) < 1e-9)
    test("constant price_change ~= 0", abs(float(const_last["price_change"])) < 1e-9)
    test("constant atr_pct ~= 0", abs(float(const_last["atr_pct"])) < 1e-9)
    test("constant RSI ~= 50", abs(float(const_last["rsi"]) - 50.0) < 1e-6)

    uptrend = make_ohlcv(rows=140, slope=0.25)
    uptrend_features = feature_pipeline.extract_features(uptrend)
    up_last = uptrend_features.iloc[-1]
    test("uptrend sma_20 positive", float(up_last["sma_20"]) > 0)
    test("uptrend sma_cross_20_50 = +1", float(up_last["sma_cross_20_50"]) == 1.0)
    test("uptrend +DI > -DI", float(up_last["adx_plus_di"]) > float(up_last["adx_minus_di"]))

    downtrend = make_ohlcv(rows=140, slope=-0.2, start_price=50.0)
    downtrend_features = feature_pipeline.extract_features(downtrend)
    down_last = downtrend_features.iloc[-1]
    test("downtrend sma_20 negative", float(down_last["sma_20"]) < 0)
    test("downtrend sma_cross_20_50 = -1", float(down_last["sma_cross_20_50"]) == -1.0)
    test("downtrend -DI > +DI", float(down_last["adx_minus_di"]) > float(down_last["adx_plus_di"]))

    volume_spike = make_ohlcv(rows=120, slope=0.1)
    volume_spike.iloc[-1, volume_spike.columns.get_loc("volume")] = 500_000.0
    spike_features = feature_pipeline.extract_features(volume_spike)
    test("engineered volume spike > 1", float(spike_features.iloc[-1]["volume_spike"]) > 1.0)
    test("volume_ratio_prev responds to spike", float(spike_features.iloc[-1]["volume_ratio_prev"]) > 1.0)

    manual = make_ohlcv(rows=40, slope=0.5, start_price=20.0)
    manual_features = feature_pipeline.extract_features(manual)
    manual_close = manual["close"]
    manual_last = manual_features.iloc[-1]
    expected_ret_1d = manual_close.iloc[-1] / manual_close.iloc[-2] - 1.0
    expected_ret_5d = manual_close.iloc[-1] / manual_close.iloc[-6] - 1.0
    expected_ret_20d = manual_close.iloc[-1] / manual_close.iloc[-21] - 1.0
    test("ret_1d matches manual value", abs(float(manual_last["ret_1d"]) - expected_ret_1d) < 1e-12)
    test("ret_5d matches manual value", abs(float(manual_last["ret_5d"]) - expected_ret_5d) < 1e-12)
    test("ret_20d matches manual value", abs(float(manual_last["ret_20d"]) - expected_ret_20d) < 1e-12)
    test("day_of_week extracted from timestamp", float(manual_last["day_of_week"]) == float(manual.index[-1].dayofweek))
    test("month extracted from timestamp", float(manual_last["month"]) == float(manual.index[-1].month))

    section("FEATURE STORE")

    conn = sqlite3.connect(":memory:")
    conn = feature_pipeline.init_feature_store(":memory:")
    count_before = feature_pipeline.count_vectors(conn)
    test("empty feature store starts at zero", count_before == 0)

    valid_row = extracted.dropna().iloc[0]
    ts_1 = datetime(2026, 2, 3, 15, 30).isoformat()
    ts_2 = datetime(2026, 2, 4, 15, 30).isoformat()
    ts_3 = datetime(2026, 2, 5, 15, 30).isoformat()
    inserted_id = feature_pipeline.insert_feature_vector(conn, "TEST", ts_1, valid_row.values, target=1)
    test("insert_feature_vector returns row id", inserted_id > 0)
    test("count increments after insert", feature_pipeline.count_vectors(conn) == 1)

    X, y, meta = feature_pipeline.load_feature_matrix(conn)
    test("load_feature_matrix returns one training row", len(X) == 1)
    test("load_feature_matrix returns one target", y == [1])
    test("load_feature_matrix returns metadata", len(meta) == 1 and meta[0]["symbol"] == "TEST")
    test(
        "DB round trip preserves feature values",
        all(abs(a - b) < 1e-12 for a, b in zip(X[0], valid_row.values.tolist())),
    )

    feature_pipeline.insert_feature_vector(conn, "TEST", ts_2, valid_row.values, target=None)
    X2, y2, meta2 = feature_pipeline.load_feature_matrix(conn)
    test("rows with NULL target are excluded", len(X2) == 1 and len(y2) == 1 and len(meta2) == 1)

    partial_row = extracted.iloc[10].values
    feature_pipeline.insert_feature_vector(conn, "TEST", ts_3, partial_row, target=0)
    X3, y3, meta3 = feature_pipeline.load_feature_matrix(conn)
    test("rows with NaN features are excluded", len(X3) == 1 and y3 == [1])
    test("excluded NaN row does not leak metadata", len(meta3) == 1)

    updated = feature_pipeline.update_target(conn, "TEST", ts_2, 0)
    test("update_target updates exactly one row", updated == 1)
    X4, y4, _ = feature_pipeline.load_feature_matrix(conn)
    test("updated row becomes trainable", len(X4) == 2)
    test("updated target persisted", sorted(y4) == [0, 1])

    conn.close()

    print("\n" + "=" * 60)
    print(f"RESULT: {PASS} passed, {FAIL} failed")
    print("=" * 60)
    return PASS, FAIL, ERRORS


if __name__ == "__main__":
    _, fail, _ = run_tests()
    raise SystemExit(1 if fail else 0)
