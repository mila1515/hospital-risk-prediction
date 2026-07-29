"""Compare classification baselines, evaluate them, and persist the best model."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
)
from sklearn.model_selection import StratifiedKFold, cross_validate, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


FEATURE_COLUMNS = [
    "age",
    "temperature_c",
    "systolic_bp",
    "diastolic_bp",
    "spo2",
    "heart_rate",
    "glucose_mg_dl",
    "pain_score",
    "admission_type",
]
NUMERIC_FEATURES = FEATURE_COLUMNS[:-1]
CATEGORICAL_FEATURES = ["admission_type"]
RISK_ORDER = ["Low", "Medium", "High", "Critical"]
SCORING = {
    "accuracy": "accuracy",
    "balanced_accuracy": "balanced_accuracy",
    "f1_macro": "f1_macro",
    "f1_weighted": "f1_weighted",
}


@dataclass(frozen=True)
class TrainConfig:
    input_csv: Path
    model_out: Path
    reports_dir: Path
    test_size: float
    random_state: int


def parse_args() -> TrainConfig:
    parser = argparse.ArgumentParser(prog="train_risk_model")
    parser.add_argument("--input", type=Path, default=Path("data/processed/patient_vitals_processed.csv"))
    parser.add_argument("--model-out", type=Path, default=Path("ml/models/risk_model.joblib"))
    parser.add_argument("--reports-dir", type=Path, default=Path("reports/model"))
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--random-state", type=int, default=42)
    args = parser.parse_args()
    if not 0.05 <= args.test_size <= 0.5:
        raise SystemExit("--test-size must be between 0.05 and 0.5")
    return TrainConfig(args.input, args.model_out, args.reports_dir, float(args.test_size), int(args.random_state))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_preprocessor() -> ColumnTransformer:
    numeric_pipeline = Pipeline(
        [("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]
    )
    categorical_pipeline = Pipeline(
        [
            ("impute", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore")),
        ]
    )
    return ColumnTransformer(
        [
            ("numeric", numeric_pipeline, NUMERIC_FEATURES),
            ("categorical", categorical_pipeline, CATEGORICAL_FEATURES),
        ],
        verbose_feature_names_out=False,
    )


def build_candidates(random_state: int) -> dict[str, Pipeline]:
    estimators = {
        "dummy_most_frequent": DummyClassifier(strategy="most_frequent"),
        "logistic_regression": LogisticRegression(
            max_iter=2000,
            class_weight="balanced",
            random_state=random_state,
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=400,
            min_samples_leaf=2,
            class_weight="balanced",
            random_state=random_state,
            n_jobs=1,
        ),
    }
    return {
        name: Pipeline([("preprocess", build_preprocessor()), ("model", estimator)])
        for name, estimator in estimators.items()
    }


def validate_training_data(df: pd.DataFrame) -> None:
    required = [*FEATURE_COLUMNS, "risk_level"]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    if df["risk_level"].nunique() < 2:
        raise ValueError("Training requires at least two target classes")
    if int(df["risk_level"].value_counts().min()) < 2:
        raise ValueError("Every target class needs at least two rows for stratified evaluation")


def cross_validation_results(
    candidates: dict[str, Pipeline], X: pd.DataFrame, y: pd.Series, random_state: int
) -> tuple[list[dict[str, object]], int]:
    folds = min(5, int(y.value_counts().min()))
    splitter = StratifiedKFold(n_splits=folds, shuffle=True, random_state=random_state)
    results: list[dict[str, object]] = []
    for name, pipeline in candidates.items():
        scores = cross_validate(pipeline, X, y, cv=splitter, scoring=SCORING, n_jobs=1)
        row: dict[str, object] = {"model": name, "cv_folds": folds}
        for metric in SCORING:
            values = scores[f"test_{metric}"]
            row[f"{metric}_mean"] = float(np.mean(values))
            row[f"{metric}_std"] = float(np.std(values))
        results.append(row)
    return results, folds


def evaluate_holdout(y_true: pd.Series, y_pred: np.ndarray) -> dict[str, object]:
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "f1_macro": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "f1_weighted": float(f1_score(y_true, y_pred, average="weighted", zero_division=0)),
        "classification_report": classification_report(y_true, y_pred, output_dict=True, zero_division=0),
    }


def save_feature_importance(pipeline: Pipeline, reports_dir: Path) -> None:
    estimator = pipeline.named_steps["model"]
    names = pipeline.named_steps["preprocess"].get_feature_names_out()
    if hasattr(estimator, "feature_importances_"):
        importance = np.asarray(estimator.feature_importances_)
    elif hasattr(estimator, "coef_"):
        importance = np.abs(np.asarray(estimator.coef_)).mean(axis=0)
    else:
        return
    pd.DataFrame({"feature": names, "importance": importance}).sort_values(
        "importance", ascending=False
    ).to_csv(reports_dir / "feature_importance.csv", index=False)


def main() -> None:
    cfg = parse_args()
    if not cfg.input_csv.exists():
        raise SystemExit(f"Input CSV not found: {cfg.input_csv.as_posix()}")

    df = pd.read_csv(cfg.input_csv)
    validate_training_data(df)
    X = df[FEATURE_COLUMNS].copy()
    y = df["risk_level"].astype(str)

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=cfg.test_size,
        random_state=cfg.random_state,
        stratify=y,
    )
    candidates = build_candidates(cfg.random_state)
    cv_results, folds = cross_validation_results(candidates, X_train, y_train, cfg.random_state)
    best_name = max(cv_results, key=lambda row: float(row["f1_macro_mean"]))["model"]
    best_pipeline = candidates[str(best_name)]
    best_pipeline.fit(X_train, y_train)
    predictions = best_pipeline.predict(X_test)
    holdout = evaluate_holdout(y_test, predictions)

    labels = [label for label in RISK_ORDER if label in set(y)]
    cfg.reports_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(cv_results).sort_values("f1_macro_mean", ascending=False).to_csv(
        cfg.reports_dir / "model_comparison.csv", index=False
    )
    pd.DataFrame(
        confusion_matrix(y_test, predictions, labels=labels), index=labels, columns=labels
    ).to_csv(cfg.reports_dir / "confusion_matrix.csv")
    pd.DataFrame({"row_index": y_test.index, "actual": y_test.values, "predicted": predictions}).to_csv(
        cfg.reports_dir / "holdout_predictions.csv", index=False
    )
    save_feature_importance(best_pipeline, cfg.reports_dir)

    metadata = {
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "path": cfg.input_csv.as_posix(),
            "sha256": file_sha256(cfg.input_csv),
            "rows": int(len(df)),
            "class_distribution": {key: int(value) for key, value in y.value_counts().items()},
        },
        "target": "risk_level",
        "target_type": "rule_based_proxy",
        "methodology_warning": (
            "risk_level is deterministically derived from the same vital signs used as features; "
            "results measure rule reproduction, not clinical outcome prediction."
        ),
        "selection_metric": "cross_validation_f1_macro",
        "cross_validation_folds": folds,
        "selected_model": best_name,
        "model_comparison": cv_results,
        "holdout_metrics": holdout,
        "random_state": cfg.random_state,
        "test_size": cfg.test_size,
        "versions": {"pandas": pd.__version__, "scikit_learn": sklearn.__version__},
    }
    (cfg.reports_dir / "metrics.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    cfg.model_out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "pipeline": best_pipeline,
            "feature_cols": FEATURE_COLUMNS,
            "metadata": {
                "selected_model": best_name,
                "target_type": "rule_based_proxy",
                "dataset_sha256": metadata["dataset"]["sha256"],
                "holdout_metrics": {key: value for key, value in holdout.items() if key != "classification_report"},
            },
        },
        cfg.model_out,
    )

    print(pd.DataFrame(cv_results).sort_values("f1_macro_mean", ascending=False).to_string(index=False))
    print(f"\nSelected model: {best_name}")
    print(f"Holdout macro F1: {holdout['f1_macro']:.3f}")
    print(f"Saved model to: {cfg.model_out.as_posix()}")
    print(f"Saved evaluation reports to: {cfg.reports_dir.as_posix()}")


if __name__ == "__main__":
    main()
