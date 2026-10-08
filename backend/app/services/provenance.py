"""Provenance manifest loading and verification (Phase 2.2 foundation).

Reads and validates the committed manifest at `settings.PROVENANCE_MANIFEST`
and recomputes artifact digests so drift between a committed file and the
manifest is caught (the same idea the model suite uses for
`data/historical_landslide_data.csv`).

Not part of any API route or the DEMO prediction path: this module is a
building block for the future REAL-data acquisition phase.
"""
import hashlib
import json
from pathlib import Path

from app.config import PROJECT_ROOT, settings
from app.schemas.provenance import ProvenanceManifest, RecordProvenance, SourceProvenance


class ProvenanceContractError(ValueError):
    """Raised when the committed manifest is missing, invalid, or has drifted."""


def sha256_of(path: Path) -> str:
    """Hex SHA-256 digest of a file's bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_path() -> Path:
    """Resolved path of the committed provenance manifest."""
    return Path(settings.PROVENANCE_MANIFEST)


def load_manifest(path: Path | None = None) -> ProvenanceManifest:
    """Parse and validate the committed provenance manifest.

    Raises ProvenanceContractError when the file is missing or does not match
    the contract, so a malformed manifest fails loudly rather than silently.
    """
    target = Path(path) if path is not None else manifest_path()
    if not target.exists():
        raise ProvenanceContractError(f"provenance manifest not found: {target}")
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProvenanceContractError(f"provenance manifest is not valid JSON: {target}") from exc
    try:
        return ProvenanceManifest.model_validate(raw)
    except Exception as exc:
        raise ProvenanceContractError(f"provenance manifest violates the contract: {exc}") from exc


def verify_artifact_checksums(manifest: ProvenanceManifest | None = None) -> list[str]:
    """Recompute each committed artifact's SHA-256 and diff it against the manifest.

    Returns a list of human-readable mismatch messages; an empty list means
    every recorded artifact matches the file on disk.
    """
    root = PROJECT_ROOT
    manifest = manifest or load_manifest()
    mismatches: list[str] = []
    for artifact in manifest.artifacts:
        path = root / artifact.path
        if not path.exists():
            mismatches.append(f"{artifact.name}: file missing at {artifact.path}")
            continue
        actual = sha256_of(path)
        if actual != artifact.sha256:
            mismatches.append(
                f"{artifact.name}: checksum drift at {artifact.path} "
                f"(manifest {artifact.sha256} != file {actual})"
            )
    return mismatches


def validate_record_source_match(record: RecordProvenance, source: SourceProvenance) -> None:
    """A record may only claim a source of the same provenance kind.

    REAL record + DEMO source (or DEMO record + REAL source) is a contract
    violation: it would blur the DEMO/REAL line the provenance layer exists to
    keep explicit.
    """
    if record.kind != source.kind:
        raise ProvenanceContractError(
            f"record kind {record.kind!r} does not match source {source.name!r} "
            f"kind {source.kind!r}"
        )
    if record.source != source.name:
        raise ProvenanceContractError(
            f"record source {record.source!r} does not match registered source "
            f"{source.name!r}"
        )