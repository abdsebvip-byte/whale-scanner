"""Integration checks for the Phase 3 Track 1 pipeline."""

from __future__ import annotations

import numpy as np
import pandas as pd

import feature_pipeline
import predictive_scanner
import signals

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


def make_ohlcv(rows: int = 140) -> pd.DataFrame:
    idx = pd.bdate_range("2026-01-05", periods=rows)
    close = 10 + np.linspace(0, 8, rows) + np.sin(np.arange(rows) / 8.0) * 0.2
    open_ = close - 0.05
    high = close + 0.3
    low = close - 0.25
    volume = np.full(rows, 100_000.0)
    volume[-1] = 300_000.0
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )


def run_tests() -> tuple[int, int, list[str]]:
    global PASS, FAIL, ERRORS
    PASS = 0
    FAIL = 0
    ERRORS = []

    print("=" * 60)
    print("  PHASE 3 INTEGRATION TEST SUITE")
    print("=" * 60)

    df = make_ohlcv()
    features = feature_pipeline.extract_features(df)
    valid = features.dropna()
    test("feature pipeline yields valid rows", not valid.empty)
    vector = [float(v) for v in valid.iloc[-1].tolist()]
    test("vector size matches canonical feature count", len(vector) == feature_pipeline.N_FEATURES)

    predictive_scanner._ENSEMBLE_PREDICTOR = None
    fallback_stock = {
        "change_1d": 1.0,
        "volume_ratio": 2.5,
        "rsi": 50,
        "cmf": 0.2,
        "bollinger_squeeze": 1,
        "obv_above_sma": 1,
        "volume_z_score": 1.8,
        "macd_diff": 0.2,
        "volume_build_days": 2,
        "price_position": 0.2,
    }
    fallback_score = predictive_scanner.calculate_explosion_score(fallback_stock)
    test("fallback path produces int score", isinstance(fallback_score, int))
    test("fallback path does not inject ml_prob", fallback_stock.get("ml_prob") is None)

    Dummy = type(
        "Dummy",
        (),
        {
            "is_ready": lambda self: True,
            "predict_proba": lambda self, feature_values: 0.82,
        },
    )
    predictive_scanner._ENSEMBLE_PREDICTOR = Dummy()
    ml_stock = {"ml_feature_vector": vector}
    ml_score = predictive_scanner.calculate_explosion_score(ml_stock)
    test("ML path converts probability to score", ml_score == 82)
    test("ML path stores ml_prob on stock", abs(ml_stock.get("ml_prob", 0.0) - 0.82) < 1e-12)

    saved = signals.generate_signals_from_predictions(
        [
            {
                "symbol": "INTG",
                "price": 12.34,
                "explosion_probability": ml_score,
                "ml_prob": 0.82,
                "volume_ratio": 2.0,
                "z_score": 1.2,
                "rsi": 54,
                "cmf": 0.12,
                "bollinger_squeeze": True,
                "obv_above_sma": True,
                "change_1d": 1.1,
            }
        ],
        source_scan_id=434343,
    )
    test("ML-backed signal is saved", saved == 1)
    active = signals.get_active_signals(limit=20)
    integration_rows = [row for row in active if row.get("symbol") == "INTG"]
    test("saved ML-backed signal is queryable", len(integration_rows) >= 1)
    if integration_rows:
        row = integration_rows[0]
        test("ML-backed signal exposes ml_prob", abs(float(row.get("ml_prob") or 0.0) - 0.82) < 1e-12)
        test("ML-backed signal level is actionable", row.get("signal_level") in {"STRONG_BUY", "BUY", "WATCH"})

    def rule_score(**overrides) -> int:
        stock = {
            "change_1d": 1.0,
            "volume_ratio": 0,
            "rsi": 50,
            "cmf": 0,
            "bollinger_squeeze": 1,
            "obv_above_sma": 0,
            "volume_z_score": 0.9,
            "macd_diff": -0.2,
            "volume_build_days": 0,
            "price_position": 0.1,
        }
        stock.update(overrides)
        return predictive_scanner.calculate_explosion_score(stock)

    NotReady = type(
        "NotReady",
        (),
        {
            "is_ready": lambda self: False,
            "predict_proba": lambda self, feature_values: 0.99,
        },
    )
    predictive_scanner._ENSEMBLE_PREDICTOR = NotReady()
    test(
        "ensemble not-ready returns None",
        predictive_scanner._predict_with_ensemble({"ml_feature_vector": vector}) is None,
    )
    test(
        "ensemble rejects missing feature vector",
        predictive_scanner._predict_with_ensemble({"price": 10}) is None,
    )
    predictive_scanner._ENSEMBLE_PREDICTOR = Dummy()
    test(
        "ready ensemble predicts again",
        abs(predictive_scanner._predict_with_ensemble({"ml_feature_vector": vector}) - 0.82) < 1e-12,
    )

    test("change_1d > MAX_CHANGE_1D caps at 0", rule_score(change_1d=9.0) == 0)
    test("change_1d > 5 caps at 0", rule_score(change_1d=6.0) == 0)
    test("change_1d > 3 applies -15", rule_score(change_1d=4.0) == rule_score() - 15)

    test("z>2.0 adds +18", rule_score(volume_z_score=2.1) == rule_score() + 18)
    test("z>1.5 adds +14", rule_score(volume_z_score=1.6) == rule_score() + 14)
    test("z>1.0 adds +8", rule_score(volume_z_score=1.1) == rule_score() + 8)
    test("z<=1.0 adds nothing", rule_score(volume_z_score=0.9) == rule_score())

    test("cmf>0.25 adds +20", rule_score(cmf=0.26) == rule_score() + 20)
    test("cmf>0.15 adds +15", rule_score(cmf=0.16) == rule_score() + 15)
    test("cmf>0.08 adds +10", rule_score(cmf=0.09) == rule_score(cmf=0.04) + 5)
    test("cmf>0.03 adds +5", rule_score(cmf=0.04) == rule_score() + 5)
    test("cmf<-0.1 applies -15", rule_score(cmf=-0.2) == rule_score() - 15)

    test(
        "rsi in [40,65] adds +12",
        rule_score(rsi=65) == rule_score() and rule_score(rsi=66) == rule_score() - 12,
    )
    test("rsi>75 applies -10", rule_score(rsi=80) == rule_score() - 22)
    test("rsi<25 applies -5", rule_score(rsi=20) == rule_score() - 17)

    test(
        "volume_build>=3 adds +12",
        rule_score(volume_build_days=3) == rule_score(volume_build_days=2) + 5,
    )

    bull = rule_score(
        volume_ratio=5,
        volume_z_score=3.0,
        cmf=0.3,
        obv_above_sma=1,
        macd_diff=0.2,
        volume_build_days=5,
        change_1d=0.5,
        rsi=50,
        price_position=0.1,
        bollinger_squeeze=1,
    )
    test("score clamps at 99", bull == 99)
    bear = rule_score(
        change_1d=4.0,
        rsi=90,
        cmf=-0.5,
        price_position=0.9,
        bollinger_squeeze=0,
    )
    test("score clamps at 0", bear == 0)

    test("classify STRONG_BUY >=70", signals.classify_signal(75, {})[0] == "STRONG_BUY")
    test("classify BUY >=55", signals.classify_signal(60, {})[0] == "BUY")
    test("classify WATCH >=40", signals.classify_signal(45, {})[0] == "WATCH")
    test("classify IGNORE <40", signals.classify_signal(10, {})[0] == "IGNORE")
    lifts = {"rsi": {"lift": 10, "total": 10, "accuracy": 0.8, "baseline": 0.5}}
    level, label, adjusted, count, lst = signals.classify_signal(50, lifts)
    test(
        "classify applies lift bonus and tracks active indicators",
        adjusted == 54 and count == 1 and lst == ["rsi"],
    )

    print("\n" + "=" * 60)
    print(f"RESULT: {PASS} passed, {FAIL} failed")
    print("=" * 60)
    return PASS, FAIL, ERRORS


if __name__ == "__main__":
    _, fail, _ = run_tests()
    raise SystemExit(1 if fail else 0)
