"""Acquisition schemas (Phase 3.2).

Per-download provenance for REAL (and DEMO) acquisition events. Every attempt
to store bytes is recorded in an :class:`AcquisitionManifest`: successful
downloads, deduplicated re-acquisitions, checksum mismatches and failures. The
manifest is committed metadata; the raw bytes themselves live under
``data/raw/real/``, which is git-ignored.

Relationship to source-level provenance: ``SourceProvenance``
(``app.schemas.provenance``) describes a source once -- license, coverage,
retrieval timestamp, checksums of its registered artifacts. An
``AcquisitionRecord`` describes one actual retrieval event: which product
version was fetched, the exact retrieval and valid/publication times, the
resulting file's SHA-256, and the honest outcome. Shared fields are not
duplicated beyond what a single event needs.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import AwareDatetime, BaseModel, Field, field_validator, model_validator

from app.schemas.provenance import GeographicCoverage, _validate_standard_checksum


class AcquisitionStatus(str, Enum):
    """Terminal outcome of one acquisition attempt.

    ``downloaded`` and ``skipped_existing`` both mean the bytes are present
    (and were already stored on the first one). ``checksum_mismatch`` and
    ``failed`` mean no artifact was kept -- the ledger records the honest
    outcome rather than a fake success.
    """

    DOWNLOADED = "downloaded"
    SKIPPED_EXISTING = "skipped_existing"
    CHECKSUM_MISMATCH = "checksum_mismatch"
    FAILED = "failed"


class AuthenticationMethod(str, Enum):
    """How a source authenticates, when it does.

    ``none`` sources need no credentials. ``earthdata-bearer`` and ``cds-api``
    sources require named environment variables; the rig fails loudly when
    they are missing instead of silently falling back to another source.
    """

    NONE = "none"
    EARTHDATA_BEARER = "earthdata-bearer"
    CDS_API = "cds-api"


class SourceConfig(BaseModel):
    """Configuration of one approved acquisition source.

    Static, verified-at-enable-time metadata. ``credentials`` names the
    environment variables required when ``authentication`` is not ``none``.
    ``endpoint_base`` is only set for sources whose live endpoint was actually
    verified (Phase 2.3); for the others, download URLs are supplied by the
    caller at acquisition time so nothing is assumed.
    """

    name: str = Field(min_length=1, max_length=200, pattern=r"^[a-z0-9][a-z0-9-]*$")
    tier: str = Field(pattern="^(event|rainfall|weather-land-state|static)$")
    product: str = Field(min_length=1, max_length=300)
    product_version: str = Field(min_length=1, max_length=100)
    access_reference: str = Field(min_length=1, max_length=500)
    kind: str = Field(pattern="^(DEMO|REAL)$")
    authentication: AuthenticationMethod = AuthenticationMethod.NONE
    credentials: list[str] = Field(default_factory=list)
    geographic_coverage: GeographicCoverage | None = None
    crs: str = Field(min_length=1, max_length=120)
    license_attribution: str = Field(min_length=1, max_length=500)
    spatial_resolution: str | None = None
    known_limitations: list[str] = Field(default_factory=list)
    endpoint_base: str | None = None
    require_bounded_scope: bool = False


class AcquisitionRecord(BaseModel):
    """Provenance for one acquisition attempt (one event in the ledger).

    Detailed contract of the fields an acquired artifact must carry with it: see
    ``docs/acquisition.md`` "Acquisition contract". Dates are timezone-aware;
    naive datetimes are rejected.
    """

    record_id: str = Field(min_length=1, max_length=300, description="Stable id of this attempt.")
    source: str = Field(min_length=1, max_length=200)
    product: str = Field(min_length=1, max_length=300)
    product_version: str = Field(min_length=1, max_length=100)
    kind: str = Field(pattern="^(DEMO|REAL)$")
    status: AcquisitionStatus
    access_reference: str = Field(min_length=1, max_length=500)
    source_record_id: str | None = Field(
        default=None, description="Id in the source's own system, if applicable."
    )
    retrieval_params: dict[str, Any] = Field(
        default_factory=dict,
        description="Snapshot of the retrieval request (secrets are stripped).",
    )
    retrieved_utc: AwareDatetime | None = Field(
        default=None, description="Exact moment the provider was asked for the bytes."
    )
    acquired_utc: AwareDatetime = Field(
        description="Moment this record was registered in the ledger."
    )
    observation_start_utc: AwareDatetime | None = Field(
        default=None, description="Start of the valid/observation time range, if applicable."
    )
    observation_end_utc: AwareDatetime | None = Field(
        default=None, description="End of the valid/observation time range, if applicable."
    )
    available_utc: AwareDatetime | None = Field(
        default=None, description="Publication/availability time of the product vintage, if known."
    )
    geographic_coverage: GeographicCoverage | None = None
    crs: str | None = None
    license_attribution: str
    sha256: str | None = Field(
        default=None, description="SHA-256 of the artifact bytes (absent only on failure)."
    )
    file_size_bytes: int | None = Field(default=None, ge=0)
    storage_path: str | None = Field(
        default=None,
        description="Path relative to data/raw/real/ of the stored artifact, when kept.",
    )
    known_limitations: list[str] = Field(default_factory=list)
    error: str | None = None

    @field_validator("sha256")
    @classmethod
    def _validate_sha256(cls, v):
        if v is None:
            return v
        return _validate_standard_checksum(v, "sha256")

    @model_validator(mode="after")
    def _state_is_coherent(self) -> "AcquisitionRecord":
        if self.status in (AcquisitionStatus.DOWNLOADED, AcquisitionStatus.SKIPPED_EXISTING):
            if not self.sha256 or self.file_size_bytes is None or not self.storage_path:
                raise ValueError(
                    "an acquired artifact (downloaded/skipped_existing) must record "
                    "sha256, file_size_bytes and storage_path"
                )
            if self.status is AcquisitionStatus.DOWNLOADED and self.error:
                raise ValueError("a downloaded artifact must not carry an error")
        else:
            if self.storage_path:
                raise ValueError("a non-acquired record must not claim a storage_path")
        return self


class AcquisitionManifest(BaseModel):
    """The committed acquisition ledger (data/provenance/acquisition_manifest.json).

    Distinguishes DEMO and REAL via ``AcquisitionRecord.kind``. Recording an
    adapter/configuration never implies data exists: only actual retrieval
    events appear here.
    """

    contract_version: str = Field(default="1.1.0", pattern=r"^\d+\.\d+\.\d+$")
    generated_at_utc: AwareDatetime
    records: list[AcquisitionRecord] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class PreflightReport(BaseModel):
    """Result of a source preflight check run before a large acquisition.

    ``ok`` is True only when the required inspection completed. ``details``
    carries endpoint/schema/count facts (e.g. the COOLR checklist): reachable
    layers, schema fields (event_id, event_date, event_time, latitude,
    longitude, location_accuracy), Northeast-India record count, and the
    observed event date range.
    """

    source: str
    ok: bool
    retrieved_utc: AwareDatetime = Field(
        description="Exact timestamp of the preflight/retrieval check."
    )
    message: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


def utcnow_aware() -> datetime:
    """Timezone-aware UTC 'now', for acquisition timestamps."""
    return datetime.now(timezone.utc)