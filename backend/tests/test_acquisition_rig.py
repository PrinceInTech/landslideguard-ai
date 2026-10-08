"""Acquisition rig tests (Phase 3.2).

Covers the approved source registry, credential gating, checksum calculation,
immutable/duplicated-artifact protection, metadata/provenance generation,
DEMO/REAL separation, raw-file ignore rules, honest failure recording, and the
COOLR preflight checklist. Provider responses are mocked -- unit tests never
touch the network.
"""
import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.acquisition import (
    AcquisitionManifest,
    AcquisitionRecord,
    AcquisitionStatus,
    PreflightReport,
    SourceConfig,
)
from app.services.acquisition import (
    NE_NORTHEAST_INDIA_CORNERS,
    SOURCE_REGISTRY,
    AcquisitionDriver,
    AcquisitionError,
    ChecksumMismatchError,
    CredentialsMissingError,
    DuplicateArtifactError,
    InvalidRetrievalRequestError,
    UnsupportedSourceError,
    acquired_real_count,
    count_by_kind,
    get_source_config,
    load_acquisition_manifest,
    resolve_credentials,
    save_acquisition_manifest,
    validate_source_configs,
)
from app.services.provenance import sha256_of

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
UTC = timezone.utc

APPROVED_SOURCES = {
    "nasa-coolr",
    "nasa-imerg-early",
    "chirps",
    "era5-land",
    "srtmgl1-v003",
    "esa-worldcover",
    "soilgrids",
    "hydrosheds",
}


def _utc(y, m, d, hh=0, mm=0, ss=0):
    return datetime(y, m, d, hh, mm, ss, tzinfo=UTC)


class FakeTransport:
    """Deterministic stand-in for AcquisitionTransport; no network."""

    def __init__(self, bytes_map=None, json_map=None, error=None):
        self.bytes_map = bytes_map or {}
        self.json_map = json_map or {}
        self.error = error
        self.get_bytes_calls = []
        self.get_json_calls = []

    def get_bytes(self, url, headers=None, timeout=120):
        self.get_bytes_calls.append(url)
        if self.error:
            raise self.error
        try:
            return self.bytes_map[url]
        except KeyError as exc:
            raise RuntimeError(f"no byte fixture for {url}") from exc

    def get_json(self, url, headers=None, timeout=60):
        self.get_json_calls.append(url)
        if self.error:
            raise self.error
        try:
            return self.json_map[url]
        except KeyError as exc:
            raise RuntimeError(f"no json fixture for {url}") from exc


# ---------------------------------------------------------------------------
# Registry / source configuration
# ---------------------------------------------------------------------------


def test_registry_has_exactly_the_approved_sources():
    assert {source.name for source in SOURCE_REGISTRY} == APPROVED_SOURCES


def test_registry_configs_validate():
    for source in SOURCE_REGISTRY:
        SourceConfig.model_validate(source.model_dump())
    assert validate_source_configs() == []


def test_registry_configs_carry_required_metadata():
    for source in SOURCE_REGISTRY:
        assert source.access_reference
        assert source.license_attribution
        assert source.crs
        assert source.geographic_coverage is not None
        assert source.kind in ("DEMO", "REAL")
        assert source.kind == "REAL"
        assert source.tier in ("event", "rainfall", "weather-land-state", "static")


def test_unsupported_source_rejected():
    with pytest.raises(UnsupportedSourceError):
        get_source_config("totally-not-a-source")
    with pytest.raises(UnsupportedSourceError):
        AcquisitionDriver("totally-not-a-source")


def test_get_source_config_returns_registered_config():
    config = get_source_config("chirps")
    assert config.product_version == "v2.x"


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["nasa-imerg-early", "srtmgl1-v003", "era5-land"],
)
def test_credentialed_sources_fail_explicitly_without_credentials(name, monkeypatch):
    config = get_source_config(name)
    for var in config.credentials:
        monkeypatch.delenv(var, raising=False)
    driver = AcquisitionDriver(
        name,
        raw_root=Path("unused"),
        manifest_path=Path("unused"),
        transport=FakeTransport(bytes_map={"https://x": b"x"}),
    )
    with pytest.raises(CredentialsMissingError) as excinfo:
        driver.acquire(acquisition_key="k1", retrieval_params={"url": "https://x"})
    message = str(excinfo.value)
    assert config.name in message
    for var in config.credentials:
        assert var in message


