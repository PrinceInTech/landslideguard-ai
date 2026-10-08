# REAL Data Feature Extraction Contract (Phase 3.7.1)

**Contract + foundation only.** This phase defines how the currently acquired
REAL artifacts become typed, leakage-safe ML-ready features. It does **not**
train a model, does **not** claim real-world prediction accuracy, acquires no
new dataset, and leaves the DEMO pipeline, the prediction API, and the UI
untouched.

> **The current REAL artifacts are acquisition-validation slices, not yet a
> complete ML training dataset.**

Code: contract in `backend/app/schemas/features.py`, extraction service in
`backend/app/services/features.py`, tests in
`backend/tests/test_feature_contract.py`.

## Supported REAL sources (as acquired)

| Source | Artifact | Observation window | `available_utc` | SHA-256 (ledger) |
| ------ | -------- | ------------------ | --------------- | ---------------- |
| `chirps` | one daily file `2026-08-31` (0.05 deg GeoTIFF, `-9999` fill) | 2026-08-31 00:00Z → 2026-09-01 00:00Z | 2026-09-11 21:10:59Z | `44934651…d9a6` |
| `era5-land` | one hourly timestep `2026-07-15 00:00Z` (0.1 deg NetCDF, NE-India slice) | 2026-07-15 00:00Z → 01:00Z | 2026-09-15 00:00Z (derived conservative bound) | `af53a81a…4ac9` |

Both are referenced **only** through the acquisition ledger
(`data/provenance/acquisition_manifest.json`, `AcquisitionRecord`): the record
id, the artifact SHA-256, the observation window, and `available_utc` are
copied verbatim into every feature's provenance.

## Feature mapping

### CHIRPS (`chirps`)

| Feature | Kind | Unit | Source | Status today |
| ------- | ---- | ---- | ------ | ------------ |
| `precipitation_daily_mm` | direct | mm | daily value, direct extraction | **valid** |
| `precipitation_1d_mm` | rolling (1 d) | mm | **one-day window only**: equals the single daily value when that day's file covers it — equality follows from the window length itself and implies no broader temporal coverage | **valid** (same as daily, by definition of a 1-day window) |
| `precipitation_3d_mm` | rolling (3 d) | mm | requires 3 contiguous daily files | **insufficient temporal coverage** |
| `precipitation_7d_mm` | rolling (7 d) | mm | requires 7 contiguous daily files | **insufficient temporal coverage** |
| `precipitation_14d_mm` | rolling (14 d) | mm | requires 14 contiguous daily files | **insufficient temporal coverage** |
| `precipitation_30d_mm` | rolling (30 d) | mm | requires 30 contiguous daily files | **insufficient temporal coverage** |

### ERA5-Land (`era5-land`)

| Feature | Source variable | Unit | Notes | Status today |
| ------- | --------------- | ---- | ----- | ------------ |
| `temperature_2m_K` | `t2m` | K | instantaneous 2 m temperature | **valid** |
| `precipitation_hourly_m` | `tp` | **m** | accumulation 00:00–01:00 UTC, raw NetCDF unit preserved | **valid** |
| `soil_water_layer1_m3m3` | `swvl1` | m3/m3 | volumetric soil water, layer 1 | **valid** |
| `surface_runoff_m` | `sro` | **m** | surface runoff over the same accumulation window | **valid** |

Short-code ↔ long-name mapping (`t2m`/`tp`/`swvl1`/`sro`) is asserted by tests.

**Units are never converted silently.** `tp` and `sro` are metres in the
acquired NetCDF and stay metres in the feature. Any future conversion must be
declared in the contract and covered by a test.

## Spatial rules

- Coordinate convention: **WGS84 decimal degrees**, expressed as
  `north / west / south / east` (study region N 29.5, W 88.0, S 21.0,
  E 97.5), CRS `EPSG:4326`.
- Only EPSG:4326 extraction is defined; a wrong CRS is rejected — **no silent
  reprojection**.
- Positions outside the study region are rejected before any read.
- Sampling is **nearest-cell** to the reported coordinate: no interpolation,
  no resampling, no invented precision.
- Source grid geometry, **confirmed against the acquired artifacts** (not
  guessed): the CHIRPS GeoTIFF's `ModelPixelScale` is **0.05° × 0.05°**
  (7200 × 2000 global grid, EPSG:4326, origin −180/50); the ERA5-Land
  NetCDF axes step **−0.1°** across 86 latitudes (29.5 → 21.0) and **+0.1°**
  across 96 longitudes (88.0 → 97.5). These match the provider registry
  (`spatial_resolution` = `"0.05 degrees"` and `"0.1 degrees, hourly"`).
- `coordinate_precision` (CHIRPS **0.025°**, ERA5-Land **0.05°**) is the
  **half-cell** width — a sampling tolerance, *not* the source resolution.
  ERA5-Land's 0.05° precision is half of its 0.1° cell and must not be read
  as a 0.05° grid; it numerically coincides with CHIRPS' *cell size*, which
  is a different quantity. A source without a verified precision raises
  instead of defaulting.
- Latitude axes may be ascending or descending; both are handled.

## Temporal rules and the leakage gate

Four distinct instants are kept separate (Phase 3.1 semantics), and every
feature carries them:

- `observation_start_utc` / `observation_end_utc` — the measurement window;
- `available_utc` — when the product vintage became public;
- `retrieved_utc` — when we downloaded the bytes;
- `prediction_cutoff_utc` — the model time the feature is evaluated at.

**Leakage rule (deterministic):**

```
observation_end_utc <= prediction_cutoff_utc
AND
available_utc      <= prediction_cutoff_utc
```

If either condition fails, the extraction returns
`rejected_leakage` for **every** requested feature with a note naming the
offending timestamp — the request never mixes gated and ungated values.
Naive datetimes are rejected outright; nothing is silently converted.

## Nodata rules

| Input | Contract value | Never |
| ----- | -------------- | ----- |
| CHIRPS `-9999.0` | `value=None`, status `missing` | never `0.0` |
| NetCDF `_FillValue` | `value=None`, status `missing` | never `0.0` |
| `NaN` | `value=None`, status `missing` | never `0.0` |
| missing spatial pixel | `value=None`, status `missing` | never interpolated from neighbours |
| missing temporal coverage | `value=None`, status `insufficient_temporal_coverage` | never zero-filled |
| leakage violation | `value=None`, status `rejected_leakage` | never partially applied |
| unverifiable artifact (SHA-256 mismatch) | extraction aborted (`invalid_source_artifact` path) | never extracted from |

A **measured `0.0` is valid data** (a dry day is not nodata) and is returned
as `0.0` with status `valid`. Every non-valid feature carries a `note`
explaining why.

Statuses: `valid`, `missing`, `insufficient_temporal_coverage`,
`rejected_leakage`, `invalid_source_artifact`.

## Provenance propagation

Each `FeatureValue` carries a `FeatureProvenance` with at least:

`source`, `product`, `product_version`, `source_record_id`,
`artifact_sha256`, `acquisition_record_id`, `observation_start_utc`,
`observation_end_utc`, `available_utc`, `retrieved_utc`,
`prediction_cutoff_utc`, `crs`, `coordinate_precision`,
`spatial_resolution`, `license_attribution`, `transform` (the derivation,
e.g. `"ERA5-Land t2m direct extraction"` / `"CHIRPS daily precipitation
(direct extraction)"`), and `derived_at_utc`.

Identity is re-verified at extraction time: the artifact's SHA-256 is
recomputed and compared to the ledger before any value is read; a mismatch
aborts the extraction.

## Currently supported direct features

- `precipitation_daily_mm`, `precipitation_1d_mm` (CHIRPS).
- `temperature_2m_K`, `precipitation_hourly_m`, `soil_water_layer1_m3m3`,
  `surface_runoff_m` (ERA5-Land).

## Currently unavailable (must not be fabricated)

With the single acquired daily CHIRPS file (and the single hourly ERA5-Land
timestep), the following are **not valid yet** and are reported as
`insufficient_temporal_coverage` rather than computed:

- 3-day / 7-day / 14-day / 30-day precipitation accumulations
- seasonal precipitation features
- temporal anomaly features requiring historical baselines
- a broad ML training dataset
- any real landslide prediction model

**Why fabricating them is forbidden:** zero-filling a missing history turns
"we do not have the data" into "it did not rain", silently biasing any future
model trained on these features. The honest status is part of the data. Rolling
windows become computable only when the ledger holds enough contiguous daily
files — which this phase deliberately does not acquire.

## Reading artifacts (decoders)

- ERA5-Land NetCDF: decoded with `netCDF4` (imported lazily; optional at
  import time). `_FillValue` → `NaN` → `missing`.
- CHIRPS GeoTIFF: decoding is backend-gated (`rasterio`). The contract's CHIRPS
  extraction is proven with bounded fixture grids that mirror the real
  artifact's documented geometry (0.05°, `-9999` fill) plus the artifact's
  checksum/identity against the real file — tests never download data, and the
  suite works on machines without a raster backend.

## Tests

`backend/tests/test_feature_contract.py` covers: valid provenance; naive
datetime rejection; both leakage conditions; CHIRPS `-9999` → missing (never
zero); NetCDF `_FillValue` → missing; valid CHIRPS direct extraction; the four
ERA5-Land direct extractions with units; wrong-CRS rejection; out-of-bounds
rejection; honest missing-coverage reporting; rolling-window refusal without
enough files; artifact SHA-256 mismatch rejection; provenance propagation of
`source_record_id` and `artifact_sha256`; deterministic leakage rejection; and
that missing history is never zero-filled. The spatial contract is pinned too:
`coordinate_precision` must be **exactly half** the provider-registered cell
size, provenance must refuse a source with no verified precision (no silent
default), and skip-guarded tests read the actual artifact headers (GeoTIFF
`ModelPixelScale`, NetCDF axis spacing) plus the CHIRPS study-window pixels
(mm scale, `-9999` fill, ledger-matching statistics) so a resolution or units
claim can never silently drift. Real-artifact checks are
skip-guarded on local file presence (nothing is downloaded).

## Boundaries (Phase 3.7.1)

- No model training, no accuracy claims, no new acquisitions, no IMERG/COOLR
  retries, no frontend/UI changes, no changes to the DEMO prediction path.
- Feature extraction is not wired into any API route; it is a contract +
  foundation for a later phase that will build a genuine training table over
  many acquisition days.
