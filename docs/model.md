# ML Model Documentation

## Problem framing

**Task:** binary classification — will this location experience a landslide
given current environmental + geological conditions?

**Label source:** `data/historical_landslide_data.csv` (1,470 rows spanning
2018-01-01 to 2025-11-20 across 30 locations and all 8 NER states, clearly
marked as **DEMO/sample data**).

Class balance: 990 positive / 480 negative (67.3% positive) — simulated toward
the positive class, which is why the model is trained with
`class_weight="balanced"`.

## Features

| Feature                 | Type        | Notes                            |
| ----------------------- | ----------- | -------------------------------- |
| `rainfall` (mm)         | numeric     | daily rainfall                  |
| `rainfall_intensity`    | numeric     | mm/h                             |
| `soil_moisture` (%)     | numeric     |                                  |
| `temperature` (°C)      | numeric     |                                  |
| `humidity` (%)          | numeric     |                                  |
| `elevation` (m)         | numeric     | DEM-sourced in production       |
| `slope` (degrees)       | numeric     |                                  |
| `historical_occurrence` | binary      | landslide previously recorded   |
| `distance_to_drain`     | numeric     | km from drainage line           |
| `land_cover`            | categorical | label-encoded                   |
| `soil_type`             | categorical | label-encoded                   |
| `rock_type`             | categorical | label-encoded                   |

## Data pipeline

1. `ml/data/generate_data.py` — creates the demo dataset (30 locations,
   8 states, seasonal realism, monsoon weighting).
2. `ml/train.py` — loads, cleans, label-encodes, splits (80/20 stratified),
   trains Random Forest, evaluates, saves artifacts:
   - `ml/model/landslide_model.joblib`
   - `ml/model/preprocessors.joblib`
   - `ml/model/model_meta.json` (metrics + feature importances)
3. `ml/evaluate.py` — re-evaluates the saved model and prints metrics.

## Algorithm

Random Forest Classifier (`n_estimators=200`, `class_weight="balanced"`).
Chosen for: robustness on tabular environmental data, interpretability
(feature importances), no heavy dependencies. XGBoost/Gradient Boosting and
time-series (LSTM) models are documented as future replacements.

## Reported metrics (DEMO dataset)

Reproduced exactly by re-running `python ml/train.py` (fixed `random_state=42`,
stratified split), and recorded in `ml/model/model_meta.json`:

- Accuracy: **0.8231**
- Precision: **0.8842**
- Recall: **0.8485**
- F1-score: **0.8660**

Per-class (test split, n=294):

| Class | Precision | Recall | F1 | Support |
| ----- | --------- | ------ | -- | ------- |
| 0 (no landslide) | 0.71 | 0.77 | 0.74 | 96 |
| 1 (landslide)    | 0.88 | 0.85 | 0.87 | 198 |

Confusion matrix: `[[74, 22], [30, 168]]`.

These are honest numbers on *synthetic* data and are labelled as such in the
README and UI. Real deployment requires properly labeled production data.
**No model accuracy is ever inflated.** The visible gap between the two classes
is the honest weak point of the model on this dataset — it is better at
confirming landslide conditions than at catching every borderline case.

## Score calibration

`risk_score = 100 * probability^1.6` (monotonic transform that spreads moderate
conditions into the middle bands), clipped to 0–100. Buckets:

| Score      | Level    |
| ---------- | -------- |
| 0–30       | LOW      |
| 31–60      | MODERATE |
| 61–80      | HIGH     |
| 81–100     | CRITICAL |

`confidence` is derived from how far the probability sits from the 0.5 decision
threshold (roughly 55–95%).

## Explainability

Each prediction returns `contributing_factors`, computed from the trained model's
feature importances combined with how far each feature is from a "safe" baseline:

```
Rainfall          ██████████  92%
Slope             ████████    78%
Soil Moisture     ███████     71%
```

The code is structured so SHAP values can be dropped in later (see `app/ml/predictor.py`
`_explain`), replacing the heuristic bars while keeping the same response shape.

## Fallback

If the model file is missing, the service uses a deterministic rule-based
scorer so the app never crashes, and reports `model: "Rule-based fallback"`.