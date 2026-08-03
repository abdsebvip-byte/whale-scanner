# Plan — Quick-Scan Runtime (Track 2 §4.5 Daily Loop)

**Date:** 2026-08-03
**Design doc:** `docs/superpowers/specs/2026-08-03-quick-scan-runtime-design.md`
**Status:** Approved design → this execution plan
**Goal:** Wire the quick scan (`quick_scan.py` regression ensemble) into the daily operational loop: each trading session, scan the `$0.10 – $10.00` universe, build a 27-feature vector per stock, predict **max upside over the next 5 trading days**, pass the honesty gate, emit the top-20 watchlist, and log every scan into `outcome_tracker` for the self-learning loop.

## Scope Check

Single coherent spec (`2026-08-03-quick-scan-runtime-design.md`). No split needed — six phases compose into one new runner plus dashboard touches. All components already exist and are tested; this plan adds the orchestration adapter and a testable smoke path.

## Architecture

```
run_real_scan.py ──get_stock_list()──> universe (~7000, band $0.10–$10.00)
run_real_scan.py ──analyze_stock()──> 27-feature vector / stock (23 canonical + 4 engine)
quick_scan.py   ──train_regressor()──> fitted VotingRegressor (xgb:3, rf:2, mlp:1)
quick_scan.py   ──backtest_honesty_gate()──> {top10_avg, random_avg, ratio, passed}
quick_scan.py   ──rank_universe()──> top-20 by predicted_upside
new runner     ──> predictions.json (always written, gate.passed flag)
new runner     ──> session_data (insert first) → outcome_tracking (FK) [self-learning]
app.py         ──load_predictions()──> unified dashboard (quick-scan + v6.0 rows)
```

Legacy `predictive_scanner.py` v6.0 is **untouched**; it shares the same output files, so rollback is file-level.

## Dependencies

```
feature_pipeline.py (FEATURE_COLUMNS, 23)
run_real_scan.py    (get_stock_list, analyze_stock, constants)
ml_engine.py        (ENSEMBLE_WEIGHTS)        ─┐
quick_scan.py       (train/gate/rank)          ─┴──> run_quick_scan.py (NEW)
outcome_tracker.py  (init_tracking_db, insert_row) ─> scanner_history.db
app.py              (load_predictions, build_df, pred_row_html)
training_matrix_band.csv (126 in-band rows)
```

- Steps 1–3 (feature adapter + runner skeleton + training/gate/rank wiring) are self-contained; ship as a unit.
- Step 4 (logging + FK order) depends on 1–3.
- Step 5 (app.py dashboard) depends on 1–4.
- Step 6 (dry-run smoke verification) depends on everything.

## File map

- **NEW** `run_quick_scan.py` — one responsibility: orchestrate the six phases; no model logic of its own (delegates to `quick_scan`/`run_real_scan`/`outcome_tracker`).
- **NEW** `test_run_quick_scan.py` — lightweight PASS/FAIL suite matching repo style (`test(name, condition, detail)`, `section(title)`, `run_tests() -> (PASS, FAIL, errors)`), no pytest dependency.
- **EDIT** `app.py` — quick-scan columns only when present; color `predicted_upside`; gate status line.

## Steps

### Step 1 — Feature adapter (in `run_quick_scan.py`, NEW)

**Task 1.1 — module skeleton + constants.**
```python
"""Quick-scan runtime (Track 2 §4.5 daily loop). Composes run_real_scan (universe +
analysis) with quick_scan (training / honesty gate / ranking) and outcome_tracker
(logging). The legacy v6.0 predictive_scanner is untouched and shares the output files."""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

import feature_pipeline
import outcome_tracker
import quick_scan
import run_real_scan

PREDICTIONS_PATH = Path(__file__).parent / "predictions.json"
SESSION_TYPE = "quick_scan"
```
Tests: module imports cleanly; `PREDICTIONS_PATH` basename is `predictions.json`; `SESSION_TYPE == "quick_scan"`.

**Task 1.2 — `build_feature_row(result) -> list[float]` adapter.**
Turns one `run_real_scan.analyze_stock()` result (dict with OHLCV keys + `price_at_scan`, `volume_ratio`, `gap_pct`, `short_percent`) into the 27-vector in `quick_scan.FEATURE_COLUMNS_FULL` order (23 canonical `feature_pipeline.FEATURE_COLUMNS` then 4 engine features).

- Use `feature_pipeline.extract_features(df)` to get the 23 canonical features from the OHLCV rows; take the **last row** (latest bar).
- Engine features come straight from the result dict.
- Guard: missing column → `ValueError` (reuse `feature_pipeline._require_columns` semantics). Missing engine feature → default `0.0`.
- Return `list[float]` length 27.

