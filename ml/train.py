"""Train the landslide risk prediction model.

Loads historical data, preprocesses, trains a Random Forest classifier,
evaluates it, and saves the model + preprocessor for use by the backend.

Usage (from project root):
    python ../../ml/train.py        (or)
    python -m ml.train               (must run with ml/ on sys.path)
"""
import json
import os
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_PATH = os.path.join(PROJECT_ROOT, "data", "historical_landslide_data.csv")
MODEL_DIR = os.path.join(PROJECT_ROOT, "ml", "model")
os.makedirs(MODEL_DIR, exist_ok=True)

FEATURE_COLUMNS = [
    "rainfall",
    "rainfall_intensity",
    "soil_moisture",
    "temperature",
    "humidity",
    "elevation",
    "slope",
    "historical_occurrence",
    "distance_to_drain",
]

CATEGORICAL_COLUMNS = ["land_cover", "soil_type", "rock_type"]

TARGET = "landslide"


def load_data():
    df = pd.read_csv(DATA_PATH)
    print(f"Loaded {len(df)} rows from {DATA_PATH}")
    return df


def clean_data(df):
    df = df.copy()
    df[TARGET] = df[TARGET].astype(int)
    for col in FEATURE_COLUMNS + CATEGORICAL_COLUMNS:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")
    numeric_cols = FEATURE_COLUMNS
    df[numeric_cols] = df[numeric_cols].fillna(df[numeric_cols].median())
    for col in CATEGORICAL_COLUMNS:
        df[col] = df[col].fillna("Unknown")
    return df


def build_preprocessor():
    """Return dict of label encoders for categorical features."""
    return {col: LabelEncoder() for col in CATEGORICAL_COLUMNS}


def main():
    print("=" * 60)
    print("LANDSLIDE RISK MODEL TRAINING")
    print("=" * 60)

    df = clean_data(load_data())

    # ---- Encode categorical features ----
    encoders = build_preprocessor()
    for col in CATEGORICAL_COLUMNS:
        # Fit on all classes present; make sure transform handles unseen later
        encoders[col].fit(df[col].astype(str))
        df[f"{col}_enc"] = encoders[col].transform(df[col].astype(str))

    feature_cols = FEATURE_COLUMNS + [f"{c}_enc" for c in CATEGORICAL_COLUMNS]

    X = df[feature_cols]
    y = df[TARGET]

    # Remember the calibration range for building a 0-100 risk score.
    calibration = {
        "min_prob": 0.0,
        "max_prob": 1.0,
    }

    # ---- Split ----
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    print(f"\nTraining samples: {len(X_train)}  Test samples: {len(X_test)}")
    print(f"Positive cases (landslide): {int(y.sum())} / {len(y)}")

    # ---- Train Random Forest ----
    model = RandomForestClassifier(
        n_estimators=200,
        max_depth=None,
        min_samples_leaf=2,
        random_state=42,
        n_jobs=-1,
        class_weight="balanced",
    )
    print("\nTraining Random Forest...")
    model.fit(X_train, y_train)

    # ---- Evaluate ----
    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1]

    acc = accuracy_score(y_test, y_pred)
    prec = precision_score(y_test, y_pred, zero_division=0)
    rec = recall_score(y_test, y_pred, zero_division=0)
    f1 = f1_score(y_test, y_pred, zero_division=0)
    cm = confusion_matrix(y_test, y_pred)

    print("\n" + "=" * 60)
    print("EVALUATION METRICS")
    print("=" * 60)
    print(f"Accuracy:  {acc:.4f}")
    print(f"Precision: {prec:.4f}")
    print(f"Recall:    {rec:.4f}")
    print(f"F1-score:  {f1:.4f}")
    print("\nConfusion Matrix (rows=true, cols=predicted):")
    print(cm)
    print("\nClassification Report:")
    print(classification_report(y_test, y_pred, zero_division=0))

    # ---- Feature importance ----
    importances = model.feature_importances_
    feat_importance = sorted(
        zip(feature_cols, importances), key=lambda x: x[1], reverse=True
    )
    print("\nFeature Importances:")
    for name, imp in feat_importance:
        print(f"  {name:<25} {imp:.4f}")

    # ---- Save model + preprocessor + metadata ----
    model_path = os.path.join(MODEL_DIR, "landslide_model.joblib")
    encoder_path = os.path.join(MODEL_DIR, "preprocessors.joblib")
    meta_path = os.path.join(MODEL_DIR, "model_meta.json")

    joblib.dump(model, model_path)
    joblib.dump({"encoders": encoders, "feature_columns": feature_cols}, encoder_path)

    metadata = {
        "model_type": "RandomForestClassifier",
        "trained_on": "DEMO/sample dataset (not production data)",
        # Store a path relative to the project root so the metadata never leaks
        # the absolute path or username of the machine that trained the model.
        "dataset": os.path.relpath(DATA_PATH, PROJECT_ROOT).replace("\\", "/"),
        "n_samples": int(len(df)),
        "n_features": len(feature_cols),
        "accuracy": float(acc),
        "precision": float(prec),
        "recall": float(rec),
        "f1_score": float(f1),
        "confusion_matrix": cm.tolist(),
        "feature_importance": {name: float(imp) for name, imp in feat_importance},
        "feature_columns": feature_cols,
        "calibration": calibration,
        "risk_buckets": {"LOW": [0, 30], "MODERATE": [31, 60], "HIGH": [61, 80], "CRITICAL": [81, 100]},
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    print(f"\nModel saved -> {model_path}")
    print(f"Preprocessors saved -> {encoder_path}")
    print(f"Metadata saved -> {meta_path}")

    print("\nNOTE: Model trained on DEMO/sample data. Real-world accuracy "
          "requires production datasets.")


if __name__ == "__main__":
    main()
