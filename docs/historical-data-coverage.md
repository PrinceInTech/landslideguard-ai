# Historical Data Coverage Audit & Temporal Decision Register

Phases 3.7.3A (coverage audit), 3.7.3A.1 (decision register), and 3.7.3B.1
(CHIRPS availability evidence audit). Planning and audit only.

- No data was downloaded, no external endpoint was called, no code, schema,
  manifest, test, model, or frontend behaviour was changed, and no rolling
  feature was created.
- Every factual claim is traced to a committed file, schema, test, or ledger
  record. Items not evidenced in the repository are labelled
  `EXTERNAL_EVIDENCE_REQUIRED`; a proposed default is never presented as a
  provider guarantee.

Evidence base: `data/provenance/acquisition_manifest.json`,
`data/provenance/manifest.json`, `backend/app/schemas/provenance.py`,
`backend/app/schemas/acquisition.py`, `backend/app/services/acquisition.py`,
`backend/app/schemas/features.py`, `backend/app/services/features.py`,
`docs/features.md`, `docs/provenance.md`, `docs/acquisition.md`,
`docs/model.md`, and the tests under `backend/tests/`.

---

## 1. Executive summary

- The repository holds exactly **two** successfully acquired REAL artifacts:
  one CHIRPS daily file for **2026-08-31** and one ERA5-Land hourly valid time
  for **2026-07-15 00:00 UTC** (`acquisition_manifest.json`, `status:
  "downloaded"` records at `:6` and `:300`).
- CHIRPS therefore covers **one** calendar day. Every requested rolling window
  (3/7/14/30 days) needs strictly more consecutive daily files than exist, so
  **no temporal window is computable today**; the code already returns
  `insufficient_temporal_coverage` for windows > 1
  (`backend/app/services/features.py:426`, `:506-532`).
- CHIRPS and ERA5-Land are **not a continuous series**: 47 days apart, different
  grids (0.05° daily vs 0.1° hourly) and different accumulation semantics. One
  artifact must never be treated as representative of a time series.
- The Q1–Q10 decision register (§3) freezes the temporal conventions from
  repository evidence + explicit engineering decisions (Q1–Q4, Q10) and isolates
  the items that genuinely require external evidence (Q5–Q9).
- **Layered verdict:**
  - **Historical acquisition: `READY_FOR_ACQUISITION_PLANNING`** for CHIRPS and
    ERA5-Land. Acquisition can be planned safely using only verified provider
    facts (URL patterns, product versions, auth) without inventing source facts.
  - **Temporal feature computation: `NEEDS_EVIDENCE`** — blocked by
    `EXTERNAL_EVIDENCE_REQUIRED` items Q5/Q6/Q7 plus the absent multi-day runway.
  - **Production use: NO-GO.** The REAL track is a contract/reader only; no
    REAL model is trained and no real-world performance is claimed
    (`docs/features.md:145-161`, `docs/model.md`).

> **Effective register status (supersedes the Q6 register rows below by
> reference: §28.6, §33.4, §34.7; Q7 restated unchanged).**
> - **Q6 CHIRPS**: research/replay evidence **recovered** and historical
>   availability **corroborated**, as documented in §28 and §33;
>   `provider_issued` availability is **not established**; the **Q6 production
>   gate remains `CLOSED`**.
> - **Q7 ERA5-Land**: remains **`EXTERNAL_EVIDENCE_REQUIRED`** (unchanged).
> - **Temporal production features** (CHIRPS and ERA5-Land): remain
>   **`NEEDS_EVIDENCE`**; overall production remains **`NO-GO`**.
>
> The Q6 `EXTERNAL_EVIDENCE_REQUIRED` references in this document (including the
> layered verdict above and the §3 register below) are the **historical state at
> those phases**; they are retained verbatim and superseded here by reference.
> "Q6 `CLOSED`" means the production gate stays closed; it does not mean the Q6
> evidence requirements are resolved.

---

## 2. Current acquired-data inventory

| # | Source | Product / version | Observation window (UTC) | `available_utc` | Retrieved | SHA-256 | Bytes | Status |
| - | ------ | ----------------- | ------------------------ | --------------- | --------- | ------- | ----- | ------ |
| 1 | `chirps` | CHIRPS v2 quasi-global precipitation v2.0 (registry `v2.x`) | [2026-08-31 00:00Z, 2026-09-01 00:00Z) | 2026-09-11 21:10:59Z (unverified, §7) | 2026-10-08 09:28:03Z | `44934651…d9a6` | 10,288,665 | downloaded |
| 2 | `era5-land` | ERA5-Land hourly, operational consolidated / ERA5-Land-T | [2026-07-15 00:00Z, 2026-07-15 01:00Z) | 2026-09-15 00:00:00Z (derived bound) | 2026-10-08 11:09:48Z | `af53a81a…4ac9` | 127,970 | downloaded |

Source: `data/provenance/acquisition_manifest.json:5-46` (CHIRPS),
`:299-361` (the one downloaded ERA5-Land attempt).

Verified CHIRPS artifact facts (Phase 3.5 note `:369`; Phase 3.7.2 tests):
float32 GeoTIFF 7200×2000, EPSG:4326, 0.05°, `-9999` fill; NE-India window
171×191 px, ~4.6% fill, 0–186.0 mm, mean ≈ 19.2 mm; one observation per day.

Verified ERA5-Land artifact facts (Phase 3.6 note `:371`; Phase 3.7.2 tests):
NetCDF `t2m`/`tp`/`swvl1`/`sro` (units K / m / m³·m⁻³ / m), `valid_time`
2026-07-15 00:00Z, latitudes 21.0–29.5 (86) step 0.1, longitudes 88.0–97.5 (96)
step 0.1, EPSG:4326.

### 2.1 Duplicate / overlap audit

- **CHIRPS:** exactly one record; no duplicate source/date, no overlap.
- **ERA5-Land:** five records share one `record_id`
  (`acquisition_manifest.json:48`, `:111`, `:174`, `:237`, `:300`): four
  `status:"failed"` (1× HTTP 422 body-format fix, 3× HTTP 403 licence gate,
  `sha256:null`, `storage_path:null`) plus one `downloaded`. These are
  honestly-recorded retry attempts, explicitly justified at `:371`; not
  duplicate artifacts.
- **Non-blocking doc inconsistency:** the append-only note at
  `acquisition_manifest.json:365` still says the REAL acquired count is 0,
  superseded by `:369` (count 1) and `:371` (count 2). Filed for a future
  maintenance edit; not touched here.

---

## 3. Q1–Q10 decision register

**Classification legend**

- `REPOSITORY_EVIDENCE` — the decision is already fixed by committed code,
  schema, ledger, or documentation.
- `ENGINEERING_DECISION` — a deliberate choice consistent with repository
  principles; it is a project convention, **not** a provider guarantee.
- `EXTERNAL_EVIDENCE_REQUIRED` — cannot be settled from the repository; needs
  provider-issued or official documentation evidence. Must not be invented.

**Blocks legend** — `acq` = historical acquisition planning, `feat` = temporal
feature computation, `prod` = production use.

| ID | Question / why it matters | Decision or default | Class | Evidence / rationale | Blocks |
| -- | ------------------------- | ------------------- | ----- | -------------------- | ------ |
| **Q1** | Does an N-day window include target day D? Sums are meaningless if the endpoint is ambiguous. | **Trailing window including D:** days `{D−(N−1) … D}`, D last. | `ENGINEERING_DECISION` | For N=1 the feature already equals that single day's daily value (`schemas/features.py:252-260`; `features.py:487-498`; `docs/features.md:36`). Extending the same trailing semantics to N>1 is the only convention consistent with the existing 1-day window; the alternative (exclusive of D) would contradict it. | feat, prod |
| **Q2** | UTC boundary semantics and the cutoff comparison operator. | Day `d` = half-open `[d 00:00Z, d+1 00:00Z)`; a day is usable when `observation_end_utc(d) <= cutoff` **and** `available_utc(d) <= cutoff` (inclusive). | `REPOSITORY_EVIDENCE` | CHIRPS observation windows are stored half-open (`acquisition_manifest.json:26-27`); registry records v2 time coordinate = start of UTC day (`acquisition.py:146`); the leakage gate allows equality (`features.py:139`, `:153`); four-time model in `docs/provenance.md:35-71`. | feat, prod |
| **Q3** | Nodata on one day inside an otherwise complete window: whole-window gap or partial sum? | **Whole window `missing`** — any required day whose sampled cell is nodata makes the aggregate `missing`; never a partial sum. | `ENGINEERING_DECISION` (informed by `REPOSITORY_EVIDENCE`) | Nodata→`missing` and never zero is already repository law (`features.py:477-486`; `schemas/features.py:51-56`; `docs/features.md:108-112`). A partial sum would silently under-count, i.e. smuggle a zero in through omission, violating that law. | feat, prod |
| **Q4** | How is target day D anchored: prediction-cutoff calendar time, or a COOLR event label? | **Cutoff-anchored.** `D = max{ d : observation_end_utc(d) <= cutoff AND available_utc(d) <= cutoff }` over UTC days; window = trailing N days ending at D. | `ENGINEERING_DECISION` | The feature contract is evaluated at `prediction_cutoff_utc` (`schemas/features.py:401-403`) and the format never permits future information (`features.py:121-158`). Event-label anchoring is a separate downstream labelling concern gated by Q9, not a feature-extraction rule. | feat, prod |
| **Q5** | CHIRPS prelim vs final: which vintage backs a target day, and how does availability differ per vintage? | **Default for historical backfill: FINAL.** Do not mix prelim and final without a vintage-specific availability rule. | `EXTERNAL_EVIDENCE_REQUIRED` | Repo verifies prelim has a ~2-day lag and final follows a month-ahead cadence (`acquisition.py:147`; `acquisition_manifest.json:369`), but not the per-vintage availability semantics needed to place a cutoff. | feat, prod |
| **Q6** | Derivation of CHIRPS `available_utc = 2026-09-11T21:10:59Z`. | **Treat as unverified / provisional.** Do not use it to clear a cutoff; acquire provider evidence and record it, or replace with a labelled derived bound. | `EXTERNAL_EVIDENCE_REQUIRED` | Exhaustive search shows the value exists only in `acquisition_manifest.json:28`, `docs/features.md:21`, the doc itself, and test fixtures (`test_feature_contract.py:91`, `test_feature_real_artifacts.py:552`). No script, README, or note derives it. Audited in §7A (Phase 3.7.3B.1); no derivation is recoverable from the repository. | feat, prod |
| **Q7** | Is ERA5-Land `available_utc = 2026-09-15T00:00Z` acceptable? | **Acceptable for research/replay only**, because it is a **derived conservative bound**; not acceptable as a provider vintage timestamp. | `EXTERNAL_EVIDENCE_REQUIRED` | The ledger states CDS exposes no per-vintage availability timestamp and the value is a derived conservative bound (`acquisition_manifest.json:371`); registry records the consolidated ~2-month lag (`acquisition.py:155-166`). See §7 for research-vs-production conditions. | feat, prod |
| **Q8** | IMERG Early remains unusable until Earthdata bearer-token file access works. | **Do not acquire or substitute.** Leave IMERG out of planning until auth is demonstrably fixed. | `EXTERNAL_EVIDENCE_REQUIRED` | Token minting returned Earthdata Login HTML instead of JSON; no artifact acquired; verdict `IMERG_LIVE_PREFLIGHT_FAILED` (`acquisition_manifest.json:368`; `acquisition.py:126-128`). | acq, feat, prod |
| **Q9** | COOLR export endpoint has not been proven; labels are unavailable. | **Do not acquire labels until a `preflight()` returns `ok` and an export URL is verified.** A missing event record is never a confirmed negative. | `EXTERNAL_EVIDENCE_REQUIRED` | COOLR requires a bounded bbox + preflight-verified `export_url` (`acquisition.py:375`, `:554-631`); connectivity was flaky (`:107`); absence in COOLR "is never evidence of no landslide" (`:104`). | acq, feat, prod |
| **Q10** | Is ERA5-Land used hourly or as an accepted daily aggregate? | **Hourly direct extraction only for now.** No daily aggregation until a documented, unit-safe rule exists; `tp`/`sro` are accumulation-over-window variables and must not be silently re-windowed. | `ENGINEERING_DECISION` | Current contract extracts raw hourly values with units preserved (`schemas/features.py:303-327`, `:37-49`; `docs/features.md:53`). Unit conversion as a side effect is forbidden by contract. | feat (deferred), prod |

**Net status:** Q1–Q4 and Q10 are **resolved** (three repository-evidenced, three
engineering decisions). Q5–Q9 remain **`EXTERNAL_EVIDENCE_REQUIRED`**. No
resolved decision depends on an invented provider fact.

> **Update (supersedes the Q6 part of this net status by reference):** Q6 is now
> research/replay-recovered, with the production gate still `CLOSED` and
> `provider_issued` availability **not established**. See the effective-status
> note above and §28.6/§33.4/§34.7. The Q6 row in §3 above is retained verbatim
> as historical record.

---

## 4. Chosen temporal-window convention

Frozen by Q1–Q4:

1. **Day unit.** A calendar day `d` is the half-open UTC interval
   `[d 00:00Z, d+1 00:00Z)`. No sub-day windows are defined for CHIRPS.
2. **Target day.** `D = max{ d : observation_end_utc(d) <= cutoff AND
   available_utc(d) <= cutoff }` over UTC days. D is anchored to the prediction
   cutoff (Q4), never to a COOLR event label.
3. **Window.** An N-day feature (`N ∈ {3,7,14,30}`) sums the daily values over
   the trailing set `{D−(N−1), …, D}` (Q1), inclusive of D.
4. **Eligibility.** Every day in the window must satisfy
   `observation_end_utc(d) <= cutoff` and `available_utc(d) <= cutoff`
   (`<=`, Q2). If any required day violates either, the feature is
   `rejected_leakage`.
5. **Coverage.** Every day in the window must have a present, identity-verified
   daily artifact (`chirps_daily_coverage_days == N`). Otherwise the feature is
   `insufficient_temporal_coverage` — never a partial sum, never zero-filled.
6. **Cell validity.** If all days are present but any required sampled cell is
   nodata, the feature is `missing` (Q3).
7. **Coverage matrix (today).**

   | Feature | Days | Present | Gap | Computable now |
   | ------- | ---- | ------- | --- | -------------- |
   | `precipitation_1d_mm` | {D} | 1 | 0 | yes (equals daily), only for D = 2026-08-31 |
   | `precipitation_3d_mm` | D−2…D | 1 | 2 | no |
   | `precipitation_7d_mm` | D−6…D | 1 | 6 | no |
   | `precipitation_14d_mm` | D−13…D | 1 | 13 | no |
   | `precipitation_30d_mm` | D−29…D | 1 | 29 | no |

   For any D other than 2026-08-31 the gap is larger by the distance from that
   date; none of the intervening days is held.

---

## 5. Availability / cutoff rules

Four distinct instants are kept separate (`docs/provenance.md:35-71`;
`schemas/provenance.py:100-151`):

| Instant | Meaning | Location | CHIRPS today | ERA5-Land today |
| ------- | ------- | -------- | ------------ | --------------- |
| `observation_start_utc` / `observation_end_utc` | measurement window | `AcquisitionRecord` | [2026-08-31 00:00Z, 2026-09-01 00:00Z) | [2026-07-15 00:00Z, 01:00Z) |
| `available_utc` | when the exact vintage became public | `AcquisitionRecord` | 2026-09-11 21:10:59Z (**unverified**, Q6) | 2026-09-15 00:00Z (**derived bound**, Q7) |
| `retrieved_utc` | when **we** pulled the bytes | `AcquisitionRecord` | 2026-10-08 09:28:03Z | 2026-10-08 11:09:48Z |
| `prediction_cutoff_utc` | model time inputs were frozen | `FeatureExtractionRequest` | request-supplied | request-supplied |

**Deterministic leakage gate.** A feature may clear a cutoff only when, for
**every** required observation:

```
observation_end_utc(d) <= prediction_cutoff_utc   AND
available_utc(d)       <= prediction_cutoff_utc
```

If either fails for any required day the whole feature is `rejected_leakage` —
never partially applied, never back-filled (`features.py:121-158`, `:1187-1209`).

**Safety rules preserved:** explicit half-open UTC intervals; target-day
inclusion and cutoff defined in §4; observations unavailable at the cutoff are
never used; observation / provider-availability / retrieval / cutoff times stay
distinct; provider-issued timestamps are never invented; derived availability
bounds stay explicitly labelled (Q6, Q7); missing dates and nodata are never
silently zero (Q3, §6); and a missing COOLR event record is never a confirmed
negative label (Q9; `acquisition.py:104`).

---

## 6. Missing-data and nodata policy (unchanged)

Implemented in `features.py` and documented in `docs/features.md:104-121`.

| Situation | Result | Never |
| --------- | ------ | ----- |
| CHIRPS `-9999` cell | `value=None`, status `missing` | never `0.0` |
| NetCDF `_FillValue` / NaN cell | `value=None`, status `missing` | never `0.0` |
| Measured `0.0` | `value=0.0`, status `valid` | never treated as nodata |
| Day not acquired (coverage gap) | `value=None`, status `insufficient_temporal_coverage` | never zero-filled |
| Complete days but one required cell nodata | `value=None`, status `missing` (Q3) | never a partial sum |
| Required observation/vintage after cutoff | `value=None`, status `rejected_leakage` | never partially applied |

Three "no rain" cases stay distinguishable: *measured zero* (valid `0.0`),
*nodata* (unknown → poisons the window), and *unavailable/not acquired*
(incomplete coverage). This phase changes none of it.

---

## 7. Unresolved external evidence (what would resolve each)

None of these are needed to **plan** CHIRPS/ERA5-Land acquisition; all are
hard gates before **computing** or **productionally using** temporal features.

- **Q5 — CHIRPS prelim/final vintage rule.** Resolve with: official CHC CHIRPS
  documentation/dataset notes stating the publication schedule and any
  versioned availability semantics for `prelim` vs `final`, or equivalent
  provider-issued metadata captured at acquisition. Until then, historical
  backfill uses FINAL and the vintage is recorded per artifact.
- **Q6 — CHIRPS `available_utc` derivation.** Audited in §7A (Phase 3.7.3B.1):
  no repository evidence derives the value and the acquisition transport never
  captured response headers, so it cannot be independently reproduced. Resolve
  with any of: the exact file's provider HTTP `Last-Modified`/directory-listing
  timestamp captured at retrieval; CHC publication-schedule documentation; or
  ERDDAP/catalog metadata. Any value kept must be recorded with its source and
  labelled provider-issued vs derived. The current `2026-09-11T21:10:59Z` is
  **not** altered here and stays unverified.
- **Q7 — ERA5-Land availability rule.** Conditions of acceptance:
  - *Research/replay:* the derived conservative bound is acceptable **iff** it is
    labelled as derived and the evaluated cutoff is at or after the bound.
  - *Production:* requires either a provider-issued per-vintage availability
    timestamp, or a documented, versioned conservative rule with a measured
    safety margin and an audit trail. Until then ERA5-Land features cannot back
    a production cutoff.
- **Q8 — IMERG authentication.** Resolve with a working Earthdata bearer-token
  flow (profile→token minting + file download) demonstrated out-of-band and
  recorded; do not substitute another source.
- **Q9 — COOLR export/preflight.** Resolve by running `preflight()` until it
  returns `ok` and recording the report (`layer_names`, `schema_fields`,
  `event_date` range, `export_endpoint_verified`), then verifying the export
  URL. Label data must keep the "absence ≠ negative" caveat.

---

## 7A. Q6 audit — CHIRPS availability evidence (Phase 3.7.3B.1)

Repository-only audit; no network access, no data acquisition. Question: does
`available_utc = 2026-09-11T21:10:59Z` have an auditable derivation?

### 7A.1 Evidence table

| # | Claim | Evidence location | Evidence type | Confidence / limitations | Q6 status | Minimum evidence to resolve |
| - | ----- | ----------------- | ------------- | ------------------------ | --------- | --------------------------- |
| 1 | The value is recorded for the CHIRPS artifact | `data/provenance/acquisition_manifest.json:28` | committed ledger literal | Present, but a bare value with no derivation field | `EXTERNAL_EVIDENCE_REQUIRED` | a provenance note or source |
| 2 | The value is echoed in docs and tests | `docs/features.md:21`; `test_feature_contract.py:91`; `test_feature_real_artifacts.py:552` | committed literal copies | Copies inherit the same missing derivation; tests only assert equality with the ledger | `EXTERNAL_EVIDENCE_REQUIRED` | same as #1 |
| 3 | No script, note, or commit derives it | repo-wide search; `git log -S "2026-09-11T21:10:59"` → only the commit that added the ledger row | negative search | Verified absent from the entire history | `EXTERNAL_EVIDENCE_REQUIRED` | a script/note deriving the value |
| 4 | The acquisition transport never captured response headers | `backend/app/services/acquisition.py:318-321` (`get_bytes` returns `response.content` only) | code inspection | Verified: `Last-Modified` was never read, so it could not have been persisted | `EXTERNAL_EVIDENCE_REQUIRED` | header capture + persistence (future phase) |
| 5 | The schema has no availability-provenance field | `backend/app/schemas/acquisition.py:115-117` | schema inspection | Verified: `available_utc` is a bare aware datetime; no source/confidence | `EXTERNAL_EVIDENCE_REQUIRED` | schema/ledger field (future phase) |
| 6 | Local artifact write time | filesystem `LastWriteTimeUtc = 2026-10-08T09:28:21Z`, equal to ledger `acquired_utc`; file is git-ignored | filesystem metadata (untracked) | Verified but is our **local write**, not provider publication; not auditable in Git | not applicable to Q6 | — |
| 7 | Retrieval instant | `acquisition_manifest.json:24` (`retrieved_utc 2026-10-08T09:28:03.770613Z`) | committed ledger | Verified; when **we** requested bytes, not when the provider published | bounds only, not proof | — |
| 8 | Publication-cadence note | `acquisition_manifest.json:369` ("month-ahead publication cadence") | committed note | Verified as a statement about data currency, not this file's publication timestamp | partial rationale | provider-issued timestamp |
| 9 | The value is internally consistent | 2026-09-11 is after observation (2026-08-31) and before retrieval (2026-10-08) | inference | Consistent with "already public before we fetched", but consistency is not provenance | `EXTERNAL_EVIDENCE_REQUIRED` | see §7A.3 |

### 7A.2 Timestamp categories (not interchangeable)

| Category | Example in repo | Meaning | Captured? |
| -------- | --------------- | ------- | --------- |
| Provider publication / availability | `available_utc 2026-09-11T21:10:59Z` | when the provider published this exact vintage | claimed, **not evidenced** |
| HTTP `Last-Modified` | none | provider server-side last-modified header | **not captured** |
| Artifact retrieval | `retrieved_utc 2026-10-08T09:28:03Z` | when we asked for the bytes | yes |
| Local write / acquired | `acquired_utc 2026-10-08T09:28:21Z` + filesystem mtime | when we wrote the bytes/ledger locally | yes |
| Prediction cutoff | request-supplied | model time | n/a |

### 7A.3 Conclusion

**Q6 remains `EXTERNAL_EVIDENCE_REQUIRED` (`NEEDS_EVIDENCE`).** Nothing in the
repository proves whether `2026-09-11T21:10:59Z` is a provider-issued
publication time, a derived bound, or an estimate. The transport never captured
headers and the schema cannot record a derivation, so the value cannot be
independently reproduced from committed evidence. The value is **retained
unchanged** — not re-dated, not replaced.

Minimum evidence to resolve Q6 (any one of):
- the exact file's provider HTTP `Last-Modified` (or directory-listing
  timestamp) captured with the request URL and response status at retrieval;
- CHC CHIRPS official publication-schedule documentation that pins the date;
- ERDDAP/catalog metadata for `chirps-v2.0.2026.08.31`.

Until one of these is captured, CHIRPS feature computation stays gated by Q6
(blocks `feat` and `prod`); acquisition planning remains unaffected.

---

## 8. Source readiness and proposed acquisition batches

Batches are **proposals**; nothing is executed or wired in this phase.

| Source | Tier | Provider verified | Acquired | Readiness | Evidence |
| ------ | ---- | ----------------- | -------- | --------- | -------- |
| `chirps` | rainfall | yes | 1 day | **ready to acquire** | `acquisition.py:131-150`; `acquisition_manifest.json:12-45,369` |
| `era5-land` | weather/land state | yes | 1 hourly time | **ready to acquire** (CDS token) | `acquisition.py:151-169`; `:299-361,371` |
| `nasa-imerg-early` | rainfall | yes | none | **blocked (Q8)** | `acquisition.py:112-130`; `:368` |
| `nasa-coolr` | event labels | yes | none | **blocked (Q9)** | `acquisition.py:87-111,375,554-631` |
| `srtmgl1-v003`, `esa-worldcover`, `soilgrids`, `hydrosheds` | static | yes | none | out of scope (temporal audit) | `acquisition.py:170-245` |

### Batch A — CHIRPS daily history (priority; unblocks all windows)

- **Goal:** ≥ 30 contiguous daily FINAL v2 files ending on a chosen target day
  (e.g. 2026-08-02 … 2026-08-31 enables `30d` for D = 2026-08-31).
- **Per-file gate:** SHA-256, 7200×2000 / 0.05° / EPSG:4326 / `-9999` / mm, UTC
  day window, one ledger record per date.
- **Mandatory evidence capture:** per the checklist below; each file records
  its availability evidence and whether the timestamp is provider-issued,
  derived, or unknown.
- **Next phase:** 3.7.3B (not started here).

#### Acquisition-time evidence-capture checklist (future CHIRPS / REAL downloads)

Reproducible, metadata-only (never credentials). Commit the values in the
ledger; do not fabricate an availability time.

1. **UTC retrieval start** — `retrieved_utc` (already recorded), plus UTC
   completion `acquired_utc`.
2. **Exact request URL and method** — the full URL (already in
   `retrieval_params.url`) and HTTP method (GET).
3. **Response status** — e.g. `HTTP 200`; record a non-2xx as a failed attempt.
4. **Availability-relevant response headers** — persist the literal values of
   `Last-Modified`, `Date`, `ETag`, `Content-Length`, `Content-Type`,
   `Server`. These are the primary candidate evidence for Q6.
5. **Provider metadata/version** — product (`CHIRPS-2.0`), version (`v2.0`),
   date, and edition (`prelim` vs `final`).
6. **Artifact identity** — SHA-256 and exact byte size (already recorded).
7. **Availability derivation statement** — explicitly classify `available_utc`
   as:
   - *provider-issued* (cite the header/metadata field and its value), or
   - *derived conservative bound* (state the formula and inputs), or
   - *unknown* (record `null`; never guess).
8. **Where recorded** — the ledger note (the `AcquisitionRecord` schema currently
   has no dedicated availability-source field; adding one is a future schema
   change and is out of scope here).

**Acceptance:** a third party can recompute from committed evidence alone why
`available_utc` has its value, or see explicitly that it is unknown.

### Batch B — ERA5-Land history aligned to Batch A (conditional)

- Only if multi-source features are in scope; needs CDS token, consolidated
  archive for older dates, ERA5-Land-T for recent. Preserve raw hourly units
  (Q10).

### Batch C — IMERG (blocked) and Batch D — COOLR labels (blocked)

- No acquisition until Q8 / Q9 respectively. No substitute source.

---

## 9. Go / No-Go checklist

**Historical acquisition planning**

- [x] CHIRPS: provider, URL pattern, product/version, auth verified in-repo → **GO**
- [x] ERA5-Land: provider, dataset DOI, auth path verified in-repo → **GO** (conditional on multi-source scope)
- [x] Temporal conventions frozen (Q1–Q4, Q10) → **GO**
- [ ] IMERG bearer-token flow (Q8) → **NO-GO**
- [ ] COOLR preflight + verified export URL (Q9) → **NO-GO**
- [ ] Availability evidence captured per acquired file (Q5/Q6/Q7) → **required by the acquisition run**

**Temporal feature computation**

- [ ] ≥ 30-day contiguous, SHA-verified CHIRPS runway present → **NO-GO**
- [ ] Per-day availability evidence captured and labelled (Q5/Q6/Q7) → **NO-GO**
- [x] Window convention frozen (§4) → GO
- [x] Leakage gate defined and already enforced (`features.py:121-158`) → GO
- [x] Missing/nodata policy defined (§6) → GO
- [ ] Explicit: no window computed on partial coverage → enforced by code

**Production use**

- [ ] REAL model trained on real labels (COOLR, Q9) → **NO-GO**
- [ ] Availability rules production-safe (Q7) → **NO-GO**
- [ ] Remain DEMO-labelled until real training data and metrics exist → **required**

---

## 10. Proposed design — acquisition evidence capture (Phase 3.7.3B.2, DESIGN ONLY)

Smallest backward-compatible change that would preserve CHIRPS availability
evidence during a **future authorized acquisition**. Nothing here is
implemented; no code, schema, manifest, or test is touched by this phase.

### 10.1 Problem

`AcquisitionTransport.get_bytes` (`acquisition.py:318-321`) returns
`response.content` only, so the HTTP status and every response header
(including `Last-Modified`, `ETag`, `Date`) are discarded. The ledger has no
place to record them or to state how `available_utc` was obtained. This is why
Q6 cannot be closed from the existing artifact.

