"""Standalone trainer for the explosion-detection ensemble."""

from __future__ import annotations

import argparse
from datetime import datetime

import numpy as np
from sklearn.model_selection import train_test_split

from feature_pipeline import FEATURE_COLUMNS, FEATURE_STORE_PATH, init_feature_store, load_feature_matrix
from ml_engine import BacktestValidator, MLModelTrainer, MODEL_PATH


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train the explosion-detection ensemble")
    parser.add_argument("--force", action="store_true", help="Reserved for future overwrite/backfill flows")
    parser.add_argument("--no-smote", action="store_true", help="Disable SMOTE rebalancing")
    parser.add_argument("--db-path", default=FEATURE_STORE_PATH, help="Path to feature_store.db")
    parser.add_argument("--model-path", default=MODEL_PATH, help="Output model artifact path")
    return parser.parse_args()


def format_metric(value: float) -> str:
    return f"{value:.4f}"


def main() -> int:
    args = parse_args()
    conn = init_feature_store(args.db_path)
    X, y, meta = load_feature_matrix(conn)
    conn.close()

    if len(X) < 30:
        print(f"[!] Not enough labeled rows to train: {len(X)} found, need at least 30")
        return 1

    X_array = np.asarray(X, dtype=float)
    y_array = np.asarray(y, dtype=int)
    X_train, X_test, y_train, y_test = train_test_split(
        X_array,
        y_array,
        test_size=0.2,
        stratify=y_array,
        random_state=42,
    )

    trainer = MLModelTrainer()
    validator = BacktestValidator()

    try:
        models = trainer.train(X_train, y_train, smote=not args.no_smote)
    except ImportError as exc:
        print(f"[!] {exc}")
        return 1

    metrics_by_model: dict[str, dict[str, object]] = {}
    probabilities: dict[str, np.ndarray] = {}
    predictions: dict[str, np.ndarray] = {}
    for name, model in models.items():
        probs = model.predict_proba(X_test)[:, 1]
        preds = (probs >= 0.5).astype(int)
        probabilities[name] = probs
        predictions[name] = preds
        metrics_by_model[name] = validator.evaluate(y_test, preds, probs)

    ensemble_probs = (
        probabilities["xgb"] * 3 + probabilities["rf"] * 2 + probabilities["mlp"] * 1
    ) / 6.0
    ensemble_preds = (ensemble_probs >= 0.5).astype(int)
    ensemble_metrics = validator.evaluate(y_test, ensemble_preds, ensemble_probs)

    metadata = {
        "trained_at": datetime.now().isoformat(),
        "n_samples": int(len(X_array)),
        "train_samples": int(len(X_train)),
        "test_samples": int(len(X_test)),
        "class_distribution": {
            "negative": int((y_array == 0).sum()),
            "positive": int((y_array == 1).sum()),
        },
        "feature_names": FEATURE_COLUMNS,
        "metrics": {
            "xgb": metrics_by_model["xgb"],
            "rf": metrics_by_model["rf"],
            "mlp": metrics_by_model["mlp"],
            "ensemble": ensemble_metrics,
        },
        "train_meta_rows": len(meta),
    }
    trainer.save(args.model_path, models, metadata=metadata)

    print("=" * 72)
    print("MODEL TRAINING SUMMARY")
    print("=" * 72)
    print(f"Samples: total={len(X_array)} train={len(X_train)} test={len(X_test)}")
    print(f"Artifact: {args.model_path}")
    print()
    print(f"{'Model':<12} {'Accuracy':<10} {'Precision':<10} {'Recall':<10} {'F1':<10}")
    print("-" * 72)
    for name in ("xgb", "rf", "mlp"):
        metrics = metrics_by_model[name]
        print(
            f"{name:<12} {format_metric(metrics['accuracy']):<10} {format_metric(metrics['precision']):<10} "
            f"{format_metric(metrics['recall']):<10} {format_metric(metrics['f1']):<10}"
        )
    print(
        f"{'ensemble':<12} {format_metric(ensemble_metrics['accuracy']):<10} {format_metric(ensemble_metrics['precision']):<10} "
        f"{format_metric(ensemble_metrics['recall']):<10} {format_metric(ensemble_metrics['f1']):<10}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
