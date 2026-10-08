# REAL-Data Acquisition Rig (Phase 3.2)

Controlled acquisition machinery for the REAL-data track. This phase builds
**infrastructure only**: no model training, no final training table, no
event/control labels, no changes to the DEMO pipeline or the prediction API.
Nothing is downloaded by this phase — the ledger below starts empty and stays
empty until real bytes are actually acquired.

## Directory layout (minimal, per the existing architecture)

| Path | Role | Git |
| ---- | ---- | --- |
| `data/raw/real/` | Acquired REAL raw bytes, per source, immutable filenames | ignored (`data/raw/.gitignore`) |
| `data/provenance/acquisition_manifest.json` | Committed acquisition ledger (metadata only) | tracked |
| `data/provenance/manifest.json` | Source-level provenance (existing) | tracked |

`data/acquired/real/` and `data/normalized/real/` staging areas are **not**
created yet: nothing in the current architecture consumes staged or normalized
outputs. They belong to the normalization/feature-engineering phase and will be
introduced when they have a consumer.

## Approved sources (verified in Phase 2.3)

| Source | Tier | Auth | Credential vars |
| ------ | ---- | ---- | --------------- |
| `nasa-coolr` (NASA COOLR events) | event | none | — |
| `nasa-imerg-early` (GPM IMERG Early) | rainfall | Earthdata | `NASA_EARTHDATA_USERNAME`, `NASA_EARTHDATA_PASSWORD` |
| `chirps` (CHIRPS v2) | rainfall | none | — |
| `era5-land` (ERA5-Land hourly) | weather/land state | CDS | `CDS_API_URL`, `CDS_API_KEY` |
| `srtmgl1-v003` (SRTM Plus DEM) | static | Earthdata | `NASA_EARTHDATA_USERNAME`, `NASA_EARTHDATA_PASSWORD` |
| `esa-worldcover` (WorldCover v200) | static | none | — |
| `soilgrids` (SoilGrids 2.0) | static | none | — |
| `hydrosheds` (HydroSHEDS v1.1 drainage inputs) | static | none | — |

Rules applied by the registry:

- A source that requires credentials **fails loudly** (`CredentialsMissingError`
  listing the absent variables) when its credentials are missing — it never
  silently falls back to another provider or product.
- No unverified download URL is embedded. `endpoint_base` exists only for
  COOLR (whose FeatureServer was verified in Phase 2.3); every other source
  requires the caller to supply a verified URL via `retrieval_params['url']`.
- COOLR acquisition requires a **bounded geographic scope**
  (`retrieval_params['bbox']`) and a preflight-verified export URL; the global
  inventory is never downloaded by default.

## The acquisition contract

Each acquired artifact must carry metadata covering: `source`, `product`,
`product_version`, `source_record_id` (if applicable), `access_reference`,
`retrieved_utc`, observation/valid-time range (if applicable), publication /
availability info (if available), geographic coverage, CRS, license /
attribution, byte size, SHA-256, acquisition status, acquisition timestamp
(`acquired_utc`) and known limitations. This is captured by
`AcquisitionRecord` (`backend/app/schemas/acquisition.py`), reusing the
existing provenance models (`GeographicCoverage`, checksum validation)
wherever the fields are identical.

The temporal semantics honoured by the contract are the four times introduced
in Phase 3.1: `observation/valid time`, `available/published time`,
`retrieved time` and the future `prediction cutoff`. IMERG Early and ERA5-Land
retrievals must preserve valid-time, publication and aggregation semantics
(never claim an observation was available before it was); CHIRPS daily values
carry their product-version accumulation-window semantics and are never
silently converted into arbitrary cutoffs.

## Immutability, dedup and checksums

- Raw byte targets are **immutable**: an existing path is never overwritten
  (`DuplicateArtifactError`). Filenames embed source, product version and an
  acquisition key.
- Files are content-deduplicated by SHA-256: re-reading identical bytes
  produces a `skipped_existing` record, not a second file.
- Every artifact gets a SHA-256. An optional `expected_sha256` is enforced;
  a mismatch is recorded as `checksum_mismatch` with no file kept.

## The ledger

`data/provenance/acquisition_manifest.json` records every attempt — honest
successes **and** failures. It distinguishes DEMO and REAL
(`AcquisitionRecord.kind`). Reporting a source as "acquired" is only possible
when bytes were actually obtained, checksummed and the record persisted.
`acquired_real_count()` returns 0 until real bytes exist.

## Preflight (COOLR)

Before any large acquisition the rig runs `driver.preflight()`. For COOLR this
inspects the live FeatureServer: reachable layers, schema fields (`event_id`,
`event_date`, `event_time`, `latitude`, `longitude`, `location_accuracy`),
Northeast-India record count (bbox 88,21,97.5,29.5), and the observed
`event_date` range, stamping the exact retrieval timestamp. A failed preflight
is reported (`ok=False`) rather than raising.

## Tests

`backend/tests/test_acquisition_rig.py` covers source-configuration validation,
unsupported-source rejection, explicit credential handling, checksum
calculation, duplicate-artifact protection, metadata/provenance generation,
DEMO/REAL separation, raw-file ignore rules and that failed acquisition never
produces a fake successful artifact. Provider responses are mocked — unit
tests never hit the network.

## Scope notes

- The rig was validated against a fresh mock environment in Phase 3.2; the
  committed ledger contains **zero** REAL records.
- Acquiring, verifying connectivity, and recording real assets is the next
  phase (`PHASE 3.3`).