"""Acquisition rig tests (Phase 3.2).

Covers the approved source registry, credential gating, checksum calculation,
immutable/duplicated-artifact protection, metadata/provenance generation,
DEMO/REAL separation, raw-file ignore rules, honest failure recording, and the
COOLR preflight checklist. Provider responses are mocked -- unit tests never
touch the network.
"""
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests
from pydantic import ValidationError

from app.schemas.acquisition import (
    ALLOWLISTED_RESPONSE_HEADERS,
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
    FetchResult,
    InvalidRetrievalRequestError,
    UnsupportedSourceError,
    acquired_real_count,
    count_by_kind,
    get_source_config,
    load_acquisition_manifest,
    redact_url,
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
    """Deterministic stand-in for AcquisitionTransport; no network.

    ``fetch`` returns a :class:`FetchResult` so evidence capture is exercised
    exactly as the real transport would. ``get_bytes`` delegates to it, keeping
    the legacy call-tracking assertions meaningful.
    """

    def __init__(
        self,
        bytes_map=None,
        json_map=None,
        error=None,
        headers_map=None,
        final_url=None,
        redirect_chain=(),
    ):
        self.bytes_map = bytes_map or {}
        self.json_map = json_map or {}
        self.error = error
        self.headers_map = headers_map or {}
        self.final_url = final_url
        self.redirect_chain = tuple(redirect_chain)
        self.get_bytes_calls = []
        self.get_json_calls = []
        self.fetch_calls = []

    def fetch(self, url, headers=None, timeout=120):
        self.fetch_calls.append(url)
        self.get_bytes_calls.append(url)
        if self.error:
            raise self.error
        try:
            content = self.bytes_map[url]
        except KeyError as exc:
            raise RuntimeError(f"no byte fixture for {url}") from exc
        return FetchResult(
            content=content,
            status_code=200,
            headers=dict(self.headers_map.get(url, {})),
            final_url=self.final_url or url,
            redirect_chain=self.redirect_chain,
        )

    def get_bytes(self, url, headers=None, timeout=120):
        return self.fetch(url, headers, timeout).content

    def get_json(self, url, headers=None, timeout=60):
        self.get_json_calls.append(url)
        if self.error:
            raise self.error
        try:
            return self.json_map[url]
        except KeyError as exc:
            raise RuntimeError(f"no json fixture for {url}") from exc


class _FakeResponse:
    """Minimal stand-in for ``requests.Response`` for transport unit tests."""

    def __init__(self, content=b"", status_code=200, headers=None, url="https://x", history=()):
        self.content = content
        self.status_code = status_code
        self.headers = headers or {}
        self.url = url
        self.history = list(history)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}", response=self)


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


def test_committed_manifest_reflects_acquired_real_artifacts():
    path = PROJECT_ROOT / "data" / "provenance" / "acquisition_manifest.json"
    assert path.exists(), "acquisition ledger must be committed"
    manifest = load_acquisition_manifest(path)
    assert manifest.contract_version == "1.1.0"
    kept_statuses = (AcquisitionStatus.DOWNLOADED, AcquisitionStatus.SKIPPED_EXISTING)
    expected = {
        "REAL-chirps-v2.0-2026-08-31",
        "REAL-era5-land-operational-consolidated-2-months-era5-land-t-5-days-2026-07-15t0000",
    }
    actual = {
        record.record_id
        for record in manifest.records
        if record.kind == "REAL" and record.status in kept_statuses
    }
    assert actual == expected, "committed ledger must reflect exactly the acquired artifacts"
    for record in manifest.records:
        if record.kind != "REAL":
            continue
        if record.status in kept_statuses:
            assert record.status == AcquisitionStatus.DOWNLOADED
            assert record.storage_path
            raw_file = PROJECT_ROOT / "data" / "raw" / "real" / record.storage_path
            if raw_file.is_file():
                assert raw_file.stat().st_size == record.file_size_bytes
        else:
            assert record.storage_path is None, "a non-acquired record must not claim a storage_path"
            assert record.error, "an honest failure must carry an error message"
    assert acquired_real_count(manifest) == 2


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


