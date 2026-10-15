"""REAL-data feature extraction service (Phase 3.7.1 contract; 3.7.2 readers).

Turns acquired REAL artifacts into typed, fully-provenanced features under the
contract in ``app.schemas.features``. Only the currently acquired artifacts
are supported; no new dataset is downloaded and no value is fabricated.

Key behaviours
--------------
* Artifact identity is pinned by the acquisition ledger: an extraction request
  resolves to a kept ``AcquisitionRecord``, the record's product/version is
  checked against the provider registry and the file's SHA-256 is re-computed
  and compared -- all before the leakage gate, so no extraction of any kind
  runs against an artifact that is not exactly what was acquired.
* Leakage is gated before any pixel is read: if the artifact's observation
  window end or its ``available_utc`` is after the prediction cutoff, every
  feature is ``rejected_leakage`` (deterministic, no partial mesh of old and
  new).
* Real artifacts are decoded by built-in readers that verify the artifact's
  geometry and encoding against the contract BEFORE interpreting any pixel:
  the CHIRPS GeoTIFF with a stdlib (gzip + struct) header reader, the
  ERA5-Land NetCDF's axes, spacing, extent and declared units with lazily
  imported ``netCDF4``. A file that deviates is refused, never guessed at.
* CHIRPS nodata (``-9999.0``) and NetCDF ``_FillValue`` / NaN are ``missing``
  and are never treated as a valid zero.
* Rolling precipitation windows report ``insufficient_temporal_coverage``
  unless enough contiguous daily files exist; with the single acquired daily
  file only the 1-day window (== the daily value) can be produced. Missing
  history is never zero-filled.
* Sampling is nearest-cell to the reported coordinate (EPSG:4326) with no
  interpolation and no resampling, so spatial precision is never invented.

Decoding backends
-----------------
The service is grid-agnostic: ``era5_grids`` consumers hand decoded grids plus
latitude / longitude axes in, and readers decode real artifacts. The
``netCDF4`` package is imported lazily. The CHIRPS reader is a built-in
classic-TIFF reader (stdlib ``gzip`` + ``struct`` only -- no raster backend,
no new dependency): it parses and verifies the GeoTIFF header (dimensions,
pixel size, origin/extent, EPSG:4326, float32 single band, nodata) and then
reads only the strips covering the requested study window, never the full
7200x2000 raster. The ``decoder`` injection point remains for bounded test
fixtures.
"""
import gzip
import struct
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

import numpy as np

from app.config import PROJECT_ROOT
from app.schemas.acquisition import (
    AcquisitionManifest,
    AcquisitionRecord,
    AcquisitionStatus,
    SourceConfig,
)
from app.schemas.features import (
    CANONICAL_CRS,
    CHIRPS_BITS_PER_SAMPLE,
    CHIRPS_COMPRESSION_NONE,
    CHIRPS_NODATA,
    CHIRPS_ORIGIN_LAT,
    CHIRPS_ORIGIN_LON,
    CHIRPS_PIXEL_SIZE,
    CHIRPS_RASTER_HEIGHT,
    CHIRPS_RASTER_WIDTH,
    CHIRPS_SAMPLE_FORMAT_IEEEFP,
    CHIRPS_SAMPLES_PER_PIXEL,
    COORDINATE_PRECISION_BY_SOURCE,
    ERA5_GRID_SPACING,
    ERA5_LATITUDE_COUNT,
    ERA5_LAND_UNITS,
    ERA5_LAND_VARIABLE_MAP,
    ERA5_LONGITUDE_COUNT,
    FEATURE_SPECS,
    FeatureDayProvenance,
    FeatureExtractionRequest,
    FeatureExtractionResult,
    FeatureKind,
    FeatureProvenance,
    FeatureSpec,
    FeatureStatus,
    FeatureValue,
    StudyRegion,
    study_region,
    utcnow_aware,
)
from app.services.acquisition import (
    UnsupportedSourceError,
    get_source_config,
    load_acquisition_manifest,
)
from app.services.provenance import sha256_of

#: Statuses that mean the artifact bytes are actually present in the ledger.
KEPT_STATUSES = (AcquisitionStatus.DOWNLOADED, AcquisitionStatus.SKIPPED_EXISTING)


class FeatureContractError(ValueError):
    """Contract violation: unsupported source, CRS, bounds, or identity."""


class ArtifactReadError(FeatureContractError):
    """The raw artifact could not be decoded with the available backends."""


def _require_aware(value: datetime | None, label: str) -> None:
    if value is not None and value.tzinfo is None:
        raise FeatureContractError(
            f"{label} must be timezone-aware UTC; naive datetimes are rejected, "
            "never silently converted"
        )


# ---------------------------------------------------------------------------
# Leakage gate (deterministic; test 19)
# ---------------------------------------------------------------------------


#: The only valid ``FeatureExtractionRequest.availability_policy`` values.
_ALLOWED_AVAILABILITY_POLICIES = ("research_replay", "production")


def evaluate_leakage(
    observation_start_utc: datetime | None,
    observation_end_utc: datetime | None,
    available_utc: datetime | None,
    prediction_cutoff_utc: datetime,
) -> FeatureStatus:
    """Leakage rule: both the observation window and the product vintage must
    be at or before the prediction cutoff.

    Returns ``VALID`` or ``REJECTED_LEAKAGE``. The same inputs always return
    the same status. Naive datetimes are rejected, never converted. A record
    with no observable window is not provably non-leaky, so it fails closed
    (``REJECTED_LEAKAGE``) rather than comparing against a missing datetime.
    """
    _require_aware(observation_start_utc, "observation_start_utc")
    _require_aware(observation_end_utc, "observation_end_utc")
    _require_aware(available_utc, "available_utc")
    _require_aware(prediction_cutoff_utc, "prediction_cutoff_utc")
    if observation_start_utc is None or observation_end_utc is None:
        return FeatureStatus.REJECTED_LEAKAGE
    if observation_end_utc > prediction_cutoff_utc:
        return FeatureStatus.REJECTED_LEAKAGE
    if available_utc is not None and available_utc > prediction_cutoff_utc:
        return FeatureStatus.REJECTED_LEAKAGE
    return FeatureStatus.VALID


def evaluate_availability_policy(
    record: AcquisitionRecord,
    *,
    availability_policy: str,
) -> FeatureStatus:
    """Availability-evidence gate (deterministic; G-4 resolution, §23).

    A prediction cutoff can only be cleared by a timestamp that exists and,
    under the ``production`` policy, by evidence explicitly classified
    ``provider_issued``. A derived/unknown/unclassified timestamp therefore
    never silently clears a production gate, and a missing timestamp can never
    clear any cutoff -- absent evidence is neither fabricated into a verified
    timestamp nor treated as provably non-leaky. Returns ``VALID`` or
    ``REJECTED_LEAKAGE``; the same inputs always return the same status. An
    unknown policy value fails closed (raises) instead of being read as the
    permissive research default.
    """
    if availability_policy not in _ALLOWED_AVAILABILITY_POLICIES:
        raise FeatureContractError(
            f"unknown availability_policy {availability_policy!r}; "
            f"allowed values: {', '.join(_ALLOWED_AVAILABILITY_POLICIES)}"
        )
    if record.available_utc is None:
        return FeatureStatus.REJECTED_LEAKAGE
    if availability_policy == "production" and record.availability_classification != "provider_issued":
        return FeatureStatus.REJECTED_LEAKAGE
    return FeatureStatus.VALID