Tests: on a synthetic result with a small OHLCV frame, returns 27 floats; first 23 names match `feature_pipeline.FEATURE_COLUMNS`; last 4 are `[price_at_scan, volume_ratio, gap_pct, short_percent]`; raises `ValueError` when an OHLCV column is absent.

**Verification:** `python -c "import run_quick_scan"` succeeds; `python test_run_quick_scan.py` green.

### Step 2 — Runner orchestration core

**Task 2.1 — `get_universe() -> list[str]`.**
```python
def get_universe() -> list[str]:
    return [s for s in run_real_scan.get_stock_list() if run_real_scan.MIN_PRICE <= 0.0 < run_real_scan.MAX_PRICE]
```
Actually: delegate directly to `run_real_scan.get_stock_list()` and return it unchanged (band filtering already enforced by `get_stock_list` constants + per-symbol guards). Keep the function as the thin seam so tests can monkeypatch.

Tests: returns a list of `str`; delegates to `run_real_scan.get_stock_list`.

**Task 2.2 — `analyze_universe(symbols, progress=None) -> list[dict]`.**
Runs `run_real_scan.analyze_stock(symbol)` per symbol; skips `None` returns and results missing the 4 engine features; preserves symbol on the result. Accepts optional `progress` callable `(done, total) -> None` for CLI feedback.

Tests: with a fake `analyze_stock` (monkeypatched), keeps only valid results, carries symbol, calls progress with correct counts.

**Task 2.3 — `train_and_gate(X, y, regressor=None) -> tuple[VotingRegressor, dict]`.**
- Load matrix: `quick_scan.load_training_matrix()` → `X, y, _`.
- Train: `regressor = regressor or quick_scan.train_regressor(X, y)`.
- Gate: `quick_scan.backtest_honesty_gate(X, y, regressor)`.
- Return `(regressor, gate)`.
- Wrap training in `try/except ImportError` → exit with clear message (xgb missing).

Tests: returns fitted regressor + gate dict with keys `top10_avg, random_avg, ratio, passed`; deterministic with fixed seed.

**Task 2.4 — `rank(X_matrix, symbols, regressor) -> list[dict]`.**
Delegates to `quick_scan.rank_universe(X, symbols, regressor)` (already sorted descending by `predicted_upside`); returns top `quick_scan.TOP_N_OUTPUT` (20).

Tests: length ≤ 20; entries carry `symbol` + `predicted_upside`; sorted descending.

### Step 3 — CLI entry + predictions.json

**Task 3.1 — `main(argv=None) -> int`.**
Flow:
1. `get_universe()`; print count.
2. `analyze_universe(...)` with progress; build `np.array` of 27-vectors + `symbols` list (aligned, only rows with all 27).
3. `train_and_gate(...)`.
4. `rank(...)`.
5. `write_predictions(ranked, gate)`.
6. `log_scan(ranked, gate)` (Step 4).
7. Return `0` (success even on gate failure — Decision 4) or non-zero on hard error.

Parse optional flags:
- `--limit N` — cap universe size for smoke tests (default: all).
- `--no-log` — skip outcome_tracker write (smoke).
- `--seed N` — pass `random_state` to gate (default 42).

**Task 3.2 — `write_predictions(ranked, gate, path=PREDICTIONS_PATH) -> Path`.**
```python
payload = {
    "generated_at": datetime.now().isoformat(),
    "session": SESSION_TYPE,
    "gate": {k: float(gate[k]) for k in ("top10_avg", "random_avg", "ratio")} | {"passed": bool(gate["passed"])},
    "predictions": [{"symbol": r["symbol"], "predicted_upside": float(r["predicted_upside"]),
                     "price_at_scan": float(r.get("price_at_scan", 0.0)),
                     "volume_ratio": float(r.get("volume_ratio", 0.0)),
                     "gap_pct": float(r.get("gap_pct", 0.0)),
                     "short_percent": float(r.get("short_percent", 0.0))} for r in ranked],
}
```
Always writes — including when `gate["passed"] is False`. Returns the path. Writes atomically (tmp then `os.replace`).

Tests: file exists after call; JSON parses; wrapper has `generated_at`, `session`, `gate`, `predictions`; `gate.passed` is bool and equals input; `predictions` list length matches `ranked`; rows contain the 5 quick-scan keys.

**Verification:** `python run_quick_scan.py --limit 5 --no-log` prints universe count + gate verdict and writes `predictions.json`.

### Step 4 — outcome_tracker logging (FK order)

**Task 4.1 — `log_scan(ranked, gate, conn=None) -> None`.**
Insert order matters: **`session_data` first, then `outcome_tracking`** (FK `prediction_id → session_data(id)`).

