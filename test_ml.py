"""ML engine smoke tests with dependency-aware assertions."""

from __future__ import annotations

import os
import tempfile

import numpy as np

import ml_engine

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


def run_tests() -> tuple[int, int, list[str]]:
    global PASS, FAIL, ERRORS
    PASS = 0
    FAIL = 0
    ERRORS = []

    print("=" * 60)
    print("  ML ENGINE TEST SUITE")
    print("=" * 60)

    trainer = ml_engine.MLModelTrainer()

    try:
        models = trainer.build_models()
        xgboost_available = True
    except ImportError as exc:
        models = None
        xgboost_available = False
        test("missing xgboost error is explicit", "xgboost" in str(exc).lower())

    predictor = ml_engine.EnsemblePredictor(model_path="missing-model-file.pkl")
    test("predictor not ready without artifact", predictor.is_ready() is False)
    test("classify_signal high prob => strong", ml_engine.classify_signal(0.9, dynamic_threshold=False) == "strong")
    test("classify_signal mid prob => medium", ml_engine.classify_signal(0.6, dynamic_threshold=False) == "medium")
    test("classify_signal low prob => weak", ml_engine.classify_signal(0.2, dynamic_threshold=False) == "weak")

    high, low = ml_engine.thresholds_from_predictions([0.1, 0.2, 0.3])
    test("small dynamic sample falls back to base thresholds", abs(high - 0.7) < 1e-12 and abs(low - 0.5) < 1e-12)

    validator = ml_engine.BacktestValidator()
    perfect = validator.evaluate([0, 1, 0, 1], [0, 1, 0, 1], [0.1, 0.9, 0.2, 0.8])
    test("perfect classifier accuracy == 1", perfect["accuracy"] == 1.0)
    test("perfect classifier precision == 1", perfect["precision"] == 1.0)
    test("perfect classifier recall == 1", perfect["recall"] == 1.0)
    test("perfect classifier f1 == 1", perfect["f1"] == 1.0)

    comparison = validator.compare_to_phase2(
        [0, 0, 1, 1],
        [0.1, 0.2, 0.8, 0.9],
        [40.0, 45.0, 50.0, 55.0],
    )
    test("compare_to_phase2 lift is positive", comparison["lift"] > 0)

    if xgboost_available and models is not None:
        test("build_models returns xgb", "xgb" in models)
        test("build_models returns rf", "rf" in models)
        test("build_models returns mlp", "mlp" in models)

        rng = np.random.RandomState(42)
        n_per_class = 20
        X = np.vstack(
            [
                rng.uniform(0.0, 0.3, size=(n_per_class, 3)),
                rng.uniform(0.7, 1.0, size=(n_per_class, 3)),
            ]
        )
        y = np.array([0] * n_per_class + [1] * n_per_class)
        trained = trainer.train(X, y, smote=False)
        test("train returns 3 fitted models", len(trained) == 3)

        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = os.path.join(tmpdir, "explosion_model.pkl")
            trainer.save(model_path, trained, metadata={"version": 1})
            payload = trainer.load(model_path)
            test("saved payload contains models", "models" in payload and len(payload["models"]) == 3)
            test("saved payload contains metadata", payload.get("metadata", {}).get("version") == 1)

            ready_predictor = ml_engine.EnsemblePredictor(model_path=model_path)
            test("predictor becomes ready from saved artifact", ready_predictor.is_ready() is True)
            prob = ready_predictor.predict_proba([0.88, 0.82, 0.91])
            test("predict_proba stays within [0,1]", 0.0 <= prob <= 1.0)

    # --- Constants ---
    test("MODEL_PATH constant", ml_engine.MODEL_PATH == "explosion_model.pkl")
    test("ENSEMBLE_WEIGHTS xgb weight", ml_engine.ENSEMBLE_WEIGHTS.get("xgb") == 3)
    test("ENSEMBLE_WEIGHTS rf weight", ml_engine.ENSEMBLE_WEIGHTS.get("rf") == 2)
    test("ENSEMBLE_WEIGHTS mlp weight", ml_engine.ENSEMBLE_WEIGHTS.get("mlp") == 1)

    # --- classify_signal exact boundaries (static mode) ---
    test("classify_signal 0.7 boundary => strong", ml_engine.classify_signal(0.7, dynamic_threshold=False) == "strong")
    test("classify_signal 0.5 boundary => medium", ml_engine.classify_signal(0.5, dynamic_threshold=False) == "medium")
    test("classify_signal just below low => weak", ml_engine.classify_signal(0.499, dynamic_threshold=False) == "weak")
    test("classify_signal 1.0 => strong", ml_engine.classify_signal(1.0, dynamic_threshold=False) == "strong")
    test("classify_signal 0.0 => weak", ml_engine.classify_signal(0.0, dynamic_threshold=False) == "weak")

    # --- thresholds_from_predictions percentile values ---
    dyn_high, dyn_low = ml_engine.thresholds_from_predictions(
        [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    )
    test("dynamic high percentile == 0.82", abs(dyn_high - 0.82) < 1e-9)
    test("dynamic low percentile == 0.595", abs(dyn_low - 0.595) < 1e-9)

    dyn_sample = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    test("dynamic classify above high => strong", ml_engine.classify_signal(0.9, recent_predictions=dyn_sample) == "strong")
    test("dynamic classify between low/high => medium", ml_engine.classify_signal(0.6, recent_predictions=dyn_sample) == "medium")
    test("dynamic classify below low => weak", ml_engine.classify_signal(0.5, recent_predictions=dyn_sample) == "weak")
    test("dynamic mode with no recent uses static thresholds", ml_engine.classify_signal(0.6, recent_predictions=None) == "medium")

    th_all_ones = ml_engine.thresholds_from_predictions([1.0] * 10)
    test("all-ones thresholds cap high at 0.95", abs(th_all_ones[0] - 0.95) < 1e-9)
    test("all-ones thresholds low == 1.0", abs(th_all_ones[1] - 1.0) < 1e-9)

    th_empty = ml_engine.thresholds_from_predictions([])
    test("empty predictions fallback high 0.7", abs(th_empty[0] - 0.7) < 1e-9)
    test("empty predictions fallback low 0.5", abs(th_empty[1] - 0.5) < 1e-9)

    th_nine = ml_engine.thresholds_from_predictions([0.9] * 9)
    test("9 predictions (<10) fallback to base", abs(th_nine[0] - 0.7) < 1e-9 and abs(th_nine[1] - 0.5) < 1e-9)

    th_const = ml_engine.thresholds_from_predictions([0.8] * 10)
    test("constant 0.8 thresholds collapse to 0.8", abs(th_const[0] - 0.8) < 1e-9 and abs(th_const[1] - 0.8) < 1e-9)

    # --- _maybe_apply_smote guards and resampling ---
    smote_X = np.vstack([np.full((20, 3), 0.1), np.full((80, 3), 0.9)])
    smote_y = np.array([0] * 20 + [1] * 80)
    sm_X, sm_y, sm_applied = ml_engine._maybe_apply_smote(smote_X, smote_y, enabled=True)
    test("smote applied on 0.25 minority", sm_applied is True)
    test("smote resampled X shape (160,3)", sm_X.shape == (160, 3))
    test("smote resampled y balanced [80,80]", list(np.bincount(sm_y)) == [80, 80])

    bal_X, bal_y, bal_applied = ml_engine._maybe_apply_smote(
        np.vstack([np.full((50, 3), 0.1), np.full((50, 3), 0.9)]),
        np.array([0] * 50 + [1] * 50),
        enabled=True,
    )
    test("smote skipped on balanced classes", bal_applied is False)
    test("smote balanced returns original X", bal_X.shape == (100, 3))

    off_X, off_y, off_applied = ml_engine._maybe_apply_smote(smote_X, smote_y, enabled=False)
    test("smote skipped when disabled", off_applied is False)
    test("smote disabled returns original X", off_X.shape == (100, 3))
    test("smote disabled preserves y distribution", list(np.bincount(off_y)) == [20, 80])

    single_X, single_y, single_applied = ml_engine._maybe_apply_smote(
        np.full((10, 3), 0.1), np.array([0] * 10), enabled=True
    )
    test("smote skipped on single class", single_applied is False)

    empty_X, empty_y, empty_applied = ml_engine._maybe_apply_smote(
        np.array([]).reshape(0, 3), np.array([]), enabled=True
    )
    test("smote skipped on empty y", empty_applied is False)

    # --- save/load roundtrip without training ---
    with tempfile.TemporaryDirectory() as tmpdir:
        bare_path = os.path.join(tmpdir, "bare.pkl")
        trainer.save(bare_path, {"xgb": "not-a-model"}, metadata={"trained": False})
        bare_payload = trainer.load(bare_path)
        test("save/load preserves models key", "models" in bare_payload)
        test("save/load preserves metadata", bare_payload.get("metadata", {}).get("trained") is False)

    # --- BacktestValidator edge cases ---
    imp = validator.evaluate([0, 1, 1, 0], [1, 1, 1, 0], [0.6, 0.7, 0.8, 0.4])
    test("imperfect accuracy == 0.75", abs(imp["accuracy"] - 0.75) < 1e-9)
    test("imperfect precision == 2/3", abs(imp["precision"] - 2.0 / 3.0) < 1e-9)
    test("imperfect recall == 1.0", abs(imp["recall"] - 1.0) < 1e-9)
    test("imperfect f1 == 0.8", abs(imp["f1"] - 0.8) < 1e-9)
    test("imperfect confusion matrix", imp["confusion_matrix"] == [[1, 1], [0, 2]])
    test("imperfect avg_probability == 0.625", abs(imp["avg_probability"] - 0.625) < 1e-9)

    no_pos = validator.evaluate([0, 0, 0], [1, 1, 1], [0.9, 0.8, 0.7])
    test("no positives precision zero_division 0", no_pos["precision"] == 0.0)
    test("no positives recall zero_division 0", no_pos["recall"] == 0.0)

    empty_prob = validator.evaluate([0, 1], [0, 1], [])
    test("empty probs avg_probability 0", empty_prob["avg_probability"] == 0.0)

    # --- compare_to_phase2 exact separation math ---
    test("compare_to_phase2 ml_separation == 0.7", abs(comparison["ml_separation"] - 0.7) < 1e-9)
    test("compare_to_phase2 phase2_separation == 10.0", abs(comparison["phase2_separation"] - 10.0) < 1e-9)
    test("compare_to_phase2 exact lift == 0.07", abs(comparison["lift"] - 0.07) < 1e-9)

    zero_old = validator.compare_to_phase2([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9], [50.0, 50.0, 50.0, 50.0])
    test("zero phase2 separation with ml signal => inf lift", zero_old["lift"] == float("inf"))

    both_zero = validator.compare_to_phase2([0, 0, 1, 1], [0.2, 0.2, 0.2, 0.2], [40.0, 40.0, 40.0, 40.0])
    test("both separations zero => lift 1.0", both_zero["lift"] == 1.0)

    # --- EnsemblePredictor not-ready guard ---
    try:
        predictor.predict_proba([0.88, 0.82, 0.91])
        test("predict_proba raises when not ready", False, "(no exception raised)")
    except RuntimeError as exc:
        test("predict_proba raises when not ready", True)
        test("predict_proba not-ready message explicit", "not ready" in str(exc).lower())

    if xgboost_available and models is not None:
        test("xgb model is XGBClassifier", models["xgb"].__class__.__name__ == "XGBClassifier")
        test("rf model is RandomForestClassifier", models["rf"].__class__.__name__ == "RandomForestClassifier")
        test("mlp model is MLPClassifier", models["mlp"].__class__.__name__ == "MLPClassifier")

    print("\n" + "=" * 60)
    print(f"RESULT: {PASS} passed, {FAIL} failed")
    print("=" * 60)
    return PASS, FAIL, ERRORS


if __name__ == "__main__":
    _, fail, _ = run_tests()
    raise SystemExit(1 if fail else 0)
