"""REAL-data feature extraction contract (Phase 3.7.1, artifact geometry 3.7.2).

CONTRACT + FOUNDATION ONLY. This module defines the typed, leakage-safe
contract for converting the currently acquired REAL artifacts (CHIRPS daily
precipitation, ERA5-Land hourly 2m_temperature / total_precipitation /
volumetric_soil_water_layer_1 / surface_runoff) into ML-ready features.
Phase 3.7.2 adds the verified geometry constants that the real-artifact
readers must check before they interpret any pixel; Phase 3.7.8 adds the
approved multi-day CHIRPS rolling aggregation with per-day source
provenance. Both changes were additive; the contract version is 1.1.0.

Nothing here is wired into the DEMO prediction path, the ML model, any API
route, or the UI. No model is trained and no real-world accuracy is claimed.

Design rule (reuse, do not fork)
--------------------------------
Artifacts are referenced the way the acquisition ledger already records them
(`AcquisitionRecord` and `AcquisitionManifest` in ``app.schemas.acquisition``).
A feature is always traceable to the exact acquisition event it came from:
its record id, its SHA-256, its observation window, and its publication
(available) time. The four-time semantics and the temporal leakage gate reuse
the Phase 3.1 rules from ``app.schemas.provenance`` -- a feature whose
observation window or product vintage is after the prediction cutoff is
``rejected_leakage``, deterministically and never silently converted.

Coordinate convention (explicit)
--------------------------------
Study region is given as WGS84 decimal degrees in the
``north / west / south / east`` form (EPSG:4326). Arrays read from providers
may order latitude ascending or descending; sampling is always nearest-cell to
the reported coordinate and never interpolates or resamples, so no spatial
precision is invented. ``coordinate_precision`` is the half-width of a grid
cell in degrees -- a sampling tolerance, not the source resolution itself
(CHIRPS cell 0.05 deg -> precision 0.025 deg; ERA5-Land cell 0.1 deg ->
precision 0.05 deg). ERA5-Land's 0.05 deg precision is half of its 0.1 deg
cell and must never be read as a 0.05 deg grid.

Units (no silent conversion)
----------------------------
* CHIRPS daily precipitation: millimetres (`precipitation_daily_mm`).
* ERA5-Land ``t2m``: kelvin (``temperature_2m_K``).
* ERA5-Land ``tp``: metres, accumulation 00:00-01:00 UTC
  (``precipitation_hourly_m``).
* ERA5-Land ``swvl1``: cubic metres per cubic metre
  (``soil_water_layer1_m3m3``).
* ERA5-Land ``sro``: metres, surface runoff over the same accumulation window
  (``surface_runoff_m``).

The raw units are preserved exactly. A unit conversion is never applied as a
side effect; if one is added later the contract must define and test it.

Nodata (never turned into a valid zero)
---------------------------------------
* CHIRPS nodata is ``-9999.0``.
* NetCDF ``_FillValue`` / NaN are missing.
* A pixel that is missing becomes ``value=None`` with status ``missing``.
  ``0.0`` remains a *valid* measured zero (a dry day is not nodata).

Statuses distinguish an honest value from every kind of gap: ``valid``,
``missing``, ``insufficient_temporal_coverage``, ``rejected_leakage``,
``invalid_source_artifact``.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field, field_validator, model_validator

from app.schemas.provenance import _validate_standard_checksum

#: Version of this feature-extraction contract.
FEATURE_CONTRACT_VERSION = "1.1.0"

#: Canonical CRS of the study region and every supported REAL source.
CANONICAL_CRS = "EPSG:4326 (WGS84)"

#: Study region requested at acquisition time (NE India): N/W/S/E in WGS84 dd.
STUDY_REGION_NORTH = 29.5
STUDY_REGION_WEST = 88.0
STUDY_REGION_SOUTH = 21.0
STUDY_REGION_EAST = 97.5

#: CHIRPS nodata fill value (float GeoTIFFs are filled with -9999.0).
CHIRPS_NODATA = -9999.0

#: Number of consecutive daily CHIRPS files required per rolling window.
CHIRPS_ROLLING_WINDOW_DAYS = (3, 7, 14, 30)

#: Per-source half-width of one grid cell in degrees: the sampling tolerance
#: recorded in provenance, exactly half the provider's registered cell size
#: (CHIRPS ``spatial_resolution`` "0.05 degrees", ERA5-Land
#: "0.1 degrees, hourly"). It is NOT the source resolution; a source without a
#: verified precision must raise rather than silently default.
COORDINATE_PRECISION_BY_SOURCE = {"chirps": 0.025, "era5-land": 0.05}

# ---------------------------------------------------------------------------
# Verified artifact geometry (Phase 3.7.2, additive; contract version 1.1.0).
# These values were read from the acquired artifacts themselves (GeoTIFF
# ModelPixelScale/tiepoint/GeoKeys, NetCDF axes). A reader must refuse any
# file whose header deviates from these values BEFORE interpreting a pixel.
# ---------------------------------------------------------------------------

#: CHIRPS GeoTIFF raster geometry (global grid covering -180..180 / -50..50).
CHIRPS_RASTER_WIDTH = 7200
CHIRPS_RASTER_HEIGHT = 2000
CHIRPS_PIXEL_SIZE = 0.05
CHIRPS_ORIGIN_LON = -180.0
CHIRPS_ORIGIN_LAT = 50.0

#: CHIRPS GeoTIFF encoding: float32 single-band, no compression. Any other
#: encoding is refused rather than guessed at.
CHIRPS_BITS_PER_SAMPLE = 32
CHIRPS_SAMPLES_PER_PIXEL = 1
CHIRPS_SAMPLE_FORMAT_IEEEFP = 3
CHIRPS_COMPRESSION_NONE = 1

#: ERA5-Land NetCDF grid: 0.1 deg spacing over the study region yields
#: (N-S)/0.1 + 1 = 86 latitudes and (E-W)/0.1 + 1 = 96 longitudes.
ERA5_GRID_SPACING = 0.1
ERA5_LATITUDE_COUNT = 86
ERA5_LONGITUDE_COUNT = 96

#: Expected ``units`` attribute of every supported ERA5-Land variable, read
#: from the artifact. Values are never interpreted when the file declares
#: anything else (no silent unit conversion, no unit guessing).
ERA5_LAND_UNITS = {
    "t2m": "K",
    "tp": "m",
    "swvl1": "m**3 m**-3",
    "sro": "m",
}


class FeatureKind(str, Enum):
    """How a feature is derived from the raw artifact."""

    DIRECT = "direct"
    ROLLING = "rolling"


class FeatureStatus(str, Enum):
    """Honest state of one extracted feature.

    ``valid`` and ``missing`` refer to a single pixel's value. Rolling
    features that lack the required historical coverage are
    ``insufficient_temporal_coverage`` -- they are never zero-filled.
    """

    VALID = "valid"
    MISSING = "missing"
    INSUFFICIENT_TEMPORAL_COVERAGE = "insufficient_temporal_coverage"
    REJECTED_LEAKAGE = "rejected_leakage"
    INVALID_SOURCE_ARTIFACT = "invalid_source_artifact"


#: Explicit nature of the ``available_utc`` evidence a feature can rely on.
#: Mirrors ``AcquisitionRecord.availability_classification`` (acquisition.py:169);
#: ``None`` means the record carried no classification (unverified / unknown).
AvailabilityClassification = Literal["provider_issued", "derived", "unknown"]

#: How strictly availability evidence must clear the leakage gate (G-4, §23).
#: ``research_replay`` accepts any present, labelled timestamp; ``production``
#: accepts only ``provider_issued`` evidence. A missing timestamp clears neither.
AvailabilityPolicy = Literal["research_replay", "production"]


class Position(BaseModel):
    """A WGS84 point at which features are sampled."""

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class StudyRegion(BaseModel):
    """The spatial extraction box in WGS84 decimal degrees.

    Convention is explicit: ``north`` (max latitude), ``west`` (min
    longitude), ``south`` (min latitude), ``east`` (max longitude). Only
    EPSG:4326 is accepted -- extracting in another CRS is a contract error,
    and no silent reprojection is performed.
    """

    north: float = Field(ge=-90, le=90)
    west: float = Field(ge=-180, le=180)
    south: float = Field(ge=-90, le=90)
    east: float = Field(ge=-180, le=180)
    crs: str = Field(default=CANONICAL_CRS)

    @field_validator("north")
    @classmethod
    def _north_order(cls, v, info):
        if "south" in info.data and v < info.data["south"]:
            raise ValueError("north must be >= south")
        return v

    @field_validator("east")
    @classmethod
    def _east_order(cls, v, info):
        if "west" in info.data and v < info.data["west"]:
            raise ValueError("east must be >= west")
        return v

    @field_validator("crs")
    @classmethod
    def _crs(cls, v: str) -> str:
        if not v.startswith("EPSG:4326"):
            raise ValueError("study region and extraction are EPSG:4326 only")
        return v

    def contains(self, position: Position) -> bool:
        return (
            self.south <= position.latitude <= self.north
            and self.west <= position.longitude <= self.east
        )


def study_region() -> StudyRegion:
    """The canonical NE-India study region (N/W/S/E as acquired)."""
    return StudyRegion(
        north=STUDY_REGION_NORTH,
        west=STUDY_REGION_WEST,
        south=STUDY_REGION_SOUTH,
        east=STUDY_REGION_EAST,
        crs=CANONICAL_CRS,
    )


class FeatureSpec(BaseModel):
    """Semantic mapping of one contract feature to its source variable."""

    name: str = Field(pattern=r"^[A-Za-z0-9_]+$", min_length=1, max_length=100)
    source: str = Field(min_length=1, max_length=200)
    source_variable: str | None = Field(
        default=None,
        description="Variable name in the raw artifact (None for derived/rolling).",
    )
    unit: str = Field(min_length=1, max_length=50)
    kind: FeatureKind = FeatureKind.DIRECT
    window_days: int | None = Field(default=None, ge=1, description="Rolling window length.")
    transform: str = Field(
        default="", max_length=500, description="Human-readable derivation directive."
    )

    @model_validator(mode="after")
    def _rolling_window_invariant(self) -> "FeatureSpec":
        if self.kind is FeatureKind.ROLLING and not self.window_days:
            raise ValueError("a rolling feature must declare window_days")
        return self


#: The supported feature vocabulary. Every feature is bounded by what the
#: currently acquired artifacts can honestly support (see docs/features.md).
FEATURE_SPECS: dict[str, FeatureSpec] = {
    spec.name: spec
    for spec in (
        # CHIRPS: daily direct + 1-day window == the daily value.
        FeatureSpec(
            name="precipitation_daily_mm",
            source="chirps",
            source_variable="precipitation",
            unit="mm",
            kind=FeatureKind.DIRECT,
            transform="CHIRPS daily precipitation (direct extraction)",
        ),
        FeatureSpec(
            name="precipitation_1d_mm",
            source="chirps",
            unit="mm",
            kind=FeatureKind.ROLLING,
            window_days=1,
            transform="CHIRPS precipitation 1-day window (a single day only: "
            "equals the daily value when that day's file covers it; implies no "
            "broader temporal coverage)",
        ),
        FeatureSpec(
            name="precipitation_3d_mm",
            source="chirps",
            unit="mm",
            kind=FeatureKind.ROLLING,
            window_days=3,
            transform="CHIRPS precipitation 3-day accumulation",
        ),
        FeatureSpec(
            name="precipitation_7d_mm",
            source="chirps",
            unit="mm",
            kind=FeatureKind.ROLLING,
            window_days=7,
            transform="CHIRPS precipitation 7-day accumulation",
        ),
        FeatureSpec(
            name="precipitation_14d_mm",
            source="chirps",
            unit="mm",
            kind=FeatureKind.ROLLING,
            window_days=14,
            transform="CHIRPS precipitation 14-day accumulation",
        ),
        FeatureSpec(
            name="precipitation_30d_mm",
            source="chirps",
            unit="mm",
            kind=FeatureKind.ROLLING,
            window_days=30,
            transform="CHIRPS precipitation 30-day accumulation",
        ),
        # ERA5-Land: direct extraction only, raw units preserved.
        FeatureSpec(
            name="temperature_2m_K",
            source="era5-land",
            source_variable="t2m",
            unit="K",
            kind=FeatureKind.DIRECT,
            transform="ERA5-Land t2m direct extraction",
        ),
        FeatureSpec(
            name="precipitation_hourly_m",
            source="era5-land",
            source_variable="tp",
            unit="m",
            kind=FeatureKind.DIRECT,
            transform="ERA5-Land tp direct extraction (accumulation 00:00-01:00 UTC, "
            "raw units in metres)",
        ),
        FeatureSpec(
            name="soil_water_layer1_m3m3",
            source="era5-land",
            source_variable="swvl1",
            unit="m3/m3",
            kind=FeatureKind.DIRECT,
            transform="ERA5-Land swvl1 direct extraction (volumetric soil water, layer 1)",
        ),
        FeatureSpec(
            name="surface_runoff_m",
            source="era5-land",
            source_variable="sro",
            unit="m",
            kind=FeatureKind.DIRECT,
            transform="ERA5-Land sro direct extraction (surface runoff, raw units in metres)",
        ),
    )
}

#: ERA5-Land NetCDF short-code -> contract feature name.
ERA5_LAND_VARIABLE_MAP = {spec.source_variable: spec.name for spec in FEATURE_SPECS.values() if spec.source == "era5-land"}


def supported_features(source: str | None = None) -> list[str]:
    """Contract feature names, optionally filtered to one source."""
    return [spec.name for spec in FEATURE_SPECS.values() if source is None or spec.source == source]


class FeatureDayProvenance(BaseModel):
    """One daily source artifact aggregated into a multi-day rolling feature.

    Carries, per required day, the acquisition record identity (acquisition
    and source record IDs), the artifact SHA-256, the observation window and
    its availability evidence -- so a multi-day window stays auditable to the
    per-day record that supplied it. Every datetime is timezone-aware; naive
    inputs are rejected.
    """

    observation_start_utc: AwareDatetime
    observation_end_utc: AwareDatetime
    available_utc: AwareDatetime | None = None
    availability_classification: AvailabilityClassification | None = None
    acquisition_record_id: str = Field(min_length=1, max_length=300)
    source_record_id: str = Field(min_length=1, max_length=200)
    artifact_sha256: str = Field(min_length=64, max_length=64)

    @field_validator("artifact_sha256")
    @classmethod
    def _sha256(cls, v: str) -> str:
        return _validate_standard_checksum(v, "sha256")

    @model_validator(mode="after")
    def _window_order(self) -> "FeatureDayProvenance":
        if self.observation_end_utc < self.observation_start_utc:
            raise ValueError("observation_end_utc must not be before observation_start_utc")
        return self


class FeatureProvenance(BaseModel):
    """Full traceability of one extracted feature to its source artifact.

    Mirrors the acquisition record (``source``, ``product``,
    ``product_version``, ``source_record_id``, artifact SHA-256 and the four
    UTC instants) plus the exact derivation performed by this contract.
    Every datetime is timezone-aware; naive inputs are rejected.

    A multi-day rolling feature carries an ordered ``days`` list in addition
    to the anchor fields; the singular fields always name the anchor (last)
    day's record, and no multi-day window is ever traced through the singular
    ``artifact_sha256``.
    """

    source: str = Field(min_length=1, max_length=200)
    product: str = Field(min_length=1, max_length=300)
    product_version: str = Field(min_length=1, max_length=100)
    source_record_id: str = Field(min_length=1, max_length=200)
    artifact_sha256: str = Field(min_length=64, max_length=64)
    acquisition_record_id: str = Field(min_length=1, max_length=300)
    observation_start_utc: AwareDatetime
    observation_end_utc: AwareDatetime
    available_utc: AwareDatetime | None = None
    availability_classification: AvailabilityClassification | None = Field(
        default=None,
        description="Nature of the available_utc evidence, copied verbatim from the "
        "acquisition record; a derived/unknown/unclassified timestamp is never "
        "presented as provider-issued.",
    )
    retrieved_utc: AwareDatetime | None = None
    prediction_cutoff_utc: AwareDatetime
    crs: str = Field(default=CANONICAL_CRS)
    coordinate_precision: float = Field(gt=0, le=360)
    spatial_resolution: str | None = None
    license_attribution: str = Field(min_length=1, max_length=500)
    transform: str = Field(min_length=1, max_length=500)
    derived_at_utc: AwareDatetime
    days: list[FeatureDayProvenance] | None = Field(
        default=None,
        description="Ascending per-day source provenance when this feature aggregates "
        "more than one daily artifact (multi-day CHIRPS rolling windows); None for "
        "single-day features so single-artifact results stay backward compatible.",
    )

    @field_validator("artifact_sha256")
    @classmethod
    def _sha256(cls, v: str) -> str:
        return _validate_standard_checksum(v, "sha256")

    @model_validator(mode="after")
    def _window_order(self) -> "FeatureProvenance":
        if self.observation_end_utc < self.observation_start_utc:
            raise ValueError("observation_end_utc must not be before observation_start_utc")
        return self

    @model_validator(mode="after")
    def _days_ascending(self) -> "FeatureProvenance":
        if not self.days:
            return self
        for earlier, later in zip(self.days, self.days[1:]):
            if later.observation_start_utc <= earlier.observation_start_utc:
                raise ValueError(
                    "per-day provenance must be strictly ascending by observation_start_utc"
                )
        if self.days[-1].observation_start_utc != self.observation_start_utc:
            raise ValueError(
                "the anchor observation_start_utc must match the last per-day entry"
            )
        return self


class FeatureValue(BaseModel):
    """One extracted feature with its honest status and provenance."""

    feature_name: str = Field(pattern=r"^[A-Za-z0-9_]+$", min_length=1, max_length=100)
    value: float | None = Field(
        default=None,
        description="None whenever the feature is not valid (missing, blocked, rejected).",
    )
    unit: str = Field(min_length=1, max_length=50)
    status: FeatureStatus
    provenance: FeatureProvenance
    note: str | None = Field(
        default=None,
        description="Human-readable reason for a non-valid status (e.g. insufficient coverage).",
    )


class FeatureExtractionRequest(BaseModel):
    """A request to extract contract features for one point from REAL artifacts."""

    source: str = Field(min_length=1, max_length=200)
    position: Position
    prediction_cutoff_utc: AwareDatetime = Field(
        description="Model time: every feature must be observed and published at or before it."
    )
    region: StudyRegion = Field(default_factory=study_region)
    artifact_sha256: str | None = Field(
        default=None,
        description="Pin the artifact by SHA-256; a non-matching value is rejected.",
    )
    requested_features: list[str] | None = Field(
        default=None,
        description="Feature names to produce; None selects every feature supported for the source.",
    )
    availability_policy: AvailabilityPolicy = Field(
        default="research_replay",
        description="How strictly the record's availability evidence must clear the leakage "
        "gate (G-4, §23): research_replay accepts any present labelled timestamp; production "
        "accepts only provider_issued evidence. A missing timestamp clears neither policy.",
    )

    @field_validator("artifact_sha256")
    @classmethod
    def _sha256(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return _validate_standard_checksum(v, "sha256")


class FeatureExtractionResult(BaseModel):
    """Outcome of one extraction request (contract version + traceability)."""

    contract_version: str = FEATURE_CONTRACT_VERSION
    extracted_at_utc: AwareDatetime
    source: str = Field(min_length=1, max_length=200)
    acquisition_record_id: str = Field(min_length=1, max_length=300)
    artifact_sha256: str = Field(min_length=64, max_length=64)
    storage_path: str = Field(min_length=1, max_length=500)
    features: list[FeatureValue] = Field(default_factory=list)


def utcnow_aware() -> datetime:
    """Timezone-aware UTC 'now', for extraction timestamps."""
    return datetime.now(timezone.utc)