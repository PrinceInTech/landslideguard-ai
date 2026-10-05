"""Evaluate the saved model against the test split.

Usage (from ml/):
    python evaluate.py
"""
import json
import os

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import train_test_split

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_PATH = os.path.join(PROJECT_ROOT, "data", "historical_landslide_data.csv")
MODEL_DIR = os.path.join(PROJECT_ROOT, "ml", "model")

FEATURE_COLUMNS = [
    "rainfall", "rainfall_intensity", "soil_moisture", "temperature",
    "humidity", "elevation", "slope", "historical_occurrence", "distance_to_drain",
]
CATEGORICAL_COLUMNS = ["land_cover", "soil_type", "rock_type"]
TARGET = "landslide"


def main():
    model_path = os.path.join(MODEL_DIR, "landslide_model.joblib")
    bundle_path = os.path.join(MODEL_DIR, "preprocessors.joblib")
    if not (os.path.exists(model_path) and os.path.exists(bundle_path)):
        print("Model not found. Run train.py first.")
        return

    df = pd.read_csv(DATA_PATH)
    df = df.copy()
    df[TARGET] = df[TARGET].astype(int)

    encoders = joblib.load(bundle_path)["encoders"]
    for col in CATEGORICAL_COLUMNS:
        df[f"{col}_enc"] = df[col].astype(str).map(
            lambda v: encoders[col].transform([v])[0]
            if v in encoders[col].classes_ else 0
        )

    feature_cols = FEATURE_COLUMNS + [f"{c}_enc" for c in CATEGORICAL_COLUMNS]
    X = df[feature_cols]
    y = df[TARGET]

    _, X_test, _, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    model = joblib.load(model_path)
    y_pred = model.predict(X_test)

    print("=" * 60)
    print("SAVED MODEL EVALUATION")
    print("=" * 60)
    print(f"Accuracy:  {accuracy_score(y_test, y_pred):.4f}")
    print(f"Precision: {precision_score(y_test, y_pred, zero_division=0):.4f}")
    print(f"Recall:    {recall_score(y_test, y_pred, zero_division=0):.4f}")
    print(f"F1-score:  {f1_score(y_test, y_pred, zero_division=0):.4f}")
    print("\nConfusion Matrix:")
    print(confusion_matrix(y_test, y_pred))
    print("\nClassification Report:")
    print(classification_report(y_test, y_pred, zero_division=0))


if __name__ == "__main__":
    main()