def _leakage_rejected_note(
    record: AcquisitionRecord, prediction_cutoff_utc: datetime
) -> str:
    reasons = []
    if record.observation_start_utc is None or record.observation_end_utc is None:
        reasons.append(
            "the observation window is not fully recorded, so the observation "
            "period cannot be placed against prediction_cutoff_utc "
            f"{prediction_cutoff_utc.isoformat()}"
        )
    elif record.observation_end_utc > prediction_cutoff_utc:
        reasons.append(
            f"observation_end_utc {record.observation_end_utc.isoformat()} is after "
            f"prediction_cutoff_utc {prediction_cutoff_utc.isoformat()}"
        )
    if record.available_utc is not None and record.available_utc > prediction_cutoff_utc:
        reasons.append(
            f"available_utc {record.available_utc.isoformat()} is after "
            f"prediction_cutoff_utc {prediction_cutoff_utc.isoformat()}"
        )
    return "rejected for leakage: " + "; ".join(reasons)


def _availability_policy_rejected_note(
    record: AcquisitionRecord, availability_policy: str
) -> str:
    if record.available_utc is None:
        return (
            "rejected for leakage: no availability timestamp is recorded, so the product "
            "vintage cannot be placed against the prediction cutoff"
        )
    return (
        f"rejected for leakage: availability_policy {availability_policy!r} requires "
        f"provider_issued evidence, but the record classifies availability as "
        f"{record.availability_classification!r}"
    )


# ---------------------------------------------------------------------------
# CRS / bounds validation (tests 12, 13)
# ---------------------------------------------------------------------------


def require_epsg4326(crs: str) -> None:
    """Only EPSG:4326 extraction is defined by this contract."""
    if not crs.startswith("EPSG:4326"):
        raise FeatureContractError(
            f"feature extraction is EPSG:4326 only; got {crs!r} "
            "(no silent reprojection is performed)"
        )


def _validate_position(request: FeatureExtractionRequest) -> None:
    if not request.region.contains(request.position):
        raise FeatureContractError(
            f"position ({request.position.latitude}, {request.position.longitude}) is "
            f"outside the study region "
            f"(N {request.region.north}, W {request.region.west}, "
            f"S {request.region.south}, E {request.region.east})"
        )


# ---------------------------------------------------------------------------
# Artifact resolution + identity (tests 16-18)
# ---------------------------------------------------------------------------


def resolve_acquired_record(
    manifest: AcquisitionManifest,
    source: str,
    artifact_sha256: str | None = None,
) -> AcquisitionRecord:
    """The kept acquisition record to extract from.

    ``artifact_sha256`` pins a specific artifact; without it the most recently
    acquired kept record for the source is used.
    """
    kept = [
        record
        for record in manifest.records
        if record.kind == "REAL"
        and record.source == source
        and record.status in KEPT_STATUSES
        and record.sha256
        and record.storage_path
    ]
    if artifact_sha256 is not None:
        for record in kept:
            if record.sha256 == artifact_sha256:
                return record
        raise FeatureContractError(
            f"no kept REAL acquisition record for source {source!r} matches "
            f"artifact_sha256 {artifact_sha256}"
        )
    if not kept:
        raise FeatureContractError(
            f"source {source!r} has no kept REAL artifact in the acquisition ledger"
        )
    return max(kept, key=lambda record: record.acquired_utc)


def artifact_path(record: AcquisitionRecord, *, raw_root: Path | None = None) -> Path:
    """Path of the artifact relative to the REAL raw root.

    ``raw_root`` lets callers point at a scratch root (tests); it defaults to
    ``<PROJECT_ROOT>/data/raw/real``.
    """
    if not record.storage_path:
        raise FeatureContractError(
            f"acquisition record {record.record_id} has no storage_path"
        )
    root = raw_root or (PROJECT_ROOT / "data" / "raw" / "real")
    return root / record.storage_path


def _product_version_compatible(record_version: str, registered_version: str) -> bool:
    """A ledger version is compatible when it matches, or when the registry
    declares a wildcard (``v2.x``) whose literal prefix the record satisfies."""
    if record_version == registered_version:
        return True
    if registered_version.endswith("x"):
        return record_version.startswith(registered_version[:-1])
    return False


def verify_artifact_identity(
    record: AcquisitionRecord,
    path: Path,
    *,
    source_config: SourceConfig | None = None,
) -> None:
    """Verify artifact identity before any extraction step runs.

    Every extraction must confirm (a) the record agrees with the provider
    registry -- same product, and a compatible product version -- and (b) the
    file on disk is byte-identical to the ledger's SHA-256. A mismatch means
    the artifact is no longer what was acquired, and extraction is aborted.
    """
    if source_config is not None:
        if record.product != source_config.product:
            raise FeatureContractError(
                f"product mismatch for {record.record_id}: ledger "
                f"{record.product!r} != registry {source_config.product!r}"
            )
        if not _product_version_compatible(
            record.product_version, source_config.product_version
        ):
            raise FeatureContractError(
                f"product version mismatch for {record.record_id}: ledger "
                f"{record.product_version!r} is not compatible with registry "
                f"{source_config.product_version!r}"
            )
    if not path.is_file():
        raise ArtifactReadError(f"raw artifact missing: {path}")
    actual = sha256_of(path)
    if actual != record.sha256:
        raise FeatureContractError(
            f"artifact SHA-256 mismatch for {record.record_id}: "
            f"ledger {record.sha256} != file {actual}"
        )


# ---------------------------------------------------------------------------
# Nodata / sample primitives (tests 5, 6, 20)
# ---------------------------------------------------------------------------


def coerce_to_missing(
    value,
    *,
    sentinels: tuple[float, ...] = (),
    nan_is_missing: bool = True,
    tolerance: float = 1e-9,
) -> float | None:
    """Map scan values onto contract floats; missing data becomes None.

    A sentinel value (CHIRPS -9999.0, NetCDF _FillValue, NaN) is None -- never
    ``0.0``. A measured ``0.0`` stays ``0.0`` (a dry day is valid data).
    """
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if nan_is_missing and np.isnan(number):
        return None
    for sentinel in sentinels:
        if abs(number - sentinel) <= tolerance:
            return None
    return number


def _nearest_index(axis: np.ndarray, value: float) -> int:
    if axis.size == 0:
        return -1
    return int(np.abs(np.asarray(axis, dtype=float) - float(value)).argmin())


def sample_grid(
    raw,
    latitudes: np.ndarray,
    longitudes: np.ndarray,
    latitude: float,
    longitude: float,
    *,
    sentinels: tuple[float, ...] = (),
    nan_is_missing: bool = True,
) -> float | None:
    """Nearest-cell sample (no interpolation, no resampling).

    Handles descending latitude axes (ERA5-Land) as well as ascending ones.
    A cell that is nodata/NaN/outside the array is None (missing).
    """
    array = np.asarray(raw)
    i = _nearest_index(latitudes, latitude)
    j = _nearest_index(longitudes, longitude)
    if not (0 <= i < array.shape[0] and 0 <= j < array.shape[1]):
        return None
    return coerce_to_missing(
        array[i, j],
        sentinels=sentinels,
        nan_is_missing=nan_is_missing,
    )


