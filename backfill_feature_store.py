"""Backfill labeled feature vectors from outcome_tracking into feature_store.db."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import sqlite3

from data_sources import DataSourceManager
from feature_pipeline import extract_features, init_feature_store, insert_feature_vector

SOURCE_DB = "scanner_history.db"


def _parse_scan_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def _load_outcomes() -> list[tuple[str, str, int]]:
    conn = sqlite3.connect(SOURCE_DB)
    rows = conn.execute(
        """
        SELECT symbol, scan_time, exploded
        FROM outcome_tracking
        WHERE symbol IS NOT NULL AND scan_time IS NOT NULL AND exploded IS NOT NULL
        ORDER BY scan_time
        """
    ).fetchall()
    conn.close()
    return [(str(symbol), str(scan_time), int(exploded)) for symbol, scan_time, exploded in rows]


def _existing_keys(conn: sqlite3.Connection) -> set[tuple[str, str]]:
    rows = conn.execute("SELECT symbol, timestamp FROM feature_vectors").fetchall()
    return {(str(symbol), str(timestamp)) for symbol, timestamp in rows}


def backfill() -> tuple[int, int, int]:
    outcomes = _load_outcomes()
    manager = DataSourceManager()
    store = init_feature_store()
    seen = _existing_keys(store)

    inserted = 0
    skipped = 0
    failed = 0

    cache: dict[str, pd.DataFrame | None] = {}
    for symbol, scan_time, exploded in outcomes:
        key = (symbol, scan_time)
        if key in seen:
            skipped += 1
            continue

        if symbol not in cache:
            cache[symbol] = manager.get_historical_data(symbol, period="6mo")
        hist = cache[symbol]
        if hist is None or len(hist) < 60:
            failed += 1
            continue

        try:
            if isinstance(hist.columns, pd.MultiIndex):
                hist.columns = hist.columns.get_level_values(0)
            normalized = hist.rename(columns=str.lower)
            features = extract_features(normalized)
            valid = features.dropna()
            if valid.empty:
                failed += 1
                continue

            scan_dt = _parse_scan_time(scan_time)
            eligible = valid.loc[valid.index <= pd.Timestamp(scan_dt)]
            if eligible.empty:
                failed += 1
                continue

            vector = eligible.iloc[-1].tolist()
            insert_feature_vector(store, symbol, scan_time, vector, target=exploded)
            seen.add(key)
            inserted += 1
        except Exception:
            failed += 1

    store.close()
    return inserted, skipped, failed


def main() -> int:
    inserted, skipped, failed = backfill()
    print(f"inserted={inserted} skipped={skipped} failed={failed}")
    return 0 if inserted > 0 or skipped > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