# ---------------------------------------------------------------------------
# Acquisition evidence capture (Phase 3.7.3B.3)
# ---------------------------------------------------------------------------


def _chirps_driver(tmp_path, fake):
    return AcquisitionDriver(
        "chirps",
        raw_root=tmp_path / "raw",
        manifest_path=tmp_path / "acquisition.json",
        transport=fake,
    )


def test_fetch_captures_allowlisted_headers_only(tmp_path):
    url = "https://chc.example/data.nc"
    fake = FakeTransport(
        bytes_map={url: b"payload"},
        headers_map={
            url: {
                "Last-Modified": "Wed, 02 Sep 2026 00:00:00 GMT",
                "ETag": '"abc123"',
                "Date": "Fri, 11 Sep 2026 21:10:59 GMT",
                "Set-Cookie": "session=topsecret",
                "Authorization": "Bearer topsecret",
                "X-Amz-Signature": "deadbeef",
            }
        },
    )
    driver = _chirps_driver(tmp_path, fake)
    record = driver.acquire(acquisition_key="k1", retrieval_params={"url": url})

    assert record.http_status == 200
    assert record.request_method == "GET"
    assert record.request_url == url
    assert record.final_url == url
    assert record.redirect_chain is None
    assert record.response_headers == {
        "last-modified": "Wed, 02 Sep 2026 00:00:00 GMT",
        "etag": '"abc123"',
        "date": "Fri, 11 Sep 2026 21:10:59 GMT",
    }
    assert set(record.response_headers) <= set(ALLOWLISTED_RESPONSE_HEADERS)

    blob = (tmp_path / "acquisition.json").read_text(encoding="utf-8")
    assert "topsecret" not in blob
    assert "deadbeef" not in blob
    assert "cookie" not in blob.lower()
    assert "authorization" not in blob.lower()


def test_content_length_header_captured_when_provided(tmp_path):
    """3.7.5B: Content-Length is allowlisted evidence (byte-count cross-check).

    Synthetic fixture: the fake provider sends Content-Length on the final
    response; the rig keeps it under the allowlisted ``content-length`` key
    alongside the other non-secret response evidence.
    """
    url = "https://chc.example/data.nc"
    payload = b"payload-bytes"
    fake = FakeTransport(
        bytes_map={url: payload},
        headers_map={url: {"Content-Length": str(len(payload)), "ETag": '"abc"'}},
    )
    driver = _chirps_driver(tmp_path, fake)
    record = driver.acquire(acquisition_key="k1", retrieval_params={"url": url})

    assert record.response_headers == {
        "content-length": str(len(payload)),
        "etag": '"abc"',
    }
    assert record.file_size_bytes == len(payload)
    assert record.available_utc is None
    assert record.availability_classification == "unknown"


def test_http_headers_never_become_availability_time(tmp_path):
    """3.7.5B: Date/Last-Modified/Content-Length are evidence, never available_utc.

    The value of ``available_utc`` must always come from an explicit caller/rule
    classification, never from wire headers. Captured headers stay in
    ``response_headers`` and leave ``availability_*`` unset.
    """
    url = "https://chc.example/data.nc"
    fake = FakeTransport(
        bytes_map={url: b"payload"},
        headers_map={
            url: {
                "Content-Length": "7",
                "Last-Modified": "Wed, 02 Sep 2026 00:00:00 GMT",
                "Date": "Fri, 11 Sep 2026 21:10:59 GMT",
            }
        },
    )
    driver = _chirps_driver(tmp_path, fake)
    record = driver.acquire(acquisition_key="k1", retrieval_params={"url": url})

    assert record.response_headers["date"] == "Fri, 11 Sep 2026 21:10:59 GMT"
    assert record.response_headers["last-modified"] == "Wed, 02 Sep 2026 00:00:00 GMT"
    assert record.response_headers["content-length"] == "7"
    assert record.available_utc is None
    assert record.availability_classification == "unknown"
    assert record.availability_source is None and record.availability_derivation is None