# ---------------------------------------------------------------------------
# Provenance builder (tests 17, 18)
# ---------------------------------------------------------------------------


def build_feature_provenance(
    record: AcquisitionRecord,
    *,
    prediction_cutoff_utc: datetime,
    transform: str,
    derived_at_utc: datetime | None = None,
    days: list[FeatureDayProvenance] | None = None,
) -> FeatureProvenance:
    if not record.sha256:
        raise FeatureContractError(
            f"acquisition record {record.record_id} has no artifact SHA-256"
        )
    if not record.source_record_id:
        raise FeatureContractError(
            f"acquisition record {record.record_id} has no source_record_id to trace to"
        )
    if record.observation_start_utc is None or record.observation_end_utc is None:
        raise FeatureContractError(
            f"acquisition record {record.record_id} has no observation window"
        )
    source = get_source_config(record.source)
    try:
        coordinate_precision = COORDINATE_PRECISION_BY_SOURCE[record.source]
    except KeyError:
        raise FeatureContractError(
            f"source {record.source!r} has no verified coordinate precision; "
            "refusing to claim a spatial resolution that was never confirmed "
            "against its artifact/provider metadata"
        ) from None
    return FeatureProvenance(
        source=record.source,
        product=record.product,
        product_version=record.product_version,
        source_record_id=record.source_record_id,
        artifact_sha256=record.sha256,
        acquisition_record_id=record.record_id,
        observation_start_utc=record.observation_start_utc,
        observation_end_utc=record.observation_end_utc,
        available_utc=record.available_utc,
        availability_classification=record.availability_classification,
        retrieved_utc=record.retrieved_utc,
        prediction_cutoff_utc=prediction_cutoff_utc,
        crs=record.crs or CANONICAL_CRS,
        coordinate_precision=coordinate_precision,
        spatial_resolution=source.spatial_resolution,
        license_attribution=record.license_attribution,
        transform=transform,
        derived_at_utc=derived_at_utc or utcnow_aware(),
        days=days,
    )


def _feature(
    spec: FeatureSpec,
    *,
    provenance: FeatureProvenance,
    value: float | None,
    status: FeatureStatus,
    note: str | None = None,
) -> FeatureValue:
    return FeatureValue(
        feature_name=spec.name,
        value=value,
        unit=spec.unit,
        status=status,
        provenance=provenance,
        note=note,
    )


# ---------------------------------------------------------------------------
# CHIRPS (tests 5, 7, 14, 15, 20)
# ---------------------------------------------------------------------------


def chirps_daily_coverage_days(
    manifest: AcquisitionManifest, record: AcquisitionRecord
) -> int:
    """Number of distinct daily CHIRPS files kept in the ledger.

    With the current single artifact this is 1; every rolling window > 1 day
    is therefore honestly reported as insufficient coverage.
    """
    days: set = set()
    for other in manifest.records:
        if (
            other.kind == "REAL"
            and other.source == record.source
            and other.status in KEPT_STATUSES
            and other.observation_start_utc is not None
        ):
            days.add(other.observation_start_utc.date())
    return len(days)


def _is_daily_candidate(record: AcquisitionRecord) -> bool:
    """True when the record is a traceable, kept REAL one-day observation.

    A rolling window can only aggregate records whose ledger fields place them
    on exactly one day and trace them to a SHA-256 and a source record ID.
    """
    return (
        record.kind == "REAL"
        and record.status in KEPT_STATUSES
        and record.observation_start_utc is not None
        and record.observation_end_utc is not None
        and bool(record.sha256)
        and bool(record.source_record_id)
        and record.observation_end_utc == record.observation_start_utc + timedelta(days=1)
    )


def _registered_compatible(record: AcquisitionRecord, source_config: SourceConfig) -> bool:
    """True when the record's product and version match the provider registry."""
    return record.product == source_config.product and _product_version_compatible(
        record.product_version, source_config.product_version
    )


def _chirps_daily_candidates(
    manifest: AcquisitionManifest, record: AcquisitionRecord
) -> dict[date, AcquisitionRecord]:
    """Deterministic day -> kept REAL daily CHIRPS record map for the source.

    Only acquisition-record fields participate: no filename or filesystem
    metadata is ever trusted for a date, identity, version or availability
    fact. A record whose observation window is not exactly the CHIRPS daily
    cadence (one day) is not a candidate for aggregation, and neither is one
    that cannot be traced (no SHA-256 or source record ID kept).

    Same-day records with identical SHA-256 (the acquisition layer deduplicates
    identical bytes to ``skipped_existing`` sharing one storage path) collapse
    to a single deterministic choice (lowest record id). Same-day records with
    different SHA-256 are a conflict that is never silently resolved: they
    raise ``FeatureContractError`` naming the date and every record ID in
    stable lexical order (approved decision C2).
    """
    day_map: dict[date, list[AcquisitionRecord]] = {}
    for other in manifest.records:
        if other.source != record.source or not _is_daily_candidate(other):
            continue
        day_map.setdefault(other.observation_start_utc.date(), []).append(other)
    chosen: dict[date, AcquisitionRecord] = {}
    for day in sorted(day_map):
        same_day = sorted(day_map[day], key=lambda other: other.record_id)
        distinct_shas = {other.sha256 for other in same_day}
        if len(distinct_shas) == 1:
            chosen[day] = same_day[0]
            continue
        raise FeatureContractError(
            "conflicting CHIRPS daily artifacts for " + day.isoformat() + ": "
            + ", ".join(other.record_id for other in same_day)
            + " have different SHA-256 values; refusing to select among them"
        )
    return chosen


def _chirps_rolling_window_days(
    manifest: AcquisitionManifest,
    record: AcquisitionRecord,
    window_days: int,
    source_config: SourceConfig,
) -> tuple[list[date], list[AcquisitionRecord | None], set[str]]:
    """The inclusive [D-(N-1), D] daily records ending on the anchor day D.

    ``D`` is the anchor record's ``observation_start_utc.date()`` (approved
    decision B). Returns (required dates ascending, record-or-None per required
    date, resolved product versions among the present selected days). A ``None``
    slot means the day is unavailable: its record is absent, or its
    product/version is not compatible with the provider registry (approved
    decision C3). Incompatibility is decided purely from ledger fields. Raises
    ``FeatureContractError`` only when ambiguity must not be resolved silently
    (conflicting same-day SHA, approved decision C2).

    The anchor day is always present when the anchor record is itself a daily
    candidate: same-day records with identical SHA-256 are interchangeable, so
    the identity-verified anchor is used for its own day even when the
    version-agnostic dedupe would otherwise pick an incompatible duplicate
    (the "anchor day is always present by construction" guarantee). This never
    fabricates a value: the anchor still passes the same identity, leakage and
    availability gates as every other day.
    """
    candidates = _chirps_daily_candidates(manifest, record)
    anchor = record.observation_start_utc.date()
    anchor_is_candidate = _is_daily_candidate(record)
    required = [
        anchor - timedelta(days=offset)
        for offset in range(window_days - 1, -1, -1)
    ]
    window: list[AcquisitionRecord | None] = []
    versions: set[str] = set()
    for day in required:
        other = candidates.get(day)
        if (
            day == anchor
            and anchor_is_candidate
            and (other is None or not _registered_compatible(other, source_config))
        ):
            other = record
        if other is None or not _registered_compatible(other, source_config):
            window.append(None)
            continue
        window.append(other)
        versions.add(other.product_version)
    return required, window, versions


