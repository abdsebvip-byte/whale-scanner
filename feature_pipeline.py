"""
feature_pipeline.py
===================

Canonical feature engineering pipeline for the explosion-detection stack.
Extracts a stable ordered feature vector from OHLCV data and provides a
lightweight sqlite feature store for later model training.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

import numpy as np
import pandas as pd
import ta

WINDOW = 20
LOOKBACK = 10
FEATURE_STORE_PATH = "feature_store.db"

FEATURE_COLUMNS: list[str] = [
    "volatility",
    "volume_spike",
    "price_change",
    "range_pct",
    "volume_ratio_prev",
    "rsi",
    "macd_line",
    "macd_signal",
    "macd_hist",
    "macd_cross",
    "sma_20",
    "sma_50",
    "sma_cross_20_50",
    "ema_20_50_cross",
    "adx",
    "adx_plus_di",
    "adx_minus_di",
    "atr_pct",
    "day_of_week",
    "month",
    "ret_1d",
    "ret_5d",
    "ret_20d",
]
N_FEATURES: int = len(FEATURE_COLUMNS)


@dataclass(frozen=True)
class FeatureMatrix:
    X: list[list[float]]
    y: list[int]
    meta: list[dict[str, str]]


def _require_columns(df: pd.DataFrame) -> None:
    required = {"open", "high", "low", "close", "volume"}
    missing = required.difference({str(col).lower() for col in df.columns})
    if missing:
        raise ValueError(f"Missing OHLCV columns: {sorted(missing)}")


def _normalize_ohlcv_columns(df: pd.DataFrame) -> pd.DataFrame:
    renamed = {}
    for column in df.columns:
        key = str(column).strip().lower()
        if key in {"open", "high", "low", "close", "volume", "timestamp"}:
            renamed[column] = key
    normalized = df.rename(columns=renamed)
    _require_columns(normalized)
    return normalized


def _compute_rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    avg_loss_safe = avg_loss.replace(0.0, np.nan)
    rs = avg_gain / avg_loss_safe
    rsi = 100 - (100 / (1 + rs))
    both_zero = (avg_gain.fillna(0.0) == 0.0) & (avg_loss.fillna(0.0) == 0.0)
    only_loss_zero = (avg_gain.fillna(0.0) > 0.0) & (avg_loss.fillna(0.0) == 0.0)
    rsi = rsi.where(~both_zero, 50.0)
    rsi = rsi.where(~only_loss_zero, 100.0)
    return rsi


def _cross_signal(diff: pd.Series) -> pd.Series:
    prev = diff.shift(1)
    signal = pd.Series(0.0, index=diff.index)
    signal = signal.mask((prev <= 0) & (diff > 0), 1.0)
    signal = signal.mask((prev >= 0) & (diff < 0), -1.0)
    return signal


def _timestamp_index(df: pd.DataFrame) -> pd.DatetimeIndex:
    if isinstance(df.index, pd.DatetimeIndex):
        return df.index
    if "timestamp" in df.columns:
        return pd.to_datetime(df["timestamp"])
    raise ValueError("DataFrame must have a DatetimeIndex or a timestamp column")


def extract_features(df: pd.DataFrame, window: int = WINDOW, lookback: int = LOOKBACK) -> pd.DataFrame:
    """Extract the canonical ordered feature set from OHLCV data."""
    source = _normalize_ohlcv_columns(df.copy(deep=True))
    timestamps = _timestamp_index(source)

    open_ = pd.to_numeric(source["open"], errors="coerce")
    high = pd.to_numeric(source["high"], errors="coerce")
    low = pd.to_numeric(source["low"], errors="coerce")
    close = pd.to_numeric(source["close"], errors="coerce")
    volume = pd.to_numeric(source["volume"], errors="coerce")

    returns = close.pct_change()
    rolling_volume = volume.rolling(window).mean()

    macd_indicator = ta.trend.MACD(close=close, window_slow=26, window_fast=12, window_sign=9)
    macd_line = macd_indicator.macd()
    macd_signal = macd_indicator.macd_signal()
    macd_hist = macd_indicator.macd_diff()

    sma_20_raw = close.rolling(20).mean()
    sma_50_raw = close.rolling(50).mean()
    ema_20_raw = close.ewm(span=20, adjust=False, min_periods=20).mean()
    ema_50_raw = close.ewm(span=50, adjust=False, min_periods=50).mean()
    ema_diff = ema_20_raw - ema_50_raw

    adx_indicator = ta.trend.ADXIndicator(high=high, low=low, close=close, window=14)
    atr_indicator = ta.volatility.AverageTrueRange(high=high, low=low, close=close, window=14)

    features = pd.DataFrame(index=source.index)
    features["volatility"] = returns.rolling(window).std()
    features["volume_spike"] = volume / rolling_volume
    features["price_change"] = close.pct_change(lookback)
    features["range_pct"] = (high - low) / close.replace(0.0, np.nan)
    features["volume_ratio_prev"] = volume / volume.shift(1)
    features["rsi"] = _compute_rsi(close)
    features["macd_line"] = macd_line
    features["macd_signal"] = macd_signal
    features["macd_hist"] = macd_hist
    features["macd_cross"] = _cross_signal(macd_hist)
    features["sma_20"] = close / sma_20_raw - 1.0
    features["sma_50"] = close / sma_50_raw - 1.0
    features["sma_cross_20_50"] = pd.Series(
        np.where(sma_20_raw > sma_50_raw, 1.0, -1.0),
        index=source.index,
    ).where(sma_20_raw.notna() & sma_50_raw.notna())
    features["ema_20_50_cross"] = _cross_signal(ema_diff)
    features["adx"] = adx_indicator.adx()
    features["adx_plus_di"] = adx_indicator.adx_pos()
    features["adx_minus_di"] = adx_indicator.adx_neg()
    features["atr_pct"] = atr_indicator.average_true_range() / close.replace(0.0, np.nan)
    features["day_of_week"] = pd.Series(timestamps.dayofweek, index=source.index, dtype=float)
    features["month"] = pd.Series(timestamps.month, index=source.index, dtype=float)
    features["ret_1d"] = close.pct_change(1)
    features["ret_5d"] = close.pct_change(5)
    features["ret_20d"] = close.pct_change(20)

    return features[FEATURE_COLUMNS]


def init_feature_store(db_path: str = FEATURE_STORE_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS feature_vectors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            target INTEGER,
            features TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_fv_symbol_ts ON feature_vectors(symbol, timestamp)"
    )
    conn.commit()
    return conn


def _coerce_feature_values(features: list[float] | tuple[float, ...] | pd.Series | np.ndarray) -> list[float | None]:
    values = list(features.tolist() if hasattr(features, "tolist") else features)
    if len(values) != N_FEATURES:
        raise ValueError(f"Expected {N_FEATURES} features, got {len(values)}")

    normalized: list[float | None] = []
    for value in values:
        if value is None or pd.isna(value):
            normalized.append(None)
        else:
            normalized.append(float(value))
    return normalized


def insert_feature_vector(
    conn: sqlite3.Connection,
    symbol: str,
    timestamp: str,
    features: list[float] | tuple[float, ...] | pd.Series | np.ndarray,
    target: int | None = None,
) -> int:
    serialized = json.dumps(_coerce_feature_values(features))
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO feature_vectors (symbol, timestamp, target, features)
        VALUES (?, ?, ?, ?)
        """,
        (symbol, timestamp, target, serialized),
    )
    conn.commit()
    return int(cursor.lastrowid)


def load_feature_matrix(conn: sqlite3.Connection) -> tuple[list[list[float]], list[int], list[dict[str, str]]]:
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, symbol, timestamp, target, features FROM feature_vectors WHERE target IS NOT NULL ORDER BY id"
    )
    rows = cursor.fetchall()

    X: list[list[float]] = []
    y: list[int] = []
    meta: list[dict[str, str]] = []
    for row_id, symbol, timestamp, target, features_json in rows:
        values = json.loads(features_json)
        if len(values) != N_FEATURES:
            continue
        if any(value is None for value in values):
            continue
        if any(pd.isna(value) for value in values):
            continue
        X.append([float(value) for value in values])
        y.append(int(target))
        meta.append({"id": str(row_id), "symbol": symbol, "timestamp": timestamp})
    return X, y, meta


def update_target(conn: sqlite3.Connection, symbol: str, timestamp: str, target: int) -> int:
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE feature_vectors SET target = ? WHERE symbol = ? AND timestamp = ?",
        (int(target), symbol, timestamp),
    )
    conn.commit()
    return int(cursor.rowcount)


def count_vectors(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM feature_vectors").fetchone()[0])