### 10.2 Smallest design

**(a) Transport returns a result object (additive).** Introduce a small value
type and a new method, keeping `get_bytes` as a thin, backward-compatible
wrapper:

```
@dataclass(frozen=True)
class FetchResult:
    content: bytes
    status_code: int
    headers: Mapping[str, str]        # raw final-response headers
    final_url: str                    # after redirects (redacted before persist)
    redirect_chain: tuple[str, ...]   # redacted before persist

class AcquisitionTransport:
    def fetch(self, url, headers=None, timeout=120) -> FetchResult: ...
    def get_bytes(self, url, headers=None, timeout=120) -> bytes:   # delegates
        return self.fetch(url, headers, timeout).content
```

**(b) Optional ledger fields (additive, default `None`).** Extend
`AcquisitionRecord` (`schemas/acquisition.py`) with:

| Field | Type | Purpose |
| ----- | ---- | ------- |
| `request_url` | `str \| None` | exact requested URL (redacted, §10.5) |
| `request_method` | `str \| None` | HTTP method, e.g. `GET` |
| `http_status` | `int \| None` | response status code |
| `response_headers` | `dict[str,str] \| None` | **allowlisted** headers only |
| `final_url` | `str \| None` | post-redirect URL (redacted) |
| `redirect_chain` | `list[str] \| None` | redacted hop URLs in order |
| `provider_metadata` | `dict[str,str] \| None` | source-specific version/catalog facts (no secrets) |
| `availability_classification` | `"provider_issued" \| "derived" \| "unknown" \| None` | explicit nature of `available_utc` |
| `availability_source` | `str \| None` | evidence reference (header/metadata field, or rule name) |
| `availability_derivation` | `str \| None` | human-readable formula when `derived` |

`retrieved_utc`, `sha256`, `file_size_bytes`, `storage_path`, `error` already
exist and are reused unchanged.

**(c) Populate evidence in `acquire()`.** Replace the single
`self.transport.get_bytes(...)` call with `self.transport.fetch(...)`; pass
`http_status`, the allowlisted subset of `result.headers`, redacted
`request_url`/`final_url`/`redirect_chain` into `_make_record`. The availability
fields stay **caller/rule-driven** — they are never auto-derived from headers
(see §10.3).

**(d) Header allowlist.** Persist only `last-modified`, `etag`, `date` (matched
case-insensitively, canonicalised to lower-case keys). Never persist
`set-cookie`, `authorization`, `www-authenticate`, or any cookie/token echo.

### 10.3 Redirects, retries, failures, multiple artifacts

- **Redirects.** `requests` follows redirects (the current code already relies
  on this). Record `request_url` (original) and `final_url`; `redirect_chain`
  lists the hops. Capture headers/status **from the final response only**, and
  state that `Last-Modified`/`ETag` describe the final resource.
- **Retries.** One ledger record per attempt (already the model: failed attempts
  are recorded honestly). Each attempt keeps its own `retrieved_utc`, status,
  and evidence. Classification is per record; a failed attempt is `unknown`.
  Note the existing `record_id` collision when a caller reuses the same
  `acquisition_key` across retries (seen for ERA5, `acquisition_manifest.json:48`…);
  retries should use a distinct key or the id should incorporate an attempt
  token — flagged, not changed here.
- **Failed requests.** Record `status = failed`, `http_status` when a response
  was received, `availability_classification = "unknown"`, and **never** a
  fabricated `available_utc`. If the exception carries no response, all HTTP
  fields stay `None`.
- **Multiple artifacts.** One record per artifact/URL; never merge. Each carries
  its own URL, status, headers, SHA-256 and byte count. Retrieval time
  (`retrieved_utc`) is our access time and is never used as availability time.

### 10.4 Backward compatibility

- All new fields are optional with a `None` default, so existing records and
  the committed manifest load unchanged and existing consumers (`provenance.py`,
  `features.py`, `test_*`) are unaffected.
- **Serialization churn risk:** `save_acquisition_manifest` uses
  `model_dump_json(indent=2)` **without** `exclude_none`, so re-saving the
  ledger will emit `null` for every new field on old records. Either accept that
  churn or switch the writer to `exclude_none=True` (itself a small, testable
  change). This must be decided and covered by tests before rollout; a schema
  migration is **not** assumed safe.
- **Contract version:** the change is purely additive, so `contract_version`
  could stay `1.1.0`. Bumping to `1.2.0` would additionally require updating
  `test_manifest_roundtrip` (`test_acquisition_rig.py:395`), which currently
  asserts `"1.1.0"`. Recommend: keep `1.1.0` for the additive step, or bump and
  update that assertion deliberately — do not bump silently.
- No enum values are added or changed; `AcquisitionStatus` is untouched.
- No manifest data migration: append-only; only future acquisitions gain fields.

### 10.5 Credential and URL redaction policy

- Never persist `Authorization`/bearer tokens, cookies, `.env` values, or
  signed-URL secrets.
- Extend `_sanitize_retrieval_params` (`acquisition.py:364-367`) so URL **values**
  (`url`, `export_url`) are redacted, not just whole keys.
- URL redaction rule: parse with `urllib.parse`; strip userinfo
  (`user:pass@`), drop the `#fragment`, and replace the value of any query
  parameter whose name matches `token|key|api_key|apikey|secret|password|auth|sig|signature|access_token|expires`
  with `REDACTED`. Keep scheme/host/path and non-sensitive query keys. Record the
  names of redacted parameters (e.g. `redacted_params`) so redaction is auditable.
- Apply the same redaction to `final_url` and every `redirect_chain` hop.
- The header allowlist (§10.2d) independently prevents header-borne secret leaks.

### 10.6 Tests to define (future implementation)

| Case | Expectation |
| ---- | ----------- |
| Provider omits `Last-Modified`/`ETag`/`Date` | `response_headers` empty/`None`; `availability_classification="unknown"`; no invented `available_utc` |
| Invalid `Last-Modified` value | raw header stored; parse failure noted; classification stays `unknown`; no crash |
| Redirect (301/302 → 200) | `request_url` original, `final_url` final, `redirect_chain` ordered; headers from final response |
| Retry after failure | two records; failed = `unknown`, no storage; downloaded = evidence; retrieval times differ |
| Failed download (no response) | `status=failed`, HTTP fields `None`, no storage, no availability |
| Checksum mismatch | `checksum_mismatch` record retains URL/status/headers; no `storage_path` |
| Legacy record load | old manifest without new fields loads; fields `None`; round-trip stable |
| URL with `?token=…&sig=…` | secrets absent from serialized ledger; `redacted_params` lists them |
| Response with `Set-Cookie` | header never persisted (allowlist) |

The existing `FakeTransport` (`test_acquisition_rig.py:64-90`) would gain a
`fetch()` returning a `FetchResult`; `get_bytes` stays for the current tests.

### 10.7 Migration / rollout plan

1. Add `FetchResult` + `AcquisitionTransport.fetch`; keep `get_bytes`
   delegating (no behaviour change for existing callers/tests).
2. Add the optional `AcquisitionRecord` fields (default `None`).
3. Thread evidence through `_make_record`/`acquire`; add URL redaction and the
   header allowlist.
4. Decide the null-serialization policy (`exclude_none`) and whether to bump
   `contract_version`; update the affected test if bumped.
5. Add the §10.6 tests; keep the full existing suite green.
6. No data migration; no backfill (the historical value cannot be recovered).
7. Separate, later step (not this phase): a documented rule may map captured
   evidence to `available_utc`; until then capture-only.

### 10.8 Acceptance criteria (for the future implementation phase)

- A future CHIRPS acquisition records: exact request URL + method, UTC
  `retrieved_utc`, HTTP status, allowlisted headers (`Last-Modified`, `ETag`,
  `Date` when present), provider metadata/version, SHA-256, byte count, and an
  explicit `availability_classification` with source/derivation.
- From the committed ledger alone, a third party can state **why** `available_utc`
  has its value, or see that it is `unknown`.
- No secrets are persisted (redaction + allowlist tests pass).
- Legacy records and manifests load unchanged; full suite green.
- `Last-Modified` is captured as evidence but is **not** asserted to prove
  provider publication time; `provider_issued` is claimed only with documented
  provider semantics.

**Explicit non-claims.** HTTP `Last-Modified` alone is *not* proof of provider
publication time (it can reflect a server-side copy). This design improves
evidence capture; it does not by itself resolve Q6, and it does not authorize
feature computation or production use.

---

## 11. Quality gate and final verdict

- Decisions verified against actual repository evidence (§3 citations);
  `EXTERNAL_EVIDENCE_REQUIRED` items are not presented as facts.
- Phase 3.7.3B.1 (§7A) audited Q6 with no network: the CHIRPS availability
  value has no recoverable derivation and is retained unchanged; a
  reproducible acquisition-time evidence-capture checklist was added (§8).
- Phase 3.7.3B.2 (§10) proposes, but does not implement, the smallest
  backward-compatible evidence-capture change. **Proposed future files:**
  `backend/app/services/acquisition.py`, `backend/app/schemas/acquisition.py`,
  `backend/tests/test_acquisition_rig.py`. No manifest change; no data
  migration; no backfill (the historical value cannot be recovered).
- `git diff --check` clean.
- Only `docs/historical-data-coverage.md` changed/added; no code, schema,
  manifest, test, model, frontend, raw-artifact, credential, or dependency
  changes.
- Phases 3.7.3B (feature computation) and 3.7.3C not started; nothing committed
  or pushed.

**Final verdict.**

- **Historical acquisition: `READY_FOR_ACQUISITION_PLANNING`** — CHIRPS and
  ERA5-Land can be planned safely from verified provider facts, provided each
  acquisition run captures availability evidence and does not claim the current
  CHIRPS/ERA5-Land availability values are provider-verified.
- **Temporal feature computation: `NEEDS_EVIDENCE`** — Q6 remains
  `EXTERNAL_EVIDENCE_REQUIRED` (confirmed by the §7A audit; the §10 design is
  capture-only and does not resolve it); Q5/Q7 unresolved; and no multi-day
  runway exists.
- **Production use: NO-GO.**
- **Q6 final status: `EXTERNAL_EVIDENCE_REQUIRED`.** The §10 design would, once
  implemented and run against an authorized acquisition, capture the evidence
  needed to close Q6 — but until such an acquisition happens, the status stands.

---

## 12. Phase 3.7.3B.3 — evidence-capture implementation record

The §10 design is now implemented (code and tests only). This section records
what changed; it does not alter any prior verdict.

**Files changed**

- `backend/app/services/acquisition.py` — added the frozen `FetchResult` value
  type and `AcquisitionTransport.fetch()`; `get_bytes` now delegates to it
  (no behaviour change for existing callers). Added URL/redirect redaction
  (`redact_url`, `_redact_chain`), the response-header allowlist helper
  (`_allowlisted_headers`), and extended `_sanitize_retrieval_params` to redact
  secrets inside `url`/`export_url` values (now returns the safe snapshot plus
  the redacted parameter names). Evidence is threaded through `_make_record`
  and `acquire()`, including the failed path (status/allowlisted headers read
  from `exc.response` when a response was received). `save_acquisition_manifest`
  now writes with `exclude_none=True`.
- `backend/app/schemas/acquisition.py` — added the optional evidence fields
  (`request_url`, `request_method`, `http_status`, `response_headers`,
  `final_url`, `redirect_chain`, `provider_metadata`,
  `availability_classification`, `availability_source`,
  `availability_derivation`, `redacted_params`), the
  `ALLOWLISTED_RESPONSE_HEADERS` constant and a defence-in-depth
  `response_headers` validator that keeps only allowlisted lower-cased keys.
- `backend/tests/test_acquisition_rig.py` — `FakeTransport` gained `fetch()`
  (returning `FetchResult`; `get_bytes` delegates) plus new offline tests for
  header allowlisting, omitted/invalid availability headers, redirects, failed
  requests with and without a response, checksum-mismatch evidence, legacy
  record load/round-trip, URL-secret redaction, and the real transport wrapper.

**Decisions recorded**

- `contract_version` stays `1.1.0` (purely additive); the committed
  `data/provenance/acquisition_manifest.json` is unchanged and no data
  migration/backfill was performed (the historical value is unrecoverable).
- `redacted_params` is implemented even though the §10.2 field table omitted it:
  §10.5 (redaction auditability) and §10.6 (test expectation) both require it.
- `availability_classification` defaults to `"unknown"` on HTTP acquisition and
  is never auto-derived from headers. A captured `Last-Modified` is evidence,
  not a claim of provider publication time.

**Verification**

- `python -m pytest tests/test_acquisition_rig.py tests/test_cds_acquisition.py`
  → 69 passed.
- `python -m pytest` (full backend suite) → 253 passed.
- `git diff --check` clean; no manifest, raw-artifact, model, frontend,
  credential or dependency changes; nothing committed or pushed.

**Status.** Q6 remains `EXTERNAL_EVIDENCE_REQUIRED`; the layered verdict
(acquisition `READY_FOR_ACQUISITION_PLANNING`, feature computation
`NEEDS_EVIDENCE`, production `NO-GO`) is unchanged. This phase enables capture
only; it is not itself evidence and does not authorize feature computation.

---

## 13. Phase 3.7.3B.4 — evidence-capture security & provenance audit

Independent offline audit of the §12 implementation. No production code was
changed. Three regression tests were added
(`backend/tests/test_acquisition_rig.py`) and are **left failing** to evidence
the defects; the minimal fix is stated for each. All other tests remain green.

### 13.1 Findings by severity

**H-1 (High) — Secret leakage through exception strings.**
`acquire` and `acquire_cds` persist `error = f"{type(exc).__name__}: {exc}"`
(`acquisition.py:825`, `:1018`, `:1026`) and re-raise the same text. `requests`
builds `HTTPError`/`ConnectionError`/`InvalidURL` messages that embed the URL
(including signed query parameters), and `CdsTransport.download`
(`cds.py:182-185`) calls `raise_for_status()` on a (typically signed) asset
`href`. The raw message therefore reaches the committed ledger and the caller.
Evidence: `test_error_message_does_not_leak_url_secrets` (fails — the ledger
contains a `token=` value). Impact: permanent, possibly public persistence of
credentials/signatures, plus log/handler leakage. Minimal fix: derive the
persisted/raised error from safe parts only (`type(exc).__name__`, redacted
request URL, HTTP status) and/or run the message through a URL-redactor before
it is stored; apply to both `acquire` and `acquire_cds`.

**M-1 (Medium) — `redact_url` fails open on malformed URLs.**
`redact_url` returns its input unchanged when `urlsplit` raises `ValueError`
(`acquisition.py:410-413`). A malformed URL (e.g. invalid IPv6 brackets)
therefore keeps `user:pass@` and query secrets, which then reach `request_url`,
`retrieval_params`, `final_url` and `redirect_chain`. Evidence:
`test_redact_url_fails_closed_on_malformed_url` (fails). Impact: secrets survive
redaction for malformed input. Minimal fix: on parse failure, redact
conservatively (strip userinfo, drop the query, or substitute a placeholder)
instead of returning the raw string.

**M-2 (Medium) — CDS acquisition path captures no HTTP evidence.**
`acquire_cds`'s `_make_record` calls (`acquisition.py:998`, `:1079`, `:1098`)
omit every evidence field, and `CdsTransport.download` returns bytes only
(`cds.py:182-185`). ERA5-Land records therefore have no `request_url`,
`http_status`, `response_headers`, `final_url`, `redirect_chain`,
`provider_metadata` or `availability_*`. Assessment: the §10 design is
HTTP-transport-scoped, so this is an acceptable limitation **only if explicitly
recorded** — but ERA5-Land is one of the two real acquisition paths, and its Q7
availability evidence cannot be captured by this mechanism. Minimal fix (future
phase): return a `FetchResult` from the CDS download and thread evidence through
`acquire_cds`; otherwise state the exclusion in the acquisition runbook.

**L-1 (Low) — Allowlisted header values are unbounded.**
`_allowlisted_headers` (`acquisition.py:440-449`) stringifies values without any
length limit or control-character stripping. Evidence:
`test_response_header_values_are_bounded` (fails; a 100 000-char `ETag` is
stored verbatim). Impact: a hostile/oversized server response bloats the
committed ledger. Minimal fix: truncate values (e.g. ≤512 chars) and strip
`\r`/`\n`/control characters.

**L-2 (Low) — Nested secrets in `retrieval_params` are not redacted.**
`_sanitize_retrieval_params` (`acquisition.py:452-468`) filters only top-level
keys and `url`/`export_url` string values; a nested value such as
`{"headers": {"Authorization": "Bearer …"}}` is persisted. Probe confirmed.
Pre-existing (the pre-B.3 sanitizer was also top-level only), not introduced by
§12. Minimal fix: recursive redaction, or reject non-scalar retrieval params.

**L-3 (Low) — `provider_metadata` is unvalidated caller input.**
The field (`schemas/acquisition.py:158-160`) is stored verbatim
(`acquisition.py:846`, `:870`); the "never secrets" contract is documentation
only. Impact: caller error can persist a secret. Minimal fix: scrub it like
`retrieval_params` or validate keys/values.

**I-1 (Informational) — retry `record_id` collision.** Reusing an
`acquisition_key` across retries yields duplicate `record_id`s (already flagged
in §10.3); per-attempt evidence stays distinct, but ledger identity is
ambiguous. Recommend distinct keys or an attempt token.

**I-2 (Informational) — `exclude_none=True` serialization churn.** Re-saving the
committed ledger is not byte-identical: 18 `null`s drop (19 180 → 18 686 bytes).
Values are semantically identical and §12 accepted this, but a future append
would reformat historical records. Recommend a one-off normalization commit or
knowingly accept the churn.

**I-3 (Informational) — over-redaction false positives.** The substring regex
redacts non-secret names containing `key`/`sig`/`auth` (e.g. `keywords`,
`design`, `author`). Safe (fail-closed) but lossy; consider explicit names.

### 13.2 Audit confirmation (no defect found)

- `http_status`, `final_url` and `redirect_chain` are taken from the actual
  final response/`response.history` (`acquisition.py:340-346`); failed attempts
  never claim a `storage_path` or a successful artifact.
- Only allowlisted headers survive both the writer (`_allowlisted_headers`) and
  the schema validator; `Set-Cookie`/`Authorization` are never serialized.
- Missing/malformed headers never fabricate availability:
  `availability_classification` defaults to `unknown` and is never derived.
- SHA-256 and byte count are computed from the exact fetched `data` and written
  unchanged to disk; observation / retrieval / availability / acquired times
  remain distinct.
- Legacy records load unchanged; `exclude_none` round-trips to equal models.

### 13.3 Tests run and results

- Focused: `python -m pytest tests/test_acquisition_rig.py
  tests/test_cds_acquisition.py` → **3 failed, 69 passed**.
- Full: `python -m pytest` → **3 failed, 253 passed** (only the three new audit
  tests fail; no previously-passing test regressed).

### 13.4 Files changed by this audit

- `backend/tests/test_acquisition_rig.py` — three focused regression tests
  (H-1, M-1, L-1), intentionally failing.
- `docs/historical-data-coverage.md` — this section.
- No production code, schema, manifest, raw artifact, model, frontend,
  credential or dependency changes; nothing committed or pushed.

### 13.5 Safety and status

The capture design is **safe for unsigned, anonymous URLs** such as the planned
CHIRPS downloads (no secret in the URL path), but is **not unconditionally safe
for any acquisition whose URL carries credentials or signatures** (including
CDS asset hrefs): H-1 and M-1 must be fixed before such an authorized
acquisition. Q6 remains `EXTERNAL_EVIDENCE_REQUIRED`; production remains
`NO-GO`. This audit does not resolve Q6 or authorize feature computation.

## 14. Phase 3.7.3B.5 — audit remediation record

Offline remediation of the §13 findings that were judged genuine production
defects. No network, no real acquisition, no manifest rewrite, no historical
timestamp change, no raw-artifact/model/feature/frontend change and no new
dependency. `contract_version` remains `1.1.0`; the committed ledger
(`data/provenance/acquisition_manifest.json`) is unchanged.

### 14.1 Fixes applied

- **H-1 — exception-string secret leakage (fixed).** Added
  `_sanitize_error(exc)` (`services/acquisition.py`), which renders
  `f"{type(exc).__name__}: {exc}"` and passes it through the new
  `redact_text()` before it is persisted or re-raised. All five raw
  `f"{type(exc).__name__}: {exc}"` constructions (one in `acquire`, four in
  `acquire_cds`) now use it. Embedded URLs are redacted and sensitive
  `key=value` / `key: value` secrets are blanked; control characters stripped.
- **M-1 — `redact_url` fails open on malformed URLs (fixed).** `redact_url` now
  lives in the new shared module `backend/app/redaction.py` and fails closed:
  when `urlsplit` raises `ValueError`, `_conservative_url_strip` drops the
  fragment and the entire query and removes userinfo, so no secret survives.
  `services/acquisition.py` imports it and re-exports `redact_url`, preserving
  the existing public import path used by tests.
- **L-1 — unbounded allowlisted header values (fixed).** `_allowlisted_headers`
  and the `response_headers` schema validator now use `bound_string()` (control
  characters stripped, value truncated to `MAX_HEADER_VALUE_LENGTH = 512`).
- **L-2 — nested secrets in `retrieval_params` (fixed).** `_sanitize_retrieval_params`
  now recurses through nested dicts/lists/sets (depth-capped at 25), dropping
  sensitive keys and redacting `url`/`export_url` values at any depth. Dropped
  key names are recorded in `redacted_params` for auditability.
- **L-3 — unvalidated `provider_metadata` (fixed).** The schema now validates it
  in `mode="before"`: credential-like keys dropped, ≤32 keys, key ≤128 chars,
  values ≤512 chars, control characters stripped and embedded URLs/secrets
  redacted.

### 14.2 Deliberately not fixed (documented)

- **M-2 — CDS path captures no HTTP evidence.** Left as a documented limitation
  (per the phase constraints, which forbid implementing CDS evidence capture
  here). `acquire_cds` still records no `request_url`/`http_status`/
  `response_headers`/`final_url`/`redirect_chain`/`provider_metadata`/
  `availability_*`; `CdsTransport.download` remains bytes-only. The §13.1 M-2
  minimal fix (return a `FetchResult` from the CDS download and thread it
  through `acquire_cds`) is the recommended future work. This phase therefore
  makes **no** claim that the ERA5-Land path is evidence-complete.
- **I-1 / I-2 / I-3** remain informational (retry `record_id` collision;
  `exclude_none` serialization churn; intentional fail-closed over-redaction).

### 14.3 Tests

- Three intentionally-failing §13 regression tests now pass; three further tests
  were added (nested-params scrub; `provider_metadata` sanitisation/bounding;
  response-header control-character stripping).
- Focused: `python -m pytest tests/test_acquisition_rig.py
  tests/test_cds_acquisition.py` → **75 passed**.
- Full: `python -m pytest` → **259 passed** (previously 253 passed / 3 failed).
- Secret scan: `secret_scan.py` over 115 files vs 4 `.env` values → **hits=0**.
- `git diff --check` clean (only benign LF→CRLF notices).

### 14.4 Files changed

- `backend/app/redaction.py` (new) — shared, stdlib-only redaction helpers
  (`redact_url` fail-closed, `redact_text`, `is_sensitive_key`,
  `strip_control_chars`, `bound_string`, size constants).
- `backend/app/schemas/acquisition.py` — bounded/clean `response_headers`;
  `provider_metadata` validator; import shared helpers.
- `backend/app/services/acquisition.py` — `_sanitize_error`, recursive
  `_sanitize_retrieval_params`, bounded `_allowlisted_headers`, shared
  `redact_url` import/re-export.
- `backend/tests/test_acquisition_rig.py` — six regression tests (three §13
  now passing, three added).
- `docs/historical-data-coverage.md` — this section.

### 14.5 Safety and status

H-1 and M-1 are fixed, so the capture path is now fail-closed on malformed URLs
and does not persist credentials/signatures from exception text. **M-2 remains
open**, so ERA5-Land (the CDS path) is still not evidence-complete and must be
excluded from any evidence-completeness claim until its own phase. Q6 remains
`EXTERNAL_EVIDENCE_REQUIRED`; historical acquisition remains
`READY_FOR_ACQUISITION_PLANNING`; temporal feature computation remains
`NEEDS_EVIDENCE`; production remains `NO-GO`. Nothing was committed or pushed.

## 15. Phase 3.7.3B.6 — post-remediation security re-audit

Independent, offline re-audit of the §14 fixes at HEAD `c7f6016` with the
working-tree changes of §§12–14 applied. No network, no acquisition, no
production/schema edit, no manifest/raw/model/feature/frontend/dependency change;
nothing committed or pushed. Adversarial cases used deterministic local
sentinels only (never real credentials) and the failing-test assertions compare
booleans, so no sentinel is echoed in test output.

### 15.1 Prior findings — verified fixed

- **H-1 (fixed).** All five raw `f"{type(exc).__name__}: {exc}"` sites in
  `acquire`/`acquire_cds` now call `_sanitize_error` (`services/acquisition.py`),
  which runs `redact_text`. Offline probes with the realistic `requests`
  exception shapes all redact correctly: `HTTPError` carrying
  `https://user:pass@h/d?X-Amz-Signature=…`, `ConnectionError` carrying
  `?access_token=…`, and `InvalidURL` carrying `?token=…` — userinfo, signature
  and token values are removed from both the persisted record and the re-raised
  `AcquisitionError`; CR/LF are stripped.
- **M-1 (fixed for the reported class).** `redact_url` (now in
  `backend/app/redaction.py`) fails closed via `_conservative_url_strip` when
  `urlsplit` raises. Probes: malformed URLs with userinfo + token query, a token
  in the fragment, and a token in the query with a fragment all reduce to
  `http://[::1` with no secret and no userinfo.
- **L-1 (fixed).** Both capture (`_allowlisted_headers`) and schema validation
  bound values (`bound_string`, ≤512) and strip control characters. Probe: a
  100 000-char `ETag` is stored at 512 chars; `X-Injected` CR/LF is removed;
  `Set-Cookie` is dropped by the allowlist.
- **L-2 (fixed).** `_sanitize_retrieval_params` recurses through nested
  dicts/lists/sets with a depth cap of 25. Probes: nested
  `{"headers": {"Authorization": …}}`, `{"options": {"nested": {"api_key": …}}}`,
  `[{"password": …}]` and a 30-level-deep structure all drop the secret-bearing
  keys (deep values beyond the cap become `"<truncated>"`), and a cyclic dict is
  bounded without infinite recursion. `redacted_params` records key/param
  **names** only, never values.
- **L-3 (fixed for keys/URLs/bounds).** The `provider_metadata` validator (and
  capture path) drops credential-like keys, caps keys/values (≤32 keys,
  ≤128/≤512 chars), strips control characters, and redacts embedded URLs. Probe:
  `api_key` dropped; `https://…?token=…` value redacted; oversized value bounded
  to 512; CR/LF removed.
- **M-2 (still open, documented).** `acquire_cds` continues to record no HTTP
  evidence and `CdsTransport.download` remains bytes-only. ERA5-Land is **not**
  evidence-complete; the §13.1 M-2 minimal fix remains future work.

### 15.2 New findings

**R-1 (Low) — scheme credentials in free text are not fully redacted.**
`redact_text`'s `key=value`/`key: value` rule consumes only the single token
after the separator: `"Authorization: Bearer <credential>"` becomes
`"Authorization=REDACTED <credential>"`, leaving the credential. This affects
both the persisted/re-raised error path (`_sanitize_error`) and
`provider_metadata` values, which share `redact_text`. Evidence:
`test_b6_redact_text_redacts_scheme_credential` (fails). Reachability: `requests`
does not normally place `Authorization` header values in exception messages, so
the practical exposure is caller-supplied `provider_metadata`/error text; the
anonymous CHIRPS path is unaffected. Minimal fix: extend `redact_text` with a
scheme-credential rule (redact the token following `Bearer`/`Basic`/`Digest`).
Severity kept Low because it is not provider-reachable and not on the CHIRPS
path.

**R-2 (Low) — percent-encoded URLs in free text are not redacted.**
`redact_text` matches URLs only by the literal `scheme://` prefix; a fully
percent-encoded URL (`https%3A%2F%2F…%3Ftoken%3D…`, as can appear in
`requests.exceptions.InvalidURL`) is not decoded, so its query secret survives.
Evidence: `test_b6_redact_text_decodes_percent_encoded_urls` (fails). Minimal
fix: percent-decode candidate tokens before applying the URL rule (or match
`%3A%2F%2F`-style prefixes). Severity Low: CHIRPS URLs are plain and unsigned.

**Informational residuals (accepted, not defects).**
- A malformed URL carrying a secret **in its path** (not query/userinfo) is not
  stripped by `_conservative_url_strip`, which only drops fragment/query/userinfo
  — the docstring's "never lets a secret survive an unparseable URL" is broader
  than the implementation. Signed URLs carry secrets in the query, which is
  stripped.
- A bare credential stored as a `provider_metadata` **value** with no
  `key=`/URL shape is not detectable and survives; callers must not place raw
  secrets in metadata values. This is inherent to value-agnostic redaction.
- Over-redaction of names containing `key`/`sig`/`auth` (e.g. `author`,
  `keywords`) persists (prior I-3) — safe (fail-closed), lossy.