def _build_chirps_features(
    record: AcquisitionRecord,
    request: FeatureExtractionRequest,
    manifest: AcquisitionManifest,
    raw,
    lats: np.ndarray,
    lons: np.ndarray,
    *,
    derived_at_utc: datetime,
    chirps_decoder: Callable | None = None,
    raw_root: Path | None = None,
) -> list[FeatureValue]:
    daily_value = sample_grid(
        raw,
        lats,
        lons,
        request.position.latitude,
        request.position.longitude,
        sentinels=(CHIRPS_NODATA,),
    )
    source_config = get_source_config(record.source)
    day_samples: dict[tuple[date, str], float | None] = {}
    window_results: dict[
        int, tuple[FeatureStatus, float | None, str | None, list[FeatureDayProvenance] | None]
    ] = {}

    def sample_a_day(day_record: AcquisitionRecord) -> float | None:
        key = (day_record.observation_start_utc.date(), day_record.record_id)
        if key not in day_samples:
            day_path = artifact_path(day_record, raw_root=raw_root)
            day_raw, day_lats, day_lons = read_chirps_grid(
                day_path, decoder=chirps_decoder, region=request.region
            )
            day_samples[key] = sample_grid(
                day_raw,
                day_lats,
                day_lons,
                request.position.latitude,
                request.position.longitude,
                sentinels=(CHIRPS_NODATA,),
            )
        return day_samples[key]

    def day_rejection_note(day_record: AcquisitionRecord) -> str:
        leakage = evaluate_leakage(
            day_record.observation_start_utc,
            day_record.observation_end_utc,
            day_record.available_utc,
            request.prediction_cutoff_utc,
        )
        if leakage is FeatureStatus.REJECTED_LEAKAGE:
            return _leakage_rejected_note(day_record, request.prediction_cutoff_utc)
        return _availability_policy_rejected_note(day_record, request.availability_policy)

    def day_provenance_for(day_record: AcquisitionRecord) -> FeatureDayProvenance:
        return FeatureDayProvenance(
            observation_start_utc=day_record.observation_start_utc,
            observation_end_utc=day_record.observation_end_utc,
            available_utc=day_record.available_utc,
            availability_classification=day_record.availability_classification,
            acquisition_record_id=day_record.record_id,
            source_record_id=day_record.source_record_id,
            artifact_sha256=day_record.sha256,
        )

    def rolling_window_result(
        window_days: int,
    ) -> tuple[FeatureStatus, float | None, str | None, list[FeatureDayProvenance] | None]:
        """One inclusive [D-(N-1), D] window: gates then coverage then pixels.

        Raise-level failures (conflicting same-day SHA during selection, or a
        selected artifact failing identity/checksum verification) abort before
        any status is produced. Every evaluated day's audit entry is kept in
        ``days`` even when the window is rejected or insufficient, so the
        rejection stays traceable without ever leaking a partial value.
        """
        cached = window_results.get(window_days)
        if cached is not None:
            return cached
        required, window, versions = _chirps_rolling_window_days(
            manifest, record, window_days, source_config
        )
        present = [other for other in window if other is not None]
        per_day = [day_provenance_for(other) for other in present]
        if per_day and per_day[-1].observation_start_utc != record.observation_start_utc:
            raise FeatureContractError(
                f"CHIRPS rolling window for anchor {record.record_id} does not end on "
                "the anchor day; refusing to name a provenance anchor the window "
                "does not actually cover"
            )
        for other in present:
            verify_artifact_identity(
                other, artifact_path(other, raw_root=raw_root), source_config=source_config
            )
        rejected = [
            other
            for other in present
            if evaluate_leakage(
                other.observation_start_utc,
                other.observation_end_utc,
                other.available_utc,
                request.prediction_cutoff_utc,
            )
            is FeatureStatus.REJECTED_LEAKAGE
            or evaluate_availability_policy(
                other, availability_policy=request.availability_policy
            )
            is FeatureStatus.REJECTED_LEAKAGE
        ]
        if rejected:
            note = (
                "rejected for leakage: required day(s) "
                + ", ".join(
                    sorted({r.observation_start_utc.date().isoformat() for r in rejected})
                )
                + " do not clear the "
                + request.availability_policy
                + " gate; "
                + "; ".join(
                    f"{r.observation_start_utc.date().isoformat()}: {day_rejection_note(r)}"
                    for r in rejected
                )
            )
            result = (FeatureStatus.REJECTED_LEAKAGE, None, note, per_day)
            window_results[window_days] = result
            return result
        unavailable = [day for day, other in zip(required, window) if other is None]
        if unavailable or len(versions) > 1:
            day = (
                record.observation_start_utc.date().isoformat()
                if record.observation_start_utc
                else "?"
            )
            note = (
                f"requires additional temporal coverage: {window_days} contiguous daily "
                f"artifacts ending {day}; {len(present)} available; "
                "missing history is never zero-filled."
            )
            reasons = []
            if unavailable:
                reasons.append(
                    "missing daily artifact(s) "
                    + ", ".join(unavailable_day.isoformat() for unavailable_day in unavailable)
                )
            if len(versions) > 1:
                reasons.append(
                    "mixed product vintages ("
                    + ", ".join(sorted(versions))
                    + ") are not aggregated"
                )
            note += " " + "; ".join(reasons)
            result = (FeatureStatus.INSUFFICIENT_TEMPORAL_COVERAGE, None, note, per_day)
            window_results[window_days] = result
            return result
        samples = [sample_a_day(other) for other in present]
        nodata_days = [
            other.observation_start_utc.date().isoformat()
            for other, sample in zip(present, samples)
            if sample is None
        ]
        if nodata_days:
            note = (
                "cell is CHIRPS nodata (-9999); never converted to zero. "
                "nodata on required day(s): "
                + ", ".join(sorted(nodata_days))
            )
            result = (FeatureStatus.MISSING, None, note, per_day)
            window_results[window_days] = result
            return result
        total = sum(sample for sample in samples)
        result = (FeatureStatus.VALID, total, None, per_day)
        window_results[window_days] = result
        return result

    features: list[FeatureValue] = []
    for name in request.requested_features:
        spec = FEATURE_SPECS[name]
        provenance = build_feature_provenance(
            record,
            prediction_cutoff_utc=request.prediction_cutoff_utc,
            transform=spec.transform,
            derived_at_utc=derived_at_utc,
        )
        is_daily = spec.name == "precipitation_daily_mm"
        is_1d = spec.kind is FeatureKind.ROLLING and spec.window_days == 1
        if is_daily or is_1d:
            if daily_value is None:
                features.append(
                    _feature(
                        spec,
                        provenance=provenance,
                        value=None,
                        status=FeatureStatus.MISSING,
                        note="cell is CHIRPS nodata (-9999); never converted to zero.",
                    )
                )
            elif is_1d:
                features.append(
                    _feature(
                        spec,
                        provenance=provenance,
                        value=daily_value,
                        status=FeatureStatus.VALID,
                        note="1-day rolling window equals the single acquired daily "
                        "value; it covers only that day and implies no multi-day "
                        "coverage.",
                    )
                )
            else:
                features.append(
                    _feature(
                        spec, provenance=provenance, value=daily_value, status=FeatureStatus.VALID
                    )
                )
            continue
        if spec.kind is FeatureKind.ROLLING and spec.window_days is not None:
            status, value, note, per_day = rolling_window_result(spec.window_days)
            rolling_provenance = build_feature_provenance(
                record,
                prediction_cutoff_utc=request.prediction_cutoff_utc,
                transform=spec.transform,
                derived_at_utc=derived_at_utc,
                days=per_day,
            )
            features.append(
                _feature(
                    spec,
                    provenance=rolling_provenance,
                    value=value,
                    status=status,
                    note=note,
                )
            )
            continue
        raise FeatureContractError(f"{spec.name}: not supported for source {record.source}")
    return features