def test_provider_omitted_availability_headers_stay_unknown(tmp_path):
    url = "https://chc.example/data.nc"
    fake = FakeTransport(bytes_map={url: b"payload"})
    driver = _chirps_driver(tmp_path, fake)
    record = driver.acquire(acquisition_key="k1", retrieval_params={"url": url})

    assert record.response_headers is None
    assert record.availability_classification == "unknown"
    assert record.available_utc is None
    assert record.availability_source is None and record.availability_derivation is None


def test_invalid_last_modified_value_is_stored_verbatim(tmp_path):
    url = "https://chc.example/data.nc"
    fake = FakeTransport(
        bytes_map={url: b"payload"},
        headers_map={url: {"Last-Modified": "not-a-real-date"}},
    )
    driver = _chirps_driver(tmp_path, fake)
    record = driver.acquire(acquisition_key="k1", retrieval_params={"url": url})

    assert record.response_headers == {"last-modified": "not-a-real-date"}
    assert record.availability_classification == "unknown"


def test_redirects_record_request_final_and_chain(tmp_path):
    url = "https://origin.example/data.nc"
    final = "https://cdn.example/data.nc"
    hop = "https://mirror1.example/data.nc"
    fake = FakeTransport(
        bytes_map={url: b"payload"},
        headers_map={url: {"Last-Modified": "Wed, 02 Sep 2026 00:00:00 GMT"}},
        final_url=final,
        redirect_chain=(hop,),
    )
    driver = _chirps_driver(tmp_path, fake)
    record = driver.acquire(acquisition_key="k1", retrieval_params={"url": url})

    assert record.request_url == url
    assert record.final_url == final
    assert record.redirect_chain == [hop]
    assert record.response_headers == {"last-modified": "Wed, 02 Sep 2026 00:00:00 GMT"}


def test_failed_fetch_without_response_has_no_http_response_fields(tmp_path):
    url = "https://x/data"
    fake = FakeTransport(bytes_map={url: b"x"}, error=RuntimeError("boom"))
    driver = _chirps_driver(tmp_path, fake)
    with pytest.raises(AcquisitionError):
        driver.acquire(acquisition_key="k1", retrieval_params={"url": url})

    record = load_acquisition_manifest(tmp_path / "acquisition.json").records[0]
    assert record.status is AcquisitionStatus.FAILED
    assert record.request_url == url
    assert record.request_method == "GET"
    assert record.http_status is None
    assert record.response_headers is None
    assert record.final_url is None
    assert record.redirect_chain is None
    assert record.availability_classification == "unknown"
    assert record.available_utc is None
    assert record.storage_path is None


def test_failed_fetch_with_response_captures_status_and_allowlisted_headers(tmp_path):
    url = "https://x/data"
    err = RuntimeError("server error")
    err.response = _FakeResponse(
        status_code=503,
        headers={"Last-Modified": "Wed, 02 Sep 2026 00:00:00 GMT", "Set-Cookie": "s=topsecret"},
    )
    fake = FakeTransport(bytes_map={url: b"x"}, error=err)
    driver = _chirps_driver(tmp_path, fake)
    with pytest.raises(AcquisitionError):
        driver.acquire(acquisition_key="k1", retrieval_params={"url": url})

    record = load_acquisition_manifest(tmp_path / "acquisition.json").records[0]
    assert record.status is AcquisitionStatus.FAILED
    assert record.http_status == 503
    assert record.response_headers == {"last-modified": "Wed, 02 Sep 2026 00:00:00 GMT"}
    assert "topsecret" not in (tmp_path / "acquisition.json").read_text(encoding="utf-8")


