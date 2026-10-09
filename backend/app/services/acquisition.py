"""REAL-data acquisition rig (Phase 3.2).

Registry of approved sources, credential gating, immutable storage of raw
bytes under ``data/raw/real/`` (git-ignored) and a committed acquisition
ledger at ``data/provenance/acquisition_manifest.json``.

Design rules
------------
- No source is silently substituted and no unverified download endpoint is
  embedded: sources that require credentials expose them via named environment
  variables and ``resolve_credentials`` fails loudly when they are absent.
- Raw bytes are stored immutably: an existing target path is never
  overwritten. Content is deduplicated by SHA-256, so re-reading identical
  bytes yields a ``skipped_existing`` record instead of a second file.
- Every attempt is recorded honestly in the ledger (``downloaded``,
  ``skipped_existing``, ``checksum_mismatch``, ``failed``). A failed attempt
  never creates a successful artifact.
- The ledger distinguishes DEMO and REAL. Registering an adapter/configuration
  never implies that REAL data exists: ``acquired_real_count`` reflects only
  actual acquisition results.
- No training, no feature derivation (slope, drainage, ...), no label
  construction happens here.
"""
import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import requests

from app.config import settings
from app.redaction import (
    MAX_HEADER_VALUE_LENGTH,
    bound_string,
    is_sensitive_key,
    redact_text,
    redact_url,
    strip_control_chars,
)
from app.schemas.acquisition import (
    ALLOWLISTED_RESPONSE_HEADERS,
    AcquisitionManifest,
    AcquisitionRecord,
    AcquisitionStatus,
    AuthenticationMethod,
    PreflightReport,
    SourceConfig,
)
from app.schemas.acquisition import utcnow_aware
from app.schemas.provenance import GeographicCoverage
from app.services import cds as cds_client

#: Constants for the approved REAL-data sources (verified in Phase 2.3). This
#: flat list is the single source of truth the rig and tests both reference.
GLOBAL_COVERAGE = GeographicCoverage(
    min_latitude=-90.0, max_latitude=90.0, min_longitude=-180.0, max_longitude=180.0
)
NE_NORTHEAST_INDIA_CORNERS = (88.0, 21.0, 97.5, 29.5)  # lon_min, lat_min, lon_max, lat_max


class AcquisitionError(Exception):
    """Base class for acquisition rig failures."""


class UnsupportedSourceError(AcquisitionError):
    """A source name that is not in the approved registry."""


class CredentialsMissingError(AcquisitionError):
    """A credentialed source is configured but its credentials are absent."""


class InvalidRetrievalRequestError(AcquisitionError):
    """The retrieval request is incomplete (missing URL/scope) or unverified."""


class DuplicateArtifactError(AcquisitionError):
    """The computed artifact path already exists; it will never be overwritten."""


class ChecksumMismatchError(AcquisitionError):
    """Downloaded bytes did not match the caller's expected SHA-256."""


class ManifestError(AcquisitionError):
    """The acquisition ledger is missing or invalid."""


# ---------------------------------------------------------------------------
# Source registry (approved by Phase 2.3)
# ---------------------------------------------------------------------------