#: Classic-TIFF field types this reader understands, in bytes per value.
_TIFF_TYPE_SIZES = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8}

#: Integer TIFF field types: struct format (endianness added at call time).
_TIFF_INT_FORMATS = {1: "B", 3: "H", 4: "I", 6: "b", 8: "h", 9: "i"}


def _parse_geotiff_directory(
    handle, path: Path
) -> tuple[dict[int, tuple[int, int, bytes]], str]:
    """Read a classic-TIFF header + IFD (stdlib ``gzip`` + ``struct`` only).

    Returns ``(tags, endian)`` where ``tags`` maps tag id -> ``(type, count,
    raw_value_bytes)``. GDAL places the CHIRPS IFD at the END of the stream, so
    the caller positions ``handle`` at offset 0 and this consumes the header.
    BigTIFF, unknown byte orders and truncated directories are rejected loudly.
    """
    head = handle.read(8)
    if len(head) < 8:
        raise ArtifactReadError(f"{path}: truncated TIFF header")
    byte_order = head[:2]
    if byte_order == b"II":
        endian = "<"
    elif byte_order == b"MM":
        endian = ">"
    else:
        raise ArtifactReadError(
            f"{path}: not a TIFF file (bad byte-order marker {byte_order!r})"
        )
    magic = struct.unpack(endian + "H", head[2:4])[0]
    if magic == 43:
        raise ArtifactReadError(f"{path}: BigTIFF is not supported by the contract reader")
    if magic != 42:
        raise ArtifactReadError(f"{path}: not a TIFF file (bad magic {magic})")
    handle.seek(struct.unpack(endian + "I", head[4:8])[0])
    count_raw = handle.read(2)
    if len(count_raw) < 2:
        raise ArtifactReadError(f"{path}: truncated TIFF directory")
    entry_count = struct.unpack(endian + "H", count_raw)[0]
    entries_blob = handle.read(entry_count * 12)
    if len(entries_blob) < entry_count * 12:
        raise ArtifactReadError(f"{path}: truncated TIFF directory entries")
    tags: dict[int, tuple[int, int, bytes]] = {}
    for index in range(entry_count):
        entry = entries_blob[index * 12 : (index + 1) * 12]
        tag, field_type, count = struct.unpack(endian + "HHI", entry[:8])
        total = _TIFF_TYPE_SIZES.get(field_type, 0) * count
        if total == 0:
            continue  # unknown field type -> tag stays absent -> verification fails
        if total <= 4:
            value = entry[8 : 8 + total]
        else:
            handle.seek(struct.unpack(endian + "I", entry[8:12])[0])
            value = handle.read(total)
            if len(value) < total:
                raise ArtifactReadError(f"{path}: truncated value for TIFF tag {tag}")
        tags[tag] = (field_type, count, value)
    return tags, endian


def _tiff_ints(tags, tag: int, endian: str) -> tuple[int, ...] | None:
    entry = tags.get(tag)
    if entry is None:
        return None
    field_type, count, value = entry
    fmt = _TIFF_INT_FORMATS.get(field_type)
    if fmt is None:
        return None
    return struct.unpack(endian + fmt * count, value[: struct.calcsize(fmt) * count])


def _tiff_doubles(tags, tag: int, endian: str) -> tuple[float, ...] | None:
    entry = tags.get(tag)
    if entry is None:
        return None
    field_type, count, value = entry
    if field_type != 12:
        return None
    return struct.unpack(endian + "d" * count, value[: 8 * count])


def _tiff_ascii(tags, tag: int) -> str | None:
    entry = tags.get(tag)
    if entry is None:
        return None
    _, _, value = entry
    return value.split(b"\x00", 1)[0].decode("ascii", "replace")


def _read_chirps_header(handle, path: Path) -> dict:
    """Parse the GeoTIFF header into the fields the contract verifies."""
    tags, endian = _parse_geotiff_directory(handle, path)

    def required_ints(tag: int, label: str) -> tuple[int, ...]:
        values = _tiff_ints(tags, tag, endian)
        if not values:
            raise FeatureContractError(
                f"CHIRPS artifact {path} has no readable {label} (TIFF tag {tag}); "
                "geometry cannot be verified"
            )
        return values

    width = required_ints(256, "ImageWidth")[0]
    height = required_ints(257, "ImageLength")[0]
    bits = required_ints(258, "BitsPerSample")[0]
    compression = required_ints(259, "Compression")[0]
    pixel_scale = _tiff_doubles(tags, 33550, endian)
    tiepoint = _tiff_doubles(tags, 33922, endian)
    if pixel_scale is None or len(pixel_scale) < 2:
        raise FeatureContractError(
            f"CHIRPS artifact {path} has no ModelPixelScale; geometry cannot be verified"
        )
    if tiepoint is None or len(tiepoint) < 6:
        raise FeatureContractError(
            f"CHIRPS artifact {path} has no ModelTiepoint; geometry cannot be verified"
        )

    epsg = None
    geokeys = _tiff_ints(tags, 34735, endian)
    if geokeys:
        for index in range(4, len(geokeys) - 3, 4):
            key_id, key_location, _, key_value = geokeys[index : index + 4]
            if key_id == 2048 and key_location == 0:
                epsg = key_value
                break
    if epsg is None:
        raise FeatureContractError(
            f"CHIRPS artifact {path} declares no EPSG GeographicTypeGeoKey (2048); "
            "CRS cannot be verified"
        )

    nodata_text = _tiff_ascii(tags, 42113)
    nodata = None
    if nodata_text is not None:
        try:
            nodata = float(nodata_text)
        except ValueError:
            raise ArtifactReadError(
                f"CHIRPS artifact {path}: unreadable GDAL_NODATA {nodata_text!r}"
            ) from None

    return {
        "endian": endian,
        "width": width,
        "height": height,
        "bits_per_sample": bits,
        "compression": compression,
        "samples_per_pixel": (_tiff_ints(tags, 277, endian) or (CHIRPS_SAMPLES_PER_PIXEL,))[0],
        "sample_format": (_tiff_ints(tags, 339, endian) or (CHIRPS_SAMPLE_FORMAT_IEEEFP,))[0],
        "rows_per_strip": (_tiff_ints(tags, 278, endian) or (height,))[0],
        "strip_offsets": _tiff_ints(tags, 273, endian),
        "strip_byte_counts": _tiff_ints(tags, 279, endian),
        "pixel_scale": pixel_scale,
        "tiepoint": tiepoint,
        "epsg": epsg,
        "nodata": nodata,
    }