def test_checksum_mismatch_retains_evidence(tmp_path):
    url = "https://x/data"
    fake = FakeTransport(bytes_map={url: b"payload"}, headers_map={url: {"ETag": '"abc"'}})
    driver = _chirps_driver(tmp_path, fake)
    with pytest.raises(ChecksumMismatchError):
        driver.acquire(
            acquisition_key="k1",
            retrieval_params={"url": url},
            expected_sha256="0" * 64,
        )

    record = load_acquisition_manifest(tmp_path / "acquisition.json").records[0]
    assert record.status is AcquisitionStatus.CHECKSUM_MISMATCH
    assert record.http_status == 200
    assert record.request_url == url
    assert record.response_headers == {"etag": '"abc"'}
    assert record.storage_path is None
    assert list((tmp_path / "raw").rglob("*")) == []


def test_legacy_record_without_evidence_fields_loads_unchanged(tmp_path):
    legacy = {
        "contract_version": "1.1.0",
        "generated_at_utc": "2026-10-08T05:00:00Z",
        "records": [
            {
                "record_id": "REAL-chirps-v2-x-k1",
                "source": "chirps",
                "product": "CHIRPS v2",
                "product_version": "v2.x",
                "kind": "REAL",
                "status": "failed",
                "access_reference": "https://data.chc.ucsb.edu/products/CHIRPS-2.0/",
                "license_attribution": "public",
                "acquired_utc": "2026-10-08T05:00:00Z",
                "error": "boom",
            }
        ],
    }
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(legacy), encoding="utf-8")

    manifest = load_acquisition_manifest(path)
    record = manifest.records[0]
    assert record.request_url is None
    assert record.http_status is None
    assert record.response_headers is None
    assert record.final_url is None
    assert record.availability_classification is None
    assert record.redacted_params is None

    save_acquisition_manifest(manifest, path)
    assert load_acquisition_manifest(path).model_dump() == manifest.model_dump()


def test_url_secrets_are_redacted_and_recorded(tmp_path):
    secret_url = (
        "https://user:pass@host.example/data"
        "?token=supersecret&sig=abcdef123&date=2026-10-07"
    )
    fake = FakeTransport(bytes_map={secret_url: b"payload"})
    driver = _chirps_driver(tmp_path, fake)
    record = driver.acquire(acquisition_key="k1", retrieval_params={"url": secret_url})

    assert "supersecret" not in record.request_url
    assert "abcdef123" not in record.request_url
    assert "user:pass" not in record.request_url
    assert "token=REDACTED" in record.request_url
    assert "sig=REDACTED" in record.request_url
    assert "date=2026-10-07" in record.request_url
    assert set(record.redacted_params) == {"token", "sig"}
    assert record.retrieval_params["url"] == record.request_url

    blob = (tmp_path / "acquisition.json").read_text(encoding="utf-8")
    for secret in ("supersecret", "abcdef123", "user:pass"):
        assert secret not in blob


def test_redact_url_strips_userinfo_fragment_and_sensitive_query():
    redacted, names = redact_url(
        "https://user:pass@host/path?id=7&access_token=abc&X-Amz-Signature=zz#frag"
    )
    assert redacted == "https://host/path?id=7&access_token=REDACTED&X-Amz-Signature=REDACTED"
    assert set(names) == {"access_token", "X-Amz-Signature"}
    assert "#" not in redacted
    assert redact_url("") == ("", [])
    assert redact_url(None) == (None, [])


# --- Audit 3.7.3B.4: regression tests for genuine defects (expected to fail) ---
# These tests document confirmed defects. They are intentionally left failing
# until production code is fixed (this audit must not modify production code).