def test_anonymous_sources_need_no_credentials(monkeypatch):
    for var in ("NASA_EARTHDATA_USERNAME", "NASA_EARTHDATA_PASSWORD", "CDS_API_URL", "CDS_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    for name in ("nasa-coolr", "chirps", "esa-worldcover", "soilgrids", "hydrosheds"):
        assert resolve_credentials(get_source_config(name)) == {}


# ---------------------------------------------------------------------------
# Checksums and immutable storage
# ---------------------------------------------------------------------------


def test_sha256_of_calculates_expected_digest(tmp_path):
    path = tmp_path / "sample.bin"
    data = b"landslideguard acquisition rig\n"
    path.write_bytes(data)
    assert sha256_of(path) == hashlib.sha256(data).hexdigest()
    assert len(sha256_of(path)) == 64


def test_successful_acquisition_records_full_provenance(tmp_path):
    raw = tmp_path / "raw"
    ledger = tmp_path / "acquisition.json"
    payload = b"chirps-p05-daily-sample"
    fake = FakeTransport(bytes_map={"https://chc.example/chirps.nc": payload})
    driver = AcquisitionDriver(
        "chirps", raw_root=raw, manifest_path=ledger, transport=fake
    )
    record = driver.acquire(
        acquisition_key="k1",
        retrieval_params={"url": "https://chc.example/chirps.nc", "extension": ".nc"},
        source_record_id="20261007",
        observation_start_utc=_utc(2026, 10, 7, 0, 0),
        observation_end_utc=_utc(2026, 10, 7, 23, 59),
        available_utc=_utc(2026, 10, 8, 0, 5),
    )
    assert record.status is AcquisitionStatus.DOWNLOADED
    assert record.kind == "REAL"
    assert record.source == "chirps"
    assert record.product_version == "v2.x"
    assert record.source_record_id == "20261007"
    assert record.sha256 == sha256_of(Path(raw) / record.storage_path)
    assert record.file_size_bytes == len(payload)
    assert record.storage_path.startswith("chirps/")
    assert record.retrieved_utc.tzinfo is not None
    assert record.acquired_utc.tzinfo is not None
    assert record.geographic_coverage is not None
    assert record.crs
    assert record.license_attribution
    assert record.access_reference
    stored = raw / record.storage_path
    assert stored.read_bytes() == payload

    manifest = load_acquisition_manifest(ledger)
    assert count_by_kind(manifest) == {"DEMO": 0, "REAL": 1}
    assert acquired_real_count(manifest) == 1


def test_expected_sha256_mismatch_is_recorded_and_raises(tmp_path):
    raw = tmp_path / "raw"
    ledger = tmp_path / "acquisition.json"
    payload = b"corrupted-or-wrong-bytes"
    fake = FakeTransport(bytes_map={"https://x/data": payload})
    driver = AcquisitionDriver(
        "chirps", raw_root=raw, manifest_path=ledger, transport=fake
    )
    with pytest.raises(ChecksumMismatchError):
        driver.acquire(
            acquisition_key="k1",
            retrieval_params={"url": "https://x/data"},
            expected_sha256="0" * 64,
        )
    manifest = load_acquisition_manifest(ledger)
    record = manifest.records[0]
    assert record.status is AcquisitionStatus.CHECKSUM_MISMATCH
    assert record.sha256 is not None
    assert "checksum mismatch" in record.error
    assert record.storage_path is None
    assert list(raw.rglob("*")) == [], "no artifact bytes may be kept on mismatch"


def test_existing_artifact_path_is_never_overwritten(tmp_path):
    raw = tmp_path / "raw"
    ledger = tmp_path / "acquisition.json"
    payload = b"same payload"
    fake = FakeTransport(bytes_map={"https://x/data": payload})
    driver = AcquisitionDriver(
        "chirps", raw_root=raw, manifest_path=ledger, transport=fake
    )
    first = driver.acquire(acquisition_key="k1", retrieval_params={"url": "https://x/data"})
    stored = raw / first.storage_path
    with pytest.raises(DuplicateArtifactError):
        driver.acquire(acquisition_key="k1", retrieval_params={"url": "https://x/data"})
    assert stored.read_bytes() == payload, "the existing artifact must be untouched"


def test_identical_content_is_deduplicated_as_skipped_existing(tmp_path):
    raw = tmp_path / "raw"
    ledger = tmp_path / "acquisition.json"
    payload = b"same bytes again"
    fake = FakeTransport(bytes_map={"https://x/data": payload})
    driver = AcquisitionDriver(
        "chirps", raw_root=raw, manifest_path=ledger, transport=fake
    )
    first = driver.acquire(acquisition_key="k1", retrieval_params={"url": "https://x/data"})
    second = driver.acquire(acquisition_key="k2", retrieval_params={"url": "https://x/data"})
    assert second.status is AcquisitionStatus.SKIPPED_EXISTING
    assert second.sha256 == first.sha256
    assert second.storage_path == first.storage_path
    files = [p for p in raw.rglob("*") if p.is_file()]
    assert len(files) == 1, "identical content must not create a second file"


def test_missing_download_url_rejected_for_config_only_source(tmp_path):
    fake = FakeTransport()
    driver = AcquisitionDriver("chirps", raw_root=tmp_path / "raw", manifest_path=tmp_path / "l.json", transport=fake)
    with pytest.raises(InvalidRetrievalRequestError):
        driver.acquire(acquisition_key="k1", retrieval_params={})
    assert fake.get_bytes_calls == [], "no network call may happen without a verified url"


# ---------------------------------------------------------------------------
# Failed acquisition must not fake success
# ---------------------------------------------------------------------------


def test_failed_acquisition_records_failure_honestly(tmp_path):
    raw = tmp_path / "raw"
    ledger = tmp_path / "acquisition.json"
    fake = FakeTransport(bytes_map={"https://x/data": b"never-delivered"}, error=RuntimeError("boom"))
    driver = AcquisitionDriver(
        "chirps", raw_root=raw, manifest_path=ledger, transport=fake
    )
    with pytest.raises(AcquisitionError) as excinfo:
        driver.acquire(acquisition_key="k1", retrieval_params={"url": "https://x/data"})
    assert "boom" in str(excinfo.value)
    manifest = load_acquisition_manifest(ledger)
    record = manifest.records[0]
    assert record.status is AcquisitionStatus.FAILED
    assert record.error and "boom" in record.error
    assert record.storage_path is None
    assert record.sha256 is None
    assert acquired_real_count(manifest) == 0
    assert list(raw.rglob("*")) == [], "a failed attempt must not leave artifact bytes"


def test_acquire_without_bbox_for_bounded_source_fails_without_network(tmp_path):
    raw = tmp_path / "raw"
    ledger = tmp_path / "acquisition.json"
    fake = FakeTransport(bytes_map={"https://export": b"x"})
    driver = AcquisitionDriver("nasa-coolr", raw_root=raw, manifest_path=ledger, transport=fake)
    with pytest.raises(AcquisitionError) as excinfo:
        driver.acquire(acquisition_key="k1", retrieval_params={"export_url": "https://export"})
    assert "bounded geographic scope" in str(excinfo.value)
    assert fake.get_bytes_calls == []


def test_bounded_coolr_acquisition_proceeds_with_export_url(tmp_path):
    raw = tmp_path / "raw"
    ledger = tmp_path / "acquisition.json"
    payload = b"coolr-ne-india-bounded-catalog"
    fake = FakeTransport(bytes_map={"https://export/coolr.csv": payload})
    driver = AcquisitionDriver("nasa-coolr", raw_root=raw, manifest_path=ledger, transport=fake)
    record = driver.acquire(
        acquisition_key="ne2026",
        retrieval_params={
            "bbox": list(NE_NORTHEAST_INDIA_CORNERS),
            "export_url": "https://export/coolr.csv",
        },
    )
    assert record.status is AcquisitionStatus.DOWNLOADED
    assert (raw / record.storage_path).read_bytes() == payload


# ---------------------------------------------------------------------------
# Metadata / provenance generation & schema rules
# ---------------------------------------------------------------------------


def _minimal_record(**overrides):
    values = {
        "record_id": "REAL-chirps-v2-x-k1",
        "source": "chirps",
        "product": "CHIRPS v2",
        "product_version": "v2.x",
        "kind": "REAL",
        "status": AcquisitionStatus.FAILED,
        "access_reference": "https://data.chc.ucsb.edu/products/CHIRPS-2.0/",
        "license_attribution": "public",
        "acquired_utc": _utc(2026, 10, 8, 5, 0),
    }
    values.update(overrides)
    return AcquisitionRecord(**values)


def test_acquisition_record_requires_kind():
    with pytest.raises(ValidationError):
        _minimal_record(kind="PROD")


def test_acquisition_record_rejects_naive_datetimes():
    with pytest.raises(ValidationError):
        _minimal_record(acquired_utc=datetime(2026, 10, 8, 5, 0))
    with pytest.raises(ValidationError):
        _minimal_record(
            status=AcquisitionStatus.DOWNLOADED,
            sha256="0" * 64,
            file_size_bytes=1,
            storage_path="chirps/x.bin",
            retrieved_utc=datetime(2026, 10, 8, 5, 0),
        )


def test_downloaded_record_requires_artifact_fields():
    with pytest.raises(ValidationError):
        _minimal_record(status=AcquisitionStatus.DOWNLOADED)


def test_failed_record_must_not_claim_storage():
    with pytest.raises(ValidationError):
        _minimal_record(
            status=AcquisitionStatus.FAILED,
            sha256="0" * 64,
            file_size_bytes=1,
            storage_path="chirps/x.bin",
        )


def test_manifest_roundtrip(tmp_path):
    manifest = AcquisitionManifest(
        generated_at_utc=_utc(2026, 10, 8, 5, 0),
        records=[_minimal_record()],
    )
    path = tmp_path / "roundtrip.json"
    save_acquisition_manifest(manifest, path)
    loaded = load_acquisition_manifest(path)
    assert loaded.model_dump() == manifest.model_dump()
    assert loaded.contract_version == "1.1.0"


# ---------------------------------------------------------------------------
# DEMO / REAL separation
# ---------------------------------------------------------------------------


def test_demo_kind_record_is_allowed_and_separated(tmp_path):
    demo = _minimal_record(kind="DEMO")
    assert demo.kind == "DEMO"
    real_downloaded = _minimal_record(
        kind="REAL",
        status=AcquisitionStatus.DOWNLOADED,
        sha256="0" * 64,
        file_size_bytes=3,
        storage_path="chirps/x.bin",
    )
    manifest = AcquisitionManifest(generated_at_utc=_utc(2026, 10, 8, 6, 0))
    manifest.records.append(demo)
    manifest.records.append(real_downloaded)
    assert count_by_kind(manifest) == {"DEMO": 1, "REAL": 1}
    assert acquired_real_count(manifest) == 1


def test_committed_manifest_has_zero_acquired_real_artifacts():
    path = PROJECT_ROOT / "data" / "provenance" / "acquisition_manifest.json"
    assert path.exists(), "acquisition ledger must be committed"
    manifest = load_acquisition_manifest(path)
    assert manifest.contract_version == "1.1.0"
    assert manifest.records == [], "adapters/configuration must not imply acquired data"
    assert acquired_real_count(manifest) == 0


# ---------------------------------------------------------------------------
# Raw files stay ignored
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path_in_repo",
    [
        "data/raw/real/nasa-imerg-early/imerg_sample.HDF5",
        "data/raw/real/srtmgl1-v003/N37W105.SRTMGL1.HGT",
        "data/raw/real/nasa-coolr/export.csv",
    ],
)
def test_raw_real_files_remain_git_ignored(path_in_repo):
    result = subprocess.run(
        ["git", "check-ignore", "-q", "--no-index", path_in_repo],
        cwd=PROJECT_ROOT,
        capture_output=True,
    )
    assert result.returncode == 0, f"{path_in_repo} should be git-ignored"