def _verify_chirps_geometry(header: dict, path: Path) -> None:
    """Refuse an artifact whose geometry/encoding deviates from the contract.

    Runs BEFORE any pixel is interpreted, so an unverified grid is never
    sampled and a different artifact never silently masquerades as CHIRPS.
    """
    if (header["width"], header["height"]) != (CHIRPS_RASTER_WIDTH, CHIRPS_RASTER_HEIGHT):
        raise FeatureContractError(
            f"CHIRPS artifact {path}: dimensions {header['width']}x{header['height']} "
            f"!= contracted {CHIRPS_RASTER_WIDTH}x{CHIRPS_RASTER_HEIGHT}; "
            "refusing to interpret pixels"
        )
    if header["bits_per_sample"] != CHIRPS_BITS_PER_SAMPLE:
        raise ArtifactReadError(
            f"CHIRPS artifact {path}: BitsPerSample {header['bits_per_sample']} "
            f"!= {CHIRPS_BITS_PER_SAMPLE}"
        )
    if header["samples_per_pixel"] != CHIRPS_SAMPLES_PER_PIXEL:
        raise ArtifactReadError(
            f"CHIRPS artifact {path}: SamplesPerPixel {header['samples_per_pixel']} "
            f"!= {CHIRPS_SAMPLES_PER_PIXEL}"
        )
    if header["sample_format"] != CHIRPS_SAMPLE_FORMAT_IEEEFP:
        raise ArtifactReadError(
            f"CHIRPS artifact {path}: SampleFormat {header['sample_format']} is not "
            "IEEE floating point"
        )
    if header["compression"] != CHIRPS_COMPRESSION_NONE:
        raise ArtifactReadError(
            f"CHIRPS artifact {path}: Compression {header['compression']} is not "
            "supported (expected uncompressed)"
        )
    px, py = header["pixel_scale"][0], header["pixel_scale"][1]
    if abs(px - CHIRPS_PIXEL_SIZE) > 1e-6 or abs(py - CHIRPS_PIXEL_SIZE) > 1e-6:
        raise FeatureContractError(
            f"CHIRPS artifact {path}: pixel size ({px}, {py}) != contracted "
            f"{CHIRPS_PIXEL_SIZE} deg; refusing to sample on an unverified grid"
        )
    ox, oy = header["tiepoint"][3], header["tiepoint"][4]
    if abs(ox - CHIRPS_ORIGIN_LON) > 1e-6 or abs(oy - CHIRPS_ORIGIN_LAT) > 1e-6:
        raise FeatureContractError(
            f"CHIRPS artifact {path}: origin ({ox}, {oy}) != contracted "
            f"({CHIRPS_ORIGIN_LON}, {CHIRPS_ORIGIN_LAT}); refusing to sample on an "
            "unverified grid"
        )
    extent = (
        ox,
        oy - header["height"] * py,
        ox + header["width"] * px,
        oy,
    )
    if (
        abs(extent[0] + 180.0) > 1e-4
        or abs(extent[1] + 50.0) > 1e-4
        or abs(extent[2] - 180.0) > 1e-4
        or abs(extent[3] - 50.0) > 1e-4
    ):
        raise FeatureContractError(
            f"CHIRPS artifact {path}: raster extent (W {extent[0]}, S {extent[1]}, "
            f"E {extent[2]}, N {extent[3]}) is not the contracted global grid; "
            "refusing to interpret pixels"
        )
    if header["epsg"] != 4326:
        raise FeatureContractError(
            f"CHIRPS artifact {path}: CRS EPSG:{header['epsg']} is not EPSG:4326; "
            "no reprojection is performed"
        )
    nodata = header["nodata"]
    if nodata is not None and abs(nodata - CHIRPS_NODATA) > 1e-9:
        raise FeatureContractError(
            f"CHIRPS artifact {path}: GDAL_NODATA {nodata} != contracted "
            f"{CHIRPS_NODATA}; refusing to interpret missing values"
        )


def _chirps_study_window(
    header: dict, region: StudyRegion, path: Path
) -> tuple[int, int, int, int]:
    """Raster row/col range covering ``region`` (cell-edge semantics).

    The region edges are cell boundaries, so the covering index is the rounded
    edge index (the CHIRPS pixel size is stored as float64 0.0500000007, which
    makes a strict floor drift by one row). Rounding is monotonic across the
    region, so the returned window bounds the nearest-centre index of every
    position inside the region: sampling never leaves the window and the window
    is never padded with rows the region does not reach.
    """
    ox, oy = header["tiepoint"][3], header["tiepoint"][4]
    px, py = header["pixel_scale"][0], header["pixel_scale"][1]
    row0 = int(round((oy - region.north) / py))
    row1 = int(round((oy - region.south) / py))
    col0 = int(round((region.west - ox) / px))
    col1 = int(round((region.east - ox) / px))
    if not (0 <= row0 <= row1 < header["height"] and 0 <= col0 <= col1 < header["width"]):
        raise FeatureContractError(
            f"study region (N {region.north}, W {region.west}, S {region.south}, "
            f"E {region.east}) falls outside the verified CHIRPS raster extent of "
            f"{path}; no resampling or padding is performed"
        )
    return row0, row1, col0, col1


