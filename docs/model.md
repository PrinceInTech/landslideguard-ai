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

These numbers are exactly reproducible on the *synthetic* dataset and are
labelled as such in the README and UI. Real deployment requires properly
labelled production data.

### Important caveat: label leakage in the DEMO dataset

The DEMO generator does not simulate landslides independently of the features.
In `ml/data/generate_data.py` the label is computed as a thresholded linear
score over seven of the very features the model receives — `temperature` and
`humidity` do **not** enter the score directly:

```
risk_input = 0.45*rainfall + 0.60*rainfall_intensity + 0.55*soil_moisture
           + 2.2*slope + 0.02*elevation + 25*historical_occurrence
           + (0 if distance_to_drain < 1.5 else 6) + U(-8, 8)
landslide  = 1 if risk_input > 185 else 1/0 with fixed probabilities above 140 and 95
```

So the classifier is largely learning to recover a known rule rather than
generalising from physical process. **The 0.8231 accuracy is therefore an upper
bound inflated by construction and must not be read as real-world performance.**
It is reported here so the figure quoted anywhere else in the project can be
traced to its true meaning.

The single-source cause of the wide gap between classes is the same artefact:
the label is close to deterministic, so borderline cases are inherently
ambiguous.

`ml/model/model_meta.json` records this explicitly under `label_leakage` so a
future reader cannot mistake the metrics for a validated field result.

**To obtain a meaningful accuracy estimate**, retrain on real labelled
landslide inventories (e.g. USGS landslide catalog data or state geological
records) with the label supplied by observation rather than computed from the
features, and validate on a geographically held-out split. `ml/train.py`
accepts any CSV with the same column contract, so only the dataset needs to be
replaced.

## Model metadata

`ml/model/model_meta.json` records, alongside the metrics:

- `model_version` (`1.1.0`) and `trained_at_utc`
- `library_versions` — scikit-learn, numpy, pandas, joblib, Python
- `hyperparameters` — including the split configuration and `random_state`
- `dataset` (repo-relative path) and `dataset_sha256`, so the exact file the
  model was fitted on can be verified
- `n_samples_train` / `n_samples_test` and class balance
- `risk_thresholds` — a snapshot of the boundaries in `app/risk.py`, which is
  the single source of truth at runtime
- `label_leakage` — the caveat above, recorded in the artifact itself

## Score calibration

`risk_score = 100 * probability^1.6` (monotonic transform that spreads moderate
conditions into the middle bands), clipped to 0–100.

Boundaries live in `backend/app/risk.py` (`RISK_LEVELS`) and are imported by the
predictor, the API schemas, and the analytics service, so all three cannot drift
apart. Upper bounds are inclusive:

| Score  | Level    |
| ------ | -------- |
| ≤ 30   | LOW      |
| ≤ 60   | MODERATE |
| ≤ 80   | HIGH     |
| ≤ 100  | CRITICAL |

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
