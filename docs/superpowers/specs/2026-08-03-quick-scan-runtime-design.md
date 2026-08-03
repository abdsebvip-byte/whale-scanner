# Quick-Scan Runtime (Track 2 §4.5 Daily Loop) — Design

**Date:** 2026-08-03
**Phase:** Phase 3, Track 2, runtime wiring
**Status:** Approved (design complete; awaiting execution plan)

## 1. Objective

Wire the quick scan (`quick_scan.py` regression ensemble) into the daily
operational loop defined by §4.5 of the Track 2 design: each trading session,
scan the `$0.10 – $10.00` universe, build a 27-feature vector per stock,
predict **max upside over the next 5 trading days**, pass the honesty gate,
emit the top-20 watchlist, and log every scan into `outcome_tracker` for the
self-learning loop.

The deliverable is a **ranked list with predicted max upside and a pass/fail
gate** — never a hard claim that specific stocks will explode.

### 1.1 How the runtime composes

A new runner `run_quick_scan.py` orchestrates six phases:

| # | Phase | Source | Output |
|---|-------|--------|--------|
| 1 | Universe | `run_real_scan.get_stock_list()` | ~7000 symbols |
| 2 | Feature extraction | `run_real_scan.analyze_stock()` → `FeatureMatrix` | 27 numbers / stock |
| 3 | Training | `quick_scan.train_regressor()` on `training_matrix_band.csv` | fitted `VotingRegressor` |
| 4 | Honesty gate | `quick_scan.backtest_honesty_gate()` | `{top10_avg, random_avg, ratio, passed}` |
| 5 | Ranking | `quick_scan.rank_universe()` | top-20 by `predicted_upside` |
| 6 | Logging | `predictions.json` + `outcome_tracker` | self-learning input |

**Design rationale:** `run_real_scan` already owns universe + analysis, and
`quick_scan.py` already owns training / gate / ranking. The runner composes
them with a small adapter. The legacy v6.0 scanner (`predictive_scanner.py`)
keeps running in parallel unchanged — the two systems share the same output
files, so rollback is a file-level concern, not a code revert.

## 2. Decisions (approved)

1. **Training data:** train only on `training_matrix_band.csv` (126 in-band
   rows, 27 features + `max_change_5d`). No live-feature alignment this round.
2. **Separate runner:** new `run_quick_scan.py`; `predictive_scanner.py` v6.0
   is untouched.
3. **Unified dashboard:** `app.py` shows both systems on one page —
   quick-scan rows carry `predicted_upside`, v6.0 rows carry
   `explosion_probability`.
4. **Gate failure still writes output:** when the honesty gate fails
   (`ratio < 3.0`), the scan **still writes** `predictions.json` with
   `"passed": false`. We never lose the operational snapshot.
5. **Scope band:** `$0.10 – $10.00` (matches `quick_scan.MIN_PRICE` /
   `MAX_PRICE` and the v6.0 constants).

## 3. Data Flow

### 3.1 Feature vector (27 features)

- The 23 canonical features from `feature_pipeline.FEATURE_COLUMNS`
  (`volatility` … `ret_20d`).
- Plus 4 engine features from `run_real_scan.analyze_stock()`:
  1. `price_at_scan`
  2. `volume_ratio`
  3. `gap_pct`
  4. `short_percent`
- Full column list: `FEATURE_COLUMNS_FULL = FEATURE_COLUMNS + ENGINE_FEATURES`
  (27), rendered **alphabetically** in the DataFrame so the vector layout is
  deterministic regardless of composition order.
- Target: `TARGET_COLUMN = "max_change_5d"` (continuous 5-day max upside).

### 3.2 `predictions.json` (new wrapper)

```json
{
  "generated_at": "...",
  "session": "regular",
  "gate": { "top10_avg": 0.0, "random_avg": 0.0, "ratio": 0.0, "passed": false },
  "predictions": [
    { "symbol": "...", "predicted_upside": 0.0, "price_at_scan": 0.0,
      "volume_ratio": 0.0, "gap_pct": 0.0, "short_percent": 0.0 }
  ]
}
```

- Wrapper remains compatible with `app.load_predictions()` (reads
  `{"predictions": [...]}`).
- quick-scan rows are distinguished by `predicted_upside`; v6.0 rows keep
  `explosion_probability`. No collision on the shared page.

### 3.3 `outcome_tracker` linkage

- Insert order matters: **`session_data` first, then `outcome_tracking`**
  (FK `prediction_id → session_data(id)`).
- New quick-scan rows are written with `max_change_5d = NULL` and the mapped
  `session_type`; the existing tracking loop backfills `price_1d/3d/5d`,
  `change_1d/3d/5d`, `max_change_5d`, `min_change_5d`, `exploded`,
  `touched_stop` on later runs.

### 3.4 `app.py` plan

- `build_df(preds)`: add quick-scan columns only when present —
  `predicted_upside, price_at_scan, volume_ratio, gap_pct, short_percent`;
  v6.0 columns are left untouched for legacy rows.
- `pred_row_html`: color `predicted_upside` — `≥5%` → `#34d399`, `≥3%` →
  `#60a5fa`, `≥1%` → `#fbbf24`, else `#64748b`.
- Status line above the table (next to the current session label): gate result
  `passed ✓ / ✗` with the measured ratio.

## 4. Honesty Gate (unchanged from Track 2)

> Average max upside of **top-10** predicted stocks **≥ 3×** the average max
> upside of a **random** stock over the same period.

- Computed by `backtest_honesty_gate(X, y, regressor)` → `{top10_avg,
  random_avg, ratio, passed}`.
- On failure the scan still writes output with `passed: false` (Decision 4) —
  the flag makes it obvious the list is unvalidated, never hidden.

## 5. Model

- `VotingRegressor` of three base regressors, weights from
  `ml_engine.ENSEMBLE_WEIGHTS` (default 1 per engine, `xgb: 3, rf: 2, mlp: 1`):
  - xgboost: 100 estimators, `max_depth=4`, `learning_rate=0.05`
  - random forest: 200 estimators, `max_depth=6`
  - MLP: single hidden layer `(64,)`, `max_iter=1000`, early stopping
- `random_state=42` everywhere for reproducibility.
- `rank_universe` sorts `argsort(-predicted)` descending →
  `[{symbol, predicted_upside}]`.

## 6. Honest Expectations

- Explosive cases (≥50%) are rare (7 of 898 ≈ 0.8% in the 08-02 data).
- The model starts conservative — better than random, often below 50%+ in the
  first weeks.
- Performance climbs as labeled rows accumulate via `outcome_tracker`.
- The 3× gate is the objective arbiter; `passed: false` is reported openly
  whenever the gate fails.

## 7. Explicit Non-Goals

- No changes to `predictive_scanner.py` v6.0.
- No binary "will explode" classification as the quick-scan deliverable.
- No live feature alignment from `feature_store.db` this round (Decision 1).
- No multi-track synthesis, live-trading execution, or position sizing.

## 8. Verification

- Existing regression suite must stay green: `test_quick_scan.py` (45),
  `test_features.py` (59), `test_ml.py` (70).
- New runner is exercised via a dry-run smoke test (scan a small universe,
  assert `predictions.json` written with a `gate` block and top-20 list).
