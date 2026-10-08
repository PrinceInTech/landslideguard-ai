# Data Contract & Provenance (Phase 2.2)

A typed provenance/data-contract layer for future REAL data. The DEMO baseline
is untouched and remains the default; nothing in this layer is wired into the
DEMO prediction path or any API route yet.

## Why

Before acquiring real training data the pipeline needs a contract that:

- makes every real prediction/training record self-describing (where the value
  came from, how precise, how stale, how transformed);
- registers every data source once, with license/attribution and a checksum;
- lets large raw files live **outside** the repository while still being
  verifiable by checksum;
- keeps DEMO and REAL provenance strictly separated so a DEMO-only surface can
  never be mistaken for validated real-world performance.

## DEMO vs REAL

Every provenance object carries a `kind` of `DEMO` or `REAL`.

- The current DEMO pipeline emits **no** provenance fields, so no existing
  record or API changes.
- A record that carries `RecordProvenance` is a REAL-data candidate by default.
- A record may only reference a source of the same kind
  (`record.kind == source.kind`), enforced by
  `app.services.provenance.validate_record_source_match`.

## Per-record provenance

`RecordProvenance` (`backend/app/schemas/provenance.py`) — the fields every
real prediction/training record must represent:

| Field                    | Type            | Meaning |
| ------------------------ | --------------- | ------- |
| `event_id`               | str             | Unique id for the event/record |
| `prediction_cutoff_utc`  | aware datetime  | UTC instant inputs were cut off; naive datetimes are rejected |
| `latitude` / `longitude` | float           | WGS84 decimal degrees, range-checked |
| `coordinate_precision`   | float           | Half-width of the coordinate cell in degrees (e.g. 0.01 ≈ 1 km) |
| `source`                 | str             | Registered source name (must exist in the manifest `sources[]`) |
| `source_record_id`       | str             | Id of the row in the source's own system |
| `feature_source`         | str             | Feature bucket the values came from (e.g. `ECMWF-ERA5`) |
| `feature_source_version` | str             | Version of that feature bucket |
| `data_quality`           | DataQualityFlags| `missing_fields`, `interpolated`, `estimated`, `stale`, `outlier`, `schema_conformance`, `note` |
| `kind`                   | `DEMO` \| `REAL`| Provenance kind |

## Source-level provenance

`SourceProvenance` — registered once per source and referenced by every record:

| Field                   | Meaning |
| ----------------------- | ------- |
| `name`                  | Unique source name |
| `kind`                  | `DEMO` \| `REAL` |
| `access_reference`      | URL / DOI / API documentation / in-repo path |
| `license_attribution`   | License + attribution; never fabricated |
| `retrieved_utc`         | When the data was retrieved (`null` for in-repo synthetic) |
| `source_checksum`       | SHA-256 of the raw file (validated 64-hex) |
| `file_size_bytes`       | Size of the raw file |
| `geographic_coverage`   | Lat/lon bounding box (validated ordering) |
| `temporal_coverage`     | `start`/`end` dates (validated ordering) |
| `field_mapping`         | Source column → contract field → transform |
| `known_limitations`     | Honest limitations list |

## The manifest

`data/provenance/manifest.json`:

- `contract_version` — version of this contract (`1.0.0`).
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
  integration, or deployment changes yet (Phase 2.1/2.2 only).
- The manifest registers **no REAL source** until one is actually acquired;
  nothing here fabricates datasets, metrics, or source availability.