### 15.3 Provenance correctness

- `Last-Modified`, `ETag` and `Date` are captured as evidence only. A code
  search confirms no `available_utc` derivation from headers anywhere in
  `backend/app`; `availability_classification` defaults to `unknown` in
  `acquire` and is never auto-set to `provider_issued`/`derived`. Existing tests
  (`test_provider_omitted_availability_headers_stay_unknown`,
  `test_invalid_last_modified_value_is_stored_verbatim`,
  `test_explicit_availability_classification_is_preserved`) pass.
- The historical CHIRPS timestamp is unchanged; `data/provenance/
  acquisition_manifest.json` is unmodified (working-tree git blob
  `07dc2cdd36fa6772b74dcf6a7a96706d99eb593c`, content SHA-256
  `1f2b9434b199fee8809232cd8bfdf889983629d29d1546af7a2dbad747967d43`).
- No false success: the schema `_state_is_coherent` validator forbids a
  `storage_path` on non-acquired records and requires `sha256`/`file_size_bytes`/
  `storage_path` on `downloaded`/`skipped_existing`; failed attempts keep
  `storage_path=None`.
- Retrieval, availability, observation and prediction-cutoff times remain
  distinct fields and are not conflated.
- CDS/ERA5-Land is not reported as evidence-complete (M-2).

### 15.4 Tests and results

- Focused: `python -m pytest tests/test_acquisition_rig.py
  tests/test_cds_acquisition.py` → **2 failed, 75 passed**. The two failures are
  the new §15.2 regression tests, kept failing deliberately:
  `test_b6_redact_text_redacts_scheme_credential` and
  `test_b6_redact_text_decodes_percent_encoded_urls`.
- `git diff --check` — clean (only benign LF→CRLF notices). The full backend
  suite was **not** re-run this audit (scope: focused acquisition tests only);
  the §14 full-suite result (259 passed) plus the two new expected failures imply
  259 passed / 2 failed if run.

### 15.5 Files changed by this audit

- `backend/tests/test_acquisition_rig.py` — two failing regression tests (R-1,
  R-2). No prior tests modified.
- `docs/historical-data-coverage.md` — this section.
- No production/schema/manifest/raw/model/feature/frontend/credential/dependency
  change; nothing committed or pushed.

### 15.6 Safety and verdicts

The two new findings are **Low** severity, are not reachable from provider HTTP
responses, and do not affect the planned anonymous, unsigned CHIRPS downloads
(no userinfo, no query signature). **A limited authorized CHIRPS acquisition is
therefore safe** from a redaction standpoint, subject to the standing rule that
no URL carrying credentials/signatures be acquired until R-1/R-2 are fixed and
M-2 is addressed. H-1/M-1/L-1/L-2/L-3 are verified fixed; M-2 remains open. Q6
remains `EXTERNAL_EVIDENCE_REQUIRED` (no genuine source evidence was obtained);
production remains `NO-GO`; historical acquisition remains
`READY_FOR_ACQUISITION_PLANNING`; temporal feature computation remains
`NEEDS_EVIDENCE`.

## 16. Phase 3.7.3B.7 — redaction regression fix (R-1, R-2)

Fixed the two residual redaction defects reported in §15.2, changing only
`redact_text` in `backend/app/redaction.py`. No acquisition behavior, temporal
provenance, contract version, manifest, artifact, model, feature, frontend or
dependency change; no network; nothing committed or pushed.

### 16.1 R-1 — scheme credentials (fixed)

`redact_text` now applies a case-insensitive authorization rule before the
generic `key=value` rule:

- `_AUTH_SCHEME_RE` matches `(Proxy-)Authorization: <scheme> <credential>` for
  `bearer`, `basic`, `digest`, `token`, `apikey`/`api-key`, `hmac`, and replaces
  the credential while preserving the field and scheme
  (`Authorization: Bearer REDACTED`) for diagnostics.
- `_BARE_SCHEME_RE` matches a standalone `Bearer`/`Basic`/`Digest` followed by a
  credential-shaped token (≥8 chars with a digit/symbol), so prose like
  `basic authentication` is not over-redacted.
- Whitespace between scheme and credential is `\s+`, so wrapped/multiline
  messages (`Authorization: Bearer\r\n<cred>`) are covered; control characters
  are stripped from the final text.

Verified for `Authorization`/`authorization`/`AUTHORIZATION`,
`Proxy-Authorization`, `Bearer`/`Basic`/`Digest`, mixed case, and multiline
input. This closes the §15.2 R-1 leak in both `_sanitize_error` (persisted and
re-raised error text) and the `provider_metadata` validator.

### 16.2 R-2 — percent-encoded URLs (fixed)