def test_error_message_does_not_leak_url_secrets(tmp_path):
    """DEFECT (High): the failure record's ``error`` embeds the raw request URL.

    ``requests`` builds ``HTTPError``/``ConnectionError``/``InvalidURL`` messages
    that include the URL (signed query params included), and ``acquire`` stores
    ``f"{type(exc).__name__}: {exc}"`` verbatim in the committed ledger and in
    the raised ``AcquisitionError``.
    """
    secret_url = "https://host.example/data?token=supersecret&date=2026-10-07"
    err = requests.HTTPError(
        f"503 Server Error: Service Unavailable for url: {secret_url}",
        response=_FakeResponse(status_code=503, url=secret_url),
    )
    fake = FakeTransport(bytes_map={secret_url: b"x"}, error=err)
    driver = _chirps_driver(tmp_path, fake)
    with pytest.raises(AcquisitionError) as excinfo:
        driver.acquire(acquisition_key="k1", retrieval_params={"url": secret_url})

    blob = (tmp_path / "acquisition.json").read_text(encoding="utf-8")
    assert "supersecret" not in blob
    assert "supersecret" not in str(excinfo.value)


def test_redact_url_fails_closed_on_malformed_url():
    """DEFECT (Medium): ``redact_url`` returns the input unchanged on ValueError.

    A malformed URL (e.g. invalid IPv6 brackets) makes ``urlsplit`` raise; the
    handler returns the raw string, so userinfo/query secrets survive redaction.
    Redaction should fail closed (redact or blank unrecognised input).
    """
    malformed = "http://user:pass@[::1?token=supersecret"
    redacted, _names = redact_url(malformed)
    assert "supersecret" not in redacted
    assert "user:pass" not in redacted


def test_response_header_values_are_bounded(tmp_path):
    """DEFECT (Low): allowlisted header values are stored without any length bound.

    ``_allowlisted_headers`` stringifies values but never truncates or strips
    control characters, so a hostile server can bloat the committed ledger.
    """
    url = "https://chc.example/data.nc"
    fake = FakeTransport(
        bytes_map={url: b"payload"},
        headers_map={url: {"ETag": "a" * 100000}},
    )
    driver = _chirps_driver(tmp_path, fake)
    record = driver.acquire(acquisition_key="k1", retrieval_params={"url": url})

    assert len(record.response_headers["etag"]) <= 512


def test_real_transport_fetch_wraps_response_and_get_bytes_delegates(monkeypatch):
    from app.services import acquisition as acq

    hop = _FakeResponse(status_code=302, url="https://hop.example/first")
    final_response = _FakeResponse(
        content=b"final-bytes",
        status_code=200,
        headers={"Last-Modified": "Wed, 02 Sep 2026 00:00:00 GMT", "Set-Cookie": "x=y"},
        url="https://cdn.example/final",
        history=[hop],
    )
    calls = {}

    def fake_get(url, headers=None, timeout=None, **kwargs):
        calls["url"] = url
        return final_response

    monkeypatch.setattr(acq.requests, "get", fake_get)
    transport = acq.AcquisitionTransport()
    result = transport.fetch("https://origin.example/data", headers={"Accept": "*/*"}, timeout=30)

    assert isinstance(result, FetchResult)
    assert calls["url"] == "https://origin.example/data"
    assert result.content == b"final-bytes"
    assert result.status_code == 200
    assert result.final_url == "https://cdn.example/final"
    assert result.redirect_chain == ("https://hop.example/first",)
    assert result.headers["Set-Cookie"] == "x=y"
    assert transport.get_bytes("https://origin.example/data") == b"final-bytes"


def test_explicit_availability_classification_is_preserved(tmp_path):
    url = "https://chc.example/data.nc"
    fake = FakeTransport(
        bytes_map={url: b"payload"},
        headers_map={url: {"Last-Modified": "Wed, 02 Sep 2026 00:00:00 GMT"}},
    )
    driver = _chirps_driver(tmp_path, fake)
    record = driver.acquire(
        acquisition_key="k1",
        retrieval_params={"url": url},
        availability_classification="derived",
        availability_source="rule:last_modified_plus_lag",
        availability_derivation="last_modified + 2d",
        provider_metadata={"product_version": "v2.0-final"},
    )
    assert record.availability_classification == "derived"
    assert record.availability_source == "rule:last_modified_plus_lag"
    assert record.availability_derivation == "last_modified + 2d"
    assert record.provider_metadata == {"product_version": "v2.0-final"}


