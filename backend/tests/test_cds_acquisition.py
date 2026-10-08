"""CDS acquisition tests (Phase 3.6).

Covers the minimal CDS retrieve API client and the driver's ``acquire_cds``
flow: execution submission, job polling, result-asset extraction, byte
download, provider/caller checksum enforcement, content dedupe, immutable
storage, honest failure records, credential gating and secret non-leakage.
All interactions are mocked -- unit tests never touch the network.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services import cds as cds_service
from app.services.acquisition import (
    AcquisitionDriver,
    AcquisitionError,
    ChecksumMismatchError,
    CredentialsMissingError,
    DuplicateArtifactError,
    get_source_config,
    load_acquisition_manifest,
    storage_relative_path,
)
from app.services.cds import (
    CdsApiError,
    CdsAuthenticationError,
    CdsJobFailed,
    CdsMalformedResponse,
    CdsTimeout,
    CdsTransport,
    asset_extension,
    provider_sha256,
)

UTC = timezone.utc

DATASET = "reanalysis-era5-land"
INPUTS = {
    "variable": ["2m_temperature", "total_precipitation"],
    "year": ["2026"],
    "month": ["07"],
    "day": ["15"],
    "time": ["00:00"],
    "area": [29.5, 88.0, 21.0, 97.5],
    "data_format": "netcdf",
    "download_format": "unarchived",
}
FAKE_KEY = "cds-test-key-not-a-secret"
FAKE_URL = "https://cds.example.invalid/api"


def _utc(y, m, d, hh=0, mm=0, ss=0):
    return datetime(y, m, d, hh, mm, ss, tzinfo=UTC)


def _credentials(monkeypatch):
    monkeypatch.setenv("CDS_API_URL", FAKE_URL)
    monkeypatch.setenv("CDS_API_KEY", FAKE_KEY)


class FakeCds:
    """Deterministic stand-in for CdsTransport; records all calls."""

    def __init__(
        self,
        *,
        job_id="job-123",
        poll_status="successful",
        payload=b"ERA5L data bytes",
        assets=None,
        submit_error=None,
        poll_error=None,
        results_error=None,
        download_error=None,
    ):
        self.job_id = job_id
        self.poll_status = poll_status
        self.payload = payload
        self.assets = assets if assets is not None else [
            {
                "type": "application/x-netcdf",
                "href": f"https://cdn.example.invalid/results/{job_id}.nc?jwt=x",
                "file:checksum": hashlib.sha256(payload).hexdigest(),
                "file:size": len(payload),
                "file:local_path": f"/results/{job_id}.nc",
            }
        ]
        self.submit_error = submit_error
        self.poll_error = poll_error
        self.results_error = results_error
        self.download_error = download_error
        self.submits = []
        self.polls = []
        self.results_calls = []
        self.downloads = []

    def submit(self, dataset, inputs):
        self.submits.append((dataset, inputs))
        if self.submit_error:
            raise self.submit_error
        return self.job_id

    def wait_for_success(self, job_id):
        self.polls.append(job_id)
        if self.poll_error:
            raise self.poll_error
        return self.poll_status, "ok"

    def results(self, job_id):
        self.results_calls.append(job_id)
        if self.results_error:
            raise self.results_error
        return self.assets

    def download(self, url, headers=None):
        self.downloads.append(url)
        if self.download_error:
            raise self.download_error
        return self.payload


def _driver(tmp_path, monkeypatch):
    _credentials(monkeypatch)
    raw_root = tmp_path / "raw"
    manifest_path = tmp_path / "manifest.json"
    return (
        AcquisitionDriver(source="era5-land", raw_root=raw_root, manifest_path=manifest_path),
        raw_root,
        manifest_path,
    )


def _failures_in(manifest):
    return [r for r in manifest.records if r.status == "failed"]


# ---------------------------------------------------------------------------
# Transport-level tests (no network; requests post/get monkeypatched)
# ---------------------------------------------------------------------------


class _Response:
    def __init__(self, status_code, payload=None, text=None, content=None):
        self.status_code = status_code
        self._payload = payload
        self.text = text if text is not None else (json.dumps(payload) if payload is not None else "")
        self.content = content if content is not None else self.text.encode("utf-8")

    def json(self):
        if self._payload is None:
            raise ValueError("no json body")
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def _fake_post(monkeypatch, response_fn):
    captured = {}

    def post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return response_fn(captured)

    monkeypatch.setattr(cds_service.requests, "post", post)
    return captured


def _fake_get(monkeypatch, response_map):
    def get(url, headers=None, timeout=None):
        return response_map[url]

    monkeypatch.setattr(cds_service.requests, "get", get)


def test_submit_returns_job_id(monkeypatch):
    transport = CdsTransport(api_url=FAKE_URL, api_key=FAKE_KEY)
    captured = _fake_post(
        monkeypatch, lambda c: _Response(201, {"jobID": "job-1", "status": "accepted"})
    )
    assert transport.submit(DATASET, INPUTS) == "job-1"
    assert captured["url"] == f"{FAKE_URL}/retrieve/v1/processes/{DATASET}/execution"
    assert captured["headers"]["PRIVATE-TOKEN"] == FAKE_KEY
    assert captured["json"]["response"] == "raw"
    assert captured["json"]["inputs"] == INPUTS


def test_submit_rejects_authentication(monkeypatch):
    transport = CdsTransport(api_url=FAKE_URL, api_key=FAKE_KEY)
    _fake_post(monkeypatch, lambda c: _Response(401, text="unauthorized"))
    with pytest.raises(CdsAuthenticationError):
        transport.submit(DATASET, INPUTS)


def test_submit_rejects_other_statuses(monkeypatch):
    transport = CdsTransport(api_url=FAKE_URL, api_key=FAKE_KEY)
    _fake_post(monkeypatch, lambda c: _Response(500, {"detail": "boom"}))
    with pytest.raises(CdsApiError):
        transport.submit(DATASET, INPUTS)


def test_submit_missing_job_id(monkeypatch):
    transport = CdsTransport(api_url=FAKE_URL, api_key=FAKE_KEY)
    _fake_post(monkeypatch, lambda c: _Response(201, {"status": "accepted"}))
    with pytest.raises(CdsMalformedResponse):
        transport.submit(DATASET, INPUTS)


def test_poll_returns_status_and_message(monkeypatch):
    transport = CdsTransport(api_url=FAKE_URL, api_key=FAKE_KEY)
    _fake_get(
        monkeypatch,
        {f"{FAKE_URL}/retrieve/v1/jobs/job-1": _Response(200, {"status": "running"})},
    )
    assert transport.poll("job-1") == ("running", None)


def test_results_extracts_nested_assets(monkeypatch):
    transport = CdsTransport(api_url=FAKE_URL, api_key=FAKE_KEY)
    payload = {
        "asset": {
            "value": [
                {
                    "href": "https://cdn.example.invalid/a.nc",
                    "file:checksum": "a" * 64,
                    "file:size": 5,
                    "file:local_path": "/a.nc",
                }
            ]
        }
    }
    _fake_get(
        monkeypatch,
        {f"{FAKE_URL}/retrieve/v1/jobs/job-1/results": _Response(200, payload)},
    )
    assets = transport.results("job-1")
    assert assets and assets[0]["href"] == "https://cdn.example.invalid/a.nc"
    assert assets[0]["file:local_path"] == "/a.nc"


def test_results_empty_is_no_assets(monkeypatch):
    transport = CdsTransport(api_url=FAKE_URL, api_key=FAKE_KEY)
    _fake_get(
        monkeypatch,
        {f"{FAKE_URL}/retrieve/v1/jobs/job-1/results": _Response(200, {"asset": {"value": []}})},
    )
    assert transport.results("job-1") == []


def test_download_returns_bytes(monkeypatch):
    transport = CdsTransport(api_url=FAKE_URL, api_key=FAKE_KEY)
    _fake_get(
        monkeypatch,
        {"https://cdn.example.invalid/a.nc": _Response(200, content=b"12345")},
    )
    assert transport.download("https://cdn.example.invalid/a.nc") == b"12345"


def test_wait_for_success_polls_to_terminal(monkeypatch):
    transport = CdsTransport(api_url=FAKE_URL, api_key=FAKE_KEY, poll_interval_seconds=1)
    calls = []

    def get(url, headers=None, timeout=None):
        calls.append(url)
        status = "successful" if len(calls) > 1 else "running"
        return _Response(200, {"status": status})

    monkeypatch.setattr(cds_service.requests, "get", get)
    monkeypatch.setattr(cds_service.time, "sleep", lambda s: None)
    assert transport.wait_for_success("job-1") == ("successful", None)


def test_wait_for_success_raises_on_failed(monkeypatch):
    transport = CdsTransport(api_url=FAKE_URL, api_key=FAKE_KEY)
    _fake_get(
        monkeypatch,
        {f"{FAKE_URL}/retrieve/v1/jobs/job-1": _Response(200, {"status": "failed", "message": "nope"})},
    )
    with pytest.raises(CdsJobFailed) as exc:
        transport.wait_for_success("job-1")
    assert exc.value.job_id == "job-1"
    assert "nope" in str(exc.value)


def test_wait_for_success_times_out(monkeypatch):
    transport = CdsTransport(
        api_url=FAKE_URL,
        api_key=FAKE_KEY,
        max_wait_seconds=0,
        poll_interval_seconds=1,
    )
    _fake_get(
        monkeypatch,
        {f"{FAKE_URL}/retrieve/v1/jobs/job-1": _Response(200, {"status": "accepted"})},
    )
    monkeypatch.setattr(cds_service.time, "sleep", lambda s: None)
    with pytest.raises(CdsTimeout):
        transport.wait_for_success("job-1")


def test_provider_sha256_and_asset_extension_helpers():
    assert provider_sha256({"file:checksum": "ab" * 32, "href": "x"}) == "ab" * 32
    assert provider_sha256({"file:checksum": "not-a-checksum"}) is None
    assert asset_extension({"href": "https://cdn.example.invalid/a.nc"}) == ".nc"
    assert asset_extension({"file:local_path": "/results/b.grib"}) == ".grib"
    assert asset_extension({"href": "https://cdn.example.invalid/a.nc?v=1"}) == ".nc"
    assert asset_extension({"href": "https://cdn.example.invalid/noext"}) == ".bin"


# ---------------------------------------------------------------------------
# Driver-level tests (FakeCds transport; no network)
# ---------------------------------------------------------------------------


def test_acquire_cds_happy_path_creates_downloaded_record(tmp_path, monkeypatch):
    driver, raw_root, manifest_path = _driver(tmp_path, monkeypatch)
    fake = FakeCds()
    record = driver.acquire_cds(
        dataset=DATASET,
        inputs=INPUTS,
        acquisition_key="2026-07-15t0000",
        observation_start_utc=_utc(2026, 7, 15, 0, 0),
        observation_end_utc=_utc(2026, 7, 15, 1, 0),
        available_utc=_utc(2026, 9, 15, 0, 0),
        cds=fake,
    )
    assert record.status == "downloaded"
    assert record.kind == "REAL"
    assert record.source == "era5-land"
    assert record.source_record_id == "job-123"
    assert record.product_version == get_source_config("era5-land").product_version
    assert record.sha256 == hashlib.sha256(fake.payload).hexdigest()
    assert record.file_size_bytes == len(fake.payload)
    assert record.observation_start_utc == _utc(2026, 7, 15, 0, 0)
    assert record.observation_end_utc == _utc(2026, 7, 15, 1, 0)
    assert record.available_utc == _utc(2026, 9, 15, 0, 0)
    stored = raw_root / record.storage_path
    assert stored.exists()
    assert stored.read_bytes() == fake.payload
    manifest = load_acquisition_manifest(manifest_path)
    assert len(manifest.records) == 1
    assert manifest.records[0].status == "downloaded"


def test_acquire_cds_missing_credentials_fails_loudly(tmp_path, monkeypatch):
    driver, _raw_root, _manifest_path = _driver(tmp_path, monkeypatch)
    monkeypatch.delenv("CDS_API_URL")
    monkeypatch.delenv("CDS_API_KEY")
    fake = FakeCds()
    with pytest.raises(CredentialsMissingError) as exc:
        driver.acquire_cds(dataset=DATASET, inputs=INPUTS, cds=fake)
    assert "CDS_API_URL" in str(exc.value)
    assert "CDS_API_KEY" in str(exc.value)
    assert fake.submits == [] and fake.polls == [] and fake.results_calls == []


def test_acquire_cds_requires_cds_api_source(tmp_path, monkeypatch):
    _credentials(monkeypatch)
    raw_root = tmp_path / "raw"
    manifest_path = tmp_path / "manifest.json"
    driver = AcquisitionDriver(source="chirps", raw_root=raw_root, manifest_path=manifest_path)
    with pytest.raises(AcquisitionError) as exc:
        driver.acquire_cds(dataset=DATASET, inputs=INPUTS)
    assert "cds-api" in str(exc.value)


def test_acquire_cds_records_failed_on_submit_error(tmp_path, monkeypatch):
    driver, raw_root, manifest_path = _driver(tmp_path, monkeypatch)
    fake = FakeCds(submit_error=CdsApiError("HTTP 500: boom"))
    with pytest.raises(AcquisitionError) as exc:
        driver.acquire_cds(dataset=DATASET, inputs=INPUTS, cds=fake)
    assert "HTTP 500" in str(exc.value)
    failures = _failures_in(load_acquisition_manifest(manifest_path))
    assert len(failures) == 1
    assert failures[0].storage_path is None
    assert list(raw_root.rglob("*")) == []


def test_acquire_cds_records_failed_on_job_failure(tmp_path, monkeypatch):
    driver, raw_root, manifest_path = _driver(tmp_path, monkeypatch)
    fake = FakeCds(poll_error=CdsJobFailed("job-123", "failed", "provider rejected"))
    with pytest.raises(AcquisitionError) as exc:
        driver.acquire_cds(dataset=DATASET, inputs=INPUTS, cds=fake)
    assert "provider rejected" in str(exc.value)
    failures = _failures_in(load_acquisition_manifest(manifest_path))
    assert len(failures) == 1
    assert failures[0].source_record_id == "job-123"
    assert "provider rejected" in (failures[0].error or "")
    assert list(raw_root.rglob("*")) == []


def test_acquire_cds_records_failed_on_timeout(tmp_path, monkeypatch):
    driver, raw_root, manifest_path = _driver(tmp_path, monkeypatch)
    fake = FakeCds(poll_error=CdsTimeout("CDS job job-123 not terminal after 1s (status=running)"))
    with pytest.raises(AcquisitionError) as exc:
        driver.acquire_cds(dataset=DATASET, inputs=INPUTS, cds=fake)
    assert "not terminal" in str(exc.value)
    failures = _failures_in(load_acquisition_manifest(manifest_path))
    assert len(failures) == 1
    assert failures[0].source_record_id == "job-123"
    assert list(raw_root.rglob("*")) == []


def test_acquire_cds_records_failed_when_no_assets(tmp_path, monkeypatch):
    driver, raw_root, manifest_path = _driver(tmp_path, monkeypatch)
    fake = FakeCds(assets=[])
    with pytest.raises(AcquisitionError) as exc:
        driver.acquire_cds(dataset=DATASET, inputs=INPUTS, cds=fake)
    assert "no downloadable asset" in str(exc.value)
    failures = _failures_in(load_acquisition_manifest(manifest_path))
    assert len(failures) == 1
    assert list(raw_root.rglob("*")) == []


def test_acquire_cds_records_failed_on_download_error(tmp_path, monkeypatch):
    driver, raw_root, manifest_path = _driver(tmp_path, monkeypatch)
    fake = FakeCds(download_error=RuntimeError("conn reset"))
    with pytest.raises(AcquisitionError) as exc:
        driver.acquire_cds(dataset=DATASET, inputs=INPUTS, cds=fake)
    assert "conn reset" in str(exc.value)
    failures = _failures_in(load_acquisition_manifest(manifest_path))
    assert len(failures) == 1
    assert failures[0].source_record_id == "job-123"
    assert list(raw_root.rglob("*")) == []


def test_acquire_cds_checksum_mismatch_raises_and_records(tmp_path, monkeypatch):
    driver, raw_root, manifest_path = _driver(tmp_path, monkeypatch)
    wrong_payload = b"not the declared checksum bytes"
    fake = FakeCds(
        payload=wrong_payload,
        assets=[
            {
                "type": "application/x-netcdf",
                "href": "https://cdn.example.invalid/job-123.nc",
                "file:checksum": "0" * 64,
                "file:size": len(wrong_payload),
                "file:local_path": "/results/job-123.nc",
            }
        ],
    )
    with pytest.raises(ChecksumMismatchError):
        driver.acquire_cds(dataset=DATASET, inputs=INPUTS, cds=fake)
    manifest = load_acquisition_manifest(manifest_path)
    records = [r for r in manifest.records if r.status == "checksum_mismatch"]
    assert len(records) == 1
    assert records[0].sha256 == hashlib.sha256(wrong_payload).hexdigest()
    assert records[0].storage_path is None
    assert list(raw_root.rglob("*")) == []


def test_acquire_cds_deduplicates_identical_bytes(tmp_path, monkeypatch):
    driver, raw_root, manifest_path = _driver(tmp_path, monkeypatch)
    first = driver.acquire_cds(
        dataset=DATASET,
        inputs=INPUTS,
        acquisition_key="2026-07-15t0000",
        cds=FakeCds(job_id="job-1"),
    )
    second = driver.acquire_cds(
        dataset=DATASET,
        inputs=INPUTS,
        acquisition_key="2026-07-15t0600",
        cds=FakeCds(job_id="job-2"),
    )
    assert first.status == "downloaded"
    assert second.status == "skipped_existing"
    assert second.storage_path == first.storage_path
    assert len(list(raw_root.rglob("*.nc"))) == 1
    manifest = load_acquisition_manifest(manifest_path)
    assert len(manifest.records) == 2
    assert manifest.records[1].source_record_id == "job-2"


def test_acquire_cds_storage_path_is_immutable(tmp_path, monkeypatch):
    driver, raw_root, manifest_path = _driver(tmp_path, monkeypatch)
    source = get_source_config("era5-land")
    rel = storage_relative_path(source, "2026-07-15t0000", ".nc")
    target = raw_root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"someone else")
    with pytest.raises(DuplicateArtifactError):
        driver.acquire_cds(
            dataset=DATASET,
            inputs=INPUTS,
            acquisition_key="2026-07-15t0000",
            cds=FakeCds(),
        )


def test_acquire_cds_never_persists_secrets(tmp_path, monkeypatch):
    driver, _raw_root, manifest_path = _driver(tmp_path, monkeypatch)
    fake = FakeCds()
    driver.acquire_cds(dataset=DATASET, inputs=INPUTS, acquisition_key="2026-07-15t0000", cds=fake)
    manifest = load_acquisition_manifest(manifest_path)
    record = manifest.records[0]
    blob = manifest.model_dump_json()
    assert FAKE_KEY not in blob
    assert "PRIVATE-TOKEN" not in blob
    assert "PRIVATE-TOKEN" not in str(record.retrieval_params)
    assert record.retrieval_params.get("dataset") == DATASET
    assert record.retrieval_params.get("inputs") == INPUTS