SOURCE_REGISTRY: list[SourceConfig] = [
    SourceConfig(
        name="nasa-coolr",
        tier="event",
        product="COOLR (Cooperative Open Online Landslide Repository) events",
        product_version="live-catalog",
        access_reference=(
            "https://gpm.nasa.gov/applications/landslides/coolr (documented FeatureServers: "
            "https://maps.nccs.nasa.gov/mapping/rest/services/COOLR/COOLR_Events_Point/FeatureServer; "
            "https://gis.earthdata.nasa.gov/gis05/rest/services/Landslides/COOLR_Events_Points/FeatureServer)"
        ),
        kind="REAL",
        authentication=AuthenticationMethod.NONE,
        geographic_coverage=GLOBAL_COVERAGE,
        crs="EPSG:4326 (WGS84)",
        license_attribution="NASA data public; per-event `citation` field attribution required.",
        known_limitations=[
            "Media-bias/citizen-science skewed coverage; absence in COOLR is never evidence of no landslide.",
            "location_accuracy is a per-event coded value (exact/1km/5km/...); positional precision must be respected.",
            "Continuously appended live catalog: pin a dated snapshot; event_id is the stable per-feature id.",
            "Sandbox connectivity to the FeatureServers was flaky during Phase 2.3; re-verify at acquisition time.",
        ],
        endpoint_base="https://maps.nccs.nasa.gov/mapping/rest/services/COOLR/COOLR_Events_Point/FeatureServer",
        require_bounded_scope=True,
    ),
    SourceConfig(
        name="nasa-imerg-early",
        tier="rainfall",
        product="NASA GPM IMERG Early precipitation (0.1 deg half-hourly)",
        product_version="unpinned-verify-at-retrieval",
        access_reference="NASA GES DISC (Earthdata Login). Catalog: https://gpm.nasa.gov/data/imerg (verified Phase 2.3). No direct download URL is assumed.",
        kind="REAL",
        authentication=AuthenticationMethod.EARTHDATA_BEARER,
        credentials=["NASA_EARTHDATA_USERNAME", "NASA_EARTHDATA_PASSWORD"],
        geographic_coverage=GLOBAL_COVERAGE,
        crs="EPSG:4326 (WGS84)",
        spatial_resolution="0.1 degrees, half-hourly accumulation",
        license_attribution="CC BY 4.0 (NASA/GPM attribution required)",
        known_limitations=[
            "Early product has ~4h publication latency: preserve valid_time and availability semantics; never claim an observation was available before it was.",
            "Pin the exact IMERG version at retrieval and record it in the acquisition record.",
            "Real-time feeds must not be used to construct cutoff-closed historical features without latency guards.",
        ],
    ),
    SourceConfig(
        name="chirps",
        tier="rainfall",
        product="CHIRPS v2 quasi-global precipitation (0.05 deg, daily/pentad/monthly)",
        product_version="v2.x",
        access_reference="https://data.chc.ucsb.edu/products/CHIRPS-2.0/ (verified README Phase 2.3; anonymous HTTPS/FTP).",
        kind="REAL",
        authentication=AuthenticationMethod.NONE,
        geographic_coverage=GeographicCoverage(
            min_latitude=-50.0, max_latitude=50.0, min_longitude=-180.0, max_longitude=180.0
        ),
        crs="EPSG:4326 (WGS84)",
        spatial_resolution="0.05 degrees",
        license_attribution="Per CHC CHIRPS data use policy (public dataset).",
        known_limitations=[
            "Daily accumulation window semantics are product-version dependent (v2 time coordinate = start of UTC day per ERDDAP; v3 ~00-24 UTC). Never convert daily values into arbitrary cutoffs silently.",
            "prelim product has a ~2-day lag and uses GTS + Conagua stations only.",
            "IR %CCD gaps over parts of E Australia/Indonesia/Japan can read as zero precipitation (coverage check required, not a fill).",
        ],
    ),
    SourceConfig(
        name="era5-land",
        tier="weather-land-state",
        product="ERA5-Land hourly reanalysis (land surface)",
        product_version="operational (consolidated ~2 months; ERA5-Land-T ~5 days)",
        access_reference="Copernicus Climate Data Store (CDS). DOI 10.24381/cds.e2161bac (verified Phase 2.3). No download endpoint is hardcoded; use the CDS API with registered credentials.",
        kind="REAL",
        authentication=AuthenticationMethod.CDS_API,
        credentials=["CDS_API_URL", "CDS_API_KEY"],
        geographic_coverage=GLOBAL_COVERAGE,
        crs="EPSG:4326 (WGS84 lat/lon grid)",
        spatial_resolution="0.1 degrees, hourly",
        license_attribution="Copernicus licence; CC-BY attribution required.",
        known_limitations=[
            "Preserve variable names, units and aggregation semantics: soil moisture / 2m temperature are instantaneous; precipitation accumulations are 00 UTC to step end.",
            "The consolidated archive lags ~2 months; use ERA5-Land-T (~5 days) for near-real-time.",
            "Publication/availability gate must be applied per vintage; do not create cutoff-ready features here.",
        ],
    ),
    SourceConfig(
        name="srtmgl1-v003",
        tier="static",
        product="SRTMGL1 v003 (SRTM Plus) 1-arc-second DEM",
        product_version="v003",
        access_reference="LP DAAC. DOI 10.5067/MEaSUREs/SRTM/SRTMGL1.003 (verified Phase 2.3). NASA Earthdata Login required for HTTP/GES DISC retrieval.",
        kind="REAL",
        authentication=AuthenticationMethod.EARTHDATA_BEARER,
        credentials=["NASA_EARTHDATA_USERNAME", "NASA_EARTHDATA_PASSWORD"],
        geographic_coverage=GeographicCoverage(
            min_latitude=-56.0, max_latitude=60.0, min_longitude=-180.0, max_longitude=180.0
        ),
        crs="EPSG:4326 geographic; vertical EGM96 (metres)",
        spatial_resolution="1 arc-second (~30 m); 1x1 degree .HGT tiles",
        license_attribution="NASA / US government works (public domain; data.nasa.gov).",
        known_limitations=[
            "Terrain acquired February 2000 (static; no change signal).",
            "v3 is void-free (filled from ASTER GDEM2/GMTED2010/NED; per-pixel fill source in SRTMGL1N .NUM).",
            "Record product/vintage (v003) as feature_source_version at use; do not derive slope/drainage here.",
        ],
    ),
    SourceConfig(
        name="esa-worldcover",
        tier="static",
        product="ESA WorldCover 10 m land cover",
        product_version="v200 (reference year 2021); v100 (2020) available separately",
        access_reference="https://esa-worldcover.org/en/data-access (verified Phase 2.3); AWS s3 esa-worldcover-s1/s2 + Terrascope; GEE ESA/WorldCover/v200.",
        kind="REAL",
        authentication=AuthenticationMethod.NONE,
        geographic_coverage=GLOBAL_COVERAGE,
        crs="EPSG:4326 (WGS84)",
        spatial_resolution="10 m COGs, 1x1 degree tiles",
        license_attribution="CC BY 4.0; (c) ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data 2021; cite 10.5281/zenodo.7254221.",
        known_limitations=[
            "A 2021 map is NOT automatically valid for earlier historical cutoffs -- vintage matching per the provenance contract is required.",
            "Single-vintage product (reference years 2020 and 2021 only).",
        ],
    ),
    SourceConfig(
        name="soilgrids",
        tier="static",
        product="SoilGrids 2.0 predicted soil properties",
        product_version="2.0 (2020 prediction run; Poggio et al. 2021)",
        access_reference="https://soilgrids.org (verified Phase 2.3); files.isric.org/soilgrids/latest/; maps.isric.org WCS; GEE projects/soilgrids-isric.",
        kind="REAL",
        authentication=AuthenticationMethod.NONE,
        geographic_coverage=GLOBAL_COVERAGE,
        crs="Homolosine (equal-area); reproject to EPSG:4326 at use",
        spatial_resolution="250 m; 6 depth bands (0-5/5-15/15-30/30-60/60-100/100-200 cm)",
        license_attribution="CC BY 4.0; cite Poggio et al. 2021 (10.5194/soil-7-217-2021).",
        known_limitations=[
            "Timeless predicted map (no temporal dimension) -- still record the prediction-run vintage.",
            "Stored in Homolosine projection since 2019, not WGS84.",
            "Each map ~5 GB (all maps ~120 GB/property): a full download is never implied; use bounded NE-India tiles.",
        ],
    ),
    SourceConfig(
        name="hydrosheds",
        tier="static",
        product="HydroSHEDS v1.1 core (drainage inputs: flow direction DIR, flow accumulation ACC, upstream area ACA)",
        product_version="v1.1 (SRTM-derived)",
        access_reference="https://www.hydrosheds.org/hydrosheds-core-downloads (verified Phase 2.3).",
        kind="REAL",
        authentication=AuthenticationMethod.NONE,
        geographic_coverage=GeographicCoverage(
            min_latitude=-56.0, max_latitude=60.0, min_longitude=-180.0, max_longitude=180.0
        ),
        crs="EPSG:4326 (WGS84 lat/lon)",
        spatial_resolution="3s/15s/30s/5m/6m (Asia 3s ~1335 MB)",
        license_attribution="Free for non-commercial and commercial use (TechDoc v1.4).",
        known_limitations=[
            "SRTM-derived: terrain fixed to year 2000 acquisition.",
            "v1.1 flow-direction grids at 5m/6m were updated vs v1.0; other layers match v1.0.",
            "SRTM-derived D8 drainage derivatives are feature-engineering outputs and belong to a later phase, not here.",
        ],
    ),
]

