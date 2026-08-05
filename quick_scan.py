"""
Track 2 quick scan: direct regression on max 5-day upside for sub-$10 pennies.
Trains an ensemble (RandomForest + MLP via VotingRegressor) on the training
matrix, honestly gates it against the historical average, then ranks today's universe.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor, VotingRegressor
from sklearn.neural_network import MLPRegressor

from feature_pipeline import FEATURE_COLUMNS
from ml_engine import ENSEMBLE_WEIGHTS

MIN_PRICE = 0.10
MAX_PRICE = 10.0

TOP_N_GATE = 10
MIN_UPSIDE_RATIO = 3.0
TOP_N_OUTPUT = 20

TRAINING_MATRIX_PATH = Path(__file__).parent / "training_matrix_band.csv"

ENGINE_FEATURES = ["price_at_scan", "volume_ratio", "gap_pct", "short_percent"]
FEATURE_COLUMNS_FULL = list(FEATURE_COLUMNS) + ENGINE_FEATURES
TARGET_COLUMN = "max_change_5d"


def load_training_matrix() -> tuple[np.ndarray, np.ndarray, list[str]]:
    df = pd.read_csv(TRAINING_MATRIX_PATH)

    band = df[(df["price_at_scan"] >= MIN_PRICE) & (df["price_at_scan"] <= MAX_PRICE)].copy()
    band = band.dropna(subset=FEATURE_COLUMNS_FULL + [TARGET_COLUMN])

    X = band[FEATURE_COLUMNS_FULL].to_numpy(dtype=np.float64)
    y = band[TARGET_COLUMN].to_numpy(dtype=np.float64)
    return X, y, FEATURE_COLUMNS_FULL


def train_regressor(X: np.ndarray, y: np.ndarray) -> object:
    """Train a weighted xgb/rf/mlp regressor ensemble on max-upside targets."""
    try:
        from xgboost import XGBRegressor
    except ImportError as exc:
        raise ImportError("xgboost is required for quick_scan regression training") from exc

    members = [
        ("xgb", XGBRegressor(n_estimators=100, max_depth=4, learning_rate=0.05, random_state=42)),
        ("rf", RandomForestRegressor(n_estimators=200, max_depth=6, random_state=42)),
        ("mlp", MLPRegressor(hidden_layer_sizes=(64,), max_iter=1000, early_stopping=True, random_state=42)),
    ]
    weights = [ENSEMBLE_WEIGHTS.get(name, 1) for name, _ in members]
    ensemble = VotingRegressor(members, weights=weights)
    ensemble.fit(X, y)
    return ensemble


def backtest_honesty_gate(
    X: np.ndarray,
    y: np.ndarray,
    regressor: object,
    top_n: int | None = None,
    random_state: int = 42,
) -> dict:
    """Compare average realized upside of the top-n predicted rows vs n random rows."""
    rng = np.random.default_rng(random_state)
    top_n = top_n or TOP_N_GATE

    predicted = np.asarray(regressor.predict(X), dtype=float)
    top_idx = np.argsort(-predicted)[:top_n]
    top10_avg = float(y[top_idx].mean())
    random_avg = float(rng.choice(y, size=top_n, replace=False).mean())

    ratio = top10_avg / random_avg if random_avg > 0 else 0.0
    return {
        "top10_avg": top10_avg,
        "random_avg": random_avg,
        "ratio": ratio,
        "passed": bool(np.isfinite(ratio) and ratio >= MIN_UPSIDE_RATIO),
    }


def rank_universe(X: np.ndarray, symbols: list[str], regressor: object) -> list[dict]:
    """Rank the universe by predicted max upside, descending."""
    predicted = np.asarray(regressor.predict(X), dtype=float)
    order = np.argsort(-predicted)
    return [
        {"symbol": symbols[i], "predicted_upside": float(predicted[i])}
        for i in order
    ]


def quick_scan(X: np.ndarray, symbols: list[str], regressor: object, top_n: int | None = None) -> list[dict]:
    """Surface the top-n ranked symbols from a universe."""
    ranked = rank_universe(X, symbols, regressor)
    return ranked[: top_n or TOP_N_OUTPUT]