# --- Audit 3.7.3B.4 remediation (Phase 3.7.3B.5): L-1/L-2/L-3 ---


def test_response_header_control_characters_are_stripped(tmp_path):
    """L-1: allowlisted header values must not carry CR/LF or other controls."""
    url = "https://chc.example/data.nc"
    fake = FakeTransport(
        bytes_map={url: b"payload"},
        headers_map={url: {"ETag": '"a"\r\nX-Injected: evil'}},
    )
    driver = _chirps_driver(tmp_path, fake)
    record = driver.acquire(acquisition_key="k1", retrieval_params={"url": url})

    assert "\r" not in record.response_headers["etag"]
    assert "\n" not in record.response_headers["etag"]


def test_nested_retrieval_params_secrets_are_scrubbed(tmp_path):
    """L-2: secrets nested inside retrieval_params must not survive to the ledger."""
    url = "https://chc.example/data.nc"
    fake = FakeTransport(bytes_map={url: b"payload"})
    driver = _chirps_driver(tmp_path, fake)
    driver.acquire(
        acquisition_key="k1",
        retrieval_params={
            "url": url,
            "headers": {"Authorization": "Bearer nested-leak", "X-Token": "tok-leak"},
            "options": {"nested": {"api_key": "deep-leak"}},
            "layers": [{"password": "list-leak"}],
        },
    )
    manifest = load_acquisition_manifest(tmp_path / "acquisition.json")
    params = manifest.records[0].retrieval_params
    assert params["headers"] == {}
    assert params["options"] == {"nested": {}}
    assert params["layers"] == [{}]

    blob = (tmp_path / "acquisition.json").read_text(encoding="utf-8")
    for secret in ("nested-leak", "tok-leak", "deep-leak", "list-leak"):
        assert secret not in blob


def test_provider_metadata_is_sanitized_and_bounded(tmp_path):
    """L-3: caller-supplied provider_metadata is bounded and de-secreted."""
    url = "https://chc.example/data.nc"
    fake = FakeTransport(bytes_map={url: b"payload"})
    driver = _chirps_driver(tmp_path, fake)
    record = driver.acquire(
        acquisition_key="k1",
        retrieval_params={"url": url},
        provider_metadata={
            "api_key": "provider-leak",
            "long": "x" * 5000,
            "weird": "line1\r\nline2",
        },
    )
    assert "api_key" not in record.provider_metadata
    assert len(record.provider_metadata["long"]) <= 512
    assert "\r" not in record.provider_metadata["weird"]
    assert "\n" not in record.provider_metadata["weird"]

    blob = (tmp_path / "acquisition.json").read_text(encoding="utf-8")
    assert "provider-leak" not in blob


# --- Phase 3.7.3B.7: redaction regression tests (R-1, R-2) ---
# These were left failing by the 3.7.3B.6 audit and are fixed in 3.7.3B.7
# (`redact_text` now handles scheme credentials and percent-encoded URLs).
# Assertions compare booleans so the sentinel is never echoed by pytest.


def test_b6_redact_text_redacts_scheme_credential():
    """R-1: ``Authorization: Bearer <token>`` credentials must be redacted."""
    from app.redaction import redact_text

    sentinel = "AUDIT_TOKEN_abc123"
    redacted, _names = redact_text(f"HTTPError: 401 Authorization: Bearer {sentinel}")
    leaked = sentinel in (redacted or "")
    assert not leaked


def test_b6_redact_text_decodes_percent_encoded_urls():
    """R-2: a percent-encoded URL embedded in free text must be redacted."""
    from urllib.parse import quote

    from app.redaction import redact_text

    sentinel = "AUDIT_TOKEN_abc123"
    encoded = quote(f"https://h/d?token={sentinel}", safe="")
    redacted, _names = redact_text(f"InvalidURL: no scheme: {encoded}")
    leaked = sentinel in (redacted or "")
    assert not leaked


