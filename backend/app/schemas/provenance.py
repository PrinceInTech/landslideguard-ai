"""Provenance and data-contract schemas (Phase 2.2 foundation).

This module defines the typed contract that every future REAL-data
prediction/training record must satisfy, plus source-level provenance and the
committed provenance manifest.

Scope: FOUNDATION ONLY. Nothing in this module is wired into the DEMO
prediction path, the SQLAlchemy models, or any API route. The DEMO baseline is
left untouched and remains the default. The contract exists so the data
acquisition phase can validate ingested records against one schema and link
them to a registered source before any training or prediction happens.

DEMO vs REAL
------------
`PROVENANCE_KINDS` (`DEMO`, `REAL`) separates the two worlds explicitly. The
current DEMO pipeline never emits these fields, so no existing record is
affected. A record that carries `RecordProvenance` is a REAL-data candidate by
construction; the coupling between a record and its source
(`record.kind == source.kind`) is enforced by
`app.services.provenance.validate_record_source_match`.

Coordinate conventions: WGS84 decimal degrees. `coordinate_precision` is the
half-width of the grid cell / reported coordinate in degrees (e.g. 0.01 degrees
is roughly 1 km), which tells a downstream consumer how spatially precise the
reading really is rather than implying exact coordinates.
"""
from datetime import date, datetime, timezone

from pydantic import AwareDatetime, BaseModel, Field, field_validator

# Canonical provenance kinds. Record.schemas validate against this pair; the
# DEMO baseline is untouched and any record carrying provenance is a REAL-data
# candidate (see module docstring).
PROVENANCE_KINDS = ("DEMO", "REAL")

# Canonical field set for a real prediction/training record. Kept in one place
# so the schemas, the manifest, and future acquisition code agree.
RECORD_PROVENANCE_FIELDS = (
    "event_id",
    "prediction_cutoff_utc",
    "latitude",
    "longitude",
    "coordinate_precision",
    "source",
    "source_record_id",
    "feature_source",
    "feature_source_version",
    "data_quality",
    "kind",
)


def _validate_standard_checksum(value: str, algorithm: str) -> str:
    """A checksum must be hex text of the length the algorithm implies."""
    if algorithm != "sha256":
        raise ValueError(f"unsupported checksum algorithm {algorithm!r}")
    if len(value) != 64:
        raise ValueError("sha256 checksum must be exactly 64 hex characters")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError("sha256 checksum must be hexadecimal") from exc
    return value


class DataQualityFlags(BaseModel):
    """Machine- and human-readable flags about the provenance of one value."""

    missing_fields: list[str] = Field(
        default_factory=list, description="Contract fields absent from the source record."
    )
    interpolated: bool = False
    estimated: bool = False
    stale: bool = False
    outlier: bool = False
    schema_conformance: bool = Field(
        default=True, description="Record passed this contract's validation/coercion."
    )
    note: str | None = None


class RecordProvenance(BaseModel):
    """Provenance attached to one prediction or training record.

    Belongs to the REAL-data track by default: any record that carries
    per-record provenance is a candidate for real training/prediction. DEMO
    records today do not emit these fields, so nothing existing is affected.
    """

    event_id: str = Field(min_length=1, max_length=200)
    prediction_cutoff_utc: AwareDatetime = Field(
        description="UTC instant the model inputs were cut off (timezone-aware)."
    )
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    coordinate_precision: float = Field(
        gt=0, le=360, description="Half-width of the coordinate cell in degrees."
    )
    source: str = Field(min_length=1, max_length=200, description="Registered source name.")
    source_record_id: str = Field(
        min_length=1, max_length=200, description="Id of the row in the source's own system."
    )
    feature_source: str = Field(min_length=1, max_length=200)
    feature_source_version: str = Field(min_length=1, max_length=100)
    data_quality: DataQualityFlags = Field(default_factory=DataQualityFlags)
    kind: str = Field(default="REAL", pattern="^(DEMO|REAL)$")


