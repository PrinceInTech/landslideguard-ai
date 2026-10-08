# Raw data policy

This directory is reserved for **raw REAL-world source files** (weather,
terrain, landslide inventories, sensor streams).

Rules:

1. **Never commit raw files here.** The entire directory is git-ignored
   (`data/raw/.gitignore`); only this README and the `.gitignore` are tracked.
2. Register every downloaded source in
   `data/provenance/manifest.json` (`sources[]`) **before** using it: record
   source name, access reference, license/attribution, retrieval timestamp,
   geographic/temporal coverage, field mapping, known limitations, file size,
   and the file's SHA-256.
3. The manifest references raw files **by checksum only**. A later verification
   step can recompute the SHA-256 of any file in this directory and compare it
   against the manifest, without the bytes having ever been in Git.
4. Do not fabricate sources or records. If a source cannot be described
   honestly, do not register it.

Schema and loader:

- `backend/app/schemas/provenance.py` — the typed contract.
- `backend/app/services/provenance.py` — manifest loading + checksum verification.
- `backend/tests/test_provenance_contract.py` — contract tests.