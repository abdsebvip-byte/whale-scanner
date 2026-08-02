"""
ml_engine.py
============

Model training and ensemble inference for explosion detection.
Keeps the live scanner safe by failing clearly when optional ML dependencies
are missing instead of breaking import-time behavior.
"""

from __future__ import annotations

from collections import deque
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score
from sklearn.neural_network import MLPClassifier

try:
    import joblib
except ImportError as exc:  # pragma: no cover - imported in normal envs
    raise ImportError("joblib is required for ml_engine.py") from exc

MODEL_PATH = "explosion_model.pkl"
ENSEMBLE_WEIGHTS: dict[str, int] = {"xgb": 3, "rf": 2, "mlp": 1}


def _require_xgboost():
    try:
        from xgboost import XGBClassifier
    except ImportError as exc:
        raise ImportError(
            "xgboost is required for ML training. Install with: pip install xgboost imbalanced-learn"
        ) from exc
    return XGBClassifier


def _maybe_apply_smote(X: np.ndarray, y: np.ndarray, enabled: bool = True) -> tuple[np.ndarray, np.ndarray, bool]:
    if not enabled or len(y) == 0:
        return X, y, False

    classes, counts = np.unique(y, return_counts=True)
    if len(classes) < 2:
        return X, y, False

    minority_ratio = counts.min() / counts.max()
    if minority_ratio >= 0.6:
        return X, y, False

    try:
        from imblearn.over_sampling import SMOTE
    except ImportError:
        return X, y, False

    sampler = SMOTE(random_state=42)
    X_resampled, y_resampled = sampler.fit_resample(X, y)
    return np.asarray(X_resampled), np.asarray(y_resampled), True


class MLModelTrainer:
    """Builds and trains the ensemble members."""

    def build_models(self) -> dict[str, object]:
        XGBClassifier = _require_xgboost()
        return {
            "xgb": XGBClassifier(
                n_estimators=100,
                max_depth=4,
                learning_rate=0.05,
                eval_metric="logloss",
            ),
            "rf": RandomForestClassifier(
                n_estimators=200,
                max_depth=6,
                random_state=42,
            ),
            "mlp": MLPClassifier(
                hidden_layer_sizes=(64,),
                max_iter=1000,
                early_stopping=True,
                random_state=42,
            ),
        }

    def train(self, X, y, smote: bool = True) -> dict[str, object]:
        X_array = np.asarray(X, dtype=float)
        y_array = np.asarray(y, dtype=int)
        X_train, y_train, _ = _maybe_apply_smote(X_array, y_array, enabled=smote)
        models = self.build_models()
        for model in models.values():
            model.fit(X_train, y_train)
        return models

    def save(self, path: str | Path, models: dict[str, object], metadata: dict | None = None) -> None:
        payload = {"models": models, "metadata": metadata or {}}
        joblib.dump(payload, str(path))

    def load(self, path: str | Path) -> dict[str, object]:
        payload = joblib.load(str(path))
        if isinstance(payload, dict) and "models" in payload:
            return payload
        return {"models": payload, "metadata": {}}


class EnsemblePredictor:
    """Soft-voting predictor over the trained model family."""

    def __init__(self, model_path: str | Path = MODEL_PATH, history_window: int = 200) -> None:
        self.model_path = Path(model_path)
        self.history: deque[float] = deque(maxlen=history_window)
        self.models: dict[str, object] = {}
        self.metadata: dict = {}
        if self.model_path.exists():
            try:
                self._load_into_memory()
            except Exception:
                self.models = {}
                self.metadata = {}

    def _load_into_memory(self) -> None:
        payload = MLModelTrainer().load(self.model_path)
        self.models = payload.get("models", {})
        self.metadata = payload.get("metadata", {})

    def is_ready(self) -> bool:
        if self.models:
            return True
        if not self.model_path.exists():
            return False
        try:
            self._load_into_memory()
        except Exception:
            return False
        return bool(self.models)

    def predict_proba(self, features: list[float] | np.ndarray) -> float:
        if not self.is_ready():
            raise RuntimeError("Ensemble model is not ready")

        vector = np.asarray(features, dtype=float).reshape(1, -1)
        weighted_sum = 0.0
        total_weight = 0
        for name, model in self.models.items():
            weight = ENSEMBLE_WEIGHTS.get(name, 1)
            prob = float(model.predict_proba(vector)[0][1])
            weighted_sum += prob * weight
            total_weight += weight

        if total_weight == 0:
            raise RuntimeError("No trained models available in ensemble")

        probability = weighted_sum / total_weight
        self.history.append(probability)
        return max(0.0, min(1.0, probability))


class BacktestValidator:
    """Utility metrics for model evaluation and old-vs-new comparison."""

    def evaluate(self, y_true, y_pred, y_prob) -> dict[str, object]:
        y_true_arr = np.asarray(y_true, dtype=int)
        y_pred_arr = np.asarray(y_pred, dtype=int)
        y_prob_arr = np.asarray(y_prob, dtype=float)
        return {
            "accuracy": float(accuracy_score(y_true_arr, y_pred_arr)),
            "precision": float(precision_score(y_true_arr, y_pred_arr, zero_division=0)),
            "recall": float(recall_score(y_true_arr, y_pred_arr, zero_division=0)),
            "f1": float(f1_score(y_true_arr, y_pred_arr, zero_division=0)),
            "confusion_matrix": confusion_matrix(y_true_arr, y_pred_arr).tolist(),
            "avg_probability": float(y_prob_arr.mean()) if len(y_prob_arr) else 0.0,
        }

    def compare_to_phase2(self, y_true, y_prob, old_scores) -> dict[str, float]:
        y_true_arr = np.asarray(y_true, dtype=int)
        y_prob_arr = np.asarray(y_prob, dtype=float)
        old_scores_arr = np.asarray(old_scores, dtype=float)

        ml_positive = y_prob_arr[y_true_arr == 1]
        ml_negative = y_prob_arr[y_true_arr == 0]
        old_positive = old_scores_arr[y_true_arr == 1]
        old_negative = old_scores_arr[y_true_arr == 0]

        ml_separation = float(ml_positive.mean() - ml_negative.mean()) if len(ml_positive) and len(ml_negative) else 0.0
        old_separation = float(old_positive.mean() - old_negative.mean()) if len(old_positive) and len(old_negative) else 0.0
        if old_separation == 0.0:
            lift = float("inf") if ml_separation > 0 else 1.0
        else:
            lift = ml_separation / old_separation
        return {
            "ml_separation": ml_separation,
            "phase2_separation": old_separation,
            "lift": float(lift),
        }


def thresholds_from_predictions(
    probs: list[float] | np.ndarray,
    base_high: float = 0.7,
    base_low: float = 0.5,
) -> tuple[float, float]:
    arr = np.asarray(probs, dtype=float)
    if len(arr) < 10:
        return base_high, base_low

    high = max(base_high, float(np.percentile(arr, 80)))
    low = max(base_low, min(high, float(np.percentile(arr, 55))))
    return min(0.95, high), min(high, low)


def classify_signal(
    prob: float,
    dynamic_threshold: bool = True,
    recent_predictions: list[float] | np.ndarray | None = None,
) -> str:
    high = 0.7
    low = 0.5
    if dynamic_threshold and recent_predictions is not None:
        high, low = thresholds_from_predictions(recent_predictions, base_high=high, base_low=low)

    if prob >= high:
        return "strong"
    if prob >= low:
        return "medium"
    return "weak"
