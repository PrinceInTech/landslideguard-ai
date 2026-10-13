# Research Decision Record

Source phases: **3.36** and **3.37**.

These are conversation-level owner choices recorded on **2026-10-12**. This file
is their **first repository persistence**; prior phases reconciled them only in
terminal output and did not write them to any repository file.

`Owner choice` is the verbatim selection made by the owner. `Status` is the
normalized value derived from it. Owner choice and normalized status are kept
distinct on purpose.

| ID | Decision | Owner choice | Status | Evidence basis | Blocker | External evidence required | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| D1 | NE India bounding box | APPROVE | APPROVED | Existing boundary in `backend/app/schemas/features.py` (EPSG:4326) | None | No | Retain the proposed EPSG:4326 boundary. Approval of scope only; no new data. |
| D2 | Temporal study window | OPEN | OPEN | `docs/historical-data-coverage.md` (single-day CHIRPS coverage) | Authorized multi-day data coverage | Yes | Window remains unfixed pending authorized, contiguous coverage. |
| D3 | COOLR location-accuracy semantics | DEFERRED | DEFERRED | `docs/historical-data-coverage.md` (accuracy codes unresolved) | Authoritative accuracy-code semantics | Yes | No accuracy-filtering rule is fixed until authoritative semantics are available. |
| D4 | Inclusion/exclusion/deduplication | DEFER | DEFERRED | Draft criteria only; not validated | Applicable reuse terms and label-source requirements | Yes | Draft remains pending until reuse terms and label-source requirements are resolved. |
| D5 | Cutoff, provenance instants and fail-closed gates | APPROVE | APPROVED | `docs/provenance.md`; `docs/features.md`; `docs/historical-data-coverage.md` | None | No | Preserve existing safeguards. Does not resolve Q7. |
| D6 | Chronological + geographic holdout with buffer | APPROVE | APPROVED | Proposed evaluation design | None | No | Approved as the proposed research evaluation design, **not** evidence of successful validation. |
| D7 | Baseline and metrics | APPROVE | APPROVED | Proposed metric set | None | No | Retain the rainfall-threshold baseline and proposed metric set. **The demo Random Forest has label leakage and is not valid real-world performance evidence** (see `docs/model.md`). |
| D8 | CHIRPS version strategy | DEFER | DEFERRED | Existing v2 artifact; no v3 docs | v3 time-coordinate/unit compatibility documentation and review | Yes | Existing v2 artifact replay remains a proposed research action; future v3 use requires compatibility documentation and review. This record does **not** authorize data acquisition or replay execution. |

## Frozen statuses (unchanged)

- Q6: `CLOSED`
- Q7: `EXTERNAL_EVIDENCE_REQUIRED`
- ERA5-Land eligibility: `NEEDS_EVIDENCE`
- Production readiness: `NO-GO`
- Remote CI: `NOT VERIFIED REMOTELY`

## References (detail kept in existing documents, not duplicated here)

- `docs/historical-data-coverage.md` — coverage, availability classification, Q6/Q7 register, go/no-go.
- `docs/provenance.md` — four-instant provenance semantics.
- `docs/features.md` — rolling-window / `insufficient_temporal_coverage` behavior.
- `docs/model.md` — demo model and label-leakage caveat.

## Label-source authorization blockers (unresolved)

- Written NRSC/ISRO/Bhuvan authorization has **not** been obtained or verified.
- The required event-level, machine-readable landslide inventory and its availability remain **unconfirmed**.
- Any permission scope must explicitly cover academic research, event-level use, derived features, publication, attribution, and any redistribution.
- Bhuvan viewing access must **not** be treated as permission to copy, derive, bulk-download, or redistribute data.
- COOLR/Global Landslide Catalog reuse rights and the relevant event-location (accuracy-code) semantics remain **unresolved** (see D3, D4).
- No provider request has been sent, no new data has been acquired, and no external authorization is implied by the approved research-protocol decisions (D1, D5, D6, D7).

## Scope boundary

Research-protocol decisions do **not** authorize provider contact, data
acquisition or download, credential use, model training, or production
deployment. No such authorization has been granted.