- `outcome_tracker.init_tracking_db(conn=conn)` ensures both tables.
- For each top-20 row: INSERT into `session_data` (reuse the column set used by `predictive_scanner.py` at its INSERT — `scan_time`, `session_type`, `symbol`, `price`, `volume`, `volume_ratio`, `gap_pct`, `short_percent`, `float_shares`, `anomaly_score`, plus `session_type = SESSION_TYPE`; engine features that are absent default 0.0), then grab `lastrowid` and INSERT into `outcome_tracking` with `prediction_id = lastrowid`, `max_change_5d = NULL`, `last_checked = now`.
- Honor gate by still logging rows (the tracking loop backfills outcomes regardless); store `gate` ratio in the `session_data` row if the schema has a fitting column, else skip.
- `conn` optional — default create/commit on the module-level `DB_PATH`; support `conn=None` to let tests pass an in-memory connection.

Tests (in-memory sqlite): both tables exist after call; `session_data` count == `len(ranked)`; `outcome_tracking` count == `len(ranked)`; each `prediction_id` matches a `session_data.id` (FK integrity); `max_change_5d` is NULL; `session_type == "quick_scan"`.

**Verification:** `python run_quick_scan.py --limit 5` runs end-to-end and both tables get rows for the 5 scanned symbols (inspect via `sqlite3 scanner_history.db "SELECT COUNT(*) FROM outcome_tracking;"`).

### Step 5 — app.py dashboard

**Task 5.1 — `build_df(preds)` quick-scan columns.**
Only add `predicted_upside, price_at_scan, volume_ratio, gap_pct, short_percent` when present in the rows (v6.0 rows keep `explosion_probability` untouched). Fill missing with `None`.

**Task 5.2 — `pred_row_html` color for `predicted_upside`.**
`≥5% → #34d399`, `≥3% → #60a5fa`, `≥1% → #fbbf24`, else `#64748b` (same pattern as existing probability coloring).

**Task 5.3 — status line.**
Above the table, next to the session label: `gate passed ✓ / ✗` with the measured `ratio` (read from the `gate` block of `predictions.json`).

Tests: with a payload containing both quick-scan rows and v6.0 rows, `build_df` includes all 5 quick-scan columns and legacy columns; color function maps thresholds correctly.

**Verification:** `streamlit run app.py` loads without error; page shows quick-scan rows with `predicted_upside` and the gate status line.

### Step 6 — Dry-run smoke + regression gate

**Task 6.1 — `smoke` path.**
`python run_quick_scan.py --limit 5` (real network, small universe) and `python run_quick_scan.py --limit 5 --no-log` (no DB writes). Assert exit 0, `predictions.json` written with `gate` block and ≤20 predictions.

**Task 6.2 — full regression suite.**
```bash
python test_features.py
python test_quick_scan.py
python test_ml.py
python test_run_quick_scan.py
```
All green (existing suites stay at 59 / 45 / 70; new suite ≥ 15 tests).

## Honesty / Non-Goals (from design, enforced in code)

- Never a hard "will explode" claim — output is `predicted_upside` + gate flag.
- `predictive_scanner.py` v6.0 unchanged.
- No live-feature alignment from `feature_store.db` this round (Decision 1).
- No multi-track synthesis, live-trading execution, or position sizing.

## Rollback

- Delete `run_quick_scan.py` + `test_run_quick_scan.py`, revert `app.py` hunks; `predictions.json` / `scanner_history.db` rows are data (keep) — legacy scanner resumes writing the same files on its own schedule.

## Commits

Frequent, one logical unit each, matching repo history style (see `git log`):
1. `feat: add quick-scan runtime runner (run_quick_scan.py) + feature adapter` (Steps 1–3)
2. `feat: log quick-scan predictions to outcome_tracker with FK order` (Step 4)
3. `feat: show quick-scan rows and gate status in app.py` (Step 5)
4. `test: quick-scan runtime test suite + dry-run smoke` (Step 6)

## Verification Summary

| Check | Command | Expect |
|-------|---------|--------|
| New suite | `python test_run_quick_scan.py` | ≥15 PASS, 0 FAIL |
| Existing suites | `python test_features.py && python test_quick_scan.py && python test_ml.py` | 59 / 45 / 70 PASS, 0 FAIL |
| Dry run | `python run_quick_scan.py --limit 5 --no-log` | exit 0, `predictions.json` written |
| Full run | `python run_quick_scan.py` | exit 0, top-20 in `predictions.json`, DB rows logged |
| Dashboard | `streamlit run app.py` | quick-scan rows + gate line render |
