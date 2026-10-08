# Raw data policy

This directory is reserved for **raw REAL-world source files** (weather,
terrain, landslide inventories, sensor streams).

Layout:

- `data/raw/` — root of the raw-data policy.
  - `data/raw/real/` — acquired REAL raw bytes, organised per source
    (e.g. `data/raw/real/nasa-coolr/...`). Files are written with immutable,
    versioned names so an existing artifact is never overwritten, and every
    artifact gets a SHA-256 recorded in the acquisition ledger.
  - `data/provenance/acquisition_manifest.json` — the committed acquisition
    ledger: one metadata record per retrieval attempt (downloaded /
    skipped_existing / checksum_mismatch / failed). The bytes themselves never
    enter Git.

Rules:

1. **Never commit raw files here.** The entire directory is git-ignored
   (`data/raw/.gitignore`); only this README, the `.gitignore` and
   `data/raw/real/.gitkeep` are tracked.
2. Register every downloaded source in
   `data/provenance/manifest.json` (`sources[]`) **before** using it: record
   source name, access reference, license/attribution, retrieval timestamp,
   geographic/temporal coverage, field mapping, known limitations, file size,
   and the file's SHA-256.
3. The manifest references raw files **by checksum only**. A later verification
   step can recompute the SHA-256 of any file in this directory and compare it
   against the manifest, without the bytes having ever been in Git.
4. Do not fabricate sources or records. If a source cannot be described
   honestly, or cannot be accessed, record the failure honestly instead.
5. The acquisition ledger (`data/provenance/acquisition_manifest.json`)
   distinguishes DEMO and REAL. Registering an adapter or a source
   configuration never implies REAL data exists: only actually acquired bytes
   count.

Schema and loader:

- `backend/app/schemas/provenance.py` — the source/record contract.
- `backend/app/schemas/acquisition.py` — acquisition records + ledger.
- `backend/app/services/provenance.py` — manifest loading + checksum verification.
- `backend/app/services/acquisition.py` — the acquisition rig.
- `backend/tests/test_provenance_contract.py`, `backend/tests/test_acquisition_rig.py` — tests.