_REGISTRY_BY_NAME = {source.name: source for source in SOURCE_REGISTRY}


def get_source_config(name: str) -> SourceConfig:
    """Look up an approved source by name; unsupported names fail loudly."""
    config = _REGISTRY_BY_NAME.get(name)
    if config is None:
        raise UnsupportedSourceError(
            f"unsupported acquisition source {name!r}; "
            f"approved sources: {sorted(_REGISTRY_BY_NAME)}"
        )
    return config


def validate_source_configs() -> list[str]:
    """Return a list of configuration problems (empty = registry is sound).

    Registered at import time as well; calling it lets tests re-check the
    invariants cheaply.
    """
    problems: list[str] = []
    names: set[str] = set()
    for source in SOURCE_REGISTRY:
        if source.name in names:
            problems.append(f"{source.name}: duplicate source name")
        names.add(source.name)
        if source.authentication is not AuthenticationMethod.NONE and not source.credentials:
            problems.append(
                f"{source.name}: authentication={source.authentication.value} requires "
                "credential environment variables"
            )
        if not source.access_reference or not source.license_attribution or not source.crs:
            problems.append(f"{source.name}: missing access_reference/license_attribution/crs")
        if source.geographic_coverage is None:
            problems.append(f"{source.name}: geographic_coverage is required")
        if source.require_bounded_scope and source.endpoint_base is None:
            problems.append(
                f"{source.name}: require_bounded_scope=True but no verified endpoint_base"
            )
    return problems


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------

def resolve_credentials(source: SourceConfig) -> dict[str, str]:
    """Return credential values from the environment for a source.

    Raises :class:`CredentialsMissingError` listing the absent variables. The
    values are returned to the caller only; they are never logged or persisted.
    """
    if source.authentication is AuthenticationMethod.NONE:
        return {}
    missing = [var for var in source.credentials if not os.getenv(var)]
    if missing:
        raise CredentialsMissingError(
            f"source {source.name!r} requires credentials absent from the environment: "
            f"{', '.join(missing)}"
        )
    return {var: os.getenv(var) or "" for var in source.credentials}


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FetchResult:
    """Outcome of one real HTTP fetch, including evidence capture.

    ``headers`` are the raw final-response headers (message casing preserved);
    only the allowlist is ever persisted. ``final_url`` and ``redirect_chain``
    are raw here and must be redacted before they reach the ledger.
    """

    content: bytes
    status_code: int
    headers: dict[str, str]
    final_url: str
    redirect_chain: tuple[str, ...] = ()


class AcquisitionTransport:
    """Real network transport for acquisitions (injectable; mocked in tests)."""

    def fetch(self, url: str, headers: dict | None = None, timeout: int = 120) -> FetchResult:
        response = requests.get(url, headers=headers or {}, timeout=timeout)
        response.raise_for_status()
        return FetchResult(
            content=response.content,
            status_code=response.status_code,
            headers=dict(response.headers),
            final_url=response.url,
            redirect_chain=tuple(hop.url for hop in response.history),
        )

    def get_bytes(self, url: str, headers: dict | None = None, timeout: int = 120) -> bytes:
        return self.fetch(url, headers, timeout).content

    def get_json(self, url: str, headers: dict | None = None, timeout: int = 60) -> object:
        response = requests.get(url, headers=headers or {}, timeout=timeout)
        response.raise_for_status()
        return response.json()


# ---------------------------------------------------------------------------
# Immutable storage helpers
# ---------------------------------------------------------------------------

def _slug(value: str, max_length: int = 60) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-_.")
    return (cleaned.lower()[:max_length] or "artifact")


def storage_relative_path(source: SourceConfig, acquisition_key: str, extension: str) -> str:
    """Immutable, content-versioned relative path under data/raw/real/.

    The stem includes the source, product version and the acquisition key, so a
    given key always maps to one path and existing paths are never rewritten.
    """
    stem = f"{source.name}__{_slug(source.product_version)}__{_slug(acquisition_key)}"
    return f"{source.name}/{stem}{extension}"


