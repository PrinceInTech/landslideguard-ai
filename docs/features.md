# REAL Data Feature Extraction Contract (Phase 3.7.1–3.7.2)

**Contract + foundation only.** This phase defines how the currently acquired
REAL artifacts become typed, leakage-safe ML-ready features. It does **not**
train a model, does **not** claim real-world prediction accuracy, acquires no
new dataset, and leaves the DEMO pipeline, the prediction API, and the UI
untouched.

> **The current REAL artifacts are acquisition-validation slices, not yet a
> complete ML training dataset.**

Code: contract in `backend/app/schemas/features.py`, extraction service in
`backend/app/services/features.py`, tests in
`backend/tests/test_feature_contract.py` (contract) and
`backend/tests/test_feature_real_artifacts.py` (Phase 3.7.2 readers).

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
| unverifiable artifact (SHA-256 mismatch) | extraction aborted (`FeatureContractError`; no feature produced) | never extracted from |

A **measured `0.0` is valid data** (a dry day is not nodata) and is returned
as `0.0` with status `valid`. Every non-valid feature carries a `note`
explaining why.

Statuses carried by an emitted `FeatureValue`: `valid`, `missing`,
`insufficient_temporal_coverage`, `rejected_leakage`. (`FeatureStatus` also
reserves `invalid_source_artifact` for artifact-identity failure, but the current
pipeline aborts with `FeatureContractError` before any feature is produced, so no
result is returned with that status today.)

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

- **CHIRPS GeoTIFF (`.tif.gz`)** — decoded by a **built-in pure-Python reader**
  (`gzip` + `struct`): it parses the TIFF IFD, requires the contracted geometry
  (7200 × 2000, ModelPixelScale 0.05°, tiepoint −180/50, GeoKey EPSG:4326,
  uncompressed 32-bit float, one sample/pixel, strip layout), reads the
  **study-window strips only** (memory-safe: one 191-pixel row at a time), and
  reports the contracted `-9999` fill. No `rasterio`, `tifffile`, or Pillow
  dependency is added.
- **ERA5-Land NetCDF** — decoded with `netCDF4` (imported lazily; optional at
  import time). Axis spacing, count, extent, and units are verified before any
  value is read; `_FillValue`/`NaN` → `missing`.

## Phase 3.7.2 — real artifact pixel extraction

Phase 3.7.1 proved the contract with synthetic fixtures; 3.7.2 makes it read the
actual on-disk artifacts and pins the real values. **No new dependency** is
introduced.

**Decode order is identity-before-leakage.** `run_extraction` resolves the
ledger record, re-verifies product/version compatibility and the artifact
SHA-256, and only then maps feature names, applies the leakage gate, decodes,
and samples. A tampered or mismatched artifact aborts the extraction with
`FeatureContractError` before any leakage decision is exposed (the
`FeatureStatus.invalid_source_artifact` member is reserved but not currently
emitted, because the failure raises rather than returning a feature).

**CHIRPS reader.** `read_chirps_grid(path, *, region=None)` parses the header,
verifies the full contracted geometry (rejecting BigTIFF, wrong dimensions,
pixel scale, tiepoint, CRS, bits/sample-format, compression, samples/pixel, and
truncated strips), computes the region's window with half-cell pixel centres
using the artifact's real float32 pixel scale, and reads only those strips.

**ERA5 reader.** `read_era5_land_variables(path, *, region=None)` verifies the
86 × 96 axes (descending latitude, ascending longitude, 0.1° spacing) and the
exact units (`t2m` K, `tp` m, `swvl1` `m**3 m**-3`, `sro` m), then reads the four
variables on the region's window.

**Real-artifact spot checks** (hardcoded in tests, from the committed ledger
files): CHIRPS window N 29.5/W 88.0/S 21.0/E 97.5 = 171 × 191, ~4.58% fill,
mean ≈ 19.1763, median ≈ 13.4128, max ≈ 186.0284; e.g. (28.02, 90.03) ≈
6.0442 mm and (24.0, 95.0) ≈ 10.4295 mm; a `-9999` cell → `missing`, a
measured `0.0` cell → valid `0.0`. ERA5 at (26.0, 94.0): `t2m` ≈ 298.8933 K,
`tp` ≈ 0.011356 m, `swvl1` ≈ 0.4433, `sro` ≈ 0.0004792 m; a NaN cell →
`missing`.

**Limitations (unchanged from 3.7.1).** Only one daily CHIRPS file and one
ERA5-Land valid time exist, so 3d/7d/14d/30d accumulations stay
`insufficient_temporal_coverage`; this is still a contract + reader, not a
training dataset. Readers only ever open artifacts read-only; tests assert the
real files' bytes are untouched.

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

`backend/tests/test_feature_real_artifacts.py` (Phase 3.7.2) adds the real
readers: the pure-Python CHIRPS GeoTIFF reader (real-window values, and
parametrized rejection of every geometry deviation — dimensions, pixel scale,
origin, CRS, bits, sample-format, compression, samples/pixel, nodata; plus
non-TIFF, BigTIFF, and truncated-strip inputs), the ERA5 axis/units/region
verification (with a crafted in-memory NetCDF missing a variable), the
identity checks (product mismatch, version mismatch — with the ledger's
`v2.0`/registry `v2.x` wildcard, checksum-before-leakage, non-REAL kind), and
end-to-end extraction over the real artifacts including the leakage gate and a
no-mutation assertion on the source bytes.

## Boundaries (Phase 3.7.1–3.7.2)

- No model training, no accuracy claims, no new acquisitions, no IMERG/COOLR
  retries, no frontend/UI changes, no changes to the DEMO prediction path, and
  no new runtime dependency (CHIRPS uses the standard library; ERA5-Land keeps
  the already-established optional `netCDF4` import).
- Feature extraction is not wired into any API route; it is a contract +
  real-artifact reader foundation for a later phase that will build a genuine
  training table over many acquisition days.
