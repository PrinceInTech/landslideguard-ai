# Data Contract & Provenance (Phase 2.2 foundation, Phase 3.1 update)

A typed provenance/data-contract layer for future REAL data. The DEMO baseline
is untouched and remains the default; nothing in this layer is wired into the
DEMO prediction path or any API route yet.

## Why

Before acquiring real training data the pipeline needs a contract that:

- makes every real prediction/training record self-describing (where the value
  came from, how precise, how stale, how transformed);
- prevents historical replay from silently leaking future information by
  tracking the four times that matter (see below);
- registers every data source once, with license/attribution and a checksum;
- lets large raw files live **outside** the repository while still being
  verifiable by checksum;
- keeps DEMO and REAL provenance strictly separated so a DEMO-only surface can
  never be mistaken for validated real-world performance.

## DEMO vs REAL

Every provenance object carries a `kind` of `DEMO` or `REAL`.

- `kind` is **required** on `RecordProvenance` and `SourceProvenance` — there
  is no default, so a record can never silently drift into the REAL track.
- The current DEMO pipeline emits **no** provenance fields, so no existing
  record or API changes.
- A `REAL`-kind record explicitly declares itself a real-data candidate; a
  `DEMO`-kind record is a provenance-bearing demo record.
- A record may only reference a source of the same kind
  (`record.kind == source.kind`), enforced by
  `app.services.provenance.validate_record_source_match`.

## The four-time model

Every record must keep four distinct instants separate. Confusing them is the
classic cause of temporal leakage in historical replay:

| Instant                 | Where it lives             | Meaning |
| ----------------------- | -------------------------- | ------- |
| `observation_time_utc`  | `RecordProvenance`         | When the underlying measurement/observation is valid for (the valid time of the value). |
| `available_utc`         | `RecordProvenance`         | When the exact product vintage used became publicly available (publication/availability time). |
| `prediction_cutoff_utc` | `RecordProvenance`         | When the model inputs were frozen — the "model time" the record is evaluated at. |
| `retrieved_utc`         | `SourceProvenance`         | When **we** downloaded/retrieved the raw data (our own access time). |

All four are UTC, and all datetime fields are timezone-aware. A naive timestamp
is rejected — never silently converted.

### Temporal leakage gate

The schema rejects any record where:

- `available_utc > prediction_cutoff_utc`, or
- `observation_time_utc > prediction_cutoff_utc` (when an `observation_time_utc`
  is present).

A record is only eligible for a cutoff if the product it uses was both
**observed and published** at or before model time.

Example from the dynamic-product rule:

```
observation_time_utc = 2026-10-08T09:00Z   (value valid for 09:00 UTC)
available_utc        = 2026-10-08T13:00Z   (product published at 13:00 UTC)
prediction_cutoff    = 2026-10-08T10:00Z   (model time 10:00 UTC)
```

This record **MUST NOT** be eligible for that cutoff: the observation exists
(09:00Z) but the product was not published until 13:00Z, after the 10:00Z
cutoff. `RecordProvenance` rejects it at construction.

## Static vs dynamic sources

- **Dynamic products** (rainfall nowcasts/reanalyses, soil-moisture reanalyses,
  real-time event feeds) change over time. Their `observation_time_utc` and
  `available_utc` are value-specific: an IMERG Early run valid at 09:00 UTC has
  a different `available_utc` than the same 09:00 window expressed by IMERG
  Final months later. Only the vintage published at/before the cutoff may be
  used for that cutoff.
- **Static products** (terrain, lithology, soil maps, hydrology) are
  time-invariant maps but still have a **vintage**: the map describes the world
  as of its acquisition/reference period and was published at a specific time.
  They must still carry product/vintage provenance. Treating them as
  time-invariant for *feature values* is a modeling decision; treating them as
  available-for-any-cutoff is a temporal-leakage decision that must be made and
  documented per product (see vintage matching).

### Vintage matching rules

- `SRTMGL1 v003` — terrain acquired Feb-2000; a static DEM, valid for any
  cutoff (pre- and post-2000) as a terrain map. Record the product release
  (`v003`, void-filled) in `feature_source_version`.
- `SoilGrids 2.0` — a 2020-run predicted soil map; a timeless predicted
  product. Record the run/vintage.
- `HydroSHEDS v1.1` — SRTM-derived hydrology. Record the product version.
- `ESA WorldCover v100` = reference year **2020** map; `v200` = reference year
  **2021** map. A 2021 map is **not** automatically valid for a 2019 cutoff —
  it describes land cover observed in 2021 and was published in Oct-2022. For
  a cutoff before the map's reference year/publish date, that vintage is future
  information and must not be used. Pick a vintage whose reference period and
  publish date both precede the cutoff, or exclude that cutoff.