def test_real_directory_placeholder_itself_is_trackable():
    result = subprocess.run(
        ["git", "check-ignore", "-q", "--no-index", "data/raw/real/.gitkeep"],
        cwd=PROJECT_ROOT,
        capture_output=True,
    )
    assert result.returncode == 1, "data/raw/real/.gitkeep should NOT be ignored"


# ---------------------------------------------------------------------------
# COOLR preflight
# ---------------------------------------------------------------------------


def _coolr_urls():
    base = get_source_config("nasa-coolr").endpoint_base
    lon_min, lat_min, lon_max, lat_max = NE_NORTHEAST_INDIA_CORNERS
    return {
        "layers": f"{base}/layers?f=pjson",
        "schema": f"{base}/0?f=pjson",
        "count": (
            f"{base}/0/query?geometry={lon_min},{lat_min},{lon_max},{lat_max}"
            "&geometryType=esriGeometryEnvelope&inSR=4326&where=1%3D1&returnCountOnly=true&f=pjson"
        ),
        "stats": (
            f"{base}/0/query?where=1%3D1&returnStatistics=true&statisticType=min"
            "&statisticType=max&onStatisticField=event_date&onStatisticField=event_date&f=pjson"
        ),
    }


def test_coolr_preflight_inspects_schema_and_counts_events(tmp_path):
    urls = _coolr_urls()
    json_map = {
        urls["layers"]: {"layers": [{"id": 0, "name": "COOLR_Events_Points"}]},
        urls["schema"]: {
            "name": "COOLR_Events_Points",
            "fields": [
                {"name": "event_id", "type": "esriFieldTypeInteger"},
                {"name": "event_date", "type": "esriFieldTypeDate"},
                {"name": "event_time", "type": "esriFieldTypeString"},
                {"name": "latitude", "type": "esriFieldTypeDouble"},
                {"name": "longitude", "type": "esriFieldTypeDouble"},
                {"name": "location_accuracy", "type": "esriFieldTypeString"},
            ],
        },
        urls["count"]: {"count": 482},
        urls["stats"]: {
            "statistics": [
                {"statisticType": "min", "onStatisticField": "event_date", "value": 1750000000000},
                {"statisticType": "max", "onStatisticField": "event_date", "value": 1770000000000},
            ]
        },
    }
    fake = FakeTransport(json_map=json_map)
    report = AcquisitionDriver(
        "nasa-coolr", raw_root=tmp_path / "raw", manifest_path=tmp_path / "l.json", transport=fake
    ).preflight()
    assert isinstance(report, PreflightReport)
    assert report.ok is True
    assert report.retrieved_utc.tzinfo is not None
    assert report.details["ne_india_record_count"] == 482
    for field in ("event_id", "event_date", "event_time", "latitude", "longitude", "location_accuracy"):
        assert field in report.details["schema_fields"]
    assert report.details["event_date_min"] == 1750000000000
    assert report.details["event_date_max"] == 1770000000000
    assert report.details["export_endpoint_verified"] is True