def _atomic_write(target: Path, data: bytes) -> None:
    """Write bytes to a temp file then atomically replace the target."""
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f"{target.name}.", suffix=".part", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp_name, target)
    except BaseException:
        try:
            os.remove(tmp_name)
        except FileNotFoundError:
            pass
        raise


def _redact_chain(chain) -> tuple[list[str], list[str]]:
    """Redact every URL in a redirect chain; return (redacted_hops, names)."""
    redacted: list[str] = []
    names: list[str] = []
    for hop in chain or ():
        value, hop_names = redact_url(hop)
        redacted.append(value)
        names.extend(hop_names)
    return redacted, names


def _allowlisted_headers(headers: dict | None) -> dict[str, str] | None:
    """Keep only allowlisted response headers, canonicalised and bounded.

    Values have control characters stripped and are truncated to
    :data:`MAX_HEADER_VALUE_LENGTH`, so a hostile server cannot bloat the
    ledger through an allowlisted header.
    """
    if not headers:
        return None
    filtered = {
        str(key).lower(): bound_string(value)
        for key, value in headers.items()
        if str(key).lower() in ALLOWLISTED_RESPONSE_HEADERS
    }
    return filtered or None


#: Maximum nesting depth walked while sanitising a retrieval-params snapshot.
_MAX_PARAM_DEPTH = 25


def _sanitize_retrieval_params(params: dict) -> tuple[dict, list[str]]:
    """Recursively drop secret-like keys and redact URL-embedded secrets.

    Walks nested dicts/lists/sets (bounded depth) so a secret hidden inside a
    nested request body cannot survive into the ledger. Returns the safe
    snapshot plus the names of everything redacted, so redaction is auditable
    from the ledger alone.
    """
    redacted_names: list[str] = []

    def scrub(obj, depth: int):
        if depth > _MAX_PARAM_DEPTH:
            return "<truncated>"
        if isinstance(obj, dict):
            out: dict = {}
            for key, value in obj.items():
                key_str = str(key)
                if is_sensitive_key(key_str):
                    redacted_names.append(key_str)
                    continue
                if key_str in ("url", "export_url") and isinstance(value, str):
                    redacted_value, url_names = redact_url(value)
                    redacted_names.extend(url_names)
                    out[key] = redacted_value
                else:
                    out[key] = scrub(value, depth + 1)
            return out
        if isinstance(obj, (list, tuple, set)):
            return [scrub(item, depth + 1) for item in obj]
        if isinstance(obj, str):
            return strip_control_chars(obj)
        return obj

    sanitized = scrub(dict(params), 0)
    return sanitized, sorted(set(redacted_names))


def _sanitize_error(exc: BaseException) -> str:
    """Render an exception without leaking URL/userinfo/query secrets.

    ``requests`` embeds the full URL in ``HTTPError``/``ConnectionError``/
    ``InvalidURL`` messages; the rendered string is passed through
    :func:`redact_text` before it can reach the ledger or a raised error.
    """
    raw = f"{type(exc).__name__}: {exc}"
    sanitized, _names = redact_text(raw)
    return sanitized or type(exc).__name__


def _extract_download_url(source: SourceConfig, params: dict) -> str:
    if source.require_bounded_scope:
        url = params.get("export_url")
        if not url:
            raise InvalidRetrievalRequestError(
                f"source {source.name!r} requires the preflight-verified 'export_url' "
                "in retrieval_params (phase 2.3: do not assume an endpoint)"
            )
        return url
    url = params.get("url")
    if not url:
        raise InvalidRetrievalRequestError(
            f"no download url supplied and source {source.name!r} has no verified, "
            "hardcoded endpoint; pass retrieval_params['url']"
        )
    return url


def _download_extension(params: dict) -> str:
    extension = params.get("extension")
    if isinstance(extension, str) and extension:
        return extension if extension.startswith(".") else f".{extension}"
    return ".bin"


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------

def load_acquisition_manifest(path: Path | None = None) -> AcquisitionManifest:
    """Load (or create an empty) acquisition ledger at ``path``/settings default."""
    target = Path(path) if path is not None else settings.ACQUISITION_MANIFEST
    if not target.exists():
        return AcquisitionManifest(
            generated_at_utc=utcnow_aware(),
            notes=["Ledger initialised empty; no acquisition attempted."],
        )
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
        return AcquisitionManifest.model_validate(raw)
    except Exception as exc:
        raise ManifestError(f"acquisition manifest invalid at {target}: {exc}") from exc


def save_acquisition_manifest(manifest: AcquisitionManifest, path: Path | None = None) -> None:
    """Atomically write the ledger (metadata only; raw bytes stay elsewhere)."""
    target = Path(path) if path is not None else settings.ACQUISITION_MANIFEST
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f"{target.name}.", suffix=".part", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            # exclude_none: additive evidence fields stay absent on legacy/new
            # records rather than emitting a wall of nulls. Loads back identically.
            fh.write(manifest.model_dump_json(indent=2, exclude_none=True) + "\n")
        os.replace(tmp_name, target)
    except BaseException:
        try:
            os.remove(tmp_name)
        except FileNotFoundError:
            pass
        raise


def count_by_kind(manifest: AcquisitionManifest) -> dict[str, int]:
    """Counts of ledger records per kind ("DEMO"/"REAL")."""
    counts = {"DEMO": 0, "REAL": 0}
    for record in manifest.records:
        counts[record.kind] = counts.get(record.kind, 0) + 1
    return counts