`redact_text` now scans whitespace-delimited candidate tokens, percent-decodes
them with `_bounded_unquote` (at most `_MAX_UNQUOTE_ROUNDS = 4`, iterative, never
recursive), and — only when the decoded token has a real `https?://`/`ftp://`
scheme — redacts it with `redact_url` (query secrets, userinfo and fragment).
Decoding is bounded and the decoded value is used only for detection/redaction,
never fed back into a URL or path, so there is no double-decoding vulnerability.
Malformed or ambiguous tokens are left unchanged unless they decode to a real
URL (fail closed via `redact_url`'s existing conservative strip). Verified for
single- and double-encoded URLs, including userinfo and fragment.

### 16.3 Tests and results

- Existing §15.2 tests now pass: `test_b6_redact_text_redacts_scheme_credential`,
  `test_b6_redact_text_decodes_percent_encoded_urls`.
- Added two focused tests: `test_b7_redact_text_redacts_scheme_variants_case_insensitively`
  and `test_b7_redact_text_decodes_nested_percent_encoding`. All use dummy
  sentinels and compare booleans, so no credential is echoed on failure.
- Focused: `python -m pytest tests/test_acquisition_rig.py
  tests/test_cds_acquisition.py` → **79 passed**.
- Full: `python -m pytest` → **263 passed** (3 benign sklearn
  version warnings).
- Secret scan: `secret_scan.py` over 115 files vs 4 `.env` values → **hits=0**.
- `git diff --check` — clean (only benign LF→CRLF notices).
- Adversarial re-probe: prior literal-URL/nested/header/metadata results
  unchanged; only the inherent §15.2 informational cases remain (a bare secret
  under a non-sensitive key; a secret in the path of a malformed URL).

### 16.4 Remaining limitations

- The §15.2 informational residuals are unchanged by design: a bare credential
  stored as a `provider_metadata` value with no `key=`/URL shape, and a secret in
  the path of an unparseable URL, are not detectable by value-agnostic
  redaction; callers must not place raw secrets in these positions.
- **M-2 (CDS/ERA5-Land evidence-capture gap) remains open** and documented (§13,
  §14.2, §15.1); ERA5-Land is still not evidence-complete.

### 16.5 Files changed

- `backend/app/redaction.py` — R-1/R-2 rules in `redact_text`, bounded
  `_bounded_unquote`, credential/URL-shape helpers. Existing public interfaces
  (`redact_url`, `redact_text`, `bound_string`, `is_sensitive_key`,
  `strip_control_chars`) unchanged.
- `backend/tests/test_acquisition_rig.py` — updated the §15.2 tests (now passing)
  and added two focused B.7 tests.
- `docs/historical-data-coverage.md` — this section.

### 16.6 Status

R-1 and R-2 are fixed and verified. The historical
`data/provenance/acquisition_manifest.json` is unchanged (git blob
`07dc2cdd36fa6772b74dcf6a7a96706d99eb593c`); the CHIRPS `available_utc` value is
untouched; M-2 remains open. Q6 remains `EXTERNAL_EVIDENCE_REQUIRED`; historical
acquisition remains `READY_FOR_ACQUISITION_PLANNING`; temporal feature
computation remains `NEEDS_EVIDENCE`; production remains `NO-GO`. Nothing was
committed or pushed.

## 17. Phase 3.7.3B.8 — final security gate & acquisition readiness audit

Independent, offline audit of the redaction/evidence boundary at HEAD `c7f6016`
with the working-tree changes of §§12–16 applied. No network, no acquisition, no
production/schema/test/manifest edit; nothing committed or pushed. All probes
used dummy sentinels and assertions compare booleans, so no credential is echoed.

### 17.1 Scope and method

- Statically traced `backend/app/redaction.py`; every error path in
  `backend/app/services/acquisition.py` (`acquire`, `acquire_cds`,
  `_sanitize_error`, `_sanitize_retrieval_params`, `_allowlisted_headers`,
  `preflight`); `backend/app/services/cds.py`; and the
  `schemas/acquisition.py` validators. Every raw
  `f"{type(exc).__name__}: {exc}"` construction in `backend/app` was located and
  classified.
- Ran a fresh independent adversarial probe
  (`C:\Users\ACER\AppData\Local\Temp\opencode\audit_b8_probe.py`) covering scheme
  credentials, literal and percent-encoded URLs, malformed URLs, nested
  retrieval params and schema-level metadata/header defence-in-depth.
- Re-ran the frozen quality gates and re-hashed the committed ledger.

### 17.2 Prior findings — independently re-verified

- **H-1 / M-1 / L-1 / L-2 / L-3** (fixed §14) — re-verified; probe PASS.
- **R-1 scheme credentials** (fixed §16) — probe PASS for
  `bearer`/`basic`/`digest`/`token`/`apikey`/`api-key`, `Proxy-Authorization`,
  mixed case and multiline input.
- **R-2 percent-encoded URLs** (fixed §16) — probe PASS for single- and
  double-encoded URLs, including userinfo and fragment.
- **M-2 (CDS has no HTTP evidence)** — still **open** and documented.
  `acquire_cds` records no `request_url`/`http_status`/`response_headers`/
  `final_url`/`redirect_chain`/`provider_metadata`/`availability_*`, and
  `CdsTransport.download` remains bytes-only. ERA5-Land is **not**
  evidence-complete.

### 17.3 Findings

**R-3 (Low) — percent-encoded URL survives when a non-space prefix is attached.**
Residual of the R-2 class. `_ENCODED_TOKEN_RE = [^\s<>"'`]{8,}`, so leading
punctuation/assignment characters (`(`, `[`, `{`, `=`, `:`, …) become part of the
candidate token; after `_bounded_unquote` the decoded string no longer starts at
`https://`, so `_URL_PREFIX_RE` (`^…`) fails and the embedded secret is not
redacted. Adversarial evidence (not redacted): `(<enc>)`, `[<enc>]`,
`url=<enc>`, `url:<enc>`. Quoted forms are safe (`'`/`"` are excluded from the
token class), and the standard `requests.exceptions.InvalidURL` shape
(`… Failed to parse: <enc>`, space-separated) is safe. Reachability:
caller-supplied error text and `provider_metadata` values only — not
provider-reachable, and the planned anonymous/unsigned CHIRPS URLs carry no
secret. Minimal fix (future micro-phase): in `_encoded_url_sub`, locate an
encoded scheme anywhere in the token (e.g.
`re.search(r"(?i)(?:https?|ftp)%3a%2f%2f", token)`) or strip a small
leading-punctuation set before `_bounded_unquote`, then redact from the URL start.

**INFO-1 — `preflight()` failure message is not passed through `_sanitize_error`.**
`services/acquisition.py:673` builds
`PreflightReport(message=f"{type(exc).__name__}: {exc}")` in memory. It is not
written to the ledger, and the only source with an `endpoint_base` (COOLR) has no
credential/signature in its URL, so nothing secret is persisted today. Recommend
routing it through `_sanitize_error` for consistency.

**INFO-2 (out of acquisition scope) — `weather_provider.last_error`.**
`services/data_provider.py:71` stores a raw exception string; the OpenWeather
`_fetch_live` URL embeds `appid=<key>`, so a connection failure could place the
key in that diagnostic attribute. It is not written to any ledger and no HTTP
endpoint returns it (`/api/...` exposes only booleans/source), so it is neither
an acquisition nor a committed-provenance exposure; flagged for a future
hardening pass.

**INFO-3 (defence-in-depth) — `AcquisitionRecord.error`/`request_url`/`final_url`
have no schema-level redaction.** All current callers sanitize before
`_make_record`, so there is no leak today; a `mode="before"` sanitizer would
ensure a future caller cannot persist a raw secret through the single record
funnel.

### 17.4 Evidence-gate review

Consistent with §§3, 7, 7A and 8; no gate changed:
- **Q6** CHIRPS `available_utc` stays `EXTERNAL_EVIDENCE_REQUIRED`; the committed
  `2026-09-11T21:10:59Z` is retained (not re-dated), the transport never captured
  headers and the schema has no derivation field.
- **Q5 / Q7 / Q8 / Q9** remain external-evidence gates; **Q1–Q4 / Q10** remain
  engineering decisions/evidence as recorded.
- Source readiness: `chirps` and `era5-land` ready to acquire;
  `nasa-imerg-early` blocked (Q8); `nasa-coolr` blocked (Q9); static sources out
  of scope.
- Verdicts unchanged: historical acquisition `READY_FOR_ACQUISITION_PLANNING`;
  temporal feature computation `NEEDS_EVIDENCE`; production `NO-GO`.

### 17.5 Manifest integrity and provenance correctness

- `data/provenance/acquisition_manifest.json` **unmodified**: working-tree git
  blob `07dc2cdd36fa6772b74dcf6a7a96706d99eb593c`; content SHA-256
  `1f2b9434b199fee8809232cd8bfdf889983629d29d1546af7a2dbad747967d43`;
  `git status -- data/` clean.
- Historical values unchanged (CHIRPS `available_utc 2026-09-11T21:10:59Z`;
  ERA5-Land derived bound `2026-09-15T00:00Z`). The committed records predate the
  B.3 evidence fields, and their `error` strings contain only public provider text
  (e.g. the CDS licence URL) — no credentials or signed URLs.
- Code search confirms no `available_utc` is derived from `Last-Modified`/headers;
  `availability_classification` defaults to `unknown` in `acquire`; the
  `_state_is_coherent` validator still forbids false success.

### 17.6 Quality gates

- Focused: `python -m pytest tests/test_acquisition_rig.py
  tests/test_cds_acquisition.py -o addopts="" -q` → **79 passed** (1.52 s).
- Full: `python -m pytest -o addopts="" -q` → **263 passed**, 3 benign sklearn
  `InconsistentVersionWarning` (179.21 s).
- Secret scan (`secret_scan.py`) over **115 files** against 4 `.env` values →
  **hits=0**.
- `git diff --check` → exit 0 (only benign LF→CRLF notices).
- Adversarial probe: every realistic shape PASS; the only failures are the four
  `R-3` prefix-attached encoded-URL cases documented in §17.3.

### 17.7 Files changed by this audit

- `docs/historical-data-coverage.md` — this section.
- `C:\Users\ACER\AppData\Local\Temp\opencode\audit_b8_probe.py` — throwaway
  probe, outside the repository.
- No production/schema/test/manifest/raw/model/feature/frontend/credential/
  dependency change; nothing committed or pushed.

### 17.8 Verdict

Redaction is **fail-closed and correct for all provider-reachable exception
shapes and for the planned anonymous, unsigned CHIRPS acquisition**, and the
committed ledger is unchanged and credential-free. One **Low** residual (**R-3**)
remains in caller-supplied free text only; **M-2** (CDS evidence capture) remains
open. Q6 stays `EXTERNAL_EVIDENCE_REQUIRED`; historical acquisition stays
`READY_FOR_ACQUISITION_PLANNING` (CHIRPS/ERA5 acquisition is safe from a redaction
standpoint under the standing rule that no URL carrying credentials/signatures is
acquired until R-3/M-2 are addressed); temporal feature computation stays
`NEEDS_EVIDENCE`; production stays **`NO-GO`**.

### 17.9 Recommended next steps

1. Micro-fix **R-3** in `redact_text` (encoded-scheme search) plus one regression
   test.
2. Address **M-2** (CDS `FetchResult` evidence capture) before any
   evidence-completeness claim.
3. Capture **Q6** provider `Last-Modified` evidence during the first authorized
   CHIRPS history batch.

## 18. Phase 3.7.3B.9 — targeted R-3 percent-encoded URL redaction fix

Fixes the R-3 Low residual reported in §17.3 by changing only `redact_text` in
`backend/app/redaction.py` and adding focused regression tests. No acquisition
behavior, temporal provenance, contract version, manifest, artifact, model,
feature, frontend, credential or dependency change; no network; nothing committed
or pushed.

### 18.1 Change

`redact_text`'s encoded-URL rule no longer requires the decoded token to start at
the scheme. `_encoded_url_sub` now:

1. percent-decodes the candidate token with the existing bounded, iterative
   `_bounded_unquote` (≤ `_MAX_UNQUOTE_ROUNDS = 4`) — unchanged, no recursion or
   double decoding;
2. locates a real `https?://`/`ftp://` scheme **anywhere** in the decoded token
   (`_URL_ANYWHERE_RE`, replacing the anchored `_URL_PREFIX_RE`/`_looks_like_url`);
3. treats everything before the scheme as a literal prefix and preserves it
   verbatim;
4. strips a trailing run of `)`, `]`, `}` (`_TRAILING_URL_CLOSERS`), preserves it
   verbatim, and redacts the remaining URL with the existing fail-closed
   `redact_url` (userinfo, sensitive query values, fragment);
5. fails closed: if the decoded URL cannot be redacted it is replaced with the
   literal `REDACTED`, never with the original encoded token.

`_URL_PREFIX_RE` and the now-unused private `_looks_like_url` helper were removed
(no other references). Public interfaces are unchanged.

### 18.2 Preserved behaviour

- Ordinary text and punctuation outside the encoded URL are untouched
  (`see [<enc>]` → `see [https://…]`).
- Non-sensitive prefixed URLs are decoded/preserved, not destroyed
  (`url=<enc example.com/path>` → `url=https://example.com/path`), with no
  `REDACTED`.
- Literal-URL, scheme-credential (R-1) and percent-encoded (R-2) handling are
  unchanged.

### 18.3 Callers / interface review

`redact_text` callers, both unchanged and still receiving
`tuple[str | None, list[str]]`:
- `backend/app/services/acquisition.py:476` — `_sanitize_error` (persisted and
  re-raised error text).
- `backend/app/schemas/acquisition.py:228` — `_sanitize_provider_metadata`
  (`provider_metadata` values).
No caller imports the removed private helpers.

### 18.4 Tests

- Added four focused regressions in `tests/test_acquisition_rig.py`:
  - `test_b8_redact_text_redacts_prefixed_encoded_urls` — all four forms
    (`(…)`, `[…]`, `url=…`, `url:…`) with **userinfo credentials and a token
    query**; asserts the token, the password and `user:` are absent and the
    prefix survives.
  - `test_b8_redact_text_redacts_prefixed_encoded_query_secret` — all four forms
    with `X-Amz-Signature`; asserts `REDACTED`, that the non-sensitive `page=2`
    is retained, and that the parameter name is recorded.
  - `test_b8_redact_text_preserves_non_sensitive_prefixed_url` — punctuation and a
    non-sensitive URL preserved; no `REDACTED`; no recorded names.
  - `test_b8_redact_text_fails_closed_on_malformed_prefixed_encoded_url` — an
    unparseable decoded URL (`http://[::1?token=…`) must not return the encoded
    token.
  Assertions compare booleans/absence, so no sentinel is echoed.
- Existing R-1/R-2 tests (`test_b6_*`, `test_b7_*`) still pass.
- Focused: `python -m pytest tests/test_acquisition_rig.py
  tests/test_cds_acquisition.py` → **83 passed**.
- Full: `python -m pytest` → **267 passed**, 3 benign sklearn
  `InconsistentVersionWarning`.
- Independent adversarial probe re-run: the four §17.3 bypass cases
  (`enc-paren`, `enc-assignment`, `enc-colon`, `enc-bracket`) now PASS;
  `FAILURES: none`.
- Secret scan (`secret_scan.py`) over 115 files vs 4 `.env` values → **hits=0**.
- `git diff --check` → exit 0 (only benign LF→CRLF notices).

### 18.5 Manifest integrity and status

- `data/provenance/acquisition_manifest.json` unchanged: git blob
  `07dc2cdd36fa6772b74dcf6a7a96706d99eb593c`; content SHA-256
  `1f2b9434b199fee8809232cd8bfdf889983629d29d1546af7a2dbad747967d43`.
- HEAD `c7f6016`. Nothing committed or pushed.

### 18.6 Residual risks

- **M-2 (open):** `acquire_cds` still captures no HTTP evidence; ERA5-Land remains
  not evidence-complete.
- The §15.2 informational residuals are unchanged by design: a bare credential
  stored as a `provider_metadata` value with no `key=`/URL shape, and a secret in
  the path of an unparseable URL, remain undetectable by value-agnostic redaction.
- R-3 fix scope: detection runs on the bounded-decoded token, so a URL hidden
  behind more than four nested encodings is still not found; such a token is left
  unchanged only when no encoded scheme is present anywhere in the decoded text.
- Trailing `)`, `]`, `}` attached to an encoded URL are preserved verbatim; other
  punctuation that is genuinely part of a URL path is not otherwise re-split.

### 18.7 Verdict

R-3 is fixed and verified. Q6 remains `EXTERNAL_EVIDENCE_REQUIRED`; historical
acquisition remains `READY_FOR_ACQUISITION_PLANNING`; temporal feature computation
remains `NEEDS_EVIDENCE`; production remains `NO-GO`.

---

## 19. Phase 3.7.3C.2 — Safe CDS/ERA5-Land download evidence capture

### 19.1 Scope and design baseline

Implements the C.1 design baseline for closing the M-2 CDS artifact-download
evidence gap and fixes the credential-boundary finding it raised. No real-data
acquisition, no external network request, no manifest edit, no contract-version
change. Starting checkpoint HEAD `da21f81` with a clean working tree.

Changed files:

- `backend/app/services/cds.py` — new `CdsDownloadResult`; host-scoped download
  headers; new `download_with_evidence`; `download` now delegates (bytes API
  preserved).
- `backend/app/services/acquisition.py` — `acquire_cds` records redacted
  artifact-download evidence on success and (when a response is attached) on
  download failure.
- `backend/app/redaction.py` — `jwt` added to sensitive query/key detection.
- `backend/tests/test_cds_acquisition.py` — enriched fakes plus 12 new tests.

`backend/app/schemas/acquisition.py` was **not** changed: the Phase 3.7.3B.3
evidence fields are already additive/optional, so CDS records simply begin
populating them.

### 19.2 Credential-boundary finding and fix

**Finding (C.1):** `CdsTransport.download` sent `self._headers()` by default,
i.e. the CDS Personal Access Token (`PRIVATE-TOKEN`) was forwarded to the
artifact `href` host, which is commonly a pre-signed third-party CDN and is not
an authorized CDS API origin.

**Fix:** `CdsTransport._download_headers(url)` now compares the asset URL's
hostname (case-insensitive) with the configured CDS API hostname
(`urlsplit(api_url).hostname`) and forwards `PRIVATE-TOKEN` **only** when they
match; otherwise it sends just `Accept: */*`. The control plane (`submit`,
`poll`, `results`) still uses `_headers()` and therefore still authenticates.
No network call is made to verify domains, and a malformed/empty host is treated
as external (token withheld). Tests prove the token is absent from the external
host request and still present on control-plane and same-origin requests.

### 19.3 Implementation

- `CdsDownloadResult` (frozen) carries `content`, `status_code`, `headers`,
  `final_url`, `redirect_chain`. Bytes are returned unmodified.
- `CdsTransport.download_with_evidence(url, headers=None)` uses the existing
  single `requests.get` flow, calls `raise_for_status()`, and returns the result
  with `response.url` / `response.history`. `CdsTransport.download` returns
  `download_with_evidence(...).content`, preserving its public bytes contract.
- `AcquisitionDriver.acquire_cds` redacts `asset["href"]` once
  (`request_url`, `request_redactions`), downloads with evidence, then records:
  `request_url` (redacted), `request_method="GET"`, `http_status`,
  `response_headers` (allowlist only via `_allowlisted_headers`), `final_url`
  (redacted), `redirect_chain` (redacted via `_redact_chain`), minimal
  string-valued `provider_metadata` (`dataset`, `job_id`, and `asset_type` when
  present), and merged `redacted_params`.
- Download-failure path: `request_url` + `request_method` are always recorded,
  but `http_status`/`response_headers` are recorded **only** when the exception
  carries a real `.response`; no status/header/redirect value is ever fabricated.
- `available_utc` is never derived from `Date`, `Last-Modified`, filesystem time
  or retrieval time; those headers are stored only as response evidence, and
  `availability_classification` stays unset unless the caller supplies it.

### 19.4 Redaction

`jwt` is now in `SENSITIVE_KEY_SUBSTRINGS`, `_SENSITIVE_QUERY_RE` and
`_KV_IN_TEXT_RE`, so `token`, `jwt`, `sig` and `X-Amz-Signature` (which already
matched `signature`) are redacted from request/final URLs, redirect hops,
provider metadata and serialized records. Authorization/cookie headers remain
outside the persisted allowlist, and CDS exception text still passes through
`_sanitize_error` → `redact_text`. The R-1/R-2/R-3 redaction tests were not
weakened; all remain green.

### 19.5 Test matrix and results

Twelve new offline tests (fake transports, fake responses, monkeypatched
`requests.get` only):

1. `download_with_evidence` returns content plus status/headers/final URL/redirect chain.
2. `download()` backward-compatible bytes (`test_download_returns_bytes`, kept).
3. `acquire_cds` records full artifact-download evidence.
4. External-host token isolation (no `PRIVATE-TOKEN`), and same-origin token retention.
5. Control plane still authenticated.
6. Signed URL/redirect redaction (`token`/`jwt`/`sig`/`X-Amz-Signature`/`X-Amz-Credential` absent from the serialized manifest).
7. Download HTTP failure: failed record, sanitized error, no artifact written.
8. Download failure with a response object records status + allowlisted headers only.
9. CDS control-plane exception text sanitized.
10. Manifest contract version stays `1.1.0`.
11. `Date`/`Last-Modified` captured only as evidence; `available_utc` stays `None`.
12. Artifact bytes/SHA-256/byte count identical.

Results:

- `python -m pytest tests/test_acquisition_rig.py tests/test_cds_acquisition.py`
  → **95 passed** (was 83).
- `python -m pytest` → **279 passed**, 3 benign sklearn `InconsistentVersionWarning` (was 267).
- Secret scan → 117 files vs 4 `.env` values, **hits=0**.
- `git diff --check` → exit 0.

### 19.6 Manifest integrity and contract

- `data/provenance/acquisition_manifest.json` unchanged: git blob
  `07dc2cdd36fa6772b74dcf6a7a96706d99eb593c`; content SHA-256
  `1f2b9434b199fee8809232cd8bfdf889983629d29d1546af7a2dbad747967d43`.
- `contract_version` remains `1.1.0`; no bump was necessary because all evidence
  fields were already optional and legacy records load unchanged.
- HEAD remains `da21f81`; nothing staged, committed or pushed.

### 19.7 Residual risks

- **M-2 status:** the code-level gap M-2 identified (CDS records no
  `request_url`/`http_status`/`response_headers`/`final_url`/`redirect_chain`;
  `download` returns bytes only) is now **closed and test-verified**. ERA5-Land
  is still **not** claimed evidence-complete: publication/availability evidence
  depends on provider semantics that no HTTP header supplies (Q6), so the
  external-evidence blocker stands.
- Credential boundary: the PAT is withheld from external hosts, but a same-host
  artifact URL still receives it (treated as the configured API origin). If the
  CDS API and its CDN ever share a host, that co-location would need
  re-verification.
- Value-agnostic redaction limits are unchanged: a secret embedded as a URL
  *path* segment, an unrecognized query name (not matching the sensitive
  substrings), or more than four nested percent-encodings can still survive.
- `provider_metadata` for CDS is limited to non-secret identifiers; the signed
  asset `href` is never stored.

### 19.8 Verdict

The credential-boundary defect is fixed and the CDS artifact-download evidence
gap is implemented and verified. Q6 remains `EXTERNAL_EVIDENCE_REQUIRED`;
historical acquisition remains `READY_FOR_ACQUISITION_PLANNING`; temporal feature
computation remains `NEEDS_EVIDENCE`; production remains `NO-GO`.

---

## 20. Phase 3.7.3C.3 — Final CDS credential boundary audit

### 20.1 Scope and method

Independent audit of the uncommitted C.2 changes, on the assumption that passing
tests alone do not prove safety. The full implementations of `_download_headers`,
`download_with_evidence`, `download`, the CDS redirect path and `acquire_cds`
were read; the credential boundary was re-derived from first principles rather
than trusted. No real network request or real credential was used.

### 20.2 Findings (hostname-only matching was insufficient)

The C.2 policy attached the Personal Access Token (PAT) whenever
`urlsplit(url).hostname == api_hostname`. Three gaps were found:

- **F-1 (High) — scheme ignored (HTTPS→HTTP downgrade).** A same-host URL on
  `http://` matched and received the PAT, sending the credential in plaintext.
- **F-2 (High) — redirects could forward the PAT off-origin.** `requests` follows
  redirects by default and (unlike `Authorization`) does **not** strip a custom
  `PRIVATE-TOKEN` header on a cross-host redirect. A trusted-origin download that
  redirected to an external host would therefore leak the PAT to that host.
- **F-3 (Medium) — port and path ignored.** Any URL on the API hostname, on any
  port or path (e.g. `:8443`, `/other`), received the PAT; same-hostname was
  treated as enough justification on its own.

### 20.3 Implemented policy (strict trusted origin + safe redirects)

Documented behavior change (from C.2's hostname-only rule, per §19.7) to a strict
trusted-origin policy. A download URL receives the PAT only when **all** hold:

- scheme is `https` and equals the configured API scheme;
- hostname equals the configured API hostname;
- effective port equals the configured API port (default 443/80 when omitted);
- path is at or below the configured API base path (`api_url` path; whole host
  when the configured base path is empty).

In addition, `download_with_evidence` now follows redirects **manually**
(`allow_redirects=False`, bounded to 10 hops), recomputing `_download_headers`
on every hop. A redirect that leaves the trusted origin (external host, http
downgrade, different port, off-path URL) therefore drops the PAT and cannot
carry it outwards. Redirect-hop URLs are still captured (for redacted evidence)
and `download()` still returns the original bytes unchanged. Control-plane
`submit`/`poll`/`results` continue to authenticate unchanged.

### 20.4 Tests added (offline, fake responses only)

- `download_with_evidence` follows a redirect and captures content, status,
  headers, final URL and ordered redirect chain.
- PAT is absent for a different hostname; present within the trusted origin.
- PAT is absent for an off-path same-host URL, a different port, and an
  `http://` downgrade (F-1/F-3 regressions).
- A trusted-origin download redirecting to an external host does **not** forward
  the PAT on the second hop; every hop is issued with `allow_redirects=False`
  (F-2 regression).
- A redirect loop beyond the bound raises `CdsApiError`.
- Control plane still sends the token.

### 20.5 Evidence and redaction re-verification

Re-confirmed from the C.2 implementation: `request_url`/`final_url`/redirect hops
are redacted via `redact_url`/`_redact_chain` before persistence; response
headers are allowlisted (`last-modified`/`etag`/`date`) and bounded; PAT, cookies
and `Authorization` are never persisted; exceptions pass through
`_sanitize_error`; `http_status`/`response_headers` are recorded on failure only
when a real `.response` exists; `Date`/`Last-Modified` are evidence only and
never populate `available_utc`; `download()` returns the unmodified bytes; the
contract remains `1.1.0`; artifact content, SHA-256 and byte count are
unchanged; the manifest is untouched.

### 20.6 Verification (from `backend/`)

- `python -m pytest tests/test_acquisition_rig.py tests/test_cds_acquisition.py`
  → **100 passed**.
- `python -m pytest` → **284 passed**, 3 benign sklearn `InconsistentVersionWarning`.
- Secret scan → 117 files vs 4 `.env` values, **hits=0**.
- `git diff --check` → exit 0.

### 20.7 Residual risks

- **Control-plane redirects** (`submit`/`poll`/`results`) still use default
  redirect following. Those URLs are constructed from the configured trusted
  base, so an external redirect would require the CDS API host itself to
  misbehave; the PAT could then be re-sent because `requests` does not strip
  `PRIVATE-TOKEN`. Left unchanged as out of scope for the asset-download
  boundary and documented here.
- Value-agnostic redaction limits are unchanged: a secret embedded as a URL
  **path** segment, under an **unrecognized** query name, or behind more than
  four nested percent-encodings may remain undetectable. No claim of arbitrary
  secret detection is made.
- If the configured API base path is empty, the whole hostname is treated as the
  trusted origin (the configured origin genuinely is that host).
- M-2's code-level evidence gap remains closed; ERA5-Land is still **not**
  claimed evidence-complete.

### 20.8 Verdict

The C.2 hostname-only credential boundary was insufficient; the strict
trusted-origin policy plus manual per-hop redirect scoping closes F-1/F-2/F-3
and is test-verified. Q6 remains `EXTERNAL_EVIDENCE_REQUIRED`; historical
acquisition remains `READY_FOR_ACQUISITION_PLANNING`; temporal feature computation
remains `NEEDS_EVIDENCE`; production remains `NO-GO`.

---

## 21. Phase 3.7.3C.4 — Final redirect and trusted-origin audit

### 21.1 Scope and method

Continuing audit of the uncommitted C.2/C.3 changes on the assumption that a
passing suite does not prove every security boundary. The C.3 work scoped
`PRIVATE-TOKEN` to a strict trusted origin for **artifact downloads** only; the
C.4 audit re-derived the control plane (`submit`/`poll`/`results`), the
trusted-origin validator and the API URL configuration from first principles.
No real network request or credential was used.

### 21.2 Findings

- **G-1 (High) — control-plane redirects could forward the PAT.** `submit`
  (POST), `poll` and `results` (GET) used `requests` default redirect following.
  `requests` strips only `Authorization` (not a custom `PRIVATE-TOKEN`) on a
  cross-host redirect, and a 301/302/303 can silently downgrade a POST to GET.
  A trusted-origin endpoint that responded 30x to a hostile location would leak
  the PAT to that host or carry it over an HTTPS-to-HTTP downgrade. The C.3
  residual-risk note (§20.7) is now **closed**.
- **G-2 (Medium) — trusted-origin path check could be bypassed by dot segments
  and confused by encoded separators.** `_in_trusted_path` compared the raw
  path: `/api/../other` *startswith* `/api/` and would have been treated as
  trusted while resolving to an off-path location, and an encoded separator
  (`%2f`/`%5c`) could be decoded to `/` by a server. Userinfo and malformed
  ports were not covered either.
- **G-3 (Low) — no configuration validation.** `CdsTransport` would accept a
  plaintext `http://` or hostless API URL and then silently send the PAT over
  it.

### 21.3 Fixes (smallest safe changes, `backend/app/services/cds.py`)

- **Control plane rejects redirects explicitly.** `submit`/`poll`/`results` now
  pass `allow_redirects=False`; `requests` never contacts the redirect target,
  so the PAT cannot follow a 30x off-origin or downgrade hop. A 3xx response is
  surfaced as `CdsApiError`. This is a behavior change: previously a redirect
  would be transparently followed. The change is safe because the documented
  CDS retrieve endpoints issue no redirects; not following one fails loudly
  instead of leaking the credential. Control-plane authentication itself is
  unchanged.
- **Trusted-origin normalization.** `_normalized_path` is applied before the
  base-path comparison: percent-escapes are decoded, literal and decoded
  `.`/`..` dot segments are collapsed via `posixpath.normpath`, and a path that
  is ``None`` (encoded `%2f`/`%5c` separator present) is rejected as untrusted.
  `_is_trusted_url` catches malformed URLs and invalid ports (returning False
  instead of raising), and compares scheme/host/effective-port exactly. An
  explicit `:443` (or default port) matches the configured port; anything else
  does not.
- **Configuration validation.** `CdsTransport.__init__` now raises `CdsError`
  unless `api_url` is a valid **https** URL with a host; an explicit port is
  validated by `urlsplit`. Previously an `http://` or hostless API URL was
  silently accepted.

### 21.4 Trust semantics of an empty base path

If the configured `api_url` has no path (e.g. `https://cds.example.invalid`),
the trusted path is empty and **the whole scheme/host/port origin is trusted**.
This cannot be broadened — an empty base path accepts the configured origin and
only the configured origin. It is tested and documented rather than silently
widened. A path with a trailing slash is normalized to its trimmed base (the
URLs `…/api` and `…/api/…` are both trusted, off-path siblings are not).

### 21.5 Evidence and redaction re-verification

No changes were needed to the C.2 evidence/redaction implementation; the
existing regression tests still pass unchanged:

- persisted `request_url`/`final_url`/`redirect_chain` are redacted;
  `jwt`/`token`/`sig` and `X-Amz-*` query parameters are stripped (§19);
- response headers stay allowlisted (`last-modified`/`etag`/`date`) and bounded;
- PAT/cookies/`Authorization`/signed URL values are never persisted;
- failure records carry `http_status`/`response_headers` only when a real
  `.response` exists (never fabricated);
- `download()` returns the exact original bytes; downloaded bytes, recorded
  SHA-256 and byte count are unchanged; the manifest is untouched;
- `available_utc` is **never** derived from `Date`, `Last-Modified`, retrieval
  time or filesystem timestamps;
- contract version remains `1.1.0`.

### 21.6 Regression tests added (offline, `backend/tests/test_cds_acquisition.py`)

Control-plane redirect rejection:

- `poll` with a cross-host 302 → `CdsApiError`, exactly one request,
  `allow_redirects=False`.
- `results` with an HTTPS-to-HTTP 301 → `CdsApiError`, one request.
- `poll` with a 307 to an unexpected port → `CdsApiError`, one request.
- `submit` with a self-referencing 308 loop → `CdsApiError`, one request.
- `poll`+`results` success still send `PRIVATE-TOKEN` with `allow_redirects=False`.

Trusted-origin matrix (parametrized, `_is_trusted_url`):

- exact base, base-with-trailing-slash, `:443` explicit, on-path → trusted.
- sibling `/apix`, off-path root, other host, `:8443`, `http` downgrade,
  `%2F`/`%5C` encoded separators, `/api/../other` dot-segment escape → not
  trusted. `/api/./retrieve/x` normalizes to trusted.
- userinfo does not change the host (`attacker@host` trusted, `host@evil`
  untrusted); malformed port and non-URL strings → untrusted, no exception.
- trailing-slash configuration and an empty base path (whole-origin trust).
  Config validation: `http://`, hostless, schemeless and bad-port API URLs
  raise `CdsError`.

### 21.7 Verification (from `backend/`)

- `python -m pytest -o addopts="" tests/test_acquisition_rig.py tests/test_cds_acquisition.py`
  → **129 passed**.
- `python -m pytest -o addopts=""` → **313 passed**, 3 benign sklearn
  `InconsistentVersionWarning`.
- Secret scan (`C:\Users\ACER\AppData\Local\Temp\opencode\secret_scan.py`)
  → 117 files vs 4 `.env` values, **hits=0**.
- `git diff --check` (repo root) → **exit 0**.

### 21.8 Manifest integrity

- `data/provenance/acquisition_manifest.json`: unchanged, git blob
  `07dc2cdd36fa6772b74dcf6a7a96706d99eb593c`, content SHA-256
  `1f2b9434b199fee8809232cd8bfdf889983629d29d1546af7a2dbad747967d43`.
- HEAD `da21f81ca76a8f886e87b7d9a8ed55a7fb7326cc`; nothing staged, committed or
  pushed.

### 21.9 Remaining security limitations

- **Value-agnostic redaction limits are unchanged:** a secret embedded as a URL
  **path** segment, under an **unrecognized** query name, or behind more than
  four nested percent-encodings can still survive. The redactor flags sensitive
  names and URL-shaped values; it is not an arbitrary secret finder.
- **Trusted-origin path check is defense-in-depth only.** The scheme/host/port
  comparison is the actual credential gate; the path check never broadens it,
  but a path lookup is only as meaningful as the server's own decoding. If the
  CDS API and its artifact host ever share an origin and a path, co-location
  semantics would need re-verification.
- **No real acquisition evidence is claimed.** External ERA5-Land
  publication/availability evidence (Q6) has not been verified and predictive
  accuracy is not established.

### 21.10 Verdict

The control-plane redirect leak (G-1) is closed: 3xx redirects, or a redirect
that tried to change origin or downgrade to HTTP, are now rejected explicitly so
the PAT can never follow them. The trusted-origin validator (G-2) and API URL
configuration (G-3) are hardened and covered by an offline test matrix. Q6
remains `EXTERNAL_EVIDENCE_REQUIRED`; historical acquisition remains
`READY_FOR_ACQUISITION_PLANNING`; temporal feature computation remains
`NEEDS_EVIDENCE`; production remains `NO-GO`.

---

## 22. Phase 3.7.4A — Historical data evidence gap audit

### 22.1 Scope and method

Evidence-only audit (no acquisition, no model/feature expansion). Goal: establish
exactly which historical-data provenance requirements remain unverified for the
existing CHIRPS and ERA5-Land artifacts. Everything below is derived from
committed repository evidence only — code, schema, ledger, tests, and this
document. No provider source was re-inspected during this phase; where a claim
needs provider-issued evidence it is stated as unresolved, never as verified.

### 22.2 Artifact inventory (repository evidence only)

| # | artifact | status | storage_path | sha256 | size |
|---|----------|--------|--------------|--------|------|
| 1 | `chirps-v2.0.2026.08.31.tif.gz` | downloaded | `chirps/chirps__v2.x__2026-08-31.tif.gz` | `44934651…` | 10,288,665 B |
| 2 | ERA5-Land hourly `2026-07-15t0000.nc` | downloaded | `era5-land/era5-land__…2026-07-15t0000.nc` | `af53a81a…` | 127,970 B |

Both files exist on disk under `data/raw/real/` (git-ignored); the ledger
(`data/provenance/acquisition_manifest.json`) is the committed record of six
attempts (1 CHIRPS success, 4 ERA5-Land failures honestly recorded, 1 ERA5-Land
success).

### 22.3 The four time concepts, separated

| concept | meaning | CHIRPS | ERA5-Land |
|---------|---------|--------|-----------|
| `observation_start_utc`/`end` | measurement window | `[2026-08-31T00:00Z, 2026-09-01T00:00Z)` (daily) | `[2026-07-15T00:00Z, 2026-07-15T01:00Z)` (hourly) |
| provider availability / vintage | when the exact vintage became public | `2026-09-11T21:10:59Z` | `2026-09-15T00:00:00Z` |
| `retrieved_utc` | when we asked for the bytes | `2026-10-08T09:28:03Z` | `2026-10-08T11:09:48Z` |
| `acquired_utc` | when registered in the ledger | `2026-10-08T09:28:21Z` | `2026-10-08T11:09:48Z` |
| prediction cutoff | when model inputs would be frozen | request-supplied | request-supplied |

The code never conflates these: `available_utc` is caller/rule-supplied into
`AcquisitionDriver.acquire` (`acquisition.py:780`) and `acquire_cds`
(`acquisition.py:969`) and is never parsed from HTTP `Date`/`Last-Modified`;
`retrieved_utc`/`acquired_utc` are always local access times. Verified by the
audit sub-report and existing tests (`test_cds_acquisition.py:809-823`).

### 22.4 Per-timestamp evidence classification

Legend: **V** = independently verified provider evidence; **R** =
repository-derived evidence; **E** = engineering assumption; **X** = unresolved /
external evidence required.

| timestamp | support | class | basis |
|-----------|---------|-------|-------|
| CHIRPS observation window | filename (`chirps-v2.0.2026.08.31`), product semantics (v2 = start-of-UTC-day), file inspection | **R** | contradicts nothing; ±1-day offset risk documented in `known_limitations` |
| CHIRPS `available_utc 2026-09-11T21:10:59Z` | present only in ledger/test fixtures; `Last-Modified` never captured at acquisition; no in-repo derivation | **X** (possibly E) | wholly unresolved (Q6). Matches a test-only `Date` header string but that is coincidence repeated in fixtures, not a derivation |
| CHIRPS `retrieved_utc`/`acquired_utc` | committed ledger timestamps | **R** | we performed the retrieval on 2026-10-08 |
| ERA5-Land observation window | CDS job request (`year/month/day` 2026-07-15, `time` 00:00) + file `valid_time` 2026-07-15T00:00Z | **R** | hourly half-open interval |
| ERA5-Land `available_utc 2026-09-15T00:00:00Z` | ledger note: "DERIVED conservative bound; CDS exposes no per-vintage availability timestamp; consolidated ~2 months per registry" | **E** | conservative bound, not provider-issued (Q7) |
| ERA5-Land `retrieved_utc`/`acquired_utc` | committed ledger (`2026-10-08T11:09:48Z`) | **R** | we performed the retrieval |

**Neither availability timestamp is independently verified provider evidence.**
This matches the standing decisions: Q6 (`EXTERNAL_EVIDENCE_REQUIRED`) and Q7
(`EXTERNAL_EVIDENCE_REQUIRED`).

### 22.5 Official sources still required

- **CHIRPS (`chirps-v2.0.2026.08.31`):** any one of (a) the exact file's
  provider HTTP `Last-Modified` or directory-listing timestamp captured at
  retrieval time with URL and status; (b) CHC publication-schedule
  documentation for FINAL v2 daily files; or (c) ERDDAP catalog metadata for
  that file. The provider publication/cadence statement in the ledger is a
  statement about data currency, not this file's publication instant.
- **ERA5-Land (vintage 2026-07-15 00:00):** a provider-issued per-vintage
  availability timestamp, or a documented, versioned conservative rule with a
  measured safety margin and audit trail (production), vs. the labelled derived
  bound (research/replay only, per Q7 acceptance conditions).

### 22.6 Audit: does code/tests treat a guessed available_utc as authoritative?

Read of `backend/app/services/features.py` and `backend/app/schemas/*`:

- `evaluate_leakage` (`features.py:121-141`) rejects only when
  `available_utc is not None and available_utc > prediction_cutoff_utc`
  (line 139). It never inspects `availability_classification`.
- `FeatureProvenance.available_utc` is copied verbatim from the record
  (`build_feature_provenance`, `features.py:391`); the feature schema carries no
  classification field.
- `AcquisitionRecord.availability_classification` (`schemas/acquisition.py:169`)
  is a bare `Literal`, defaults `None`, and no validator requires it whenever
  `available_utc` is set. The two committed REAL records both carry
  `available_utc` with **no** classification.

**Finding G-4 (documented, not "fixed"):** the leakage gate and the feature
contract are classification-blind — a `derived` or unverified `available_utc`
clears a cutoff exactly like a `provider_issued` one, and an unclassified
`available_utc` is indistinguishable downstream from a verified one. Separately,
when `available_utc` is `None` the vintage rule is skipped, so missing provider
evidence is never converted into a verified timestamp but is also not treated as
leaky on its own. No app code was changed; the behavior is pinned by regression
tests so a future classification-aware gate must update them.

### 22.7 Regression tests added (offline)

`backend/tests/test_feature_contract.py`:

- `test_available_utc_can_be_unclassified_and_gate_is_classification_blind` —
  schema accepts available_utc without classification (as the committed REAL
  records do); `derived` and `provider_issued` classifications produce identical
  `evaluate_leakage` outcomes (VALID ≤ cutoff, REJECTED > cutoff).
- `test_unknown_availability_is_not_fabricated_and_not_rejected` —
  `available_utc=None` keeps the vintage rule inactive; no timestamp is
  fabricated, and the observation-window rule alone decides.

### 22.8 Verification

- `python -m pytest -o addopts="" tests/test_feature_contract.py tests/test_acquisition_rig.py tests/test_cds_acquisition.py`
  → **171 passed**.
- Manifest: blob `07dc2cdd36fa6772b74dcf6a7a96706d99eb593c`, SHA-256
  `1f2b9434b199fee8809232cd8bfdf889983629d29d1546af7a2dbad747967d43`
  (unchanged); contract version `1.1.0` (unchanged); artifacts on disk
  unchanged.
- HEAD `0a1bd19ddafb8d11575c0a0ac22adaafd6987a5f`; only intended working-tree
  changes (test file + this section).

### 22.9 Verdict

Both `available_utc` values remain `EXTERNAL_EVIDENCE_REQUIRED` (unverified /
derived); the classification-blind gate (G-4) is documented and pinned, and no
missing provider evidence has been converted into a verified timestamp. Q6 remains
`EXTERNAL_EVIDENCE_REQUIRED`; historical acquisition remains
`READY_FOR_ACQUISITION_PLANNING`; temporal feature computation remains
`NEEDS_EVIDENCE`; production remains `NO-GO`. No external ERA5-Land or CHIRPS
publication/availability evidence is claimed.

## 23. Phase 3.7.4B — Availability provenance gate (G-4 resolution)

### 23.1 Problem (restates 22.6 G-4)

`evaluate_leakage` (`backend/app/services/features.py:121-141`) decided leakage
from the raw `available_utc` value only; it never inspected
`AcquisitionRecord.availability_classification`, `FeatureProvenance` carried no
classification field, and when `available_utc` was `None` the vintage rule was
skipped. A derived or unclassified timestamp therefore cleared a prediction
cutoff exactly like a `provider_issued` one, and the feature-layer output gave a
downstream consumer no way to tell the difference.

### 23.2 Design decision (implemented, backward compatible)

- `evaluate_leakage` is kept unchanged as the pure **time rule** (observation
  window and product vintage at or before the cutoff; deterministic).
- A second deterministic gate, `evaluate_availability_policy(record, *,
  availability_policy)` (`services/features.py`), consults the record's
  `availability_classification`. `run_extraction` now applies both gates.
- `FeatureExtractionRequest.availability_policy`
  (`Literal["research_replay", "production"]`, default `"research_replay"`) is
  an **additive** optional field. The default preserves the pre-Phase 3.7.4B
  default behaviour for every record that carries a timestamp; `production` is
  the strict, opt-in policy.
- `FeatureProvenance.availability_classification` (additive, default `None`) is
  copied verbatim from the acquisition record, so a research/replay feature made
  from a derived/unknown/unclassified timestamp is visibly labelled instead of
  being presented as provider-issued.
- The feature contract stays **1.0.0** (additions are additive, per the module
  docstring policy). The acquisition manifest and its contract **1.1.0** are not
  touched; no record, artifact bytes, or schema field is removed or renamed.

### 23.3 Acceptance policy (one dimension per policy)

| `available_utc` | `availability_classification` | research_replay | production | feature output label |
|---|---|---|---|---|
| present | `provider_issued` | usable | usable | `provider_issued` |
| present | `derived` | usable | `rejected_leakage` | `derived` |
| present | `unknown` | usable | `rejected_leakage` | `unknown` |
| present | `None` (unclassified) | usable | `rejected_leakage` | `None` |
| `None` | any | `rejected_leakage` | `rejected_leakage` | — |

The per-case rationale mapped to the task-framed cases:

1. **`provider_issued`** — the only evidence that clears a production gate; the
   pure time rule still applies on top.
2. **`derived`** — a conservative estimate, never a measured publication
   instant; usable for research/replay only and always labelled `derived`.
   Production rejects it: a derived vintage must not silently pass.
3. **`unknown`** — exactly the "QR" case explored in §22.4/§22.5; usable for
   research/replay only, labelled `unknown`.
4. **`None` (unclassified) with a timestamp** — the committed REAL record state;
   usable for research/replay only, output labelled `None` (unclassified). This
   is the crux of G-4: unclassified today is indistinguishable-from-verified
   downstream, so production refuses it while research/replay keeps working and
   labels the gap.
5. **missing timestamp (`available_utc=None`)** — rejected under **both**
   policies. A cutoff can only be placed against a timestamp that exists; absent
   evidence is never fabricated into a verified timestamp and never treated as
   provably non-leaky. This hardens the Phase 3.7.4A finding that `None`
   silently skipped the vintage rule.
6. **legacy/synthetic records** — land under cases 4-5 by their fields; no
   separate code path exists or is needed. `AcquisitionRecord` is unchanged, so
   any previously loadable ledger loads identically.

### 23.4 Behaviour changes and superseded regressions

`backend/tests/test_feature_contract.py`:

- **Superseded** `test_available_utc_can_be_unclassified_and_gate_is_classification_blind`
  (Phase 3.7.4A): it pinned the classification-blind behaviour (identical
  outcomes for derived/unclassified/provider_issued). It is replaced by the
  one-dimensional policy rules in §23.3. Superseding is intentional and
  documented here; a test that pins a known unsafe behaviour must not be kept
  once the design fixes it.
- **Superseded** `test_unknown_availability_is_not_fabricated_and_not_rejected`
  (Phase 3.7.4A): the missing-timestamp case now returns `rejected_leakage` under
  both policies. The "never fabricated" guarantee is kept (the record's
  `available_utc` stays `None`).

No other behaviour changed: the default `research_replay` policy still extracts
every committed REAL record (both carry `available_utc`; both are unclassified),
and all pre-existing leakage, determinism, nodata, schema, and real-artifact
tests pass unchanged.

### 23.5 Impact on the current committed data

- **CHIRPS** (`available_utc 2026-09-11T21:10:59Z`, classification `None`):
  research/replay usable, output labelled unclassified; production `rejected_leakage`
  until Q6 is resolved to provider-issued evidence and the record is classified
  `provider_issued`.
- **ERA5-Land** (`available_utc 2026-09-15T00:00Z`, classification `None`; the
  ledger note states this value is a DERIVED conservative bound): research/replay
  usable, output labelled unclassified (honest bound, not asserted as
  provider-issued); production `rejected_leakage` until Q7 is resolved.

### 23.6 Q6/Q7 naming consistency note

The decision register (§3, §7A) assigns **Q6 = CHIRPS** availability derivation
evidence and **Q7 = ERA5-Land** availability evidence, both
`EXTERNAL_EVIDENCE_REQUIRED`. Earlier sections (§19.7, §21.9) used "Q6" loosely
for both sources. This section does not relabel anything; the canonical mapping
to use going forward is **Q6 = CHIRPS, Q7 = ERA5-Land**.

### 23.7 Tests added (offline)

- `test_production_policy_rejects_unverified_availability`
- `test_production_policy_rejects_missing_timestamp`
- `test_production_policy_accepts_provider_issued_before_cutoff`
- `test_research_policy_accepts_labelled_availability`
- `test_research_policy_rejects_missing_timestamp`
- `test_provenance_carries_availability_classification`
- `test_run_extraction_default_research_policy_labels_output`
- `test_run_extraction_production_gate_rejects_unverified`
- `test_run_extraction_production_gate_accepts_provider_issued`

### 23.8 Verification

- Focused:
  `python -m pytest -o addopts="" tests/test_feature_contract.py tests/test_acquisition_rig.py tests/test_cds_acquisition.py`
  → **178 passed** (3.7.4A: 171; −2 superseded + 9 added).
- Full: `python -m pytest -o addopts=""` → **322 passed** (3.7.4A: 315; +7 net),
  3 benign sklearn `InconsistentVersionWarning` (pre-existing, unchanged).
- Manifest: blob `07dc2cdd36fa6772b74dcf6a7a96706d99eb593c`, SHA-256
  `1f2b9434b199fee8809232cd8bfdf889983629d29d1546af7a2dbad747967d43`
  (unchanged); contract versions unchanged (manifest `1.1.0`, feature `1.0.0`).
- Secret scan: 117 files / 4 `.env` values → 0 hits (unchanged).
- `git diff --check` clean; `FEATURE_CONTRACT_VERSION` and manifest untouched.

### 23.9 Verdict

G-4 is resolved at the feature layer: an unverified timestamp can no longer
silently clear a production-grade gate, missing availability evidence can no
longer clear any gate, and research/replay output now labels the strength of the
availability evidence it used. Production remains **NO-GO** for both committed
artifacts (neither record is `provider_issued`); temporal feature computation
remains `NEEDS_EVIDENCE` for production-grade features; Q6/Q7 remain
`EXTERNAL_EVIDENCE_REQUIRED`. No external publication/availability evidence is
claimed anywhere in this phase.

## 24. Phase 3.7.4C — Availability policy integration & release-safety audit

### 24.1 Scope and method

Read-only audit plus minimal, justified hardening. Goal: prove that
`evaluate_availability_policy()` (added in §23 / Phase 3.7.4B) is actually
reached by every production-grade feature-extraction path, and that no
bypass exists. Method: repository grep across all Python sources, API route
files, CLI/jobs/batch/training/evaluation/replay entry points, and the schema
exports; direct runtime checks of default, invalid-policy and serialization
behaviour; regression tests only where a genuine gap was found.

### 24.2 Working-tree integrity at start

- HEAD `0a1bd19ddafb8d11575c0a0ac22adaafd6987a5f` (expected; unchanged all phase).
- Modified files: exactly the four intended Phase 3.7.4A/3.7.4B files
  (`backend/app/schemas/features.py`, `backend/app/services/features.py`,
  `backend/tests/test_feature_contract.py`, `docs/historical-data-coverage.md`).
- Manifest: blob `07dc2cdd36fa6772b74dcf6a7a96706d99eb593c` (`git hash-object`),
  SHA-256 `1f2b9434b199fee8809232cd8bfdf889983629d29d1546af7a2dbad747967d43`,
  contract **1.1.0**; file unmodified.
- Feature contract stays **1.0.0** (all additions additive).

### 24.3 Entry points inspected and their effective policy

`git grep` for `run_extraction`, `evaluate_leakage`, `evaluate_availability_policy`,
`FeatureExtractionRequest`, `FeatureProvenance`, and the REAL readers
(`read_chirps_grid` / `read_era5_land_variables`) over every source, excluding
tests and docs:

| entry point | kind | effective policy | verdict |
|---|---|---|---|
| `app/services/features.py::run_extraction` | the only feature-extraction path | `research_replay` (default) unless the caller sets `production`; both gates run inside | gate enforced; production is opt-in |
| `app/api/prediction.py` `/api/predict`, `/api/predict/location/{id}` | demo inference | does **not** call `run_extraction`; feeds `predictor.predict` from `weather_provider` (DEMO/OpenWeather) | out of scope of the REAL contract; no feature extraction |
| `app/api/*` (locations, alerts, analytics, auth, admin, health) | demo CRUD/telemetry | no feature-extraction call | no bypass |
| `ml/train.py`, `ml/evaluate.py`, `ml/data/generate_data.py` | demo training/eval | use `data/historical_landslide_data.csv` + sklearn; no `run_extraction`, no REAL readers | no bypass |
| `app/ml/predictor.py`, `app/risk.py` | demo inference services | rule/RandomForest on DEMO features | no bypass |

There are **no CLI, scheduled jobs, batch, replay or evaluation entry points**
anywhere in the repository that consume the feature contract; the only non-test
reference to `FeatureExtractionRequest`/`FeatureProvenance` outside the feature
module is the schema re-export in `backend/app/schemas/__init__.py`. The feature
layer remains, by its own contract (`schemas/features.py` module docstring),
"wired into neither the DEMO prediction path, the ML model, any API route, nor
the UI" — this audit confirms that statement is still true.

**Conclusion: consistent enforcement.** Every code path that can produce REAL
features goes through `run_extraction`, and `run_extraction` always evaluates
both gates (time gate + availability-evidence gate) before any decode/sampling.
There is no second path into the readers: `_read_source_features` is the only
caller of the decoders and is itself reachable only after both gates pass.
Because no production entry point exists yet, none can today "inherit the
research default" silently.

### 24.4 Request, default and persistence validation

- **Default is explicit.** `FeatureExtractionRequest.availability_policy`
  defaults to `"research_replay"` (schema field, additive). Verified at runtime.
- **Production is opt-in.** Any future production caller must pass
  `availability_policy="production"` explicitly; the schema `Literal` has no
  coercive casing, so typo'd values cannot sneak in as research.
- **Invalid values fail closed (twice).** (a) At the typed boundary,
  `availability_policy="PRODUCTION"` / `"prod"` raises pydantic
  `ValidationError` (verified at runtime; new test). (b) At the pure-function
  boundary, `evaluate_availability_policy` now raises `FeatureContractError`
  for any value outside the allowlist instead of treating it as research
  (hardened this phase; new test). `run_extraction` can only receive
  schema-valid values, so (b) is defensive depth for direct callers.
- **No silent promotion.** `build_feature_provenance` copies
  `record.availability_classification` verbatim (None stays None; `derived` stays
  `derived`). `evaluate_availability_policy` compares with
  `!= "provider_issued"`, so only an explicitly `provider_issued` value clears
  production. Missing/unknown classifications cannot become `provider_issued`.
- **Legacy records / REAL fixtures.** `AcquisitionRecord.availability_classification`
  is unchanged, optional, default `None`; previously loadable ledgers load
  identically (existing legacy round-trip test in `test_acquisition_rig.py`).
  Both committed REAL records and both test fixtures carry `available_utc` with
  classification `None` — honest, never promoted. Under `research_replay` they
  extract with output label `None`; under `production` they are rejected.
- **Serialization retains the classification.** New test proves a
  `FeatureProvenance` dump → reload round trip preserves `derived` verbatim
  (and `None` for unclassified), and that a production-policy request keeps its
  policy across a dump/reload. There is no persistence layer or API response
  that serializes `FeatureProvenance` today (confirmed by grep), so no other
  surface can drop the label.
- **Rejected records cannot contribute.** On gate rejection, `run_extraction`
  returns every requested feature as `rejected_leakage` with `value=None` and
  does **not** call `_read_source_features`; no fallback, default-value or
  alternate extraction path exists (glob + grep over `backend/app`).

### 24.5 Regression tests added (offline)

`backend/tests/test_feature_contract.py` (3 new; nothing rewritten this phase):

- `test_invalid_availability_policy_rejected_at_schema` — fail-closed at the
  typed boundary for `"PRODUCTION"` and `"prod"`.
- `test_evaluate_availability_policy_fails_closed_on_unknown_policy` — the gate
  raises for an unknown policy even with a present timestamp (defensive depth
  for direct callers).
- `test_provenance_and_policy_survive_serialization` — classification and policy
  are retained verbatim across a dump/reload round trip.

Existing Phase 3.7.4B policy-matrix and production `run_extraction` tests are
the production-entry-point policy-selection coverage (there are no other
production entry points today); none were modified.

### 24.6 Remaining bypasses and limitations (documented, honest)

- No production-grade wiring exists yet: the demo prediction path consumes
  DEMO/OpenWeather data, not REAL artifacts. When REAL features are wired to an
  API/job/training pipeline, that integration MUST set
  `availability_policy="production"` explicitly; until then the only policy in
  effect is the `research_replay` default inside `run_extraction`.
- Production remains blocked on external availability evidence (Q6 CHIRPS, Q7
  ERA5-Land — §7A/§22) and sufficient verified historical coverage; this phase
  neither claims nor fabricates that evidence.
- `evaluate_availability_policy`'s allowlist is a literal tuple
  (`("research_replay", "production")`); values are compared by equality, never
  normalized.
- The older sections' loose "Q6" shorthand (§19.7/§21.9) is not re-labelled;
  canonical mapping remains Q6 = CHIRPS, Q7 = ERA5-Land (§23.6).

### 24.7 Verification

- Focused:
  `python -m pytest -o addopts="" tests/test_feature_contract.py tests/test_acquisition_rig.py tests/test_cds_acquisition.py`
  → **181 passed** (3.7.4B: 178; +3).
- Full backend: `python -m pytest -o addopts=""` → **325 passed** (3.7.4B: 322;
  +3), 3 benign `sklearn InconsistentVersionWarning` (pre-existing, unchanged).
- Secret scan: 117 files / 4 `.env` values → 0 hits (unchanged).
- `git diff --check` → exit 0.
- Manifest blob/SHA/contract unchanged; feature contract version unchanged;
  no artifacts or generated files touched (final diff reviewed, files changed
  listed below).

### 24.8 Files changed this phase

- `backend/app/services/features.py` — `_ALLOWED_AVAILABILITY_POLICIES` + unknown
  policy fails closed in `evaluate_availability_policy` (~+10 lines).
- `backend/tests/test_feature_contract.py` — 3 new regression tests (+~50 lines).
- `docs/historical-data-coverage.md` — this section.

Schema, acquisition, manifest, artifacts, and the rest of the working tree were
not modified by Phase 3.7.4C on top of the Phase 3.7.4A/3.7.4B delta.

### 24.9 Verdict

Integration is consistent and leak-proof to the extent the architecture reaches:
`run_extraction` is the only REAL-feature path and it enforces the
availability-policy gate; no demo API, CLI, job, training or evaluation entry
point bypasses it, and none exists to wire into tomorrow. Invalid policy values
fail closed at both the schema and the gate. Missing/unknown classifications are
never promoted and survive serialization verbatim. Production remains **NO-GO**
and Q6/Q7 remain `EXTERNAL_EVIDENCE_REQUIRED` — until external availability
evidence and sufficient verified historical coverage are actually established,
the production policy can never be satisfied by the current committed records.

## 25. Phase 3.7.5A — Official evidence research record (Q6 / Q7)

Research-and-documentation phase. Inspect the official CHC / ECMWF / CDS sources
below, record what the Q6 (CHIRPS) and Q7 (ERA5-Land) general publication
schedules actually establish, and register the verdict without altering any code,
artifact or manifest. **No commit / push in this phase; the only working-tree
change is this section.**

### 25.1 Scope and method

- Retrieval date: **2026-10-09** (UTC). Pages inspected live via an HTTP fetcher.
- Position on the decision register: Q6 = CHIRPS, Q7 = ERA5-Land, both
  `EXTERNAL_EVIDENCE_REQUIRED` since Phase 3.7.4A (§22), carried through the
  availability gate (§23) and integration audit (§24); production **NO-GO**. This
  phase does not upgrade either `available_utc`.
- No changes to `backend/`, `data/`, or any test. Only
  `docs/historical-data-coverage.md` is edited (append).
- Sources inspected: 6 URLs. Sources not inspected: 1 URL (transport error,
  recorded below; its content is not relied on anywhere).

### 25.2 URLs and inspection status

| # | URL | Status 2026-10-09 | Notes |
| - | --- | ----------------- | ----- |
| 1 | https://www.chc.ucsb.edu/data/chirps | inspected | CHIRPS v2 product page |
| 2 | https://wiki.chc.ucsb.edu/CHIRPS_FAQ | **NOT inspected — transport error (attempted twice)** | content not relied on |
| 3 | https://www.chc.ucsb.edu/data/chirps3 | inspected | CHIRPS v3 product page |
| 4 | https://data.chc.ucsb.edu/products/CHIRPS-2.0/README-CHIRPS2-Daily.txt | inspected | official daily v2 README, linked from the v2 page |
| 5 | https://confluence.ecmwf.int/pages/viewpage.action?pageId=355336451 | inspected | ECMWF Knowledge Base "ERA5-Land data documentation" (capture partially truncated) |
| 6 | https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land?tab=documentation | inspected | CDS ERA5-Land dataset page (capture partially truncated) |

### 25.3 Q6 — CHIRPS: what the official pages establish

Facts surfaced by the inspected CHC pages (general product/cadence statements;
**no per-file publication timestamps**):

- CHIRPS v2 is a 35+ year quasi-global (50°S–50°N) rainfall dataset, 1981 to
  near-present (`chirps` product page).
- "CHIRPS v3 is now available! … Production of CHIRPS v2 will end after
  December 2026." (`chirps` product page); the v3 page in turn states
  "CHIRPS v3.0 replaces the widely used CHIRPS v2.0. To support users during
  this transition, the production of CHIRPS v2.0 will continue through 2026."
- Daily CHIRPS v2 is produced from pentad totals using CFSv2 daily downscaling
  ratios; "Preliminary daily CHIRPS2 uses the same CFSv2-based daily downscaling
  approach"; CHIRP2 daily downscaling uses IMERGv7 (daily README).
- **CHIRPS v2 publication cadence (official v2 documentation).** The CHIRPS-2.0
  README states: "Two CHIRPS products are produced operationally: a rapid
  preliminary version, and a later final version. The preliminary CHIRPS product
  is available, for the entire domain, two days after the end of a pentad (2nd,
  7th, 12th, 17th, 22nd and 27th)… The final CHIRPS product … is complete
  sometime in the third week of the following month. Final products for all
  times/domains/formats are calculated at that time." The CHIRPS2 FAQ states the
  same latency: rapid (GTS and Mexico only) "available 2 days after the end of a
  pentad"; final (all station data) "available sometime in the third week of the
  following month." This cadence is **explicitly documented for CHIRPS v2**
  (README FOLDERS lists `prelim` = "Quasi-global Rapid CHIRPS with 2-day lag").
  An earlier revision of this section treated the cadence as v3-only and
  non-transferable to v2; that was **incorrect** and is superseded here.
- **Preliminary vs final daily product paths (edition identification).** The two
  streams are distinguished by documented directory tree, not filename: final
  daily lives under `/products/CHIRPS-2.0/global_daily/…`; preliminary daily
  under `/products/CHIRPS-2.0/prelim/global_daily/…`. The same filename pattern
  (`chirps-v2.0.YYYY.MM.DD.tif.gz`) can appear in both trees, so the stored
  retrieval URL — when preserved as evidence — supports path-based edition
  identification.
- Sources (official CHC/UCSB):
  https://data.chc.ucsb.edu/products/CHIRPS-2.0/README-CHIRPS.txt ;
  https://wiki.chc.ucsb.edu/CHIRPS2_FAQ .

Implications for the exact artifact
`chirps__v2.x__2026-08-31.tif.gz` (sha256 `44934651…`, 10,288,665 B; ledger
`REAL-chirps-v2.0-2026-08-31`):

- The official v2 cadence is **approximate and product-level**: it gives an
  expected publication window ("sometime in the third week of the following
  month") but not an exact day/time, not a guaranteed latest-availability
  deadline, and not the first public availability time of an individual daily
  file. It must **not** be treated as a precise per-file availability timestamp
  or a guaranteed conservative upper bound.
- The stored retrieval URL for the artifact points to the final tree
  (`…/global_daily/…`, not `…/prelim/global_daily/…`), supporting path-based
  identification of the edition as **final**; the filename alone would not
  disambiguate which stream the acquired file belongs to.
- The ledger value `available_utc = 2026-09-11T21:10:59Z` remains a bare literal:
  re-verified this phase — `availability_classification`,
  `availability_source`, `availability_derivation`, `request_url`, `final_url`,
  `response_headers` and `provider_metadata` are all `null` for the CHIRPS
  record, and no script or note derives the value (§7A, unchanged).
- A reproducible conservative bound **still cannot** be defined for this artifact
  from the inspected official sources: the v2 cadence window is approximate and
  does not guarantee a latest-availability deadline, so directory modification
  times, gzip MTIME, retrieval timestamps and the monthly cadence do not
  independently establish a provider-issued first-availability timestamp. Any
  future derived rule requires a separate recorded decision with evidence
  supporting a conservative bound; no cadence-derived rule and no safety margin
  is adopted here. Feasible artifact-specific provider-issued evidence, if ever
  needed, is external and future-dated: an HTTP `Last-Modified` / dated
  `data.chc.ucsb.edu` directory listing for the exact file name, CHC
  ERDDAP/catalog metadata, or an independent archive (e.g. IRI/LDEO,
  climateSERV). None was captured at acquisition time.

Verdict Q6: **unchanged — `EXTERNAL_EVIDENCE_REQUIRED`.** The inspected pages
support the general product/cadence narrative but do not evidence this file's
publication timestamp.

### 25.4 Q7 — ERA5-Land: what the official pages establish

Facts surfaced by the ECMWF Knowledge Base "ERA5-Land data documentation" and the
CDS dataset page (general schedule/catalog statements):

- Consolidated ERA5-Land covers January 1950 to 2–3 months before the present;
  ERA5-Land-T provides near-real-time daily updates (~5 days behind real time),
  with monthly mean updates ~5 days after the end of the month.
- On the CDS, ERA5-Land-T data for a month are overwritten by the final
  ERA5-Land data **about two months** after the month in question.
- netCDF caveat: "for netCDF data requests which return just ERA5-Land or just
  ERA5-Land-T data, there is no means of differentiating between ERA5-Land and
  ERA5-Land-T data in the resulting netCDF files" (the `expver` discriminator
  exists only in GRIB headers).
- CDS catalog page: "ERA5-Land hourly data from 1950 to present"; DOI
  `10.24381/cds.e2161bac` — matches the ledger access reference; dataset
  publication date 2019-07-12; update date 2026-10-09.

Implications for the exact artifact
`era5-land__operational-consolidated-2-months-era5-land-t-5-days__2026-07-15t0000.nc`
(sha256 `af53a81a…`, 127,970 B; ledger
`REAL-era5-land-…-2026-07-15t0000`, status `downloaded`):

- Observation month is July 2026. Per the docs, final consolidated ERA5-Land for
  that month becomes available "about two months after the month" (≈ end of
  September 2026).
- The file is netCDF; per the official caveat, the in-file stream (Land vs
  Land-T) cannot be differentiated — stream identity rests on the filename label
  ("operational-consolidated-2-months", "era5-land-t-5-days"), which is
  self-attested, not provider-verified.
- The ledger value `available_utc = 2026-09-15T00:00:00Z` is algebraically
  consistent with the vintage datetime (2026-07-15T00:00Z) + 2 months, matching
  the "2-months" label, but: it is **not** provider-issued; the docs' wording is
  approximate ("about two months", no published constant); and the value precedes
  the ≈ end-of-September reading, so it is a conservative engineering bound and
  must not be presented as a validated safety margin. All derivation/evidence
  fields are `null` for the record (§25.5 re-verified).
  - The manifest stores 5 records for this `record_id` (4 `failed`, 1
    `downloaded`); the identical `available_utc` appears on the failed attempts,
    confirming it was fixed ahead of any successful provider response —
    consistent with a derived bound, not a captured header.
- Candidate reproducible rule (design only, not yet adopted): rule v1 —
  `available_bound_utc = vintage_start + 2 calendar months + K days` (integer
  slack `K` as a conservative engineering parameter), citing the KB page URL, with
  rule version and audit trail. `K` is **not provider-validated**; the current
  ledger value corresponds to `K = 0` under same-day-of-month arithmetic and is
  not yet this documented rule. Adopting rule v1 is a separate recorded decision.

Verdict Q7: **unchanged — `EXTERNAL_EVIDENCE_REQUIRED`.** Official pages confirm
the general schedule the label encodes, but no official source gives a
provider-issued timestamp for this exact vintage.

### 25.5 Evidence matrix

| # | Claim | Evidence location | Evidence type | Confidence / limitations | Register status |
| - | ----- | ----------------- | ------------- | ------------------------ | --------------- |
| 1 | CHIRPS v2: 35+ yr, 50°S–50°N, 1981 to near-present | `chirps` page | official product page | general; no per-file timestamps | supports inventory note, not Q6 |
| 2 | CHIRPS v2 production ends after December 2026 (v3 transition) | `chirps` + `chirps3` pages | official product pages | general migration statement | supports §22/§23 note; not Q6 evidence |
| 3 | Daily CHIRPS v2 from pentads via CFSv2 ratios; preliminary daily same approach; CHIRP2 uses IMERGv7 | daily README | official README | general; filename cannot separate preliminary vs final | not Q6 evidence |
| 4 | CHIRPS preliminary/final publication cadence (preliminary ~2 days after pentad end; final ~3rd week of following month) is documented for **v2** | CHIRPS-2.0 README + CHIRPS2 FAQ | official v2 docs | approximate, product-level; does not establish per-file first availability or a guaranteed conservative upper bound | supports §25.3 narrative; not Q6 evidence |
| 5 | v2 artifact `available_utc=2026-09-11T21:10:59Z` is provider-issued | none | — | no external evidence; all derivation fields `null` (§7A unchanged) | **Q6 `EXTERNAL_EVIDENCE_REQUIRED`** |
| 6 | ERA5-Land consolidated 1950 to 2–3 months before present | KB page | official docs | general | supports inventory note; not Q7 evidence |
| 7 | ERA5-Land-T NRT ~5 days behind real time; monthly means ~5 days after month end | KB page | official docs | general; NRT stream ≠ consolidated artifact | not Q7 evidence |
| 8 | Final ERA5-Land overwrites ERA5-Land-T on CDS ~2 months after the month | KB page | official docs | general; approximate wording only | basis for a future derived rule; not Q7 proof |
| 9 | netCDF cannot differentiate ERA5-Land vs ERA5-Land-T in-file | KB page | official docs | artifact-relevant; stream identity = filename label | limitation on Q7 evidence |
| 10 | ERA5 artifact `available_utc=2026-09-15T00:00:00Z` is provider-issued | none | — | derived bound (vintage + 2 mo); all derivation fields `null`; identical value on failed attempts | **Q7 `EXTERNAL_EVIDENCE_REQUIRED`** |
| 11 | CDS catalog: hourly 1950–present, DOI `10.24381/cds.e2161bac`, publ. 2019-07-12, upd. 2026-10-09 | CDS page | official catalog | general; matches ledger access reference | not Q7 evidence |

### 25.6 Not inspected / limitations

- `https://wiki.chc.ucsb.edu/CHIRPS_FAQ` could not be inspected (transport error,
  attempted twice). Recorded as not inspected; its content is not relied upon.
- The ECMWF and CDS captures were partially truncated in retrieval; the facts
  above are those surfaced in the captured content, not necessarily the full
  wording of the live pages.
- Historic HTTP metadata (`Last-Modified`, `Date`, final URL, response headers)
  was never captured at acquisition time (§7A item 4 verified), so a
  provider-issued timestamp for either committed artifact is **not recoverable
  from repository records** — any future evidence requires a new external query,
  which would only reflect the file's state at that later time.
- The CHIRPS publication cadence (§25.3) is approximate and product-level: it is
  documented for CHIRPS v2 (README, CHIRPS2 FAQ) but must not be silently
  converted into a per-file provider-issued availability timestamp or a
  guaranteed conservative upper bound for the v2 artifact.
- The manifest's repeated ERA5 records (4 failed + 1 downloaded for the same
  `record_id`) document retry history; the committed artifact is the single
  downloaded netCDF, and no record, manifest field, or checksum was modified by
  this phase.

### 25.7 Verification

- `git rev-parse HEAD` → `7a4afbe` (unchanged; no commit made this phase).
- `git status --short` → only `docs/historical-data-coverage.md` modified.
- `git diff --check` → exit 0.
- `data/provenance/acquisition_manifest.json` byte-identical (blob
  `07dc2cdd…`, sha256 `1f2b9434…`, contract `1.1.0`); no push performed.

### 25.8 Verdict

Both registers are **unchanged**: Q6 and Q7 remain `EXTERNAL_EVIDENCE_REQUIRED`,
production remains **NO-GO**, and production-grade temporal features for both
sources remain `NEEDS_EVIDENCE`. Neither `available_utc` was upgraded, re-dated,
or replaced. The official pages validate the general publication narratives
(v2 production ending after December 2026; ERA5-Land-T ≈ 5 days NRT; consolidated
≈ 2 months) but no inspected page provides the per-file, provider-issued
timestamps that Q6/Q7 require. Phase 3.7.5A leaves the decision register intact
and adds a persistent official-source record for future phases to cite.

## 26. Phase 3.7.5B — Acquisition evidence capture audit

Audit of whether future CHIRPS and ERA5-Land acquisitions can capture
trustworthy availability evidence **at acquisition time**, without fabricating
historical publication timestamps. One backward-compatible fix was applied
(see §26.6); the registers are otherwise unchanged. **No commit / push; the
manifest and feature contract are untouched.**

### 26.1 Scope and method

- Starting checkpoint: HEAD `7a4afbe` with only `docs/historical-data-coverage.md`
  modified (Phase 3.7.5A §25). §25 is preserved verbatim.
- Inspected: `backend/app/services/acquisition.py`, `backend/app/services/cds.py`,
  `backend/app/redaction.py`, `backend/app/schemas/acquisition.py`,
  `backend/app/schemas/provenance.py`, `backend/tests/test_acquisition_rig.py`,
  `backend/tests/test_cds_acquisition.py`, documentation §§19–25.
- No live provider access anywhere in unit tests; all fixtures are synthetic and
  offline. No evidence is invented for the existing 2026-08-31 / 2026-07-15
  artifacts. CDS job-payload field names cited in §26.3 are taken from the
  official ECMWF API documentation (example job-status payload), not from a live
  request.

### 26.2 CHIRPS direct-download path — what `acquire()` captures today

| Evidence | Where | Captured? | Failure path |
| -------- | ----- | --------- | ------------ |
| Requested URL (userinfo / signed-query secrets redacted) | `request_url` | yes, every attempt | yes |
| HTTP method | `request_method` | yes ("GET") | yes |
| Final HTTP status | `http_status` | yes | only if the exception carries a `.response` |
| Redirect chain (redacted hops) | `redirect_chain`, `final_url` | yes | only if a real response exists |
| `Date` / `Last-Modified` / `ETag` when provided | `response_headers` (allowlist) | yes | only if a real response exists |
| `Content-Length` when provided | `response_headers` | **now yes** (§26.6); omitted before | only if a real response exists |
| Retrieval instant (when the GET was issued) | `retrieved_utc` | yes | yes (acquisition start) |
| Content SHA-256 / byte count | `sha256`, `file_size_bytes` | yes (computed) | computed only when bytes exist |
| Source/version and observation interval | `product_version`, `observation_start/end_utc` | caller-supplied | caller-supplied |
| Availability timestamp + classification/source/derivation | `available_utc`, `availability_*` | caller/rule-supplied; **never auto-derived from headers** | caller/rule-supplied |

The direct path captures full artifact-response HTTP evidence for every
download. What it cannot do today: fetch or persist a dated directory/catalog
record (see §26.5).

### 26.3 ERA5-Land CDS path — what timestamps each stage exposes

The CDS retrieve/v1 flow (`CdsTransport.submit` → `wait_for_success`/`poll` →
`results` → `download_with_evidence`) is a two-phase job API. Per stage:

1. **Request submission** — `POST …/processes/{dataset}/execution` returns HTTP
   201 with the job status object (per the official ECMWF FAQ the creation
   response is "nearly identical" to the job-status response and carries the
   job's `created`/`updated` fields). The client extracts only `jobID`; the
   201 payload's timestamps, status and headers are **not captured**.
2. **Job state transitions / completion** — `GET …/jobs/{job_id}` returns e.g.
   `status`, `message`, `created`, `started`, `finished`, `updated` (official
   ECMWF example). The client keeps only `status` (and `message` on a terminal
   failure); the provider's `created`/`started`/`finished`/`updated`
   **job-state timestamps are discarded** — a concrete, fixable gap.
3. **Result-link issuance** — `GET …/jobs/{job_id}/results` returns asset
   descriptors (`href`, `type`, `file:checksum`, `file:size`, `file:local_path`).
   No timestamp is exposed on the asset itself, so there is no separate
   "link issuance time"; the nearest provider instant is the job `finished`.
4. **Artifact retrieval** — `GET {href}` (manual, token re-scoped redirects).
   Full HTTP evidence is captured exactly as in §26.2, and `retrieved_utc`
   records when the artifact bytes were requested.
5. **Dataset vintage / observation time** — caller-supplied
   `observation_start/end_utc` (e.g. ERA5-Land 2026-07-15T00:00Z); recorded.
6. **Provider-issued availability time** — **not exposed anywhere in the CDS
   request/asset flow.** The catalogue/catalog and Knowledge Base pages provide
   only general schedule statements (§25.4). A job completing does not mean the
   dataset vintage was "published" then; the CDS generates the requested subset
   from the consolidated archive, which lags ~2 months by its own schedule.

`acquire_cds` persists `provider_metadata = {dataset, job_id, asset_type}` today.
Control-plane responses (submit/poll/results) carry no ledger record; only the
final artifact GET is evidenced. Note also that `retrieved_utc` means "download
start" on the success/download-failure branches but "acquisition start" on the
submit-poll-results failure branches — a documented, minor meaning shift.

### 26.4 Metadata semantics and limitations (what each field proves)

- `Date` — instant the server generated the response (server clock). Proves the
  server answered then; **not** dataset publication/availability.
- `Last-Modified` — server-side last modification of the resource object; usually
  the object's mtime for a static file. A **server-evidenced bound**
  ("resource in this state no later than its mtime"), not a provider *declared*
  availability time.
- `ETag` — opaque validator; no time semantics; supports conditional GET/dedupe.
- `Content-Length` — response-body byte count; evidence for size/truncation
  cross-check; no time semantics. **Not enforced** this phase (recorded only).
- `retrieved_utc` vs `observation_*` vs `available_utc` — three distinct
  instants; the schema never conflates them and headers are never promoted into
  `available_utc` (test-verified, §19/§26.8).

Limitation to state plainly: even perfect HTTP capture gives **server-side
bounds**, not a provider *declaration* of availability. Under the §23 policy,
`provider_issued` stays reserved for independently supported provider evidence
(an explicit catalog field or an official cadence statement pinned to the exact
vintage). A captured `Last-Modified`/directory mtime would upgrade the current
records from "no evidence" to a *derived, server-evidenced bound* — strictly
better, but still not `provider_issued`. This phase does not weaken that policy.

### 26.5 Trustworthy dated directory/catalog record — feasibility

For a **future** CHIRPS download, a dated index (e.g.
`data.chc.ucsb.edu/products/CHIRPS-2.0/…/daily/tifs/2026/`) is fetchable by the
existing transport, and per-file `Last-Modified`/`Date` could be parsed into an
explicit evidence label. But the rig has no secondary-evidence persistence today
(`provider_metadata` is a bounded, sanitised string map, unsuitable for an HTML
body), so this capability needs a small implementation (index fetch + parse +
persist under an explicit, labelled field). It is **feasible for new
acquisitions, not repairable retrospectively**: the existing CHIRPS
2026-08-31 artifact's server-side metadata was never captured, and a re-download
would evidence only the file's then-current state (§25).

### 26.6 Schema & policy review — smallest backward-compatible design

**Schema adequacy:** existing fields already separate `retrieved_utc`,
`acquired_utc`, `observation_start/end_utc` and `available_utc`, plus
`availability_classification` (`provider_issued`/`derived`/`unknown`) with
`availability_source`/`availability_derivation`. No new field is required to
represent any timestamp this path exposes; the CDS job-state times belong in
`provider_metadata` with explicit `cds_job_*` labels. No manifest contract bump
is needed or made (`1.1.0` unchanged). The one residual risk is caller
truthfulness (a caller could pass a fabricated `available_utc` with a bogus
classification); that is mitigated, not eliminated, by the Phase 3.7.4B
availability-policy gate, which rejects `available_utc is None` under both
policies and requires `provider_issued` for `production`.

**Change applied (backward compatible):** `Content-Length` added to
`ALLOWLISTED_RESPONSE_HEADERS` in `backend/app/schemas/acquisition.py`
(`last-modified`, `etag`, `date`, `content-length`). Compatibility: records
already carry optional `response_headers: dict[str, str]`; adding an allowlisted
name only lets new records include one more key. Legacy records load unchanged;
the JSON manifest shape and the feature contract (`1.0.0`) are untouched.

**Smallest design proposed, not implemented:** CDS job-state timestamp capture.
Keep `poll()`/`wait_for_success()` return contracts; add a capture that reads the
provider job status fields (`created`/`started`/`finished`/`updated`) and
persists them as `provider_metadata["cds_job_created_utc"]` (etc.), always
labelled as job-state times, validated as aware datetimes when parseable and
otherwise stored verbatim with a note. Never written to `available_utc`, never
classified `provider_issued`. The `201` submission response should likewise
yield a submit-time stamp. This requires enriching `FakeCds` and verifying the
exact field names once against the live API before implementation.

### 26.7 Fixable vs not fixable retroactively

Fixable **for future downloads** (no code change needed or minimal):
- `Content-Length` capture — fixed this phase (§26.6).
- CDS job-state timestamps — proposed design ready (§26.6); needs live field
  verification before coding.
- CHIRPS dated directory/catalog record — small implementation (§26.5).
- Any future artifact gets full HTTP evidence + `retrieved_utc` automatically.

Not repairable **from repository evidence**:
- The committed CHIRPS 2026-08-31 and ERA5-Land 2026-07-15 artifacts carry no
  provider HTTP metadata and no CDS job-state timestamps (all evidence fields
  `null` in the manifest, re-verified 3.7.5A). Neither `available_utc` can be
  turned into a provider-issued timestamp retroactively; Q6/Q7 remain
  `EXTERNAL_EVIDENCE_REQUIRED` and production stays **NO-GO**.

### 26.8 Verification

- Focused: `python -m pytest -o addopts="" tests/test_acquisition_rig.py
  tests/test_cds_acquisition.py` → **132 passed** (was 129; +3).
- Full backend: `python -m pytest -o addopts=""` → **328 passed** (was 325; +3),
  same 3 benign pre-existing `sklearn InconsistentVersionWarning`.
- Secret scan: 117 files / 4 `.env` values → 0 hits (unchanged).
- `git diff --check` → exit 0. HEAD stays `7a4afbe`; no commit/push.
- Manifest hash/blob/contract unchanged: blob `07dc2cdd…`, SHA-256
  `1f2b9434…`, `contract_version 1.1.0`.

### 26.9 Files changed this phase

- `backend/app/schemas/acquisition.py` — allowlist now includes `content-length`.
- `backend/tests/test_acquisition_rig.py` — 2 new offline tests (Content-Length
  captured; headers never become availability).
- `backend/tests/test_cds_acquisition.py` — 1 new offline test (CDS artifact GET
  captures Content-Length; still not availability).
- `docs/historical-data-coverage.md` — this section.

### 26.10 Recommended next implementation step

Implement the CDS **job-state timestamp capture** (§26.6), verified against the
live API field names first, followed by the CHIRPS dated directory-index capture
(§26.5) before the next CHIRPS download. Both are forward-only: they improve
future records and cannot backfill Q6/Q7 for the two committed artifacts.

### 26.11 Verdict

Future acquisitions can now capture trustworthy acquisition-time evidence:
full artifact HTTP metadata on both sources, explicit `retrieved_utc`, content
SHA-256, and caller/rule-accountable availability classification — with
`Content-Length` newly included. The CDS control plane still discards the
provider's job-state timestamps (fixable, §26.6). None of this fabricates
historical publication times: the two committed artifacts remain
`EXTERNAL_EVIDENCE_REQUIRED`, production remains **NO-GO**, production-grade
temporal features remain `NEEDS_EVIDENCE`, and `provider_issued` remains
reserved for independently supported provider evidence.

## 27. Phase 3.7.5C — CDS job-state lifecycle evidence capture

Implements §26.6 (CDS job-state timestamp capture): future ERA5-Land
acquisitions now persist the provider's CDS job-state fields
(`status`, `created`, `started`, `finished`, `updated`) as auditable
**acquisition-process evidence** in `provider_metadata`. The change is
forward-only and fully backward-compatible; it cannot backfill Q6/Q7 for the
two committed artifacts. **No commit / push; the manifest, feature contract
and availability registers are untouched.**

### 27.1 Scope and method

- Starting checkpoint: HEAD `7a4afbe` with only §25/§26 documentation and the
  3.7.5B code/tests applied. §§19–26 are preserved verbatim.
- Inspected: `backend/app/services/cds.py`, `backend/app/services/acquisition.py`,
  `backend/app/redaction.py`, `backend/app/schemas/acquisition.py`,
  `backend/tests/test_cds_acquisition.py`, documentation §§19–26.
- Official CDS job-status field names (`status`, `message`, `created`, `started`,
  `finished`, `updated`) are taken from the ECMWF API documentation, not a live
  request. All tests are offline/synthetic; no live provider access anywhere.
- No evidence is invented for the existing 2026-08-31 / 2026-07-15 artifacts;
  job-state fields are recorded only as returned by the provider, verbatim.

### 27.2 What is captured

A whitelist helper `job_evidence(payload, *, prefix)` selects exactly five
fields from a CDS job payload: the scalar `status` plus the four job-state
timestamps `created` / `started` / `finished` / `updated`. It emits keys of the
form `cds_{prefix}_{field}` (`prefix` is `submit` for the 201 creation response
and `poll` for the terminal status GET) with the raw string value kept exactly
as the provider returned it — no parsing, no timezone reinterpretation, no
synthesis. Every other field (`jobID`, `processID`, `links`, `href`, `message`,
signed URLs, credentials) is dropped at the whitelist boundary so a secret can
never enter the ledger through this channel; values are still bounded (512
chars) and control-stripped by the shared redaction layer as defence in depth.

### 27.3 Per-field semantics

| Ledger key | CDS field | Meaning recorded |
| ---------- | --------- | ---------------- |
| `cds_submit_status` / `cds_poll_status` | `status` | workflow state at that instant (submit: usually `accepted`; poll: the terminal `successful`) |
| `cds_submit_created` / `cds_poll_created` | `created` | provider-side creation time of the job-state record |
| `cds_submit_started` / `cds_poll_started` | `started` | provider-side start of execution |
| `cds_submit_updated` / `cds_poll_updated` | `updated` | provider-side last update of the job-state record |
| `cds_poll_finished` | `finished` | provider-side terminal instant (meaningful only on the terminal GET) |

Fields the provider does not return at a given phase are simply absent: the
201 submission response typically has no `finished`, so
`cds_submit_finished` will not appear. Records only what was actually returned.

### 27.4 What the timestamps are NOT

Job-state timestamps describe the **retrieval workflow**: when the CDS created,
ran, updated and finished our *job*. They are not dataset vintage, not
publication time, and not availability. To forbid misreading, every
`provider_metadata` block from this phase carries a
`cds_lifecycle_note` stating exactly that, and the values are deliberately
kept as raw strings rather than parsed datetimes so they cannot be fed into
`available_utc`, `observation_start/end_utc` or `provider_issued` by accident.
The existing `available_utc / availability_*` and `observation_start/end_utc`
fields remain caller/rule-supplied and untouched.

### 27.5 Backward compatibility

- `submit(process_id, inputs) -> str` returns the bare job id, as before
  (delegates to `submit_with_evidence()`).
- `poll(job_id) -> (status, message)` and `wait_for_success(job_id)` are
  unchanged in signature and behaviour (poll delegates to `_poll_payload()`).
- New surface: `CdsSubmission` frozen dataclass (`job_id` + `evidence`);
  `submit_with_evidence()`; `poll_evidence(job_id)`; `job_evidence()`.
- Adding `submit_with_evidence` / `poll_evidence` to the transport extends the
  injected interface; the test double mirrors it.

### 27.6 Driver integration (`acquire_cds`)

1. `transport.submit_with_evidence(dataset, inputs)` replaces the bare submit;
   the job id drives the unchanged poll/download/checksum/dedupe flow and the
   submission evidence is carried forward.
2. After `wait_for_success`, exactly **one extra terminal status GET**
   (`transport.poll_evidence(job_id)`) captures the terminal job-state fields
   the poll loop discards. If that GET fails, the acquisition fails honestly as
   `failed` with `source_record_id = job_id` (never fabricated evidence).
3. `submit_evidence` and `poll_evidence` are merged into `provider_metadata`
   beside `dataset` / `job_id` / `asset_type`, plus the `cds_lifecycle_note`.
4. Evidence is persisted on `downloaded` and `skipped_existing` records.
   `failed` records carry no `provider_metadata` (unchanged behaviour);
   `checksum_mismatch` records likewise remain without it.

### 27.7 Schema / serialization compatibility

No schema field was added. Everything lives in the existing
`provider_metadata: dict[str, str]`, which the record sanitizer already bounds
and de-secrets before commit. Manifest `contract_version` stays `1.1.0`,
feature contract stays `1.0.0`, and the committed manifest (`6` records,
blob `07dc2cdd…`, SHA-256 `1f2b9434…`) is byte-identical.

### 27.8 Tests added and results

Ten new offline tests in `backend/tests/test_cds_acquisition.py`:

- `job_evidence` whitelists exactly the five job-state fields (poll payload);
- missing / non-string / non-whitelisted (credential-bearing) fields are
  dropped;
- values are bounded (2000-char status → 512);
- `submit_with_evidence` returns `CdsSubmission` and stays backward compatible
  with `submit()`; non-object 201 payload → `CdsMalformedResponse`;
- `poll_evidence` captures the terminal job state verbatim; `poll()` unchanged;
  non-object status body → `CdsMalformedResponse`;
- `acquire_cds` persists submit+poll lifecycle evidence with exactly one extra
  terminal GET, and never promotes it to availability fields;
- evidence-GET failure → honest `failed` record;
- `skipped_existing` keeps lifecycle evidence.

The suite caught a real integration bug during development: the `FakeCds`
attribute `poll_evidence` shadowed its `poll_evidence` method, producing
`TypeError: 'dict' object is not callable` across 17 tests; renamed the
attribute and all tests pass.

Test results: focused `tests/test_cds_acquisition.py`
`tests/test_acquisition_rig.py` → **142 passed** (+10); full backend suite →
**338 passed** (+10).

### 27.9 Verification

- `git diff --check` — exit 0 (docs are a pure append; code diff reviewed).
- Secret scan `secret_scan.py` — 117 files / 4 `.env` scanned, **hits = 0**.
- Manifest re-verified — `contract_version 1.1.0`, 6 records (CHIRPS 1×
  downloaded; ERA5-Land 5 records, 1× downloaded + 4× failed), blob and SHA-256
  unchanged.
- Availability registers unchanged: both committed artifacts remain
  `EXTERNAL_EVIDENCE_REQUIRED`; production remains **NO-GO**; production-grade
  temporal features remain `NEEDS_EVIDENCE`.
- HEAD `7a4afbe`; **no commit, no push**.

### 27.10 Files changed

- `backend/app/services/cds.py` — `submit`/`poll` refactor behind
  `submit_with_evidence` / `_poll_payload`; new `CdsSubmission`,
  `job_evidence`, `poll_evidence`, whitelist constants; `isinstance(dict)`
  payload guards; module docstring updated.
- `backend/app/services/acquisition.py` — `acquire_cds` lifecycle-evidence
  wiring (submit evidence, one extra terminal GET, `provider_metadata` merge,
  `cds_lifecycle_note`).
- `backend/tests/test_cds_acquisition.py` — `FakeCds` extended
  (`submit_with_evidence`, `poll_evidence`, evidence params) + 10 new tests.
- `docs/historical-data-coverage.md` — this section.

### 27.11 Verdict

Future ERA5-Land acquisitions now persist the full CDS retrieval-workflow
timeline as bounded, de-secreted, verbatim acquisition-process evidence, with
an explicit note that these are job-state timestamps rather than availability.
ERF 3.7.5 (capture trustworthy future acquisition evidence) is complete. Q7
remains `EXTERNAL_EVIDENCE_REQUIRED`: job timestamps answer *when our job ran*,
not *when the dataset vintage became available*, so the two committed ERA5-Land
artifacts are still unsupported. Preferred next step (unchanged from §26.5):
CHIRPS dated directory/index catalog capture before the next CHIRPS download.

---

## 28. Phase 3.7.6A — Historical availability evidence recovery audit

Read-only audit phase: can file-specific historical availability evidence for
the two committed artifacts be **recovered** (from the artifact bytes, provider
metadata, or independently archived records), must it be **reacquired**, or is it
left **unresolved**? Live introspection only; no downloads, no CDS job
submissions, no commit/push. Manifest, feature contract, artifacts, and code are
untouched; §§19–27 are preserved verbatim (this phase appended only).

### 28.1 Scope and method

- Starting checkpoint: HEAD `1fee198`, working tree clean (only this document
  modified once §28 is appended).
- Inspected this phase:
  - local artifact bytes (gzip header, netCDF global attributes);
  - the live CHC directory listing
    `https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_daily/tifs/p05/2026/`
    (fetched 2026-10-10);
  - Internet Archive Wayback CDX queries for the exact CHIRPS file URL, the
    `2026/` directory, and the `data.chc.ucsb.edu` domain;
  - two Internet Archive captures of the public CDS catalogue (STAC collection)
    JSON for `reanalysis-era5-land` (2026-09-16 and 2026-09-23), retrieved with
    the `id_` flag to obtain the original bytes.
- Not inspected (do not claim): the CDS dataset HTML page behind the Wayback CDX
  query (fetch timed out); any FEWS NET / NOAA / IRI mirrors (search provider
  rate-limited); the **live** CDS catalogue (current state only adds nothing over
  the archived captures and would be excluded by the current-server-metadata
  caveat).
- Guardrails held: no fabricated timestamps; no URL claimed inspected unless
  actually inspected; current server metadata distinguished from historical
  evidence; production temporal features stay `NEEDS_EVIDENCE`; production stays
  **NO-GO**; no live downloads; no CDS job submissions.

### 28.2 Q6 CHIRPS — recovered evidence

| # | Source | Value | Type | Observed |
| - | ------ | ----- | ---- | -------- |
| 1 | Ledger `available_utc` (`acquisition_manifest.json:28`) | `2026-09-11T21:10:59Z` | committed literal, previously "unverified" | at acquisition |
| 2 | Committed artifact gzip header (bytes held, immutable) | MTIME raw `1789161059` = **`2026-09-11T21:10:59Z`**; FLG bit 0x08 (FNAME) → original name `chirps-v2.0.2026.08.31.tif`; compressed size `10,288,665` B | provider-produced, artifact-embedded creation metadata (set by the provider's compression tool at production) | read from artifact this phase (not filesystem mtime of our copy, which is `2026-10-08`) |
| 3 | CHC live directory listing of `.../tifs/p05/2026/` | `chirps-v2.0.2026.08.31.tif.gz` `9.8 MiB` `2026-Sep-11 21:10`; the entire August-2026 batch (`08.01`–`08.31`) shares the same mtime `2026-Sep-11 21:10` | provider-issued per-file directory-listing timestamp (= the server-side file mtime §7A identified as acceptable evidence) | fetched 2026-10-10 |
| 4 | Wayback CDX | no captures of the exact file URL, of `.../p05/2026/`, or of any dated CHIRPS `.tif.gz` listing | negative result | queried this phase |

Interpretation. The ledger value is now **reproducible from the artifact itself**
(§7A premise "no derivation is recoverable from the repository" is superseded:
the derivation *source* is inside the committed bytes) and is independently
corroborated to the second by the provider's own directory listing for the exact
file. The mtime agreeing with our artifact's gzip MTIME also means the provider
file has **not** been re-touched since `2026-09-11T21:10:59Z` (else the on-disk
mtime would diverge from the mtime embedded in the bytes we hold). The whole
month-published-at-once pattern (`08.01–08.31` one mtime) matches CHC's
monthly-batch publication cadence noted in `acquisition_manifest.json:369`.

Caveats, stated honestly:
- The directory listing was observed **post-hoc** (`2026-10-10`), not at
  retrieval (`2026-10-08`); its Date column has minute granularity.
- The gzip MTIME is a *production* timestamp (compression time). Publication
  normally follows immediately for a batch-generated product, and the mtime is
  the standard web-server `Last-Modified`-equivalent, but a strict reading keeps
  "production instant" distinct from "serving/published instant".
- No independent third-party (Wayback) capture of the CHIRPS file exists; CHC
  itself is the authoritative provider, and the listing is that provider.
- A theoretical future re-upload that *preserved* the mtime would not be caught;
  direct evidence still favours an unchanged original.

### 28.3 Q6 register decision — recovered; production gate retained

Per decision recorded this phase, the Q6 evidence classification is flipped from
**"unverified / provisional"** to **recovered**: the exact-file provider
directory-listing timestamp called for in §7A is produced and corroborated
in-artifact. The value **`2026-09-11T21:10:59Z` is retained, unchanged**, and now
carries provenance (this section supersedes §6 Q6 row and §7A's conclusion as
historical record; both are kept verbatim above).

Remaining gates, by the literal §7A wording ("directory-listing timestamp
**captured at retrieval**"):
- **Research / replay**: Q6 no longer blocks feature computation for the
  committed CHIRPS artifact — recording of the recovered, provider-corroborated
  value is acceptable.
- **Production**: still **CLOSED**. The observance was post-hoc, not at
  retrieval, so the production gate remains conditional on one authorized
  reacquisition that captures `Last-Modified`/directory metadata with the
  request URL and response status at retrieval (the 3.7.5C evidence pipeline
  supports this). First opportunity: the next authorized CHIRPS download.
- Production temporal features remain `NEEDS_EVIDENCE`; production remains
  **NO-GO**.

### 28.4 Q7 ERA5-Land — findings

Artifact semantics. The committed NetCDF carries a global `history` attribute
`2026-10-08T11:07 GRIB to CDM+CF via cfgrib-0.9.15.1/ecCodes-2.48.2 …` — the CDS
service built this netCDF **on demand** at retrieval, minutes before the download
(`retrieved_utc 2026-10-08T11:09:48Z`, job `4548c91f-…`). The file therefore
postdates `available_utc = 2026-09-15T00:00:00Z` by ~54 days and can never be
evidence of that bound: for on-demand formats the file's own birth is at
retrieval, and `available_utc` can only ever describe **dataset vintage**
availability, never this file's existence.

Manifest attempts (uninformative for availability, re-stated for the record):
R2 HTTP 422 (malformed input) proves the API was reachable and rejected the
request shape, nothing about data; R3–R5 HTTP 403 (licences not accepted) prove
authentication succeeded and the licence gate did not; R6 proves the vintage was
retrievable **as of** `2026-10-08T11:09:48Z` (retrospective lower bound only).

Independently archived provider evidence (new this phase), via Internet Archive
captures of the public CDS STAC collection JSON:

| Capture (Wayback timestamp) | `extent.temporal.interval` end | `updated` |
| --------------------------- | ------------------------------- | --------- |
| `20260916151323` (2026-09-16) | `2026-09-10T00:00:00+00:00` | `2026-09-16T00:00:00Z` |
| `20260923183724` (2026-09-23) | `2026-09-17T00:00:00+00:00` | `2026-09-23T00:00:00Z` |

Reading. The ERA5-Land archive continuously covered `1950-01-01` → the listed
end date on both capture dates, with the end tracking ~5–6 days behind real time
(consistent with ERA5-Land-T near-real-time latency). Provider-issued, dated,
and independently archived: the **2026-07-15 vintage was within the continuous
cover and therefore in-archive and retrievable by 2026-09-16** — one day after
the claimed bound. This *corroborates the direction and conservativeness of the
derived bound* but is dataset-level coverage, **not** a per-vintage availability
timestamp; it cannot pin `2026-09-15T00:00:00Z` to the consolidation of the
July-2026 consolidated stream.

### 28.5 Q7 register decision — unresolved (unchanged)

Q7 stays `EXTERNAL_EVIDENCE_REQUIRED`. `available_utc 2026-09-15T00:00:00Z`
remains the derived engineering bound (vintage `2026-07-15` + 2 calendar months,
`K = 0`), **not provider-issued**. The archived-catalogue finding is recorded as
corroboration of the bound's direction only; per guardrails no unvalidated `K`
safety margin is adopted, and rule v1 (§25.4) remains design-only pending a
separate recorded decision.

Recovery decision: **leave unresolved — no reacquisition for evidence.** An
on-demand reacquisition can only re-prove retrieval-time availability (it cannot
recover the historical instant 2026-09-15); a live catalogue fetch today would
reflect current state only. The archived `2026-09-16` JSON is the closest dated
provider document available, and it is already recorded here.

### 28.6 Register amendment (effective; supersedes earlier rows by reference)

| Question | Previous status | Status after §28 | Production gate |
| -------- | --------------- | ---------------- | --------------- |
| Q6 CHIRPS `available_utc 2026-09-11T21:10:59Z` | `EXTERNAL_EVIDENCE_REQUIRED` — "unverified / provisional"; not derivable (§6 row, §7A) | **Recovered** — provider-issued exact-file directory-listing timestamp, corroborated in-artifact (gzip MTIME); value retained | **Closed** until one authorized on-retrieval capture (3.7.5C pipeline); research/replay unblocked |
| Q7 ERA5-Land `available_utc 2026-09-15T00:00:00Z` | `EXTERNAL_EVIDENCE_REQUIRED` — derived bound (vintage + 2 mo) | `EXTERNAL_EVIDENCE_REQUIRED` — unchanged; **corroborated only** by archived provider catalogue cover (in-archive by 2026-09-16) | Closed (production NO-GO) |

Both artifacts keep their ledger `available_utc`, SHA-256, size, and manifests;
no timestamp was re-dated or invented.

### 28.7 Explicit non-claims

- The live CHC listing's Date column was observed once (2026-10-10); it is the
  provider's current rendering of a fixed per-file mtime and is treated as
  corroborating provider metadata, **not** as a capture at acquisition.
- No Wayback capture of the CHIRPS file or its dated `2026/` listing exists
  (CDX negative); third-party archival independence is **not** claimed for Q6.
- FEWS NET / NOAA / IRI mirror listings were not inspected (search provider
  unavailable) and are not relied upon.
- The CDS catalogue JSON captures were retrieved via the Wayback `id_` endpoint
  as original bytes; the live catalogue was not fetched.
- `extent.temporal.interval` end is a dataset-coverage bound, not a per-vintage
  availability timestamp; the Q7 reading above does not upgrade the bound.

### 28.8 Verification

- `git rev-parse HEAD` → `1fee198` (unchanged; no commit made this phase).
- `git status --short` → only `docs/historical-data-coverage.md` modified.
- `git diff --check` → exit 0; docs are a pure append (numstat `0` insertions on
  existing lines), §§19–27 byte-for-byte preserved.
- Manifest byte-identical (blob `07dc2cdd…`, SHA-256 `1f2b9434…`, contract
  `1.1.0`, 6 records); feature contract `1.0.0`.
- Artifacts byte-identical: CHIRPS SHA-256 `44934651…d9a6` (10,288,665 B),
  ERA5-Land SHA-256 `af53a81a…4ac9` (127,970 B).
- No push performed.

### 28.9 Verdict

- **Q6 CHIRPS — recovered** for research/replay: the exact-file provider
  directory-listing timestamp is established and matches the artifact-embedded
  gzip MTIME and the ledger to the second; value retained. The production gate
  stays closed until one authorized reacquisition captures evidence at retrieval
  (3.7.5C now supports this; §26.5's "dated directory/index catalog capture
  before the next CHIRPS download" is the concrete trigger).
- **Q7 ERA5-Land — left unresolved**: no provider-issued per-vintage timestamp
  exists in any inspected record; the archived catalogue corroborates
  in-archive-by-2026-09-16 only. Register status unchanged.
- Production temporal features for **both** sources remain `NEEDS_EVIDENCE`;
  production remains **NO-GO**. The findings here narrow the outstanding work
  for CHIRPS to a single authorized evidence-capturing reacquisition.

---

## 29. Phase 3.7.6B — CHIRPS retrieval-time evidence closure audit

Audit and documentation only: establish the exact, smallest safe path to obtain
**retrieval-time** CHIRPS HTTP evidence for the existing daily artifact so the Q6
production gate can later be reconsidered, without misclassifying the recovered
historical evidence and without mutating any repo data. **No live downloads, no
network acquisition, no code changes, no commit/push.** §28 (Phase 3.7.6A) is
preserved byte-for-byte; §29 appends only.

### 29.1 Scope and method

- Starting checkpoint: HEAD `1fee198`; working tree contains only the §28
  append from Phase 3.7.6A (verified via `git status --short`, `rev-parse`).
- Read: `backend/app/services/acquisition.py`, `backend/app/schemas/acquisition.py`,
  `backend/app/services/cds.py` (Q7-scope only), the rig tests
  `backend/tests/test_acquisition_rig.py` / `test_cds_acquisition.py`, and §28.
- Confirmation run (no code changed): `python -m pytest tests/test_acquisition_rig.py
  tests/test_cds_acquisition.py -q -o addopts=""` → **142 passed** (2.01 s),
  confirming the overwrite/dedupe/header-capture behaviour cited below.
- Guardrails: no fabricated values; no live requests; existing artifact,
  committed manifest records, contracts, and code untouched; Q7 stays
  `EXTERNAL_EVIDENCE_REQUIRED`; production stays **NO-GO**.

### 29.2 CHIRPS acquisition call path (traced)

`AcquisitionDriver(source="chirps")` (`acquisition.py:636`, constructor accepts
injectable `raw_root`, `manifest_path`, `transport`) → `acquire()`
(`acquisition.py:770`):

1. `resolve_credentials(source)` — CHIRPS `authentication = NONE`, so no
   credential gate and no env reads (`acquisition.py:304-318`).
2. Retrieval params: `url` is required and must be supplied by the caller
   (`_extract_download_url`, `acquisition.py:480-495`; config-only source, no
   hardcoded endpoint). `request_url` = redacted URL (`acquisition.py:813`).
3. `acquisition_key` (caller-supplied or a fresh timestamp `%Y%m%dT%H%M%SZ`,
   `acquisition.py:815`) → immutable path via `storage_relative_path`
   (`acquisition.py:373-380`):
   `data/raw/real/{source}/{source}__{version_slug}__{key_slug}{extension}`.
4. **Immutability gate** `acquisition.py:821-824`: if the target path already
   exists → `DuplicateArtifactError` raised **before any network call**. An
   existing artifact is never overwritten by construction and by test
   (`test_existing_artifact_path_is_never_overwritten`).
5. `retrieved_utc = utcnow_aware()` `acquisition.py:827` — this is the captured
   retrieval time for the attempt.
6. `transport.fetch(url)` (`acquisition.py:344-356`) returns `FetchResult(
   content, status_code, headers, final_url, redirect_chain)`. A fetch failure
   is recorded as an honest `FAILED` record (with `http_status` and any
   allowlisted headers from the error response) and re-raised as
   `AcquisitionError` (`acquisition.py:832-862`); **no retries exist** — one
   fetch, one record, no artifact bytes left on failure
   (`test_failed_acquisition_records_failure_honestly`).
7. Evidence assembled from the **final** response (`acquisition.py:864-884`):
   `request_url`, `request_method=GET`, `http_status=result.status_code`,
   `response_headers=_allowlisted_headers(result.headers)`, `final_url`/`redirect_chain`
   (redacted), `provider_metadata`, `availability_classification/source/derivation`,
   `redacted_params`.
8. SHA-256 of the delivered bytes vs caller-supplied `expected_sha256`
   (`acquisition.py:886-906`): mismatch records `CHECKSUM_MISMATCH` and raises —
   never silently accepted.
9. Content dedupe (`acquisition.py:908-936`): if a kept record (`DOWNLOADED` /
   `SKIPPED_EXISTING`) already exists for the same `kind`+`source` with the same
   `sha256`, a `SKIPPED_EXISTING` record is **appended** with its own evidence
   and `storage_path = existing[0].storage_path`, and the function **returns
   before any write**. No second file is created
   (`test_identical_content_is_deduplicated_as_skipped_existing`).
10. Otherwise `_atomic_write` (`acquisition.py:383-396`, temp + `os.replace`) to
    the new path and persist a `DOWNLOADED` record (`acquisition.py:938-957`).

Evidence capture points, exactly:

| Evidence | Where captured | Persisted as |
| -------- | -------------- | ------------ |
| `Last-Modified` (+ `etag`, `date`, `content-length`) | raw final-response headers captured in `FetchResult.headers` (`acquisition.py:350`), filtered by `_allowlisted_headers` (`acquisition.py:410-424`, allowlist `schemas/acquisition.py:36`) and again by the record field validator (`schemas/acquisition.py:192-207`; values bounded/cleaned) | `record.response_headers` |
| Retrieval time | `retrieved_utc = utcnow_aware()` (`acquisition.py:827`) | `record.retrieved_utc`, plus `acquired_utc` at registration |
| Final URL + redirect chain | `redact_url(result.final_url)`, `_redact_chain(...)` (`acquisition.py:867-868`) | `record.final_url`, `record.redirect_chain` |
| HTTP status | `result.status_code` | `record.http_status` |
| Content hash | `hashlib.sha256(data)` (`acquisition.py:887`) | `record.sha256` (+ `file_size_bytes`) |
| Artifact identity | `storage_relative_path` key + `_make_record` (`acquisition.py:596`) | `record_id` (`REAL-chirps-{version}-{key}`), `storage_path`, `source_record_id` |
| Availability | **caller-supplied only**; never parsed from headers (`acquisition.py:780-791`) | `available_utc`, `availability_classification` (default `"unknown"`), source/derivation |

`available_utc` is never derived from `Last-Modified`/`Date`/`ETag` anywhere in
the codebase (consistent with §22.6 and §26 audits).

### 29.3 Can a fresh authorized acquisition capture safe retrieval-time evidence?

The driver can already do this with **no code change**, by constructor
injection (`raw_root`, `manifest_path`) plus a new `acquisition_key`:

- **Same `acquisition_key` as the original → `DuplicateArtifactError` before any
  fetch** (step 4). Safe but useless: no evidence is captured. Not the path.
- **New `acquisition_key`, same vintage URL**: the fetch performs and evidence
  is captured for the same URL/bytes. If the delivered bytes hash exactly to the
  committed artifact (sha `44934651…d9a6`), step 9 appends a `SKIPPED_EXISTING`
  record — `storage_path` points at the original artifact, **no new file is
  written, the original artifact is untouched**, and the record carries the
  retrieval-time headers/status/final-url. If the bytes differ, step 8 records a
  `CHECKSUM_MISMATCH` (or step 10 stores a new file under the new key) — in all
  cases the original artifact and its record are never modified.
- The one unavoidable mutation: **any run that points `manifest_path` at the
  committed manifest appends a record and re-saves the JSON**, changing the
  manifest blob/sha and record count. This phase requires the committed manifest
  stays at 6 records, so the closure run must target an **isolated copy** of the
  manifest in a scratch location (same for `raw_root`). No dedicated CLI or
  "evidence-only" mode exists; the isolation is achieved through the public
  constructor parameters, which is the smallest safe mechanism available.

Conclusion: **yes** — with (a) scratch `raw_root`, (b) a byte copy of the
committed manifest at a scratch `manifest_path`, (c) a fresh `acquisition_key`,
(d) `expected_sha256` = the committed artifact hash, (e) the exact CHC URL. The
evidence is recorded in the isolated ledger only and can be transcribed here;
merging it into the committed manifest is a separate, recorded decision (it
would change the manifest blob/hash by design).

### 29.4 Overwrite / duplicate / metadata risks (checked against code + tests)

- **Overwrite of the original artifact**: impossible. Same-key runs abort before
  fetch (immutability gate); new-key runs write to a new path or take the
  dedupe short-circuit. `_atomic_write` is the only writer and is never reached
  with the original key.
- **Duplicate records**: every attempt appends one record; `record_id` embeds
  the acquisition key, so distinct keys give distinct ids and identical content
  is marked `SKIPPED_EXISTING` (the intended duplicate-content marker), not
  re-downloaded bytes. Alternative outcome is a `FAILED`/`CHECKSUM_MISMATCH`
  record, still one record per attempt.
- **Silent metadata changes**: none. Existing records are never edited or
  re-timestamped; the ledger is load → append → atomic re-save. The only JSON
  wobble risk is the whole-file blob/hash change from appending itself, which is
  why the committed file must not be the write target during a closure audit run.
- **Retries**: none in `acquire()` (single fetch; single failure record).
- **Failure handling**: honest `FAILED` records; no bytes left behind; no fake
  success (tests at `test_acquisition_rig.py:332`).
- **Provider content drift**: if the provider currently serves different bytes
  for the 2026-08-31 vintage, no retrieval-time evidence is obtained **for the
  committed artifact** (hashes diverge). This is the key acceptance gate.
- **Misleading derivation**: nothing auto-labels a captured header as
  `provider_issued`; the default classification stays `unknown`.

### 29.5 Minimum safe execution plan (documented, NOT executed this phase)

Preconditions: explicit authorization to perform one live GET to
`data.chc.ucsb.edu`; record today's observation date. Then:

1. Create scratch `raw_root` and a scratch `manifest_path`; byte-copy the
   committed `data/provenance/acquisition_manifest.json` to the scratch path (so
   dedupe sees the original CHIRPS record).
2. `driver = AcquisitionDriver(source="chirps", raw_root=<scratch>,
   manifest_path=<scratch manifest>, transport=AcquisitionTransport())`.
3. `record = driver.acquire(
   acquisition_key="2026-08-31-evidence-<utcnow>",
   retrieval_params={"url": "https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_daily/tifs/p05/2026/chirps-v2.0.2026.08.31.tif.gz",
                     "extension": ".tif.gz"},
   expected_sha256="449346515d840eeb4bf5c613a344777afe317800269386f2e93fdb3943a8d9a6",
   source_record_id="chirps-v2.0.2026.08.31.tif.gz",
   observation_start_utc=..., observation_end_utc=... (same as original record),
   available_utc=<recovered value>, availability_classification="unknown",
   availability_source="response_headers.last-modified")`.
4. Assert `record.status == SKIPPED_EXISTING` and `record.sha256 == 449…` and
   `record.response_headers` contains `last-modified`. If bytes differ, STOP
   (evidence would describe new bytes, not the committed artifact).
5. Transcribe the captured evidence (HTTP 200, `last-modified`, `etag`, `date`,
   `final_url`, `redirect_chain`, `retrieved_utc`) into the evidence record.
6. Verify the scratch `raw_root` contains **no** new files and the scratch
   manifest gained exactly one (`SKIPPED_EXISTING`) record; then discard the
   scratch tree. Committed manifest stays 6 records, blob/hash unchanged.

### 29.6 Evidence acceptance criteria and precise limits

Accepted as **retrieval-time server evidence** (not "provider_issued"):
- HTTP 200 to the exact vintage URL, allowlisted headers captured at that
  fetch, final URL and status recorded, delivered bytes hash exactly to the
  committed artifact. This is what §7A's "directory-listing/`Last-Modified`
  captured with the request URL and response status at retrieval" describes at
  the form level — but for a **new** retrieval instant, not the original
  `2026-10-08` one.
- If the returned `last-modified` equals `2026-09-11T21:10:59Z`, it *corroborates*
  the recovered gzip MTIME and directory-listing timestamp (the provider's file
  mtime is the same stable value) and closes the evidence chain:
  artifact bytes → gzip MTIME → provider directory listing → live `Last-Modified`.
- It does **not** prove the provider served/published that value on the original
  retrieval date, and it is not, by itself, a `provider_issued` `available_utc`.
  Classification must stay `unknown` on the record; the header value is evidence,
  not a derivation. Production-gate reconsideration is a separate recorded
  decision and is **out of scope for this phase**.

### 29.7 Register posture after §29 (unchanged by this phase)

- **Q6 CHIRPS**: recovered for research/replay (§28). Production remains
  **CLOSED** until an authorized retrieval-time capture **and** a recorded
  production-gate decision. This section documents the smallest safe path to
  obtain that capture; it does not perform it.
- **Q7 ERA5-Land**: stays `EXTERNAL_EVIDENCE_REQUIRED`. No CDS jobs launched; no
  ERA5-Land reacquisition. Production temporal features for both sources remain
  `NEEDS_EVIDENCE`; overall production remains **NO-GO**.

### 29.8 Verification

- `git rev-parse HEAD` → `1fee198` (unchanged; no commit made this phase).
- `git status --short` → only `docs/historical-data-coverage.md` modified.
- `git diff --check` → exit 0; docs are a pure append; §§19–28 byte-for-byte
  preserved (this edit touched only the §28 final lines/EOF).
- Confirmation tests (no code changed): `pytest tests/test_acquisition_rig.py
  tests/test_cds_acquisition.py -q -o addopts=""` → **142 passed** in 2.01 s.
- Manifest byte-identical (blob `07dc2cdd…`, SHA-256 `1f2b9434…`, contract
  `1.1.0`, 6 records); feature contract `1.0.0`.
- Artifacts byte-identical: CHIRPS SHA-256 `44934651…d9a6` (10,288,665 B);
  ERA5-Land SHA-256 `af53a81a…4ac9` (127,970 B).
- Secret scan scope/result reported at closing (§29.9 of the run, outside this
  document) — 117 files scanned against 4 `.env` values, **hits = 0**.
- No push performed.

### 29.9 Verdict

The existing driver already provides a safe, isolated, evidence-capturing path
through constructor injection (`raw_root`, `manifest_path`, `transport`) plus a
fresh `acquisition_key` and the `SKIPPED_EXISTING`/checksum dedupe — **no code
change is required**. The minimum safe closure is a single authorized live GET in
a scratch environment per §29.5, gated on `sha256 == 4493…`, with the captured
headers kept as retrieval-time server evidence (classification stays `unknown`).
Q6 research/replay stays recovered; the production gate stays closed pending that
capture and an explicit recorded decision; Q7 remains unresolved; production
remains NO-GO.

## 30. Phase 3.7.6C — Isolated CHIRPS evidence capture readiness (2026-10-10)

Readiness-only audit: no live network request was made, no acquisition ran, no
source code or configuration changed, no manifest record or artifact was
mutated, and nothing was committed or pushed this phase. It delivers a
verified, reproducible execution plan for a future explicitly authorized
retrieval-time `Last-Modified` capture (the missing Q6 production-gate evidence,
§28.4/§28.5), so later approval needs no further investigation. §29/§28/§27
are preserved byte-for-byte; §30 appends only.

### 30.1 Phase ground rules (unchanged from §28/§29)

- Nothing is captured, fetched, or labelled `provider_issued` in this phase; the
  live GET runs only on explicit future authorization.
- The Q6 production gate remains **CLOSED**; Q6 research/replay stays recovered;
  Q7 remains `EXTERNAL_EVIDENCE_REQUIRED`; production temporal features stay
  `NEEDS_EVIDENCE`; production remains **NO-GO**.
- No timestamp or header is fabricated, and a current `Last-Modified` is never
  treated as proof of historical availability by itself (§28.5).

### 30.2 Repository facts verified in this phase

- Driver defaults resolve to tracked paths (`backend/app/config.py:142-146`):
  `ACQUISITION_MANIFEST = <root>/data/provenance/acquisition_manifest.json`,
  `RAW_REAL_DIR = <root>/data/raw/real`; both overridable by constructor args
  (`backend/app/services/acquisition.py:649-651`).
- Registry `chirps` (`acquisition.py:141-160`): `authentication=NONE`, no
  `endpoint_base`, `require_bounded_scope=False`,
  `product_version="v2.x"`. `get_source_config("chirps")` returns it (`:261`).
- Committed manifest (`data/provenance/acquisition_manifest.json`): contract
  `1.1.0`, 6 records; first record `REAL-chirps-v2.0-2026-08-31`
  (`status="downloaded"`, `product_version="v2.0"`,
  `storage_path="chirps/chirps__v2.x__2026-08-31.tif.gz"`,
  `observation_start_utc=2026-08-31T00:00:00Z`,
  `observation_end_utc=2026-09-01T00:00:00Z`,
  `available_utc=2026-09-11T21:10:59Z`, `sha256=44934651…d9a6`,
  `file_size_bytes=10288665`, `retrieval_params` = CHC HTTPS URL +
  `extension=".tif.gz"` + NE-India bbox).
- Evidence headers allowlist (`backend/app/schemas/acquisition.py:36`):
  `last-modified`, `etag`, `date`, `content-length`; `_allowlisted_headers`
  (`acquisition.py:410-424`) canonicalises, bounds, and truncates values.
- `AcquisitionRecord.availability_classification` is
  `Literal["provider_issued","derived","unknown"]`
  (`backend/app/schemas/features.py:158`); default `unknown`; `available_utc` is
  caller-supplied only, never derived from response headers.
- Coherence validator (`schemas/acquisition.py:232-245`): `downloaded`/
  `skipped_existing` records must carry `sha256`, `file_size_bytes`,
  `storage_path`; a `failed` record may not claim a `storage_path`.

### 30.3 Specified isolated invocation (executed only when authorized)

No CLI/executable acquisition interface exists; the supported surface is the
programmatic driver API (`AcquisitionDriver`, `acquisition.py:770`). The run
wires `AcquisitionTransport()` only when authorized, keeps all writes inside a
fresh scratch directory outside the repo, and never points at the committed
manifest or the live artifact:

| Parameter | Value |
|---|---|
| `source` | `"chirps"` (registry config applied automatically) |
| `acquisition_key` | `2026-08-31-evidence-<utcnow>` — fresh, never reused |
| `raw_root` | fresh scratch dir under `$env:TEMP`, outside `PROJECT_ROOT` |
| `manifest_path` | byte-for-byte scratch copy of the committed manifest |
| `transport` | `AcquisitionTransport()` (single anonymous GET) |
| `retrieval_params` | url `https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_daily/tifs/p05/2026/chirps-v2.0.2026.08.31.tif.gz`, extension `.tif.gz` |
| `source_record_id` | `chirps-v2.0.2026.08.31.tif.gz` |
| `product_version` | `v2.0` (mirrors the committed record) |
| `expected_sha256` | full `449346515d840eeb4bf5c613a344777afe317800269386f2e93fdb3943a8d9a6` |
| `observation_start_utc` / `observation_end_utc` | `2026-08-31T00:00:00Z` / `2026-09-01T00:00:00Z` |
| `available_utc` | `2026-09-11T21:10:59Z` (caller-supplied recovered value, §28) |
| `availability_classification` | `"unknown"` (default; never auto-issued) |

Expected outcome: identical bytes → `SKIPPED_EXISTING` (`acquisition.py:908-936`)
record whose `storage_path` equals the existing artifact's, no file written after
fetch, and committed manifest/artifact byte-identical.

### 30.4 Preflight checks — all demonstrated offline 2026-10-10 (no network)

| # | Check | Evidence | Result |
|---|---|---|---|
| 1 | Scratch root resolves outside `PROJECT_ROOT` | path resolution + containment | PASS |
| 2 | Pre-run capture of artifact SHA-256 and committed-manifest SHA-256 | `sha256` digest capture | PASS |
| 3 | Scratch manifest is a byte-for-byte copy (same SHA-256) and `load_acquisition_manifest` validates it (contract `1.1.0`, 6 records) | copy + hash compare + pydantic load | PASS |
| 4 | Fresh `acquisition_key` yields a `record_id` absent from the committed manifest | `_slug`/`_make_record`-identical template + set membership | PASS |
| 5 | `expected_sha256` equals the committed record's SHA-256 and the artifact's | hash comparison | PASS |
| 6 | Intended endpoint is the CHC HTTPS URL only; `chirps` is `NONE`-auth with no `endpoint_base`; `era5-land` (the only `cds-api` source) is not invoked | code/config inspection + manifest | PASS |
| 7 | Candidate artifact path lands under the scratch `raw_root`, not the repo | `storage_relative_path` + containment | PASS |
| 8 | No live network request occurred during this phase | nothing invoked; phase executed no acquisition | PASS |

All 12 sub-checks passed (one demonstrator bug was corrected: the `era5-land`
auth enum value is `cds-api`, not `cds_api`). Checks 1–5 and 7 re-run as
commands at execution time; none require network.

### 30.5 Post-run acceptance criteria (authorized run only)

- Exactly one evidence-bearing record is appended to the **scratch** manifest
  with `status="skipped_existing"` and `storage_path` equal to the existing
  artifact's path; the coherence validator (`sha256` + `file_size_bytes` +
  `storage_path`) passes.
- Evidence holds only allowlisted headers; `last-modified` may equal or differ
  from the recovered `2026-09-11T21:10:59Z` — either is reported verbatim,
  never coerced, and never acts as historical-availability proof by itself.
- Request snapshot is redacted (no secrets) and records a live server `status`
  plus any redirect chain honestly.
- `availability_classification` stays `"unknown"`. The captured header is
  evidence for the recorded decision workflow (§28.6), not a self-labelling
  `provider_issued` claim.
- Committed manifest (SHA-256 `1f2b9434…`, contract `1.1.0`, 6 records) and
  artifact (SHA-256 `44934651…d9a6`, 10,288,665 B) are byte-identical before
  and after the run.

### 30.6 Failure and cleanup plan

- Any HTTP failure, timeout, or non-2xx status → one honest `failed` record on
  the scratch manifest, `AcquisitionError` raised, nothing else written; fail
  closed.
- Missing/empty allowlisted headers → capture whatever exists, never
  synthesize; the gate stays closed.
- SHA-256 drift from `expected_sha256` → `CHECKSUM_MISMATCH` + raise
  (`acquisition.py:886-906`); original artifact untouched.
- Storage-key collision (`target.exists()`) → `DuplicateArtifactError` before
  any fetch (`:821-824`, `:1075-1078`).
- Corrupt scratch manifest → `ManifestError` on load; abort.
- Cleanup discards the scratch directory only; the original artifact and the
  committed manifest are never deleted or overwritten. Post-cleanup, verify the
  repo `data/` tree and manifest are byte-identical to their pre-run hashes.

### 30.7 Findings from this phase

- Readiness proven: every preflight check was exercised offline and passed; the
  authorized run needs only explicit authorization plus re-execution of the
  §30.4 commands.
- **Schema gap (new)**: `AcquisitionManifest.records` has no `record_id`
  uniqueness enforcement (`schemas/acquisition.py:258`). The committed manifest
  already holds five ERA5-Land records sharing one `record_id`
  (`REAL-era5-land-operational-…-2026-07-15t0000`: four `failed`, one
  `downloaded`) — only 2 unique ids across 6 records, from repeated CDS attempts
  under one key (`acquire_cds`, `acquisition.py:960`). §29's "no retries"
  observation was specific to the plain HTTP `acquire()` path and is not a
  global guarantee. Consequence: fresh-key uniqueness is an explicit preflight
  responsibility (check 4), not a ledger invariant.
- No CLI/executable acquisition interface exists (only the programmatic driver
  API); recorded as a missing capability rather than implemented.
- No new availability evidence was claimed this phase; the production gate
  stays closed.

### 30.8 Final state

- HEAD `1fee198`; working tree: only `docs/historical-data-coverage.md`
  modified (append-only §§28–30; diff is pure append, `git diff --check`
  clean).
- Manifest SHA-256 `1f2b9434…`, contract `1.1.0`, 6 records, blob `07dc2cdd…`;
  feature contract `1.0.0`; CHIRPS SHA-256 `44934651…d9a6` (10,288,665 B);
  ERA5-Land SHA-256 `af53a81a…4ac9` (127,970 B) — all unchanged.
- Focused offline acquisition suite: **142 passed**. Secret scan (outside this
  document, §29.9 pattern): 117 files / 4 `.env` values, hits = 0.
- No push. STOP: no acquisition, no code changes, no commit.

## 31. Phase 3.7.6D — Final pre-acquisition decision-gate audit (2026-10-10)

No-network decision-gate audit: determine whether the project is ready for a
separately authorized, isolated CHIRPS retrieval-time evidence capture, or
whether an additional safety control is required first. **Read-only plus
documentation append only; no acquisition, no HTTP, no CDS job, no code/manifest/
artifact/contract change, no commit/push.** §§19–30 are preserved byte-for-byte;
§31 appends only.

### 31.1 Scope and method

Each audit task was answered by direct inspection of the actual implementation
(`backend/app/services/acquisition.py`, `backend/app/schemas/acquisition.py`,
`backend/app/redaction.py`, `backend/app/config.py`), the committed manifest
and artifact, and the existing offline test suite. No live endpoint was
contacted. Findings are split into **verified code behavior**, **operator-enforced
safeguards**, and **unresolved risks**.

### 31.2 Task 1 — Manifest write/append and validation path

- `AcquisitionDriver.acquire` sequence (:770–957): config gates (credentials,
  URL/scope) → `load_acquisition_manifest` (:826) → evidence-capturing fetch
  (:830–884) → checksum (:886–906) → content dedupe (:908–936) → immutable
  store (:938–956). Every terminal outcome ends in `_persist_record`.
- `_persist_record` (:559–561) is a **pure append**: `manifest.records.append(
  record)` then `save_acquisition_manifest`. There is **no** duplicate-id check,
  no rejection, no overwrite, no merge — a repeated `record_id` is simply a
  second record with the same id, exactly as the ledger already shows for
  ERA5-Land (one id across four `failed` + one `downloaded`).
- `save_acquisition_manifest` (:524–540) writes `model_dump_json(indent=2,
  exclude_none=True) + "\n"` atomically (tmp file + `os.replace`,
  `_atomic_write` semantics at :383–396); it creates parent directories it is
  pointed at.
- `load_acquisition_manifest` (:509–521): an existing file is validated with
  `AcquisitionManifest.model_validate` (invalid JSON → `ManifestError`); a
  **missing path silently returns an empty ledger** (`generated_at_utc=now`,
  note "Ledger initialised empty…"), which matters for task 4.
- Validation happens at (a) record construction — field constraints plus the
  coherence validator `_state_is_coherent` (`schemas/acquisition.py:232-245`;
  kept records must carry `sha256`+`file_size_bytes`+`storage_path`, failed
  records must not claim a path) — and (b) manifest load. No manifest-level
  constraint exists over `records`.

### 31.3 Task 2 — Does a fresh acquisition key guarantee a unique record_id?

**No.** Two independent reasons from code:

- `record_id` is `f"{kind}-{source}-{_slug(version)}-{_slug(acquisition_key)}"`
  (`_make_record`, :596), where `_slug` (:368–370) lowercases, collapses
  non-word characters and truncates to 60. Two runs that resolve the same
  `kind`/`source`/`version`/key-slug produce an identical id.
- The default key when none is supplied is `utcnow().strftime("%Y%m%dT%H%M%SZ")`
  (:815) — **second resolution**. Two `acquire()` calls for the same
  source/version within the same second collide, and nothing in the schema
  (`records: list[AcquisitionRecord]`, `schemas/acquisition.py:258`) or in
  `_persist_record` rejects, overwrites, or merges the duplicate. Ids collide
  and are **retained**.

Freshness is therefore entirely a caller obligation. The §30.3 key form
(`2026-08-31-evidence-<utcnow>`) must embed a collision-free component (e.g.,
microsecond timestamp or fresh unique suffix) **and** the §30.4 check-4
set-membership test against every existing `record_id` must remain mandatory.
The offline demonstrator confirmed the constructed candidate
`REAL-chirps-v2.0-2026-08-31-evidence-20261010t000000z` is currently absent.

### 31.4 Task 3 — SKIPPED_EXISTING persistence and storage_path

- Reachable only after a **successful fetch whose SHA-256 equals
  `expected_sha256`** (:887–906 passes); dedupe then finds the first kept
  (`downloaded`/`skipped_existing`) record with the same `kind`+`source`+sha
  (:908–917).
- The new record is built (:918–934) with `status="skipped_existing"`,
  `storage_path = existing[0].storage_path` — i.e. the **path string of the
  already-present artifact** (`chirps/chirps__v2.x__2026-08-31.tif.gz` for the
  single CHIRPS kept record) — plus `sha256=actual` and `file_size_bytes`.
- `_atomic_write` is **not** called on this branch, so the existing artifact
  bytes are untouched; the record is appended and returned.
- Caveats: (i) dedupe trusts ledger bytes + live fetch bytes and does **not**
  re-hash the on-disk file — post-run on-disk re-hash closes that loop
  (operator check, §31.7 G9); (ii) `existing[0]` is order-dependent, but with a
  single candidate the reference is unambiguous; (iii) `available_utc` and
  `availability_classification` remain caller-supplied — headers never become
  availability time (test `test_http_headers_never_become_availability_time`).

### 31.5 Task 4 — Scratch isolation: code-enforced or operator convention?

**Operator preflight convention only; no code enforcement exists.**

- Constructor defaults point into the repo tree when no overrides are passed
  (`acquisition.py:649-651`; `config.py:142-146`): `raw_root →
  <root>/data/raw/real`, `manifest_path →
  <root>/data/provenance/acquisition_manifest.json`.
- `save_acquisition_manifest`/`_atomic_write` will `mkdir(parents=True)` and
  write wherever they are pointed; there is **no repo-containment check** and no
  "is this the committed manifest?" check anywhere in the driver.
- Accidental in-repo scratch is therefore possible three ways:
  - **R1** running with default arguments → the evidence record is appended to
    the **committed** manifest and bytes written under `data/raw/real/`;
  - **R2** a typo'd scratch path → `load_acquisition_manifest` silently returns
    an empty ledger (missing path is not an error, :512–516) and the first
    persist creates a fresh manifest (plus any `mkdir`) at the resolved path —
    possibly inside the repo — without ever touching the committed ledger;
  - **R3** a scratch path that resolves inside `PROJECT_ROOT` (relative-path
    mishandling) — both a mis-resolution and R1/R2 are prevented only by the
    explicit §30.4 preflight checks 1–3 (containment + byte-equal copy +
    validating load), which were demonstrated offline.

Minimal-fix proposal only (not implemented, per task 7): (a) a `must_exist=True`
option on `load_acquisition_manifest` to fail on a missing ledger (defeats R2);
(b) an opt-in driver-time guard rejecting `raw_root`/`manifest_path` that
resolve inside `PROJECT_ROOT` unless the caller explicitly acknowledges the
committed paths; (c) an assert that the supplied `manifest_path` content is
byte-identical to `settings.ACQUISITION_MANIFEST` at construction. Forward-only
additions; they would require a separate reviewed change and must not touch
legacy records.

### 31.6 Task 5 — Evidence whitelist and sanitization: verified vs assumed

**Verified by code and offline tests** (tests in
`backend/tests/test_acquisition_rig.py` unless noted):

- Header allowlist only: `last-modified`, `etag`, `date`, `content-length`
  (`schemas/acquisition.py:36`); `_allowlisted_headers` (:410–424) keeps only
  those, lowercased, control-chars stripped and truncated to 512 chars
  (`redaction.py:19`, `bound_string` :100). Tests: allowlisted-only capture,
  bounded values, control-char stripping.
- `Last-Modified` is stored verbatim even when invalid and **never** becomes
  `available_utc`; absent headers keep classification `"unknown"`. Tests:
  `test_invalid_last_modified_value_is_stored_verbatim`,
  `test_provider_omitted_availability_headers_stay_unknown`,
  `test_explicit_availability_classification_is_preserved`.
- Request URL, `final_url` and every redirect hop are redacted by
  `redact_url`/`_redact_chain` and the redacted names are recorded
  (`:867–871`); malformed URLs fail closed. Tests: redirect request/final/chain,
  URL-secret redaction, malformed-URL fail-closed.
- `retrieval_params` are scrubbed recursively (sensitive keys dropped, `url`/
  `export_url` redacted, depth cap 25) (:431–465). Tests: sensitive and nested
  secret scrubbing.
- `provider_metadata` is sanitized and bounded by the schema validator
  (`schemas/acquisition.py:200-230`; caps at `redaction.py:22-23`). Test:
  `test_provider_metadata_is_sanitized_and_bounded`.
- Error strings are redacted via `redact_text` (:468–477); failed fetches (with
  and without a response) and checksum mismatches still persist honest evidence
  records (:830–862, :886–906). CDS-side token/host protection is separately
  tested (`tests/test_cds_acquisition.py`).

**Remaining operational assumptions (not provable offline this phase):**

- A1 the exact committed CHIRPS URL still serves the same bytes over HTTPS
  (single anonymous GET, `timeout=120`, `headers={}`) at run time;
- A2 CHC actually returns an allowlisted header (especially `Last-Modified`) —
  absence is handled but leaves only `date`/`etag` or an empty evidence set;
- A3 if a redirect occurs, the final resource's headers/status describe the
  resolved file (code captures that); CHC's live behavior is external;
- A4 even a captured current `Last-Modified` is evidence, not historical-proof
  (§28.5) — an audit posture, not a code property;
- A5 redaction correctness depends on the tuned `redact_url`/`redact_text`
  (tested, fail-closed on malformed URLs, but novel adversarial shapes are not
  exhaustively provable).

### 31.7 Task 6 — Explicit go/no-go criteria for a future authorized run

All checks below must re-clear **as run-time commands** at the authorized
execution, in addition to the recorded human authorization for the GET itself
(G10). G1–G9 mirror §30.4 and were all demonstrated offline on 2026-10-10.

| # | Criterion | Required evidence |
|---|---|---|
| G1 | Scratch root and scratch manifest resolve **outside** all tracked repo paths | containment test vs `PROJECT_ROOT` (PASS, §30.4-1) |
| G2 | Full SHA-256 and size of the **original** artifact and of the **committed** manifest recorded pre-run | `sha256` digests (PASS, §30.4-2); artifact `44934651…d9a6` 10,288,665 B; manifest `1f2b9434…` |
| G3 | Fresh record identity verified against **every** existing `record_id` | set-membership == absent (PASS, §30.4-4); schema has no enforcement, caller substitutes |
| G4 | `expected_sha256` equals the original artifact's hash | hash comparison (PASS, §30.4-5) |
| G5 | Exact CHIRPS endpoint + GET-only request verified | URL host check + `request_method="GET"` (PASS, §30.4-6) |
| G6 | No CDS/ERA5 path reachable from this invocation | `chirps` is `authentication=NONE`, no `endpoint_base`; `era5-land` is the only `cds-api` source and is not constructed (PASS, §30.4-6/§30.3) |
| G7 | Result evidence written **only** to scratch | candidate path lands under scratch raw root (PASS, §30.4-7); stride on defaults (R1) rejected |
| G8 | Content drift or missing headers never fabricate an availability timestamp or `provider_issued`; `availability_classification="unknown"` | verbatim header capture + caller-supplied time (tests in §31.6); enforced at run |
| G9 | Post-run hashes prove committed manifest and original artifact byte-identical | pre/post hash diff (G2 baseline) |
| G10 | Explicit recorded human authorization for the live GET | decision record before any request |

**Verdict: CONDITIONAL GO.** The path is safe and fully specified, requires no
code change, and every offline-demonstrable criterion already passes. Execution
is permitted **only** under explicit authorization and re-clearing G1–G9 at run
time. The conditions are: (C1) isolation and uniqueness are operator-enforced,
not code-enforced (§31.5) — each run must repeat the preflight; (C2) live server
behavior (A1–A3) can only be confirmed at run time; (C3) the mandatory post-run
integrity re-hash (G9) precedes any decision on the captured evidence.

### 31.8 Unresolved risks register

| # | Risk | Impact | Control / owner |
|---|---|---|---|
| R1 | Default `raw_root`/`manifest_path` write into the repo tree | committed manifest mutated on an unauthorized default-style run | Operator: always pass scratch paths; G1/G7 preflight (operator) |
| R2 | Missing/typo'd scratch manifest silently yields an empty ledger | stray manifest created at the wrong path; committed ledger untouched but evidence lost/misplaced | Operator: G2/G3 byte-equal + load-validation preflight (operator); proposal §31.5*(a)* (unimplemented) |
| R3 | Scratch path accidentally inside `PROJECT_ROOT` | evidence/bytes land in the repo | Operator: containment check G1 (operator) |
| R4 | No `record_id` uniqueness enforcement (R4) | duplicate ids retained on re-entry (already observed for ERA5-Land) | Operator: fresh-key discipline + G3 (operator); proposal §31.5 numeric/enum approach (unimplemented) |
| R5 | On-disk artifact drift vs recorded sha is not re-checked at dedupe time | a dedupe hit could point at a changed file | Operator: post-run on-disk re-hash G9 (operator) |
| R6 | Q7 ERA5-Land availability unresolved; Q6 production gate closed | production temporal features stay `NEEDS_EVIDENCE`; production **NO-GO** | Audit stance, unchanged; decision workflow per §28.6 |

### 31.9 Final state

- HEAD `1fee198`; working tree: only `docs/historical-data-coverage.md`
  modified (append-only §§28–31; `git diff --check` clean, diff is pure append).
- Manifest SHA-256 `1f2b9434…`, contract `1.1.0`, 6 records, blob `07dc2cdd…`;
  feature contract `FEATURE_CONTRACT_VERSION="1.0.0"`
  (`backend/app/schemas/features.py:71`) — unchanged.
- CHIRPS artifact SHA-256 `44934651…d9a6` (10,288,665 B) and ERA5-Land
  SHA-256 `af53a81a…4ac9` (127,970 B) — unchanged.
- Focused offline acquisition suite (`python -m pytest
  tests/test_acquisition_rig.py tests/test_cds_acquisition.py -q -o addopts=""`
  from `backend/`): **142 passed**.
- Secret scan: 117 files against 4 `.env` values, **hits = 0**.
- No push; no live network request occurred this phase.

### 31.10 Verdict

CONDITIONAL GO, gated on explicit authorization (§31.7 G10). No additional
safety control is a required **code** change; the required controls are the
operator-enforced preflight G1–G9 and the recorded authorization — all defined
and offline-verified. Q6 production gate stays **CLOSED** pending that authorized
capture and a recorded decision; Q6 research/replay stays recovered; Q7 remains
`EXTERNAL_EVIDENCE_REQUIRED`; temporal production features remain `NEEDS_EVIDENCE`;
overall production remains **NO-GO**. STOP — no acquisition was performed.

## 32. Phase 3.7.6E1 — Final runtime preflight, no acquisition (2026-10-10)

Preflight only: prepare the final execution manifest for a potential isolated
CHIRPS evidence capture. **No HTTP/network, no `AcquisitionDriver.acquire`/
`acquire_cds`, no calls into any acquisition code path, no writes to scratch
manifests or artifact roots, no mutation of committed manifest/original
artifact/source/schemas/contracts/tests, and no authorization of the future
capture is given this phase.** §§19–31 are preserved byte-for-byte; §32 appends
only. All numbers below were **recomputed** read-only this phase (script run
from `backend/`, `PYTHONPATH=backend`, writes nothing).

### 32.1 Actual paths and full hashes checked

- Committed manifest: `D:\PROJECTS\landslideguard-ai\data\provenance\acquisition_manifest.json`
  — exists at the settings path, parsed successfully, `contract_version=1.1.0`,
  **6 records**; full SHA-256 `1f2b9434b199fee8809232cd8bfdf889983629d29d1546af7a2dbad747967d43`.
- Original artifact: `D:\PROJECTS\landslideguard-ai\data\raw\real\chirps\chirps__v2.x__2026-08-31.tif.gz`
  — exists, full SHA-256 `449346515d840eeb4bf5c613a344777afe317800269386f2e93fdb3943a8d9a6`,
  size 10,288,665 B; manifest record fields match (record `sha256` and
  `file_size_bytes` equal).
- All 6 existing record IDs enumerated (two unique values; the ERA5-Land ID
  repeats five times — duplicates retained, as documented in §30.7/§31.3).

### 32.2 G1–G9 matrix (recorded this phase; runtime-only facts never inferred)

| # | Criterion | Status | Evidence this phase |
|---|---|---|---|
| G1 | Scratch root + scratch manifest outside tracked repo paths | **PASS** | resolved to `%TEMP%\p376e1_scratch\raw` and `…\acquisition_manifest.json`; outside `PROJECT_ROOT`, not under `data/`, not equal to committed manifest or artifact root (path resolution only — no files created per no-write rule) |
| G2 | Pre-run full artifact + committed-manifest hashes recorded | **PASS** | full SHA-256/sizes recomputed (§32.1) |
| G3 | Fresh `record_id` verified against every existing ID | **PASS** | candidate `REAL-chirps-v2.0-2026-08-31-evidence-20261010t041641.555264z` (from a freshly generated key) absent from both the unique set and the full list incl. duplicates; operator re-check mandatory at run time — no schema enforcement (§31.3) |
| G4 | `expected_sha256` equals original artifact | **PASS** | `44934651…d9a6` == artifact SHA-256 == manifest record SHA-256 |
| G5 | Exact CHIRPS endpoint + GET-only | **PASS** | URL `https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_daily/tifs/p05/2026/chirps-v2.0.2026.08.31.tif.gz`, host prefix `https://data.chc.ucsb.edu/`, `authentication=NONE`, no `endpoint_base`, `require_bounded_scope=False`, extension `.tif.gz`, `request_method="GET"` hardcoded, `timeout=120` |
| G6 | No CDS/ERA5 path reachable | **PASS** | `chirps` has no CDS entry; only `era5-land` is `cds-api` and is not constructed by this invocation |
| G7 | Result evidence written only to scratch | **BLOCKED** | runtime-only; requires the authorized run (no-write rule forbids creating scratch this phase). Preflight mapping verified: fresh-key storage path
  `chirps/chirps__v2.x__2026-08-31-evidence-…z.tif.gz` resolves inside scratch raw root |
| G8 | Drift/missing headers never fabricate timestamp or `provider_issued` | **PASS** (code/tests); runtime observation deferred | verbatim header capture; `available_utc` caller-supplied; classification default `unknown` (§31.6 tests) |
| G9 | Post-run hashes prove committed manifest + artifact unchanged | **BLOCKED** | post-run by definition; mandatory before judging captured evidence (§31.7 C3) |

### 32.3 Empty-ledger-on-missing-manifest risk and fail-closed operator safeguard (R2)

`load_acquisition_manifest` returns a **fresh empty ledger** when the target
path does not exist (`acquisition.py:512-516`). A typo'd scratch manifest path
would therefore silently carry an empty ledger instead of the committed copy,
and the first persist would create a stray manifest at the wrong path (R2,
§31.8). Nothing relies on that fallback: this phase verified the committed
manifest exists at the exact settings path and parses. **Fail-closed run-time
gate (before constructing the driver):** (1) `manifest_path` argument given
explicitly (never default); (2) `assert scratch_manifest.exists()`; (3)
`assert sha256(scratch_manifest bytes) == 1f2b9434b199fee8809232cd8bfdf889983629d29d1546af7a2dbad747967d43`;
(4) `assert scratch_raw`/`scratch_manifest` resolve outside `PROJECT_ROOT`;
any assertion failure → ABORT, no GET. Same discipline protects against R1
(default `raw_root` write to the repo tree) and R3 (in-repo scratch).

### 32.4 Byte-for-byte scratch-copy property (verified without writing)

Per the no-write rule no scratch file was created this phase. The copy property
was verified **in-memory**: reading the committed manifest bytes yields
SHA-256 `1f2b9434…d43`, identical to the on-disk file digest, so any copy made
from those bytes at the authorized run is byte-for-byte identical (and then the
run-time gate §32.3 re-asserts equality on the file before any execution).

### 32.5 Proposed future invocation (grounded in the implementation; NOT executed)

Programmatic driver call only (no CLI exists). This is the exact parameter set
the implementation accepts (`AcquisitionDriver.acquire`, `acquisition.py:770`):

```python
from pathlib import Path
from datetime import datetime, timezone
from app.services.acquisition import AcquisitionDriver, AcquisitionTransport

C = "https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_daily/tifs/p05/2026/chirps-v2.0.2026.08.31.tif.gz"
driver = AcquisitionDriver(
    source="chirps",
    raw_root=Path(r"%TEMP%\p376e1_scratch\raw"),                 # outside repo; assert in §32.3
    manifest_path=Path(r"%TEMP%\p376e1_scratch\acquisition_manifest.json"),  # byte-copy; assert exists+hash in §32.3
    transport=AcquisitionTransport(),                            # anonymous single GET, timeout=120
)
record = driver.acquire(
    retrieval_params={"url": C, "extension": ".tif.gz"},         # bbox optional: chirps require_bounded_scope=False
    expected_sha256="449346515d840eeb4bf5c613a344777afe317800269386f2e93fdb3943a8d9a6",
    acquisition_key=<fresh key re-verified against ALL existing record_ids>,   # see G3
    source_record_id="chirps-v2.0.2026.08.31.tif.gz",
    product_version="v2.0",
    observation_start_utc=datetime(2026, 8, 31, tzinfo=timezone.utc),
    observation_end_utc=datetime(2026, 9, 1, tzinfo=timezone.utc),
    available_utc=datetime(2026, 9, 11, 21, 10, 59, tzinfo=timezone.utc),  # caller-supplied recovered value (§28)
    availability_classification="unknown",
    availability_source="response_headers.last-modified",
    availability_derivation=None,
)
```

Expected outcome (if executed with byte-identical content): one
`SKIPPED_EXISTING` record on the scratch manifest whose `storage_path` equals
`chirps/chirps__v2.x__2026-08-31.tif.gz`; no file written; committed manifest
and original artifact byte-identical; then mandatory G9 post-run re-hash before
any decision on the captured header. Not authorized, not executed this phase.

### 32.6 Facts that still require explicit authorization or runtime observation

- G10: an explicit recorded human authorization for the single live GET.
- The actual `acquisition_key` value at run time (this phase's sample key is
  illustrative only) plus a repeated G3 membership check.
- A1–A3 server behavior: reachability, exact headers returned (esp.
  `Last-Modified`), and any redirect resolution of the final resource.
- G7 evidence-write location and G9 post-run integrity — runtime only.

### 32.7 Final state and close-out

- HEAD `1fee198`; working tree: only `docs/historical-data-coverage.md`
  modified (append-only §§28–32; `git diff --check` clean).
- Manifest SHA-256 `1f2b9434…d43`, contract `1.1.0`, 6 records, blob
  `07dc2cdd…`; feature contract `1.0.0`
  (`backend/app/schemas/features.py:71`); CHIRPS SHA-256 `44934651…d9a6`
  (10,288,665 B); ERA5-Land SHA-256 `af53a81a…4ac9` (127,970 B) — unchanged.
- Focused offline acquisition suite (`python -m pytest
  tests/test_acquisition_rig.py tests/test_cds_acquisition.py -q -o addopts=""`
  from `backend/`): **142 passed**.
- Secret scan: 117 files against 4 `.env` values, hits = 0.
- No commit, no push, and no acquisition was performed or authorized in this
  phase. Q6 production gate stays **CLOSED** (research/replay recovered); Q7
  remains `EXTERNAL_EVIDENCE_REQUIRED`; temporal production features remain
  `NEEDS_EVIDENCE`; overall production remains **NO-GO**.

## 33. Phase 3.7.6H — Q6 CHIRPS availability evidence adjudication (2026-10-10)

Adjudication-only phase: apply the pre-authorized acceptance criteria
(§23.8, §28, §29.6, §29.7, §30) to the single authorized isolated
retrieval-time capture reported by Phase 3.7.6G, and record the bounded Q6
decision. No network call, no acquisition, no change to source code, manifest
(records or ids), artifact bytes, schemas, contracts, or classification values;
no commit, no push. §§19–32 are preserved byte-for-byte; only §33 is appended.

### 33.1 Evidence under adjudication (reported run results)

The values below are transcribed from the Phase 3.7.6G run report and are
treated as **reported run results, not independently verified local files**.
Because the scratch manifest that held the acquisition record was discarded
after post-run verification, **the evidence record is not available for future
reinspection in this repository** unless separately retained; this section does
not claim the scratch record can still be retrieved.

| Fact | Reported value |
|---|---|
| Request URL | `https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_daily/tifs/p05/2026/chirps-v2.0.2026.08.31.tif.gz` |
| HTTP status | `200`; `redirect_chain` `None`; `final_url` == request URL |
| `retrieved_utc` | `2026-10-10T04:47:17.083682Z` |
| `acquired_utc` | `2026-10-10T04:47:28.072259Z` |
| `last-modified` | `Fri, 11 Sep 2026 21:10:59 GMT` (= `2026-09-11T21:10:59Z`) |
| `etag` | `"6aa46e63-9cfe19"` |
| `content-length` | `10288665` |
| `date` header | `Sat, 10 Oct 2026 04:47:19 GMT` |
| Delivered bytes SHA-256 | `449346515d840eeb4bf5c613a344777afe317800269386f2e93fdb3943a8d9a6` (= committed artifact) |
| Outcome | `SKIPPED_EXISTING`; `storage_path` `chirps/chirps__v2.x__2026-08-31.tif.gz`; existing artifact not rewritten; scratch `raw_root` gained no files |
| Capture record id | `REAL-chirps-v2.0-2026-08-31-evidence-20261010t044717.014650z` (scratch-only) |
| `availability_classification` | `unknown`; `availability_source` `response_headers.last-modified` |
| Post-run integrity (reported) | committed manifest and original artifact hashes unchanged; scratch tree discarded |

### 33.2 Acceptance-criteria reading (§22.3, §23.8, §28, §29.6)

Evidence classes involved in Q6 (distinguished per §22.3/§25):

- **Provider/archive evidence**: CHC live directory listing of
  `.../tifs/p05/2026/`, per-file mtime `2026-Sep-11 21:10` for the exact file,
  fetched 2026-10-10 (§28.2 row 3). Corroborating, but a retrieval-time
  observation; §28 treats it as corroborating provider metadata, **not** as a
  capture at the original acquisition (§28.5).
- **Artifact-embedded**: gzip MTIME raw `1789161059` = `2026-09-11T21:10:59Z`,
  FLG 0x08 (FNAME), compressed size 10,288,665 B (§28.2 row 2) —
  provider-produced production/compression metadata inside the immutable bytes
  we hold.
- **Retrieval-time HTTP headers**: `Last-Modified`/`ETag`/`Date`/`Content-Length`
  captured during the 3.7.6G single GET (retrieval instant
  `2026-10-10T04:47:17Z`).
- **Retrieval/acquisition lifecycle**: `retrieved_utc`/`acquired_utc` of the
  3.7.6G request — when *our* GET ran, not the original `2026-10-08`
  acquisition.
- **Engineering-derived bounds**: Q7 `available_utc 2026-09-15T00:00:00Z`
  (vintage + 2 months, K=0, §25.4).

What the matching `Last-Modified` **corroborates** (§29.6):

1. The provider's served copy of this exact file carries the same stable mtime
   as the historical directory listing and our artifact's gzip MTIME; the file
   has not been re-touched since `2026-09-11T21:10:59Z`.
2. The delivered bytes hash exactly to the committed artifact (the
   `SKIPPED_EXISTING` dedupe requires this), so the provider currently serves
   content byte-identical to our artifact.
3. The evidence chain is internally consistent at every link:
   **artifact bytes → gzip MTIME → provider directory listing → live
   `Last-Modified`** (§29.6).

What it does **not** establish (§23.8, §28.2 caveats, §29.6):

1. It was captured at a new retrieval instant, not the original `2026-10-08`
   acquisition; it does not prove the provider served/published that value on
   the original retrieval date or on any specific earlier date.
2. `Last-Modified` is a server-evidenced bound ("resource in this state **no
   later than** its mtime", §23.8) — a modification-time property, **not** a
   provider-declared publication time and **not** proof of the artifact's first
   availability; it cannot backdate availability below the recovered value, and
   a hypothetical re-upload that preserved the mtime would be
   indistinguishable (§28.2 caveat).
3. Per the pre-authorized criteria it is accepted only as **retrieval-time
   server evidence**, never auto-labelled `provider_issued`; the record's
   classification must stay `unknown` (§29.6).

### 33.3 Bounded Q6 decision

Applying §23.8/§29.6/§29.7 exactly (no new classification, no loosening):

- **Research/replay** — stays **RECOVERED** (unchanged from §28; not newly
  loaded by this phase).
- **Historical availability** — **CORROBORATED**: the retrieval-time
  `Last-Modified` equals the recovered `2026-09-11T21:10:59Z`, closing the
  chain in §33.2. Corroboration strengthens confidence in the recovered value
  but does not change its classification.
- **Classification of the 3.7.6G record** — remains **`unknown`**:
  `Last-Modified` is evidence, not a derivation (§29.6), and it is a
  server-evidenced modification time, not proof of first availability.
- **Production gate** — position: §29.7 holds Q6 production **CLOSED** until
  "an authorized retrieval-time capture **and** a recorded production-gate
  decision". The capture occurred, but on adjudication it yields retrieval-time
  server evidence observed at a later instant — not a `provider_issued`
  `available_utc` at the original acquisition — and the only evidence that
  clears a production gate is `provider_issued` (§23.8). The recorded decision
  (this section) therefore **keeps the gate CLOSED**; no production-gate change
  is authorized this phase. A future reconsideration would additionally need
  the evidence retained in-repo (the 3.7.6G record was discarded with its
  scratch) and a fresh §28.6/§29.7 recorded decision; neither is authorized.

### 33.4 Register posture after §33 (unchanged except as explicitly recorded)

- **Q6 CHIRPS**: research/replay **recovered** (§28); historical availability
  **corroborated** by retrieval-time server evidence (this section);
  `provider_issued` **not** established; production gate **CLOSED** (recorded
  decision: no production-gate change).
- **Q7 ERA5-Land**: stays `EXTERNAL_EVIDENCE_REQUIRED`; unchanged.
- Temporal production features (CHIRPS + ERA5-Land): stay `NEEDS_EVIDENCE`;
  unchanged. Overall production stays **NO-GO**; unchanged.
- No `provider_issued` claim, no manifest/artifact/contract/classification or
  system change; nothing stored in-repo beyond this sub-section.
- Scratch-only provenance: the underlying capture record is not retained
  in-repo and cannot be re-inspected unless separately retained; §§33.1/33.2
  are the retained transcription.

### 33.5 Explicit non-claims

- Not claiming the 3.7.6G scratch record is retrievable (it was discarded after
  post-run verification; §33.1).
- Not claiming `Last-Modified` proves the provider served/published the file on
  `2026-09-11` or on the original `2026-10-08` retrieval date.
- Not claiming `Last-Modified` proves first availability or constitutes a
  `provider_issued` `available_utc`.
- Not claiming any production-gate change, any code/manifest/artifact/
  classification/contract change, or any independently verifiable in-repo
  evidence beyond this transcribed appendix.

### 33.6 Verification and scope

- HEAD `7c5e262`; working tree: only `docs/historical-data-coverage.md` modified
  (this §33 append); `git diff --check` clean.
- Manifest SHA-256 `1f2b9434…d43`, contract `1.1.0`, 6 records, blob
  `07dc2cdd…`; feature contract `1.0.0` (`backend/app/schemas/features.py:71`);
  CHIRPS SHA-256 `44934651…d9a6` (10,288,665 B); ERA5-Land SHA-256
  `af53a81a…4ac9` (127,970 B) — all unchanged.
- Focused offline suite (`python -m pytest tests/test_acquisition_rig.py
  tests/test_cds_acquisition.py -q -o addopts=""` from `backend/`): **142
  passed**.
- Secret scan: 117 files against 4 `.env` values, hits = 0.
- Sections audit: §§28–33 each appear exactly once, in order; §§19–32 preserved
  byte-for-byte.
- No network call made in this phase; no commit, no push.

### 33.7 Verdict

Q6 historical availability is now **corroborated** by a matching retrieval-time
`Last-Modified` (server-evidenced mtime identical to the recovered value), but
the evidence does not rise to `provider_issued` and cannot prove the artifact's
first availability; the Q6 **production gate therefore remains CLOSED by
recorded decision**, while research/replay stays **recovered**. Q7 remains
`EXTERNAL_EVIDENCE_REQUIRED`; temporal production features remain
`NEEDS_EVIDENCE`; overall production remains **NO-GO**. Because the underlying
record lived only in discarded scratch, this appendix is the retained
transcription of the evidence and the recorded decision.

## 34. Phase 3.7.8G — CHIRPS multi-day rolling aggregation: feature contract 1.1.0 documentation (2026-10-10)

Documentation-only phase. It records the accepted Phase 3.7.8F implementation of
multi-day CHIRPS precipitation rolling aggregation and the feature-contract
version bump to `1.1.0`. No source code, test, schema, manifest, artifact,
acquisition policy, or feature classification was changed this phase; no network
call, no acquisition, no commit, no push. §§1–33 are preserved byte-for-byte;
only §34 is appended. Where earlier sections (§§22–33) state the **feature**
contract was `1.0.0`, that is a correct historical snapshot of those phases;
this section records the current, changed value. The **acquisition manifest**
contract remains `1.1.0` and is unrelated to this bump.

### 34.1 Two contract versions (do not conflate)

- **Acquisition manifest contract** — `contract_version` `1.1.0`, unchanged by
  this phase (6 records; manifest SHA-256 `1f2b9434…d43`, blob `07dc2cdd…`).
- **Feature-extraction contract** — `FEATURE_CONTRACT_VERSION` was `1.0.0`
  through Phase 3.7.6H and is now **`1.1.0`**
  (`backend/app/schemas/features.py`), bumped in Phase 3.7.8F because the change
  is additive but observable in `FeatureExtractionResult.contract_version` and
  in the provenance schema.

### 34.2 Schema additions (`backend/app/schemas/features.py`)

- `FEATURE_CONTRACT_VERSION = "1.1.0"`.
- New `FeatureDayProvenance`: the per-day trace for one daily artifact
  aggregated into a multi-day window. Fields: `observation_start_utc`,
  `observation_end_utc`, `available_utc` (nullable),
  `availability_classification` (nullable), `acquisition_record_id`,
  `source_record_id`, and `artifact_sha256` (validated as a standard SHA-256 hex
  digest). Datetimes must be timezone-aware, and `observation_end_utc` must not
  precede `observation_start_utc`.
- `FeatureProvenance` gains `days: list[FeatureDayProvenance] | None`
  (default `None`). When present it must be strictly ascending by
  `observation_start_utc`, and its **last** entry must equal the anchor's
  `observation_start_utc`. Single-day features keep `days = None`, so
  single-artifact results are unchanged.

### 34.3 Rolling aggregation semantics (`backend/app/services/features.py`)

- **Anchor day `D`** is the resolved record's `observation_start_utc.date()`.
  The record is resolved as the most recently acquired kept REAL record for the
  source (or one pinned by `artifact_sha256`), so the anchor day is always
  present by construction.
- **Inclusive window** `[D − (N − 1), D]`, where `N = window_days`. Supported
  CHIRPS precipitation features: `precipitation_daily_mm` (direct) and rolling
  `precipitation_1d_mm` (1), `precipitation_3d_mm` (3), `precipitation_7d_mm`
  (7), `precipitation_14d_mm` (14), `precipitation_30d_mm` (30). The 1-day
  window is handled on the single-day path and equals the anchor day's value.
- **Summation in millimetres**: the value is the sum of each required day's
  nearest-cell precipitation sample, in `mm`. No averaging, weighting,
  interpolation, or spatial resampling.
- **Double precision, unrounded**: samples are IEEE-754 float64 and are summed
  without rounding, quantization, or clamping, so the stored value is the raw
  floating-point total (for example `0.1 + 0.1 + 0.1 != 0.3`).

### 34.4 Fail-closed behavior

Status precedence within a window is
**raise > rejected > insufficient > missing > valid**:

- **Conflicting same-day hashes → raise.** Two kept records for the same day
  with different SHA-256 raise `FeatureContractError` naming the date and every
  candidate `record_id` in stable lexical order; the ambiguity is never
  silently resolved. Identical same-day SHA-256 values dedupe deterministically
  to one day (lowest `record_id`).
- **Rejected required day → whole window rejected.** If any required present day
  fails the leakage rule or the request's availability policy, the entire window
  is `REJECTED_LEAKAGE` with a null value. A rejected day invalidates every
  window whose inclusive range contains it (for example a rejected interior day
  rejects both the 3-day and 7-day windows, while the daily value is unaffected).
- **Missing day / incompatible product-version → insufficient.** A required day
  with no kept daily record, or whose product/version is not compatible with the
  provider registry, yields `INSUFFICIENT_TEMPORAL_COVERAGE`, a null value, and
  an explanatory note. Missing history is never zero-filled.
- **Mixed vintages → insufficient.** Two or more distinct compatible
  `product_version` values within one window fail closed as
  `INSUFFICIENT_TEMPORAL_COVERAGE` ("mixed product vintages … are not
  aggregated"), never averaged or concatenated.
- **Nodata → missing.** If any required day's sampled cell is CHIRPS nodata
  (`-9999`), the window is `MISSING` with a null value; a nodata cell is never
  converted to zero.

No partial sum is ever emitted: the total is computed only after every required
day is present, single-vintage, and non-nodata. Each selected day's
product/version and recomputed SHA-256 are verified before any pixel decoding or
sampling begins.

### 34.5 Per-day provenance vs anchor-day provenance

- For a multi-day window, `FeatureProvenance.days` lists one
  `FeatureDayProvenance` per selected (present) day, in ascending date order;
  absent days have no entry and are instead named in the feature note.
- The singular `FeatureProvenance` fields continue to describe the **anchor
  (last) day**: `artifact_sha256`, `acquisition_record_id`, `source_record_id`,
  and `observation_start_utc` all equal the last `days` entry. A multi-day
  window is therefore never traced through the singular hash alone.
- For single-day and 1-day features, `days = None` and the singular fields
  describe that single artifact (unchanged from before 1.1.0).

### 34.6 Implementation/test coverage ≠ real-world evidence

- The behavior above is verified by **synthetic fixture grids** and in-memory
  manifests in `backend/tests/test_feature_contract.py` (18 added test
  functions / 25 collected cases: 3/7/14/30-day sums, unrounded float64, nodata
  and missing positions, same-SHA dedupe, conflicting-SHA error,
  order-independent determinism under a shuffled manifest, incompatible and
  mixed versions, production vs research availability gates, rejected-day
  propagation, SHA-before-decode, per-day provenance, and anchor
  short-circuit), plus the full backend suite (**370 passed**).
- **Only one real CHIRPS daily artifact exists** in the repository
  (`data/raw/real/chirps/chirps__v2.x__2026-08-31.tif.gz`, SHA-256
  `44934651…d9a6`, 10,288,665 B). Real, end-to-end **multi-day** validation has
  therefore **not** been demonstrated; the single real-artifact production-path
  test asserts that the 7-day request is `INSUFFICIENT_TEMPORAL_COVERAGE` for
  exactly this reason.
- Test success is engineering verification only. It is not provider evidence,
  not a real-world accuracy claim, and not production approval.

### 34.7 Preserved evidence posture (unchanged by this phase)

- **Q6 CHIRPS**: research/replay **recovered**; historical availability
  **corroborated** by retrieval-time `Last-Modified`; `provider_issued` **not**
  established; production gate **CLOSED** by recorded decision (§33).
- **Q7 ERA5-Land**: remains `EXTERNAL_EVIDENCE_REQUIRED`.
- Temporal production features (CHIRPS and ERA5-Land): remain `NEEDS_EVIDENCE`.
- Overall production: remains **NO-GO**.

This phase claims **no** `provider_issued` availability and **no** production
readiness; either would require new, separately authorized evidence.

### 34.8 Verification for this phase

- HEAD `7c5e262f42c7a1bfe1a27cc47c73f79d29b8d02a`, branch `main`.
- Before this phase the working tree held the four code/test modifications plus
  the §33 docs baseline; this phase additionally edits only
  `docs/historical-data-coverage.md` (appends §34).
- `git diff --check`: clean. §§1–33 preserved; §34 appended. No code, test,
  schema, manifest, artifact, or policy change.

### 34.9 Explicit non-claims

- Not claiming real multi-day CHIRPS validation (only one real daily artifact is
  available).
- Not claiming `provider_issued` availability or any production-gate change.
- Not claiming model training, accuracy, or deployment readiness.
- Not modifying the historical `1.0.0` feature-contract statements in §§22–33,
  which remain accurate for the phases they record.