- `MCD12Q1 v061` = **annual** land-cover product (2001-present, 500m). Use the
  layer for year <= cutoff year, and honour the documented C6.1 caveat that
  the training database was not updated after ~2021 (layers for 2021+ are
  lower-trust).

Historical replay must respect these product availability/vintage semantics;
never default to "the newest map is valid for every cutoff".

## Per-record provenance

`RecordProvenance` (`backend/app/schemas/provenance.py`) — the fields every
real prediction/training record must represent:

| Field                    | Type            | Meaning |
| ------------------------ | --------------- | ------- |
| `event_id`               | str             | Unique id for the event/record |
| `prediction_cutoff_utc`  | aware datetime  | UTC instant inputs were cut off; naive datetimes are rejected |
| `observation_time_utc`   | aware datetime \| None | UTC instant the measurement is valid for; `None` for static features with no observation instant |
| `available_utc`          | aware datetime  | UTC instant the product vintage used became publicly available; **must be <= `prediction_cutoff_utc`** |
| `latitude` / `longitude` | float           | WGS84 decimal degrees, range-checked |
| `coordinate_precision`   | float           | Half-width of the coordinate cell in degrees (e.g. 0.01 ≈ 1 km) |
| `source`                 | str             | Registered source name (must exist in the manifest `sources[]`) |
| `source_record_id`       | str             | Id of the row in the source's own system |
| `feature_source`         | str             | Feature bucket the values came from (e.g. `ECMWF-ERA5`) |
| `feature_source_version` | str             | Version of that feature bucket (product/vintage) |
| `data_quality`           | DataQualityFlags| `missing_fields`, `interpolated`, `estimated`, `stale`, `outlier`, `schema_conformance`, `note` |
| `kind`                   | `DEMO` \| `REAL`| Provenance kind — **required**, no default |

`retrieved_utc` deliberately lives only on `SourceProvenance` (the retrieval
time of the raw data), not on the per-record schema; the record-level temporal
gate is the pair `observation_time_utc <= prediction_cutoff_utc` and
`available_utc <= prediction_cutoff_utc`.

## Source-level provenance

`SourceProvenance` — registered once per source and referenced by every record:

| Field                   | Meaning |
| ----------------------- | ------- |
| `name`                  | Unique source name |
| `kind`                  | `DEMO` \| `REAL` |
| `access_reference`      | URL / DOI / API documentation / in-repo path |
| `license_attribution`   | License + attribution; never fabricated |
| `retrieved_utc`         | When WE retrieved the raw data (`null` for in-repo synthetic) |
| `source_checksum`       | SHA-256 of the raw file (validated 64-hex) |
| `file_size_bytes`       | Size of the raw file |
| `geographic_coverage`   | Lat/lon bounding box (validated ordering) |
| `temporal_coverage`     | `start`/`end` dates (validated ordering) |
| `field_mapping`         | Source column → contract field → transform |
| `known_limitations`     | Honest limitations list |

## The manifest

`data/provenance/manifest.json`:

- `contract_version` — version of this contract (`1.1.0` since the Phase 3.1
  record-level temporal fields and required `kind`).
- `generated_at_utc` — when the manifest was written.
- `artifacts[]` — committed DEMO artifacts with SHA-256 + size
  (`data/historical_landslide_data.csv`, the three `ml/model/*` files, and
  `data/monitoring_locations.csv`).
- `sources[]` — source-level provenance (today: the DEMO generator only).
- `notes[]` — policy notes.

Loader/verifier: `backend/app/services/provenance.py` —

- `load_manifest()` parses and validates the manifest against the Pydantic
  contract;
- `verify_artifact_checksums()` recomputes every artifact digest and reports
  drift;
- `validate_record_source_match()` enforces the DEMO/REAL coupling.

Tests: `backend/tests/test_provenance_contract.py`.

## Raw files

Raw REAL data is never committed. It belongs in `data/raw/` (git-ignored — see
`data/raw/.gitignore` and `data/raw/README.md`), and the manifest references it
by `source_checksum` only, so a verification step can later re-hash an
uncommitted file against what was registered.

## Boundaries

- No acquisition adapters, real-data training, model retraining, API/UI
  integration, or deployment changes yet (Phases 2.1/2.2 + 3.1 contract only).
- The manifest registers **no REAL source** until one is actually acquired;
  nothing here fabricates datasets, metrics, or source availability.