def acquired_real_count(manifest: AcquisitionManifest) -> int:
    """Number of REAL artifacts actually kept (downloaded or confirmed existing)."""
    kept = (AcquisitionStatus.DOWNLOADED, AcquisitionStatus.SKIPPED_EXISTING)
    return sum(
        1 for record in manifest.records if record.kind == "REAL" and record.status in kept
    )


def _persist_record(manifest: AcquisitionManifest, record: AcquisitionRecord, path: Path) -> None:
    manifest.records.append(record)
    save_acquisition_manifest(manifest, path)


def _make_record(
    source: SourceConfig,
    *,
    acquisition_key: str,
    params: dict,
    status: AcquisitionStatus,
    retrieved_utc: datetime,
    sha256: str | None = None,
    file_size_bytes: int | None = None,
    storage_path: str | None = None,
    error: str | None = None,
    source_record_id: str | None = None,
    product_version: str | None = None,
    observation_start_utc: datetime | None = None,
    observation_end_utc: datetime | None = None,
    available_utc: datetime | None = None,
    request_url: str | None = None,
    request_method: str | None = None,
    http_status: int | None = None,
    response_headers: dict | None = None,
    final_url: str | None = None,
    redirect_chain: list | None = None,
    provider_metadata: dict | None = None,
    availability_classification: str | None = None,
    availability_source: str | None = None,
    availability_derivation: str | None = None,
    redacted_params: list[str] | None = None,
) -> AcquisitionRecord:
    version = product_version or source.product_version
    params_snapshot, param_redactions = _sanitize_retrieval_params(dict(params))
    combined_redactions = sorted(set((redacted_params or []) + param_redactions)) or None
    return AcquisitionRecord(
        record_id=f"{source.kind}-{source.name}-{_slug(version)}-{_slug(acquisition_key)}",
        source=source.name,
        product=source.product,
        product_version=version,
        kind=source.kind,
        status=status,
        access_reference=source.access_reference,
        source_record_id=source_record_id,
        retrieval_params=params_snapshot,
        retrieved_utc=retrieved_utc,
        acquired_utc=utcnow_aware(),
        observation_start_utc=observation_start_utc,
        observation_end_utc=observation_end_utc,
        available_utc=available_utc,
        geographic_coverage=source.geographic_coverage,
        crs=source.crs,
        license_attribution=source.license_attribution,
        sha256=sha256,
        file_size_bytes=file_size_bytes,
        storage_path=storage_path,
        known_limitations=list(source.known_limitations),
        error=error,
        request_url=request_url,
        request_method=request_method,
        http_status=http_status,
        response_headers=response_headers,
        final_url=final_url,
        redirect_chain=redirect_chain,
        provider_metadata=provider_metadata,
        availability_classification=availability_classification,
        availability_source=availability_source,
        availability_derivation=availability_derivation,
        redacted_params=combined_redactions,
    )


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

