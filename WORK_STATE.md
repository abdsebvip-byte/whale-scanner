# Work State — Whale Scanner (Track 2 quick-scan)

**Last updated:** 2026-08-03
**Repo:** `C:\Users\sahar\Desktop\abdseb\whale-scanner`
**Environment:** Windows (win32) · Python 3.12.10 · sklearn 1.9.0 · xgboost 3.3.0

---

## Objective (approved spec)

Track 2 (Phase 3) — daily discovery of stocks that explode **50–100%+ per day**
via a regression ensemble on **max 5-day upside** (`max_change_5d`), ranked
**top-20**, gated by an honesty check: in backtest, the average max upside of
the **top-10 predicted** stocks must be **≥ 3–5×** a random stock's average.
No success is claimed without the gate.

Spec: `docs/superpowers/specs/2026-08-02-track2-ensemble-design.md` (fully read).

Key design facts:
- Scan universe = `$0.10 – $10.00` band only.
- Features = 23 canonical (`feature_pipeline.FEATURE_COLUMNS`) + 4 engine
  features (`price_at_scan`, `volume_ratio`, `gap_pct`, `short_percent`).
- Weights reused from `ml_engine.ENSEMBLE_WEIGHTS = {"xgb": 3, "rf": 2, "mlp": 1}`.
- Training matrix = `training_matrix_band.csv` (31 cols, 126 in-band rows,
  `TARGET_COLUMN = "max_change_5d"`). Aligned from JOIN of `feature_vectors`
  (399 rows) with `outcome_tracking` (898 rows); 126 in-band.
- Daily loop target (design §4.5): `run_real_scan.py` → engines score →
  `FeatureMatrix` builds vectors → model predicts max upside → top-20 emitted →
  `outcome_tracker` appends labels.

---

## COMPLETED

1. **`quick_scan.py` fully implemented (100 lines).** Functions:
   - `load_training_matrix()` → `(X=(126,27), y=(126,), feature_names=27)`
   - `train_regressor(X, y)` → weighted xgb/rf/mlp `VotingRegressor`
     (xgb `n_estimators=100, max_depth=4, lr=0.05`; rf `n_estimators=200, max_depth=6`;
     mlp `hidden_layer_sizes=(64,), early_stopping`; all `random_state=42`).
   - `backtest_honesty_gate(X, y, regressor, top_n=None, random_state=42)`
     → dict `{top10_avg, random_avg, ratio, passed}`; threshold `MIN_UPSIDE_RATIO=3.0`.
   - `rank_universe(X, symbols, regressor)` → list of `{symbol, predicted_upside}`
     descending.
   - `quick_scan(X, symbols, regressor, top_n=None)` → top `TOP_N_OUTPUT` (20).
   - Constants: `MIN_PRICE=0.10`, `MAX_PRICE=10.0`, `TOP_N_GATE=10`,
     `MIN_UPSIDE_RATIO=3.0`, `TOP_N_OUTPUT=20`.

2. **All test suites GREEN (no side effects):**
   - `test_quick_scan.py` → **45 passed, 0 failed** (RED loop done: was 21/7).
   - `test_features.py` → 59 passed, 0 failed.
   - `test_ml.py` → 70 passed, 0 failed.
   - Only `test_quick_scan.py` imports `quick_scan` (grep confirmed).

3. **`ml_engine.py` pinned (read):** `_require_xgboost` (line 29),
   `_maybe_apply_smote` (39), `MLModelTrainer.build_models` (64) builds
   **classifiers only**, `BacktestValidator.evaluate` is **binary-only** —
   neither reusable for the regression gate; hence `quick_scan.py` owns it.

---

## IN PROGRESS (next session)

**Task: wire `quick_scan` into the operational platform so it actually runs daily.**

Steps queued (only the first two reads are pending — nothing was written yet):
1. Read `predictive_scanner.py` (523 lines; `_predict_with_ensemble` at ~345)
   and `app.py` (web UI, ~167–758) to find integration points.
2. Read `feature_pipeline.py` (`FeatureMatrix` at line 53) and locate
   `run_real_scan.py` + `outcome_tracker` per design §4.5.
3. Decide wiring: likely a small runner (e.g. `run_quick_scan.py`) that:
   - loads today's universe (band `$0.10–$10.00`),
   - builds 27-feature vectors via `FeatureMatrix`,
   - trains/evaluates the honesty gate on `training_matrix_band.csv`,
   - ranks + emits top-20 to `predictions.json` (design §4.4).
4. Re-run full suite after any wiring changes.
5. Optional cleanup: `quick_scan.py` docstring line 3 still says
   "train GradientBoostingRegressor" — wording is stale vs the xgb/rf/mlp
   ensemble; fix when convenient.

---

## Key files

- `quick_scan.py` — implemented module (target of wiring).
- `test_quick_scan.py` — 45 GREEN tests.
- `ml_engine.py` — classifiers-only engine; `ENSEMBLE_WEIGHTS`, `MODEL_PATH`.
- `feature_pipeline.py` — `FEATURE_COLUMNS` (23), `FeatureMatrix` (line 53).
- `predictive_scanner.py` — v6.0 scanner (523 lines), `_predict_with_ensemble` (~345).
- `app.py` — web UI.
- `train_models.py` — standalone classifier trainer (not the regression path).
- `training_matrix_band.csv` — 31 cols, 126 in-band rows.
- `test_features.py`, `test_ml.py` — regression suites (both green).
- Spec: `docs/superpowers/specs/2026-08-02-track2-ensemble-design.md`.
- Databases: `scanner_history.db` (`outcome_tracking` 898 rows, `session_data`,
  `signals` 51, `explosions` 0), `feature_store.db` (`feature_vectors` 399).

## Not done / next time
- Platform wiring (above).
- Honesty-gate backtest result on real data (gate ratio value unknown yet).
- Any git commit — user has not requested commits.