def _read_chirps_window(handle, header: dict, window, path: Path) -> np.ndarray:
    """Read only the strips covering the study window (memory-safe)."""
    row0, row1, col0, col1 = window
    width, height = header["width"], header["height"]
    bytes_per_pixel = (header["bits_per_sample"] // 8) * header["samples_per_pixel"]
    rows_per_strip = header["rows_per_strip"]
    offsets = header["strip_offsets"]
    if not offsets:
        raise FeatureContractError(
            f"CHIRPS artifact {path} has no StripOffsets; pixels cannot be read"
        )
    counts = header["strip_byte_counts"]

    def rows_in_strip(strip: int) -> int:
        return min(rows_per_strip, height - strip * rows_per_strip)

    strip0, strip1 = row0 // rows_per_strip, row1 // rows_per_strip
    if strip1 >= len(offsets):
        raise ArtifactReadError(
            f"CHIRPS artifact {path}: strip offsets do not cover the study window"
        )
    resolved_counts: list[int] = []
    for strip in range(strip0, strip1 + 1):
        expected = rows_in_strip(strip) * width * bytes_per_pixel
        declared = counts[strip] if counts and strip < len(counts) else None
        if declared is not None and declared != expected:
            raise ArtifactReadError(
                f"CHIRPS artifact {path}: strip {strip} byte count {declared} != "
                f"expected {expected}"
            )
        resolved_counts.append(expected)

    dtype = np.dtype(header["endian"] + "f4")
    contiguous = all(
        offsets[strip + 1] == offsets[strip] + resolved_counts[index]
        for index, strip in enumerate(range(strip0, strip1))
    )
    if contiguous:
        total = sum(resolved_counts)
        handle.seek(offsets[strip0])
        blob = handle.read(total)
        if len(blob) != total:
            raise ArtifactReadError(
                f"CHIRPS artifact {path}: truncated strip data for the study window"
            )
        strip_rows = sum(rows_in_strip(strip) for strip in range(strip0, strip1 + 1))
        stacked = np.frombuffer(blob, dtype=dtype).reshape(strip_rows, width)
    else:
        pieces = []
        for strip, count in zip(range(strip0, strip1 + 1), resolved_counts):
            handle.seek(offsets[strip])
            blob = handle.read(count)
            if len(blob) != count:
                raise ArtifactReadError(f"CHIRPS artifact {path}: truncated strip {strip}")
            pieces.append(
                np.frombuffer(blob, dtype=dtype).reshape(rows_in_strip(strip), width)
            )
        stacked = np.vstack(pieces)

    top = row0 - strip0 * rows_per_strip
    window_array = stacked[top : top + (row1 - row0 + 1), col0 : col1 + 1]
    return np.array(window_array, dtype=np.float64)


def read_chirps_grid(
    path: Path,
    decoder: Callable | None = None,
    *,
    region: StudyRegion | None = None,
):
    """Decode the CHIRPS GeoTIFF study window into ``(raw, lats, lons)``.

    Phase 3.7.2: no raster backend is needed. A built-in classic-TIFF reader
    (stdlib ``gzip`` + ``struct``) verifies the artifact's dimensions, pixel
    size, origin/extent, EPSG:4326, float32 single-band encoding and nodata
    against the contract BEFORE any pixel is interpreted, then reads only the
    strips covering ``region`` -- never the full 7200x2000 raster. ``lats`` and
    ``lons`` are cell-centre axes; a deviating artifact is refused
    (``FeatureContractError`` / ``ArtifactReadError``), never guessed at.

    ``decoder`` is an injected ``(path) -> (raw_2d, lats, lons)`` callable used
    by tests with bounded fixture grids; when supplied, no file is read.
    ``region`` defaults to the canonical study region.
    """
    if decoder is not None:
        return decoder(path)
    if not path.is_file():
        raise ArtifactReadError(f"raw artifact missing: {path}")
    region = region or study_region()
    with gzip.open(path, "rb") as handle:
        header = _read_chirps_header(handle, path)
        _verify_chirps_geometry(header, path)
        window = _chirps_study_window(header, region, path)
        raw = _read_chirps_window(handle, header, window, path)
    ox, oy = header["tiepoint"][3], header["tiepoint"][4]
    px, py = header["pixel_scale"][0], header["pixel_scale"][1]
    row0, row1, col0, col1 = window
    lats = oy - (np.arange(row0, row1 + 1) + 0.5) * py
    lons = ox + (np.arange(col0, col1 + 1) + 0.5) * px
    return raw, lats, lons


# ---------------------------------------------------------------------------
# ERA5-Land (tests 6, 8-11)
# ---------------------------------------------------------------------------


def _verify_era5_axes(lats, lons, *, path: Path | None = None) -> None:
    """Verify the ERA5-Land axes against the contract (pure array check).

    Dimensions, strict descending latitude / ascending longitude, exact 0.1 deg
    spacing and extent equal to the canonical study region. Verified BEFORE any
    value is interpreted; a deviation raises.
    """
    where = f" in {path}" if path is not None else ""
    if lats.size != ERA5_LATITUDE_COUNT or lons.size != ERA5_LONGITUDE_COUNT:
        raise FeatureContractError(
            f"ERA5-Land grid{where}: {lats.size}x{lons.size} points != contracted "
            f"{ERA5_LATITUDE_COUNT}x{ERA5_LONGITUDE_COUNT}; refusing to interpret values"
        )
    if not np.all(np.diff(lats) < 0):
        raise FeatureContractError(
            f"ERA5-Land latitude axis{where} is not strictly descending; "
            "refusing to sample on an unverified grid"
        )
    if not np.all(np.diff(lons) > 0):
        raise FeatureContractError(
            f"ERA5-Land longitude axis{where} is not strictly ascending; "
            "refusing to sample on an unverified grid"
        )
    if not np.allclose(np.diff(lats), -ERA5_GRID_SPACING, rtol=0, atol=1e-9):
        raise FeatureContractError(
            f"ERA5-Land latitude spacing{where} is not {ERA5_GRID_SPACING} deg; "
            "refusing to sample on an unverified grid"
        )
    if not np.allclose(np.diff(lons), ERA5_GRID_SPACING, rtol=0, atol=1e-9):
        raise FeatureContractError(
            f"ERA5-Land longitude spacing{where} is not {ERA5_GRID_SPACING} deg; "
            "refusing to sample on an unverified grid"
        )
    expected = study_region()
    if (
        abs(float(lats[0]) - expected.north) > 1e-6
        or abs(float(lats[-1]) - expected.south) > 1e-6
        or abs(float(lons[0]) - expected.west) > 1e-6
        or abs(float(lons[-1]) - expected.east) > 1e-6
    ):
        raise FeatureContractError(
            f"ERA5-Land grid extent{where} (lat {lats[0]}..{lats[-1]}, lon "
            f"{lons[0]}..{lons[-1]}) != contracted study region "
            f"(N {expected.north}, S {expected.south}, W {expected.west}, E {expected.east})"
        )


def _require_era5_units(units_by_variable: dict, *, path: Path | None = None) -> None:
    """Require every supported variable's declared ``units`` to match.

    Units are checked BEFORE values are interpreted: an unexpected or missing
    unit would mean the values are misread, so extraction is refused (no silent
    unit conversion).
    """
    where = f" in {path}" if path is not None else ""
    for short, expected in ERA5_LAND_UNITS.items():
        if short not in units_by_variable:
            raise FeatureContractError(
                f"ERA5-Land variable {short!r}{where} is missing; refusing to "
                "interpret values"
            )
        declared = units_by_variable[short]
        declared = None if declared is None else str(declared).strip()
        if declared != expected:
            raise FeatureContractError(
                f"ERA5-Land variable {short!r}{where} declares units {declared!r} != "
                f"contracted {expected!r}; refusing to interpret values "
                "(no silent unit conversion)"
            )


def _require_region_within_axes(
    lats, lons, region: StudyRegion, *, path: Path | None = None
) -> None:
    """Require the requested region to fall inside the artifact's cell area."""
    half = ERA5_GRID_SPACING / 2
    lat_min, lat_max = float(np.min(lats)), float(np.max(lats))
    lon_min, lon_max = float(np.min(lons)), float(np.max(lons))
    if (
        region.north > lat_max + half + 1e-9
        or region.south < lat_min - half - 1e-9
        or region.west < lon_min - half - 1e-9
        or region.east > lon_max + half + 1e-9
    ):
        raise FeatureContractError(
            f"study region (N {region.north}, W {region.west}, S {region.south}, "
            f"E {region.east}) falls outside the verified ERA5-Land grid extent of "
            f"{path}; no resampling, padding or reprojection is performed"
        )


def read_era5_land_variables(
    path: Path,
    *,
    region: StudyRegion | None = None,
) -> dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Read the real NetCDF artifact: short code -> (raw, lats, lons).

    Phase 3.7.2: the axes (dimensions, ordering, 0.1 deg spacing, extent) and
    every variable's declared ``units`` are verified against the contract
    BEFORE values are interpreted. ``_FillValue``/NaN cells become NaN (later
    mapped to ``missing``). Requires ``netCDF4``, imported lazily so the rest
    of the stack never needs it.
    """
    if not path.is_file():
        raise ArtifactReadError(f"raw artifact missing: {path}")
    try:
        import netCDF4  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover - depends on environment
        raise ArtifactReadError(
            f"NetCDF decoding requires netCDF4, which is not installed: {exc}"
        ) from exc
    region = region or study_region()
    with netCDF4.Dataset(path, "r") as dataset:
        for axis in ("latitude", "longitude"):
            if axis not in dataset.variables:
                raise FeatureContractError(
                    f"ERA5-Land artifact {path} has no {axis!r} axis; geometry "
                    "cannot be verified"
                )
        lats = np.asarray(dataset.variables["latitude"][:], dtype=float)
        lons = np.asarray(dataset.variables["longitude"][:], dtype=float)
        _verify_era5_axes(lats, lons, path=path)
        _require_region_within_axes(lats, lons, region, path=path)
        units_by_variable: dict[str, str | None] = {}
        for short in ERA5_LAND_VARIABLE_MAP:
            if short not in dataset.variables:
                raise FeatureContractError(
                    f"ERA5-Land artifact {path} is missing required variable "
                    f"{short!r}; refusing to interpret values"
                )
            units_by_variable[short] = getattr(dataset.variables[short], "units", None)
        _require_era5_units(units_by_variable, path=path)
        grids: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
        for short in ERA5_LAND_VARIABLE_MAP:
            variable = dataset.variables[short]
            arr = np.asarray(variable[:], dtype=float).squeeze()
            fill = getattr(variable, "_FillValue", None)
            if fill is not None and not np.isnan(float(fill)):
                arr = np.where(np.isclose(arr, float(fill)), np.nan, arr)
            grids[short] = (arr, lats, lons)
    return grids


def _build_era5_features(
    record: AcquisitionRecord,
    request: FeatureExtractionRequest,
    grids: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]],
    *,
    derived_at_utc: datetime,
) -> list[FeatureValue]:
    features: list[FeatureValue] = []
    for name in request.requested_features:
        spec = FEATURE_SPECS[name]
        raw, lats, lons = grids[spec.source_variable]
        value = sample_grid(
            raw, lats, lons, request.position.latitude, request.position.longitude
        )
        provenance = build_feature_provenance(
            record,
            prediction_cutoff_utc=request.prediction_cutoff_utc,
            transform=spec.transform,
            derived_at_utc=derived_at_utc,
        )
        if value is None:
            features.append(
                _feature(
                    spec,
                    provenance=provenance,
                    value=None,
                    status=FeatureStatus.MISSING,
                    note=f"{spec.source_variable} cell is _FillValue/NaN; never converted to zero.",
                )
            )
        else:
            features.append(
                _feature(spec, provenance=provenance, value=value, status=FeatureStatus.VALID)
            )
    return features


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _read_source_features(
    request: FeatureExtractionRequest,
    record: AcquisitionRecord,
    *,
    manifest: AcquisitionManifest,
    chirps_decoder: Callable | None = None,
    era5_grids: dict | None = None,
    raw_root: Path | None = None,
    derived_at_utc: datetime,
) -> list[FeatureValue]:
    path = artifact_path(record, raw_root=raw_root)
    if request.source == "chirps":
        raw, lats, lons = read_chirps_grid(
            path, decoder=chirps_decoder, region=request.region
        )
        return _build_chirps_features(
            record,
            request,
            manifest,
            raw,
            lats,
            lons,
            derived_at_utc=derived_at_utc,
            chirps_decoder=chirps_decoder,
            raw_root=raw_root,
        )
    if request.source == "era5-land":
        grids = (
            era5_grids
            if era5_grids is not None
            else read_era5_land_variables(path, region=request.region)
        )
        return _build_era5_features(record, request, grids, derived_at_utc=derived_at_utc)
    raise FeatureContractError(
        f"feature extraction is not defined for source {request.source!r}"
    )


def run_extraction(
    request: FeatureExtractionRequest,
    *,
    manifest: AcquisitionManifest | None = None,
    chirps_decoder: Callable | None = None,
    era5_grids: dict | None = None,
    raw_root: Path | None = None,
) -> FeatureExtractionResult:
    """Extract contract features for one point from the REAL artifacts.

    Order of checks (all deterministic):
    1. source is an approved REAL source;
    2. CRS is EPSG:4326;
    3. position is inside the study region;
    4. artifact resolves to a kept ledger record (pinned by SHA-256 if given);
    5. artifact identity: the record's product/version is checked against the
       provider registry and the file's SHA-256 is recomputed and compared with
       the ledger -- if either fails, extraction aborts;
    6. requested feature names resolve to the source's supported vocabulary;
    7. leakage gates: the time rule (observation window and vintage at or before
       the cutoff) plus the availability-evidence rule per the request's
       ``availability_policy`` (production requires ``provider_issued`` evidence,
       G-4 / §23); a rejection marks every requested feature and returns;
    8. decode (the readers verify artifact geometry before interpreting a
       pixel); nearest-cell sample; build provenance.
    """
    supported_by_source = {
        spec.source for spec in FEATURE_SPECS.values()
    }
    if request.source not in supported_by_source:
        raise FeatureContractError(
            f"feature extraction is not defined for source {request.source!r}"
        )
    try:
        source_config = get_source_config(request.source)
    except UnsupportedSourceError as exc:
        raise FeatureContractError(str(exc)) from exc
    if source_config.kind != "REAL":
        raise FeatureContractError(
            f"source {request.source!r} is {source_config.kind}, not REAL; "
            "feature extraction is only defined for REAL artifacts"
        )
    require_epsg4326(request.region.crs)
    require_epsg4326(source_config.crs)
    _validate_position(request)

    resolved = manifest or load_acquisition_manifest()
    record = resolve_acquired_record(resolved, request.source, request.artifact_sha256)
    path = artifact_path(record, raw_root=raw_root)
    verify_artifact_identity(record, path, source_config=source_config)

    supported = {spec.name for spec in FEATURE_SPECS.values() if spec.source == request.source}
    names = request.requested_features
    if names is None:
        names = sorted(supported)
    unknown = [name for name in names if name not in supported]
    if unknown:
        raise FeatureContractError(
            f"unsupported feature(s) for source {request.source!r}: {sorted(unknown)}"
        )
    request = request.model_copy(update={"requested_features": names})

    extracted_at_utc = utcnow_aware()
    leakage = evaluate_leakage(
        record.observation_start_utc,
        record.observation_end_utc,
        record.available_utc,
        request.prediction_cutoff_utc,
    )
    availability = evaluate_availability_policy(
        record, availability_policy=request.availability_policy
    )
    if leakage is FeatureStatus.REJECTED_LEAKAGE:
        note = _leakage_rejected_note(record, request.prediction_cutoff_utc)
    elif availability is FeatureStatus.REJECTED_LEAKAGE:
        note = _availability_policy_rejected_note(record, request.availability_policy)
    else:
        note = None
    if note is not None:
        features = [
            _feature(
                FEATURE_SPECS[name],
                provenance=build_feature_provenance(
                    record,
                    prediction_cutoff_utc=request.prediction_cutoff_utc,
                    transform=FEATURE_SPECS[name].transform,
                    derived_at_utc=extracted_at_utc,
                ),
                value=None,
                status=FeatureStatus.REJECTED_LEAKAGE,
                note=note,
            )
            for name in request.requested_features
        ]
    else:
        features = _read_source_features(
            request,
            record,
            manifest=resolved,
            chirps_decoder=chirps_decoder,
            era5_grids=era5_grids,
            raw_root=raw_root,
            derived_at_utc=extracted_at_utc,
        )

    return FeatureExtractionResult(
        extracted_at_utc=extracted_at_utc,
        source=request.source,
        acquisition_record_id=record.record_id,
        artifact_sha256=record.sha256,
        storage_path=record.storage_path,
        features=features,
    )