class AcquisitionDriver:
    """Guarded acquisition of one source into immutable storage + the ledger."""

    def __init__(
        self,
        source: str | SourceConfig,
        *,
        raw_root: Path | None = None,
        manifest_path: Path | None = None,
        transport: AcquisitionTransport | None = None,
    ):
        name = source.name if isinstance(source, SourceConfig) else source
        self.source = get_source_config(name)
        self.raw_root = Path(raw_root) if raw_root is not None else settings.RAW_REAL_DIR
        self.manifest_path = (
            Path(manifest_path) if manifest_path is not None else settings.ACQUISITION_MANIFEST
        )
        self.transport = transport if transport is not None else AcquisitionTransport()

    # -- Preflight ----------------------------------------------------------
    def preflight(self) -> PreflightReport:
        """Run the source's preflight checks (connectivity/metadata inspection).

        For sources with a verified ``endpoint_base`` (COOLR) this inspects the
        live FeatureServer schema and record counts. For config-only sources it
        returns an honest report that no live endpoint is hardcoded (per the
        Phase 2.3 rule); endpoints must be verified at acquisition time.
        """
        source = self.source
        if source.endpoint_base:
            try:
                return self._coolr_preflight(source)
            except Exception as exc:  # a preflight failure is reported, not raised
                return PreflightReport(
                    source=source.name,
                    ok=False,
                    retrieved_utc=utcnow_aware(),
                    message=f"{type(exc).__name__}: {exc}",
                    details={"endpoint_base": source.endpoint_base},
                )
        return PreflightReport(
            source=source.name,
            ok=True,
            retrieved_utc=utcnow_aware(),
            message=(
                "config-only source: no live endpoint hardcoded (Phase 2.3 rule); "
                "verify endpoints at acquisition time"
            ),
            details={
                "authentication": source.authentication.value,
                "access_reference": source.access_reference,
            },
        )

    def _coolr_preflight(self, source: SourceConfig) -> PreflightReport:
        """COOLR pre-acquisition checklist (schema, counts, date range)."""
        base = source.endpoint_base
        layer_id = 0
        lon_min, lat_min, lon_max, lat_max = NE_NORTHEAST_INDIA_CORNERS

        layers = self.transport.get_json(f"{base}/layers?f=pjson")
        layer_names = [layer.get("name") for layer in layers.get("layers", [])]

        schema = self.transport.get_json(f"{base}/{layer_id}?f=pjson")
        schema_fields = sorted(
            field.get("name", "") for field in schema.get("fields", []) if field.get("name")
        )

        count_payload = self.transport.get_json(
            f"{base}/{layer_id}/query?geometry={lon_min},{lat_min},{lon_max},{lat_max}"
            "&geometryType=esriGeometryEnvelope&inSR=4326&where=1%3D1&returnCountOnly=true&f=pjson"
        )
        ne_india_record_count = count_payload.get("count")

        stats_payload = self.transport.get_json(
            f"{base}/{layer_id}/query?where=1%3D1&returnStatistics=true"
            "&statisticType=min&statisticType=max&onStatisticField=event_date"
            "&onStatisticField=event_date&f=pjson"
        )
        statistics = stats_payload.get("statistics") or []
        date_bounds = {
            stat.get("statisticType"): stat.get("value")
            for stat in statistics
            if stat.get("onStatisticField") == "event_date"
        }

        required_fields = [
            "event_id",
            "event_date",
            "event_time",
            "latitude",
            "longitude",
            "location_accuracy",
        ]
        missing_fields = [field for field in required_fields if field not in schema_fields]
        ok = ne_india_record_count is not None and not missing_fields
        if ok:
            message = (
                f"preflight OK: {len(layer_names)} layer(s), "
                f"{ne_india_record_count} NE-India events, required schema fields present"
            )
        else:
            message = (
                f"preflight incomplete: missing schema fields={missing_fields or 'none'}, "
                f"ne_india_count={ne_india_record_count!r}"
            )
        return PreflightReport(
            source=source.name,
            ok=ok,
            retrieved_utc=utcnow_aware(),
            message=message,
            details={
                "endpoint_base": base,
                "layer_names": layer_names,
                "schema_fields": schema_fields,
                "ne_bbox": {
                    "xmin": lon_min,
                    "ymin": lat_min,
                    "xmax": lon_max,
                    "ymax": lat_max,
                },
                "ne_india_record_count": ne_india_record_count,
                "event_date_min": date_bounds.get("min"),
                "event_date_max": date_bounds.get("max"),
                "export_endpoint_verified": ok,
                "event_id_field": "event_id" if "event_id" in schema_fields else None,
                "event_time_field": "event_time" if "event_time" in schema_fields else None,
                "location_accuracy_field": (
                    "location_accuracy" if "location_accuracy" in schema_fields else None
                ),
            },
        )

    # -- Acquisition --------------------------------------------------------
    def acquire(
        self,
        *,
        retrieval_params: dict | None = None,
        expected_sha256: str | None = None,
        acquisition_key: str | None = None,
        product_version: str | None = None,
        source_record_id: str | None = None,
        observation_start_utc: datetime | None = None,
        observation_end_utc: datetime | None = None,
        available_utc: datetime | None = None,
        availability_classification: str | None = "unknown",
        availability_source: str | None = None,
        availability_derivation: str | None = None,
        provider_metadata: dict | None = None,
    ) -> AcquisitionRecord:
        """Fetch one artifact into immutable storage and record it in the ledger.

        HTTP evidence (request URL/method, final status, allowlisted headers and
        redirect chain) is captured for every attempt. ``availability_*`` are
        caller/rule-supplied and never auto-derived from headers, so a captured
        ``Last-Modified`` is evidence, not a claim of provider publication time.

        Raises
        ------
        CredentialsMissingError  - credentialed source with absent credentials
                                   (no network is touched; loud config failure).
        InvalidRetrievalRequestError - no verified download URL / missing scope.
        DuplicateArtifactError   - the computed target path already exists.
        ChecksumMismatchError    - bytes did not match expected_sha256 (recorded).
        AcquisitionError         - the fetch itself failed (recorded as failed).
        """
        source = self.source

        # 1. Config gates, before any network call.
        resolve_credentials(source)
        params = dict(retrieval_params or {})
        if source.require_bounded_scope and not params.get("bbox"):
            raise AcquisitionError(
                f"source {source.name!r} requires a bounded geographic scope; pass "
                "retrieval_params['bbox'] (never download the global inventory by default)"
            )
        url = _extract_download_url(source, params)
        request_url, request_redactions = redact_url(url)

        acquisition_key = acquisition_key or utcnow_aware().strftime("%Y%m%dT%H%M%SZ")
        extension = _download_extension(params)
        relative_path = storage_relative_path(source, acquisition_key, extension)
        target = self.raw_root / relative_path

        # 2. Immutability: never overwrite an existing artifact.
        if target.exists():
            raise DuplicateArtifactError(
                f"artifact already exists and will never be overwritten: {target}"
            )

        manifest = load_acquisition_manifest(self.manifest_path)
        retrieved_utc = utcnow_aware()

        # 3. Fetch (capturing evidence; a failed attempt is recorded honestly).
        try:
            result = self.transport.fetch(url, headers={}, timeout=120)
        except Exception as exc:
            response = getattr(exc, "response", None)
            error = _sanitize_error(exc)
            record = _make_record(
                source,
                acquisition_key=acquisition_key,
                params=params,
                status=AcquisitionStatus.FAILED,
                retrieved_utc=retrieved_utc,
                error=error,
                source_record_id=source_record_id,
                product_version=product_version,
                observation_start_utc=observation_start_utc,
                observation_end_utc=observation_end_utc,
                available_utc=available_utc,
                request_url=request_url,
                request_method="GET",
                http_status=getattr(response, "status_code", None),
                response_headers=(
                    _allowlisted_headers(dict(getattr(response, "headers", {}) or {}))
                    if response is not None
                    else None
                ),
                provider_metadata=provider_metadata,
                availability_classification="unknown",
                availability_source=availability_source,
                availability_derivation=availability_derivation,
                redacted_params=request_redactions,
            )
            _persist_record(manifest, record, self.manifest_path)
            raise AcquisitionError(f"{source.name}: {error}") from exc

        # Evidence captured from the final response (headers/status describe the
        # final resource after any redirect).
        data = result.content
        final_url, final_redactions = redact_url(result.final_url)
        redirect_chain, chain_redactions = _redact_chain(result.redirect_chain)
        combined_redactions = sorted(
            set(request_redactions + final_redactions + chain_redactions)
        ) or None
        evidence = dict(
            request_url=request_url,
            request_method="GET",
            http_status=result.status_code,
            response_headers=_allowlisted_headers(result.headers),
            final_url=final_url,
            redirect_chain=redirect_chain or None,
            provider_metadata=provider_metadata,
            availability_classification=availability_classification,
            availability_source=availability_source,
            availability_derivation=availability_derivation,
            redacted_params=combined_redactions,
        )

        # 4. Checksum.
        actual_sha256 = hashlib.sha256(data).hexdigest()
        if expected_sha256 and expected_sha256.lower() != actual_sha256:
            error = f"checksum mismatch: expected {expected_sha256}, got {actual_sha256}"
            record = _make_record(
                source,
                acquisition_key=acquisition_key,
                params=params,
                status=AcquisitionStatus.CHECKSUM_MISMATCH,
                retrieved_utc=retrieved_utc,
                sha256=actual_sha256,
                error=error,
                source_record_id=source_record_id,
                product_version=product_version,
                observation_start_utc=observation_start_utc,
                observation_end_utc=observation_end_utc,
                available_utc=available_utc,
                **evidence,
            )
            _persist_record(manifest, record, self.manifest_path)
            raise ChecksumMismatchError(f"{source.name}: {error}")

        # 5. Content dedupe: identical bytes already kept -> skipped_existing.
        kept = (AcquisitionStatus.DOWNLOADED, AcquisitionStatus.SKIPPED_EXISTING)
        existing = [
            record
            for record in manifest.records
            if record.kind == source.kind
            and record.source == source.name
            and record.status in kept
            and record.sha256 == actual_sha256
        ]
        if existing:
            record = _make_record(
                source,
                acquisition_key=acquisition_key,
                params=params,
                status=AcquisitionStatus.SKIPPED_EXISTING,
                retrieved_utc=retrieved_utc,
                sha256=actual_sha256,
                file_size_bytes=len(data),
                storage_path=existing[0].storage_path,
                source_record_id=source_record_id,
                product_version=product_version,
                observation_start_utc=observation_start_utc,
                observation_end_utc=observation_end_utc,
                available_utc=available_utc,
                **evidence,
            )
            _persist_record(manifest, record, self.manifest_path)
            return record

        # 6. Store immutably.
        _atomic_write(target, data)
        record = _make_record(
            source,
            acquisition_key=acquisition_key,
            params=params,
            status=AcquisitionStatus.DOWNLOADED,
            retrieved_utc=retrieved_utc,
            sha256=actual_sha256,
            file_size_bytes=len(data),
            storage_path=relative_path,
            source_record_id=source_record_id,
            product_version=product_version,
            observation_start_utc=observation_start_utc,
            observation_end_utc=observation_end_utc,
            available_utc=available_utc,
            **evidence,
        )
        _persist_record(manifest, record, self.manifest_path)
        return record

    # -- CDS acquisition -----------------------------------------------------
    def acquire_cds(
        self,
        *,
        dataset: str,
        inputs: dict,
        acquisition_key: str | None = None,
        source_record_id: str | None = None,
        observation_start_utc: datetime | None = None,
        observation_end_utc: datetime | None = None,
        available_utc: datetime | None = None,
        expected_sha256: str | None = None,
        cds: cds_client.CdsTransport | None = None,
    ) -> AcquisitionRecord:
        """Acquire one artifact through the CDS async job flow into the ledger.

        Mirrors :meth:`acquire` (credential gate, immutable storage, SHA-256
        dedupe, honest failure records) but drives the real CDS two-phase API:
        submit execution -> poll -> download the result reference. The access
        token is read through :func:`resolve_credentials` and kept in memory
        only; the request snapshot stored in the ledger never contains it.

        Raises the same contract exceptions as :meth:`acquire`; a failed job or
        timed-out submission is recorded as ``failed`` before raising
        :class:`AcquisitionError`.
        """
        source = self.source
        if source.authentication is not AuthenticationMethod.CDS_API:
            raise AcquisitionError(
                f"source {source.name!r} is not a CDS API source; acquire_cds "
                "requires authentication=cds-api"
            )
        creds = resolve_credentials(source)
        transport = cds or cds_client.CdsTransport(
            api_url=creds["CDS_API_URL"],
            api_key=creds["CDS_API_KEY"],
        )

        if not isinstance(inputs, dict) or not inputs:
            raise InvalidRetrievalRequestError(
                f"source {source.name!r}: CDS acquisition requires a non-empty inputs dict"
            )
        params = {"dataset": dataset, "inputs": dict(inputs)}
        acquisition_key = acquisition_key or utcnow_aware().strftime("%Y%m%dT%H%M%SZ")
        manifest = load_acquisition_manifest(self.manifest_path)
        retrieved_utc = utcnow_aware()

        def fail(
            kind: AcquisitionStatus,
            *,
            error: str,
            sha: str | None = None,
            rec_id: str | None = None,
            evidence: dict | None = None,
        ):
            record = _make_record(
                source,
                acquisition_key=acquisition_key,
                params=params,
                status=kind,
                retrieved_utc=retrieved_utc,
                sha256=sha,
                error=error,
                source_record_id=rec_id,
                observation_start_utc=observation_start_utc,
                observation_end_utc=observation_end_utc,
                available_utc=available_utc,
                **(evidence or {}),
            )
            _persist_record(manifest, record, self.manifest_path)
            return record

        # 1. Submit the execution.
        try:
            job_id = transport.submit(dataset, dict(inputs))
        except Exception as exc:
            error = _sanitize_error(exc)
            fail(AcquisitionStatus.FAILED, error=error, rec_id=source_record_id)
            raise AcquisitionError(f"{source.name}: {error}") from exc

        # 2. Poll until the job finishes (or the waiting budget is exhausted).
        try:
            _status, _message = transport.wait_for_success(job_id)
        except Exception as exc:
            error = _sanitize_error(exc)
            fail(AcquisitionStatus.FAILED, error=error, rec_id=job_id)
            raise AcquisitionError(f"{source.name}: {error}") from exc

        # 3. Read the result assets.
        try:
            assets = transport.results(job_id)
        except Exception as exc:
            error = _sanitize_error(exc)
            fail(AcquisitionStatus.FAILED, error=error, rec_id=job_id)
            raise AcquisitionError(f"{source.name}: {error}") from exc
        if not assets or not isinstance(assets[0].get("href"), str):
            error = f"CDS job {job_id} succeeded but returned no downloadable asset"
            fail(AcquisitionStatus.FAILED, error=error, rec_id=job_id)
            raise AcquisitionError(f"{source.name}: {error}")

        asset = assets[0]
        extension = cds_client.asset_extension(asset)
        relative_path = storage_relative_path(source, acquisition_key, extension)
        target = self.raw_root / relative_path
        if target.exists():
            raise DuplicateArtifactError(
                f"artifact already exists and will never be overwritten: {target}"
            )

        # 4. Download the bytes (capturing artifact-response HTTP evidence).
        retrieved_utc = utcnow_aware()
        request_url, request_redactions = redact_url(asset["href"])
        try:
            result = transport.download_with_evidence(asset["href"])
        except Exception as exc:
            error = _sanitize_error(exc)
            response = getattr(exc, "response", None)
            # Evidence stays optional on failure: the redacted target URL and
            # method are always known, but status/headers are recorded only if a
            # real response object is attached. Never fabricate them.
            failure_evidence: dict = {"request_url": request_url, "request_method": "GET"}
            if response is not None:
                failure_evidence["http_status"] = getattr(response, "status_code", None)
                failure_headers = _allowlisted_headers(
                    dict(getattr(response, "headers", {}) or {})
                )
                if failure_headers:
                    failure_evidence["response_headers"] = failure_headers
            fail(
                AcquisitionStatus.FAILED,
                error=error,
                rec_id=job_id,
                evidence=failure_evidence,
            )
            raise AcquisitionError(f"{source.name}: {error}") from exc

        data = result.content
        final_url, final_redactions = redact_url(result.final_url)
        redirect_chain, chain_redactions = _redact_chain(result.redirect_chain)
        combined_redactions = sorted(
            set(request_redactions + final_redactions + chain_redactions)
        ) or None
        provider_metadata = {"dataset": dataset, "job_id": job_id}
        asset_type = asset.get("type")
        if isinstance(asset_type, str) and asset_type:
            provider_metadata["asset_type"] = asset_type
        evidence = dict(
            request_url=request_url,
            request_method="GET",
            http_status=result.status_code,
            response_headers=_allowlisted_headers(result.headers),
            final_url=final_url,
            redirect_chain=redirect_chain or None,
            provider_metadata=provider_metadata,
            redacted_params=combined_redactions,
        )

        # 5. Checksum (caller's value wins; otherwise the provider-declared one).
        actual_sha256 = hashlib.sha256(data).hexdigest()
        expected = expected_sha256 or cds_client.provider_sha256(asset)
        if expected and expected.lower() != actual_sha256:
            error = f"checksum mismatch: expected {expected}, got {actual_sha256}"
            fail(AcquisitionStatus.CHECKSUM_MISMATCH, error=error, sha=actual_sha256, rec_id=job_id)
            raise ChecksumMismatchError(f"{source.name}: {error}")

        # 6. Content dedupe: identical bytes already kept -> skipped_existing.
        kept = (AcquisitionStatus.DOWNLOADED, AcquisitionStatus.SKIPPED_EXISTING)
        existing = [
            record
            for record in manifest.records
            if record.kind == source.kind
            and record.source == source.name
            and record.status in kept
            and record.sha256 == actual_sha256
        ]
        if existing:
            record = _make_record(
                source,
                acquisition_key=acquisition_key,
                params=params,
                status=AcquisitionStatus.SKIPPED_EXISTING,
                retrieved_utc=retrieved_utc,
                sha256=actual_sha256,
                file_size_bytes=len(data),
                storage_path=existing[0].storage_path,
                source_record_id=job_id,
                observation_start_utc=observation_start_utc,
                observation_end_utc=observation_end_utc,
                available_utc=available_utc,
                **evidence,
            )
            _persist_record(manifest, record, self.manifest_path)
            return record

        # 7. Store immutably.
        _atomic_write(target, data)
        record = _make_record(
            source,
            acquisition_key=acquisition_key,
            params=params,
            status=AcquisitionStatus.DOWNLOADED,
            retrieved_utc=retrieved_utc,
            sha256=actual_sha256,
            file_size_bytes=len(data),
            storage_path=relative_path,
            source_record_id=job_id,
            observation_start_utc=observation_start_utc,
            observation_end_utc=observation_end_utc,
            available_utc=available_utc,
            **evidence,
        )
        _persist_record(manifest, record, self.manifest_path)
        return record