"""REAL-data feature extraction service (Phase 3.7.1 foundation).

Turns acquired REAL artifacts into typed, fully-provenanced features under the
contract in ``app.schemas.features``. Only the currently acquired artifacts
are supported; no new dataset is downloaded and no value is fabricated.

Key behaviours
--------------
* Artifact identity is pinned by the acquisition ledger: an extraction request
  resolves to a kept ``AcquisitionRecord``, the file's SHA-256 is re-computed
  and compared, then features are sampled.
* Leakage is gated before anything else: if the artifact's observation window
  end or its ``available_utc`` is after the prediction cutoff, every feature
  is ``rejected_leakage`` (deterministic, no partial mesh of old and new).
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
``netCDF4`` package is imported lazily. CHIRPS GeoTIFF decoding is
backend-gated (``rasterio``); when that backend is absent the contract's
CHIRPS extraction is still proven with bounded fixture grids that mirror the
real artifact's documented geometry (0.05 deg, -9999 fill) -- never by
downloading more data.
"""
from datetime import datetime
from pathlib import Path
from typing import Callable

import numpy as np

from app.config import PROJECT_ROOT
from app.schemas.acquisition import (
    AcquisitionManifest,
    AcquisitionRecord,
    AcquisitionStatus,
)
from app.schemas.features import (
    CANONICAL_CRS,
    CHIRPS_NODATA,
    COORDINATE_PRECISION_BY_SOURCE,
    ERA5_LAND_VARIABLE_MAP,
    FEATURE_SPECS,
    FeatureExtractionRequest,
    FeatureExtractionResult,
    FeatureKind,
    FeatureProvenance,
    FeatureSpec,
    FeatureStatus,
    FeatureValue,
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


def evaluate_leakage(
    observation_start_utc: datetime,
    observation_end_utc: datetime,
    available_utc: datetime | None,
    prediction_cutoff_utc: datetime,
) -> FeatureStatus:
    """Leakage rule: both the observation window and the product vintage must
    be at or before the prediction cutoff.

    Returns ``VALID`` or ``REJECTED_LEAKAGE``. The same inputs always return
    the same status. Naive datetimes are rejected, never converted.
    """
    _require_aware(observation_start_utc, "observation_start_utc")
    _require_aware(observation_end_utc, "observation_end_utc")
    _require_aware(available_utc, "available_utc")
    _require_aware(prediction_cutoff_utc, "prediction_cutoff_utc")
    if observation_end_utc > prediction_cutoff_utc:
        return FeatureStatus.REJECTED_LEAKAGE
    if available_utc is not None and available_utc > prediction_cutoff_utc:
        return FeatureStatus.REJECTED_LEAKAGE
    return FeatureStatus.VALID


def _leakage_rejected_note(
    record: AcquisitionRecord, prediction_cutoff_utc: datetime
) -> str:
    reasons = []
    if record.observation_end_utc is not None and record.observation_end_utc > prediction_cutoff_utc:
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


def verify_artifact_identity(record: AcquisitionRecord, path: Path) -> None:
    """Re-hash the file and require it to equal the ledger's SHA-256.

    A mismatch means the artifact is no longer what was acquired.
    """
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
        retrieved_utc=record.retrieved_utc,
        prediction_cutoff_utc=prediction_cutoff_utc,
        crs=record.crs or CANONICAL_CRS,
        coordinate_precision=coordinate_precision,
        spatial_resolution=source.spatial_resolution,
        license_attribution=record.license_attribution,
        transform=transform,
        derived_at_utc=derived_at_utc or utcnow_aware(),
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


def _build_chirps_features(
    record: AcquisitionRecord,
    request: FeatureExtractionRequest,
    manifest: AcquisitionManifest,
    raw,
    lats: np.ndarray,
    lons: np.ndarray,
    *,
    derived_at_utc: datetime,
) -> list[FeatureValue]:
    daily_value = sample_grid(
        raw,
        lats,
        lons,
        request.position.latitude,
        request.position.longitude,
        sentinels=(CHIRPS_NODATA,),
    )
    available = chirps_daily_coverage_days(manifest, record)
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
            window = spec.window_days
            if available >= window and window > 1:
                raise FeatureContractError(
                    f"{spec.name}: {window} daily files are kept, but multi-file rolling "
                    "aggregation is not implemented in this single-artifact foundation; "
                    "refusing to fabricate a value"
                )
            day = (
                record.observation_start_utc.date().isoformat()
                if record.observation_start_utc
                else "?"
            )
            features.append(
                _feature(
                    spec,
                    provenance=provenance,
                    value=None,
                    status=FeatureStatus.INSUFFICIENT_TEMPORAL_COVERAGE,
                    note=(
                        f"requires additional temporal coverage: {window} contiguous daily "
                        f"artifacts ending {day}; {available} available; "
                        "missing history is never zero-filled."
                    ),
                )
            )
            continue
        raise FeatureContractError(f"{spec.name}: not supported for source {record.source}")
    return features


def read_chirps_grid(path: Path, decoder: Callable | None = None):
    """Decode a CHIRPS GeoTIFF into ``(raw, lats, lons)``.

    ``decoder`` is an injected ``(path) -> (raw_2d, lats, lons)`` callable used
    by tests with bounded fixture grids. Without one this tries the ``rasterio``
    backend and fails loudly when it is absent -- a contract decision, not a
    reason to add a surprise dependency here.
    """
    if decoder is not None:
        return decoder(path)
    try:
        import rasterio  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover - depends on environment
        raise ArtifactReadError(
            "GeoTIFF decoding requires a raster backend (e.g. rasterio), which is "
            f"not installed: {exc}"
        ) from exc
    with rasterio.open(path) as src:
        if src.crs is None or not str(src.crs).startswith("EPSG:4326"):
            raise FeatureContractError(f"CHIRPS artifact {path} is not EPSG:4326")
        arr = src.read(1).astype(float)
        bounds = src.bounds
        lats = np.linspace(bounds.top, bounds.bottom, arr.shape[0])
        lons = np.linspace(bounds.left, bounds.right, arr.shape[1])
    return arr, lats, lons


# ---------------------------------------------------------------------------
# ERA5-Land (tests 6, 8-11)
# ---------------------------------------------------------------------------


def read_era5_land_variables(
    path: Path,
) -> dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Read the real NetCDF artifact: short code -> (raw, lats, lons).

    ``_FillValue`` cells become NaN (later mapped to ``missing``). Requires the
    ``netCDF4`` package, imported lazily so the rest of the stack never needs it.
    """
    try:
        import netCDF4  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover - depends on environment
        raise ArtifactReadError(
            f"NetCDF decoding requires netCDF4, which is not installed: {exc}"
        ) from exc
    with netCDF4.Dataset(path, "r") as dataset:
        lats = np.asarray(dataset.variables["latitude"][:], dtype=float)
        lons = np.asarray(dataset.variables["longitude"][:], dtype=float)
        grids: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
        for short in ERA5_LAND_VARIABLE_MAP:
            variable = dataset.variables[short]
            arr = np.asarray(variable[:], dtype=float).squeeze()
            fill = getattr(variable, "_FillValue", None)
            if fill is not None:
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
    verify_artifact_identity(record, path)
    if request.source == "chirps":
        raw, lats, lons = read_chirps_grid(path, decoder=chirps_decoder)
        return _build_chirps_features(
            record,
            request,
            manifest,
            raw,
            lats,
            lons,
            derived_at_utc=derived_at_utc,
        )
    if request.source == "era5-land":
        grids = era5_grids if era5_grids is not None else read_era5_land_variables(path)
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
    5. leakage gate; a rejection marks every requested feature and returns;
    6. identity re-checksum; decode; sample; build provenance.
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
    if leakage is FeatureStatus.REJECTED_LEAKAGE:
        note = _leakage_rejected_note(record, request.prediction_cutoff_utc)
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