class GeographicCoverage(BaseModel):
    min_latitude: float = Field(ge=-90, le=90)
    max_latitude: float = Field(ge=-90, le=90)
    min_longitude: float = Field(ge=-180, le=180)
    max_longitude: float = Field(ge=-180, le=180)

    @field_validator("max_latitude")
    @classmethod
    def _lat_order(cls, v, info):
        data = info.data
        if "min_latitude" in data and v < data["min_latitude"]:
            raise ValueError("max_latitude must be >= min_latitude")
        return v

    @field_validator("max_longitude")
    @classmethod
    def _lon_order(cls, v, info):
        data = info.data
        if "min_longitude" in data and v < data["min_longitude"]:
            raise ValueError("max_longitude must be >= min_longitude")
        return v


class TemporalCoverage(BaseModel):
    start: date
    end: date

    @field_validator("end")
    @classmethod
    def _time_order(cls, v, info):
        data = info.data
        if "start" in data and v < data["start"]:
            raise ValueError("end must be >= start")
        return v


class FieldMapping(BaseModel):
    """Maps one source column to one contract feature and the transform applied."""

    source_column: str = Field(min_length=1, max_length=200)
    contract_field: str = Field(min_length=1, max_length=200)
    transform: str = Field(default="", max_length=500, description="Human-readable transform note.")


class SourceProvenance(BaseModel):
    """Source-level provenance for one registered data source.

    For REAL sources the raw file is referenced by checksum only and never
    committed to the repository; `access_reference` points at how the data can
    be retrieved. For the in-repo DEMO generator it documents the generator
    path instead.
    """

    name: str = Field(min_length=1, max_length=200)
    kind: str = Field(pattern="^(DEMO|REAL)$")
    access_reference: str = Field(min_length=1, max_length=500)
    license_attribution: str = Field(min_length=1, max_length=500)
    retrieved_utc: AwareDatetime | None = Field(
        default=None, description="When the data was retrieved; None for in-repo synthetic data."
    )
    checksum_algorithm: str = Field(default="sha256")
    source_checksum: str = Field(min_length=64, max_length=64)
    file_size_bytes: int = Field(ge=0)
    geographic_coverage: GeographicCoverage
    temporal_coverage: TemporalCoverage
    field_mapping: list[FieldMapping] = Field(default_factory=list)
    known_limitations: list[str] = Field(default_factory=list)

    @field_validator("source_checksum")
    @classmethod
    def _checksum(cls, v, info):
        algorithm = info.data.get("checksum_algorithm", "sha256")
        return _validate_standard_checksum(v, algorithm)


class ManifestArtifact(BaseModel):
    """A committed artifact recorded in the provenance manifest with its digest."""

    name: str = Field(min_length=1, max_length=200)
    path: str = Field(min_length=1, max_length=500, description="Repo-relative path, / separators.")
    role: str = Field(
        pattern="^(training-data|model|model-metadata|locations|realtime-sample|config)$"
    )
    sha256: str = Field(min_length=64, max_length=64)
    size_bytes: int = Field(ge=0)
    description: str = Field(default="", max_length=500)

    @field_validator("sha256")
    @classmethod
    def _sha256(cls, v):
        return _validate_standard_checksum(v, "sha256")


class ProvenanceManifest(BaseModel):
    """The committed provenance manifest.

    Registers committed artifacts (with digests) and source-level provenance.
    Raw REAL data files are represented by `SourceProvenance.source_checksum`
    alone; their bytes live outside Git (see `data/raw/`), so the manifest is
    the thing that later lets a consumer re-verify a raw file against what was
    registered.
    """

    contract_version: str = Field(default="1.0.0", pattern=r"^\d+\.\d+\.\d+$")
    generated_at_utc: AwareDatetime = Field(
        description="When this manifest file was generated (timezone-aware)."
    )
    artifacts: list[ManifestArtifact] = Field(default_factory=list)
    sources: list[SourceProvenance] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def utcnow_aware() -> datetime:
    """Timezone-aware UTC 'now', for manifest generation timestamps."""
    return datetime.now(timezone.utc)