def test_coolr_preflight_failure_is_reported_not_raised(tmp_path):
    fake = FakeTransport(error=RuntimeError("endpoint timeout"))
    report = AcquisitionDriver(
        "nasa-coolr", raw_root=tmp_path / "raw", manifest_path=tmp_path / "l.json", transport=fake
    ).preflight()
    assert report.ok is False
    assert "endpoint timeout" in report.message


def test_config_only_preflight_is_honest(tmp_path):
    report = AcquisitionDriver(
        "chirps", raw_root=tmp_path / "raw", manifest_path=tmp_path / "l.json", transport=FakeTransport()
    ).preflight()
    assert report.ok is True
    assert "no live endpoint hardcoded" in report.message


# ---------------------------------------------------------------------------
# Ledger integrity safety nets
# ---------------------------------------------------------------------------


def test_sensitive_retrieval_params_are_stripped_from_ledger(tmp_path):
    raw = tmp_path / "raw"
    ledger = tmp_path / "acquisition.json"
    payload = b"bytes"
    fake = FakeTransport(bytes_map={"https://x/data": payload})
    driver = AcquisitionDriver("chirps", raw_root=raw, manifest_path=ledger, transport=fake)
    driver.acquire(
        acquisition_key="k1",
        retrieval_params={"url": "https://x/data", "api_key": "supersecret", "token": "abc"},
    )
    manifest = load_acquisition_manifest(ledger)
    params = manifest.records[0].retrieval_params
    assert "url" in params
    assert "api_key" not in params and "token" not in params
    assert "supersecret" not in manifest.model_dump_json()