def test_b7_redact_text_redacts_scheme_variants_case_insensitively():
    """R-1: Basic/Proxy-Authorization and mixed case must all be redacted."""
    from app.redaction import redact_text

    cases = [
        ("authorization: basic QUJDREVGR0g=", "QUJDREVGR0g="),
        ("AUTHORIZATION: BEARER AUDIT_TOKEN_xyz789", "AUDIT_TOKEN_xyz789"),
        ("Proxy-Authorization: Digest AUDIT_TOKEN_xyz789", "AUDIT_TOKEN_xyz789"),
        ("wrapped\nAuthorization: Bearer\r\nAUDIT_TOKEN_xyz789", "AUDIT_TOKEN_xyz789"),
    ]
    for text, sentinel in cases:
        redacted, _names = redact_text(text)
        leaked = sentinel in (redacted or "")
        assert not leaked, text.split(":")[0]


def test_b7_redact_text_decodes_nested_percent_encoding():
    """R-2: bounded decoding must also cover doubly-encoded URLs (userinfo too)."""
    from urllib.parse import quote

    from app.redaction import redact_text

    sentinel = "AUDIT_TOKEN_nested1"
    once = quote(f"https://user:pass@h/d?token={sentinel}#frag", safe="")
    twice = quote(once, safe="")
    redacted, _names = redact_text(f"InvalidURL: no scheme: {twice}")
    leaked = sentinel in (redacted or "")
    assert not leaked
    assert "user:pass" not in (redacted or "")


def test_b8_redact_text_redacts_prefixed_encoded_urls():
    """R-3: a percent-encoded URL glued to a literal prefix must be redacted."""
    from urllib.parse import quote

    from app.redaction import redact_text

    sentinel = "B8_QUERY_TOKEN_abc123"
    password = "B8_USERINFO_pw_xyz"
    encoded = quote(f"https://user:{password}@h/d?token={sentinel}", safe="")
    forms = [
        (f"({encoded})", "("),
        (f"[{encoded}]", "["),
        (f"url={encoded}", "url="),
        (f"url:{encoded}", "url:"),
    ]
    for form, prefix in forms:
        redacted, _names = redact_text(form)
        text = redacted or ""
        assert sentinel not in text
        assert password not in text
        assert "user:" not in text
        assert text.startswith(prefix)


def test_b8_redact_text_redacts_prefixed_encoded_query_secret():
    """R-3: sensitive query parameters survive no prefix form."""
    from urllib.parse import quote

    from app.redaction import redact_text

    sentinel = "B8_SIG_value_456"
    encoded = quote(f"https://h/d?X-Amz-Signature={sentinel}&page=2", safe="")
    for form in (f"({encoded})", f"[{encoded}]", f"url={encoded}", f"url:{encoded}"):
        redacted, names = redact_text(form)
        text = redacted or ""
        assert sentinel not in text
        assert "REDACTED" in text
        assert "page=2" in text
        assert "X-Amz-Signature" in names


def test_b8_redact_text_preserves_non_sensitive_prefixed_url():
    """R-3: non-sensitive URLs and surrounding punctuation are preserved."""
    from urllib.parse import quote

    from app.redaction import redact_text

    encoded = quote("https://example.com/path/file?page=2", safe="")
    redacted, names = redact_text(f"see [{encoded}]")
    text = redacted or ""
    assert "example.com/path/file" in text
    assert text.startswith("see [")
    assert text.endswith("]")
    assert "REDACTED" not in text
    assert names == []


def test_b8_redact_text_fails_closed_on_malformed_prefixed_encoded_url():
    """R-3: an unparseable decoded URL must not fall back to the encoded token."""
    from urllib.parse import quote

    from app.redaction import redact_text

    sentinel = "B8_MALFORMED_secret_789"
    encoded = quote(f"http://[::1?token={sentinel}", safe="")
    redacted, _names = redact_text(f"url={encoded}")
    assert sentinel not in (redacted or "")