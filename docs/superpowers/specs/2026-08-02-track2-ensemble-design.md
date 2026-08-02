# Track 2: ML Ensemble for Daily Explosive-Stock Detection — Design

**Date:** 2026-08-02
**Phase:** Phase 3, Track 2
**Status:** Proposed (pending user approval)

## 1. Objective

Daily discovery of stocks that explode **50–100%+ per day**. Extend the ML
ensemble (`ml_engine.py`) from the current single-engine signal path across the
four detection engines of `full_market_whale_scanner.py` (Short Squeeze, Volume
Anomaly, Price Spike, Insider Buying).

Success is not a one-time result: the system must be **repeatable every day**
and **measurably better than random** in backtest before it is trusted.

## 2. Constraints & Non-Negotiables

- **Honesty gate:** In backtest, the average max upside of the top-10 predicted
  stocks must be ≥ **3–5x** the average of a random stock in the same period.
  Only if this holds do we upgrade from Approach 1 (direct regression) to
  Approach 3 (two-stage hybrid). If it does not hold, we do not claim success.
- **No implementation before this design is approved.**
- **Scan universe = $10 and under:** explosions concentrate in low-priced
  stocks; high-priced stocks produce only ordinary/small moves. The scan must
  run on the `$1.00 – $10.00` band (matching `predictive_scanner.py` constants
  `MIN_PRICE = 1.0`, `MAX_PRICE = 10.0`). Do not include higher-priced stocks
  in the explosive-detection universe.
- **No fake positives:** the deliverable is a ranked list with predicted max
  upside and a pass/fail gate on the backtest metric — never a hard claim that
  specific stocks will explode.

## 3. Data Inventory (measured, not assumed)

| Source | Rows | Target field | Notes |
|---|---|---|---|
| `scanner_history.db` → `outcome_tracking` | 898 | `max_change_5d` (5-day max upside) | avg 6.36%, max +283%, min −0.07%; rows ≥10% = 106, ≥30% = 16, ≥50% = 7, ≥100% = 5; 50 rows flagged `exploded` |
| `scanner_history.db` → `session_data` | 898 | — | scan snapshot features per session |
| `scanner_history.db` → `signals` | 51 | — | signal-level store |
| `scanner_history.db` → `explosions` | 0 | — | empty; not a target source |
| `feature_store.db` → `feature_vectors` | 399 | `target` (binary 0/1) | avg 0.123, max 1.0; **binary, not suitable as regression target**; single timestamp 2026-07-27 |

**Conclusion:** `outcome_tracking.max_change_5d` is the correct regression
target (fully populated, 898 labeled rows). `feature_vectors.target` is a
binary classification target from a single timestamp — not usable for the
regression in Approach 1.

## 4. Approach 1 — Direct Regression on Max Upside

### 4.1 Training target
- Continuous `max_change_5d` from `outcome_tracking` (5-day horizon now).
- **Upgrade path:** move to a 10-day horizon (`max_change_10d`) once
  `outcome_tracking` accumulates 10-day labels, matching the radar horizon.

### 4.2 Features (input vector)
- The existing **23 features** from `feature_pipeline.FEATURE_COLUMNS`.
- Plus **4 engine features**:
  1. Short interest ratio (Short Squeeze engine)
  2. Volume Z-score (Volume Anomaly engine)
  3. Gap percentage (Price Spike engine)
  4. Insider buying signal (Insider Buying engine)
- Feature alignment at scan time via `FeatureMatrix` in `feature_pipeline.py`.

### 4.3 Model
- Regression ensemble reusing `ml_engine.MLModelTrainer` weights
  (`xgb: 3, rf: 2, mlp: 1`), but configured for **regression output**
  (predicted max upside) rather than binary classification.
- `BacktestValidator` from `ml_engine.py` reused for the gate metric.

### 4.4 Output
- Rank all scanned stocks **descending by predicted max upside**.
- Surface the **top 20** each day as the actionable watchlist.
- Store predictions in `predictions.json` alongside per-stock predicted upside.

### 4.5 Daily loop
- `run_real_scan.py` → engines score → `FeatureMatrix` builds vectors →
  model predicts max upside → top-20 emitted → `outcome_tracker` appends
  `max_change_5d` for the self-learning loop.

## 5. Success Gate (backtest)

> Average max upside of **top-10** predicted stocks **≥ 3–5×** the average max
> upside of a **random** stock over the same period.

- If passed → proceed to **Approach 3** (two-stage hybrid: coarse rank then
  fine regression on the top candidates).
- If not passed → keep iterating on features/horizon/model; do **not** upgrade.

## 6. Data-Readiness Decision (adopted recommendation)

- If directed rows (outcome-labeled vectors aligned with features) **≥ 100**:
  start the quick scan on current data immediately.
- Otherwise: first build the **data-collection loop** (daily scans appending
  labeled rows) until ≥ 100 rows, then train.

Current state: 898 outcome rows exist; the binding question is how many can be
aligned with a full 23+4 feature vector. The design assumes alignment is
feasible for the majority; if not, the data-collection loop runs first.

## 7. Honest Expectations

- Explosive cases (≥50%) are rare in the current data (7 of 898 ≈ 0.8%).
- The model will start **conservative** — consistently "better than random,"
  often below the 50%+ threshold in the first month.
- Performance climbs as explosive cases accumulate each day via `self_learning`.
- The 3–5x gate is the objective arbiter; no success is claimed without it.

## 8. Explicit Non-Goals

- No binary "will explode" classification as the primary deliverable (that is
  Approach 2 and was rejected).
- No direct 10-day horizon until 10-day labels exist.
- No hard predictions of specific symbols as guaranteed movers.

## 9. Out of Scope (future tracks)

- Multi-track synthesis, live-trading execution, position sizing.
