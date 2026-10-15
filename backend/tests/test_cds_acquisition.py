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
    CdsError,
    CdsJobFailed,
    CdsMalformedResponse,
    CdsSubmission,
    CdsTimeout,
    CdsTransport,
    asset_extension,
    job_evidence,
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
        poll_evidence_error=None,
        download_headers=None,
        download_final_url=None,
        download_redirect_chain=(),
        submit_evidence=None,
        poll_evidence=None,
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
        self.poll_evidence_error = poll_evidence_error
        self.download_headers = download_headers
        self.download_final_url = download_final_url
        self.download_redirect_chain = tuple(download_redirect_chain)
        self.submit_evidence = dict(submit_evidence or {})
        self.poll_evidence_data = dict(poll_evidence or {})
        self.submits = []
        self.polls = []
        self.results_calls = []
        self.downloads = []
        self.poll_evidence_calls = []

    def submit(self, dataset, inputs):
        return self.submit_with_evidence(dataset, inputs).job_id

    def submit_with_evidence(self, dataset, inputs):
        self.submits.append((dataset, inputs))
        if self.submit_error:
            raise self.submit_error
        return cds_service.CdsSubmission(
            job_id=self.job_id, evidence=dict(self.submit_evidence)
        )

    def wait_for_success(self, job_id):
        self.polls.append(job_id)
        if self.poll_error:
            raise self.poll_error
        return self.poll_status, "ok"

    def poll_evidence(self, job_id):
        self.poll_evidence_calls.append(job_id)
        if self.poll_evidence_error:
            raise self.poll_evidence_error
        return dict(self.poll_evidence_data)

    def results(self, job_id):
        self.results_calls.append(job_id)
        if self.results_error:
            raise self.results_error
        return self.assets

    def download(self, url, headers=None):
        return self.download_with_evidence(url, headers).content

    def download_with_evidence(self, url, headers=None):
        self.downloads.append(url)
        if self.download_error:
            raise self.download_error
        final_url = self.download_final_url
        if final_url is None:
            final_url = self.assets[0]["href"] if self.assets else url
        return cds_service.CdsDownloadResult(
            content=self.payload,
            status_code=200,
            headers=dict(self.download_headers or {}),
            final_url=final_url,
            redirect_chain=self.download_redirect_chain,
        )


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
    def __init__(
        self,
        status_code,
        payload=None,
        text=None,
        content=None,
        headers=None,
        url="",
        history=(),
    ):
        self.status_code = status_code
        self._payload = payload
        self.text = text if text is not None else (json.dumps(payload) if payload is not None else "")
        self.content = content if content is not None else self.text.encode("utf-8")
        self.headers = headers if headers is not None else {}
        self.url = url
        self.history = history

    def json(self):
        if self._payload is None:
            raise ValueError("no json body")
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def _fake_post(monkeypatch, response_fn):
    captured = {}

    def post(url, headers=None, json=None, timeout=None, allow_redirects=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["allow_redirects"] = allow_redirects
        return response_fn(captured)

    monkeypatch.setattr(cds_service.requests, "post", post)
    return captured


def _fake_get(monkeypatch, response_map):
    def get(url, headers=None, timeout=None, allow_redirects=None):
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

    def get(url, headers=None, timeout=None, allow_redirects=None):
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


# ---------------------------------------------------------------------------
# Phase 3.7.3C.2 -- artifact-download evidence, credential boundary, redaction
# ---------------------------------------------------------------------------


def test_download_with_evidence_follows_redirect_and_captures_evidence(monkeypatch):
    transport = CdsTransport(api_url=FAKE_URL, api_key=FAKE_KEY)
    start = "https://cdn.example.invalid/a.nc"
    final = "https://cdn.example.invalid/final.nc"
    responses = {
        start: _Response(302, content=b"", headers={"location": final}, url=start),
        final: _Response(
            200,
            content=b"\x00\x01bytes",
            headers={"Last-Modified": "Wed, 01 Oct 2026 00:00:00 GMT", "ETag": '"abc"'},
            url=final,
        ),
    }
    monkeypatch.setattr(
        cds_service.requests,
        "get",
        lambda url, headers=None, timeout=None, allow_redirects=None: responses[url],
    )
    result = transport.download_with_evidence(start)
    assert result.content == b"\x00\x01bytes"
    assert result.status_code == 200
    assert result.headers["Last-Modified"] == "Wed, 01 Oct 2026 00:00:00 GMT"
    assert result.final_url == final
    assert result.redirect_chain == (start,)


def test_download_does_not_send_token_to_external_host(monkeypatch):
    transport = CdsTransport(api_url=FAKE_URL, api_key=FAKE_KEY)
    captured = {}

    def get(url, headers=None, timeout=None, allow_redirects=None):
        captured["headers"] = headers
        return _Response(200, content=b"x", url=url)

    monkeypatch.setattr(cds_service.requests, "get", get)
    transport.download("https://cdn.example.invalid/results/a.nc?jwt=abc")
    assert "PRIVATE-TOKEN" not in captured["headers"]
    assert FAKE_KEY not in json.dumps(captured["headers"])


def test_download_sends_token_only_to_trusted_origin(monkeypatch):
    transport = CdsTransport(api_url=FAKE_URL, api_key=FAKE_KEY)
    captured = {}

    def get(url, headers=None, timeout=None, allow_redirects=None):
        captured["headers"] = headers
        return _Response(200, content=b"x", url=url)

    monkeypatch.setattr(cds_service.requests, "get", get)
    transport.download(f"{FAKE_URL}/retrieve/v1/jobs/job-1/results/file.nc")
    assert captured["headers"]["PRIVATE-TOKEN"] == FAKE_KEY


def test_download_token_absent_for_off_path_same_host(monkeypatch):
    transport = CdsTransport(api_url=FAKE_URL, api_key=FAKE_KEY)
    captured = {}

    def get(url, headers=None, timeout=None, allow_redirects=None):
        captured["headers"] = headers
        return _Response(200, content=b"x", url=url)

    monkeypatch.setattr(cds_service.requests, "get", get)
    transport.download("https://cds.example.invalid/other/file.nc")
    assert "PRIVATE-TOKEN" not in captured["headers"]


def test_download_token_absent_for_different_port(monkeypatch):
    transport = CdsTransport(api_url=FAKE_URL, api_key=FAKE_KEY)
    captured = {}

    def get(url, headers=None, timeout=None, allow_redirects=None):
        captured["headers"] = headers
        return _Response(200, content=b"x", url=url)

    monkeypatch.setattr(cds_service.requests, "get", get)
    transport.download("https://cds.example.invalid:8443/api/retrieve/v1/file.nc")
    assert "PRIVATE-TOKEN" not in captured["headers"]


def test_download_token_absent_on_http_downgrade(monkeypatch):
    transport = CdsTransport(api_url=FAKE_URL, api_key=FAKE_KEY)
    captured = {}

    def get(url, headers=None, timeout=None, allow_redirects=None):
        captured["headers"] = headers
        return _Response(200, content=b"x", url=url)

    monkeypatch.setattr(cds_service.requests, "get", get)
    transport.download("http://cds.example.invalid/api/retrieve/v1/file.nc")
    assert "PRIVATE-TOKEN" not in captured["headers"]


def test_download_redirect_does_not_forward_token_to_external_host(monkeypatch):
    transport = CdsTransport(api_url=FAKE_URL, api_key=FAKE_KEY)
    trusted = f"{FAKE_URL}/retrieve/v1/jobs/job-1/results/file.nc"
    external = "https://cdn.example.invalid/stolen.nc"
    seen = []

    def get(url, headers=None, timeout=None, allow_redirects=None):
        seen.append((url, dict(headers or {}), allow_redirects))
        if url == trusted:
            return _Response(302, content=b"", headers={"location": external}, url=url)
        return _Response(200, content=b"artifact", url=url)

    monkeypatch.setattr(cds_service.requests, "get", get)
    result = transport.download_with_evidence(trusted)
    assert result.content == b"artifact"
    assert result.final_url == external
    assert result.redirect_chain == (trusted,)
    assert "PRIVATE-TOKEN" in seen[0][1]
    assert "PRIVATE-TOKEN" not in seen[1][1]
    assert FAKE_KEY not in json.dumps(seen[1][1])
    assert all(hop[2] is False for hop in seen)


def test_download_too_many_redirects_raises(monkeypatch):
    transport = CdsTransport(api_url=FAKE_URL, api_key=FAKE_KEY)
    loop = "https://cdn.example.invalid/loop.nc"

    def get(url, headers=None, timeout=None, allow_redirects=None):
        return _Response(302, content=b"", headers={"location": loop}, url=url)

    monkeypatch.setattr(cds_service.requests, "get", get)
    with pytest.raises(CdsApiError):
        transport.download_with_evidence(loop)


def test_control_plane_still_sends_token(monkeypatch):
    transport = CdsTransport(api_url=FAKE_URL, api_key=FAKE_KEY)
    captured = _fake_post(
        monkeypatch, lambda c: _Response(201, {"jobID": "job-1", "status": "accepted"})
    )
    transport.submit(DATASET, INPUTS)
    assert captured["headers"]["PRIVATE-TOKEN"] == FAKE_KEY
    assert captured["allow_redirects"] is False


def test_acquire_cds_records_download_evidence(tmp_path, monkeypatch):
    driver, _raw_root, manifest_path = _driver(tmp_path, monkeypatch)
    fake = FakeCds(
        download_headers={
            "Last-Modified": "Wed, 01 Oct 2026 00:00:00 GMT",
            "ETag": '"abc"',
            "Set-Cookie": "session=SECRETCOOKIE",
            "Authorization": "Bearer SECRETTOKEN",
            "Retry-After": "30",
        },
        download_final_url="https://cdn.example.invalid/final.nc?token=FINALSECRET",
        download_redirect_chain=["https://cdn.example.invalid/hop?sig=HOPSECRET"],
    )
    record = driver.acquire_cds(
        dataset=DATASET, inputs=INPUTS, acquisition_key="2026-07-15t0000", cds=fake
    )
    assert record.status == "downloaded"
    assert record.request_method == "GET"
    assert record.http_status == 200
    assert record.response_headers == {
        "last-modified": "Wed, 01 Oct 2026 00:00:00 GMT",
        "etag": '"abc"',
    }
    assert "REDACTED" in (record.request_url or "")
    assert "jwt" in (record.redacted_params or [])
    assert "token" in (record.redacted_params or [])
    assert "sig" in (record.redacted_params or [])
    assert "FINALSECRET" not in (record.final_url or "")
    assert "HOPSECRET" not in "".join(record.redirect_chain or [])
    assert record.provider_metadata["dataset"] == DATASET
    assert record.provider_metadata["job_id"] == "job-123"
    assert record.provider_metadata["asset_type"] == "application/x-netcdf"
    assert record.provider_metadata["cds_lifecycle_note"].startswith(
        "cds_submit_*/cds_poll_* are CDS retrieval-workflow job-state timestamps"
    )
    assert "cds_submit_started" not in record.provider_metadata
    assert set(record.provider_metadata) == {
        "dataset",
        "job_id",
        "asset_type",
        "cds_lifecycle_note",
    }
    blob = load_acquisition_manifest(manifest_path).model_dump_json()
    for secret in ("SECRETCOOKIE", "SECRETTOKEN", "FINALSECRET", "HOPSECRET", FAKE_KEY):
        assert secret not in blob


def test_acquire_cds_redacts_signed_asset_urls(tmp_path, monkeypatch):
    driver, _raw_root, manifest_path = _driver(tmp_path, monkeypatch)
    payload = b"ERA5L data bytes"
    href = (
        "https://cdn.example.invalid/r.nc?"
        "token=TOKVAL&jwt=JWTVAL&sig=SIGVAL"
        "&X-Amz-Signature=AWSSIGVAL&X-Amz-Credential=CREDVAL"
    )
    fake = FakeCds(
        assets=[
            {
                "type": "application/x-netcdf",
                "href": href,
                "file:checksum": hashlib.sha256(payload).hexdigest(),
                "file:size": len(payload),
                "file:local_path": "/r.nc",
            }
        ]
    )
    record = driver.acquire_cds(
        dataset=DATASET, inputs=INPUTS, acquisition_key="2026-07-15t0000", cds=fake
    )
    blob = load_acquisition_manifest(manifest_path).model_dump_json()
    for secret in ("TOKVAL", "JWTVAL", "SIGVAL", "AWSSIGVAL", "CREDVAL"):
        assert secret not in blob
    assert set(record.redacted_params or []) >= {"token", "jwt", "sig"}
    assert any("signature" in name.lower() for name in record.redacted_params or [])
    assert any("credential" in name.lower() for name in record.redacted_params or [])


class _FailingResponseError(RuntimeError):
    def __init__(self, message, response):
        super().__init__(message)
        self.response = response


def test_acquire_cds_download_failure_records_no_artifact(tmp_path, monkeypatch):
    driver, raw_root, manifest_path = _driver(tmp_path, monkeypatch)
    boom = RuntimeError(
        "failed to GET https://cdn.example.invalid/r.nc?token=TOPSECRET&jwt=JWTSECRET"
    )
    fake = FakeCds(download_error=boom)
    with pytest.raises(AcquisitionError) as exc:
        driver.acquire_cds(dataset=DATASET, inputs=INPUTS, cds=fake)
    assert "TOPSECRET" not in str(exc.value)
    assert "JWTSECRET" not in str(exc.value)
    failures = _failures_in(load_acquisition_manifest(manifest_path))
    assert len(failures) == 1
    assert failures[0].storage_path is None
    assert failures[0].request_method == "GET"
    assert "REDACTED" in (failures[0].request_url or "")
    assert failures[0].http_status is None
    assert list(raw_root.rglob("*")) == []


def test_acquire_cds_download_failure_with_response_records_status(tmp_path, monkeypatch):
    driver, raw_root, manifest_path = _driver(tmp_path, monkeypatch)
    resp = _Response(503, text="upstream down", headers={"Retry-After": "30", "ETag": '"x"'})
    boom = _FailingResponseError(
        "HTTP 503 https://cdn.example.invalid/r.nc?token=TOPSECRET", resp
    )
    fake = FakeCds(download_error=boom)
    with pytest.raises(AcquisitionError):
        driver.acquire_cds(dataset=DATASET, inputs=INPUTS, cds=fake)
    failures = _failures_in(load_acquisition_manifest(manifest_path))
    assert failures[0].http_status == 503
    assert failures[0].response_headers == {"etag": '"x"'}
    assert list(raw_root.rglob("*")) == []


def test_acquire_cds_control_plane_errors_are_sanitized(tmp_path, monkeypatch):
    driver, _raw_root, manifest_path = _driver(tmp_path, monkeypatch)
    boom = CdsApiError(
        "HTTP 500: https://api.example/x?token=TOPSECRET&jwt=JWTSECRET"
    )
    fake = FakeCds(submit_error=boom)
    with pytest.raises(AcquisitionError) as exc:
        driver.acquire_cds(dataset=DATASET, inputs=INPUTS, cds=fake)
    assert "TOPSECRET" not in str(exc.value)
    assert "JWTSECRET" not in str(exc.value)
    failures = _failures_in(load_acquisition_manifest(manifest_path))
    assert "TOPSECRET" not in (failures[0].error or "")
    assert "JWTSECRET" not in (failures[0].error or "")


def test_acquire_cds_available_utc_not_derived_from_headers(tmp_path, monkeypatch):
    driver, _raw_root, manifest_path = _driver(tmp_path, monkeypatch)
    fake = FakeCds(
        download_headers={
            "Date": "Wed, 01 Oct 2026 12:00:00 GMT",
            "Last-Modified": "Wed, 01 Oct 2026 00:00:00 GMT",
        }
    )
    record = driver.acquire_cds(
        dataset=DATASET, inputs=INPUTS, acquisition_key="2026-07-15t0000", cds=fake
    )
    assert record.available_utc is None
    assert record.availability_classification is None
    assert record.response_headers.get("date") == "Wed, 01 Oct 2026 12:00:00 GMT"
    assert record.response_headers.get("last-modified") == "Wed, 01 Oct 2026 00:00:00 GMT"


def test_acquire_cds_captures_content_length_header(tmp_path, monkeypatch):
    """3.7.5B: Content-Length is allowlisted evidence on the CDS artifact GET.

    Synthetic fixture: the artifact download response includes Content-Length
    and Last-Modified; both are persisted under the allowlisted keys, and the
    header is never promoted into ``available_utc``.
    """
    driver, _raw_root, manifest_path = _driver(tmp_path, monkeypatch)
    fake = FakeCds(
        download_headers={
            "Content-Length": "5120",
            "Last-Modified": "Wed, 01 Oct 2026 00:00:00 GMT",
        }
    )
    record = driver.acquire_cds(
        dataset=DATASET, inputs=INPUTS, acquisition_key="2026-07-15t0000", cds=fake
    )
    assert record.response_headers == {
        "content-length": "5120",
        "last-modified": "Wed, 01 Oct 2026 00:00:00 GMT",
    }
    assert record.file_size_bytes == len(fake.payload)
    assert record.available_utc is None
    assert record.availability_classification is None


def test_acquire_cds_artifact_bytes_sha_size_identical(tmp_path, monkeypatch):
    driver, raw_root, _manifest_path = _driver(tmp_path, monkeypatch)
    payload = b"\x00\x01binary artifact\r\n with trailing bytes"
    fake = FakeCds(payload=payload)
    record = driver.acquire_cds(
        dataset=DATASET, inputs=INPUTS, acquisition_key="2026-07-15t0000", cds=fake
    )
    assert record.sha256 == hashlib.sha256(payload).hexdigest()
    assert record.file_size_bytes == len(payload)
    assert (raw_root / record.storage_path).read_bytes() == payload


def test_acquire_cds_manifest_contract_version_unchanged(tmp_path, monkeypatch):
    driver, _raw_root, manifest_path = _driver(tmp_path, monkeypatch)
    driver.acquire_cds(
        dataset=DATASET, inputs=INPUTS, acquisition_key="2026-07-15t0000", cds=FakeCds()
    )
    assert load_acquisition_manifest(manifest_path).contract_version == "1.1.0"


# ---------------------------------------------------------------------------
# Phase 3.7.3C.4 -- control-plane redirect rejection and trusted-origin matrix
# ---------------------------------------------------------------------------


def _capture_get(monkeypatch, response):
    """Monkeypatch ``requests.get`` and record every call."""
    calls = []

    def get(url, headers=None, timeout=None, allow_redirects=None):
        calls.append(
            {"url": url, "headers": dict(headers or {}), "allow_redirects": allow_redirects}
        )
        return response

    monkeypatch.setattr(cds_service.requests, "get", get)
    return calls


def test_poll_rejects_cross_host_redirect(monkeypatch):
    transport = CdsTransport(api_url=FAKE_URL, api_key=FAKE_KEY)
    calls = _capture_get(
        monkeypatch,
        _Response(302, text="", headers={"location": "https://evil.example/stolen"}),
    )
    with pytest.raises(CdsApiError):
        transport.poll("job-1")
    assert len(calls) == 1
    assert calls[0]["allow_redirects"] is False
    assert calls[0]["url"].startswith(f"{FAKE_URL}/retrieve/v1/jobs/")


def test_results_rejects_https_to_http_redirect(monkeypatch):
    transport = CdsTransport(api_url=FAKE_URL, api_key=FAKE_KEY)
    calls = _capture_get(
        monkeypatch,
        _Response(301, text="", headers={"location": "http://cds.example.invalid/api/x"}),
    )
    with pytest.raises(CdsApiError):
        transport.results("job-1")
    assert len(calls) == 1
    assert calls[0]["allow_redirects"] is False


def test_poll_rejects_redirect_to_unexpected_port(monkeypatch):
    transport = CdsTransport(api_url=FAKE_URL, api_key=FAKE_KEY)
    calls = _capture_get(
        monkeypatch,
        _Response(307, text="", headers={"location": "https://cds.example.invalid:8443/api/x"}),
    )
    with pytest.raises(CdsApiError):
        transport.poll("job-1")
    assert len(calls) == 1
    assert calls[0]["allow_redirects"] is False


def test_submit_rejects_redirect_loop(monkeypatch):
    transport = CdsTransport(api_url=FAKE_URL, api_key=FAKE_KEY)
    calls = []

    def post(url, headers=None, json=None, timeout=None, allow_redirects=None):
        calls.append({"url": url, "allow_redirects": allow_redirects})
        return _Response(308, text="", headers={"location": url})

    monkeypatch.setattr(cds_service.requests, "post", post)
    with pytest.raises(CdsApiError):
        transport.submit(DATASET, INPUTS)
    assert len(calls) == 1
    assert calls[0]["allow_redirects"] is False
    assert "PRIVATE-TOKEN" not in str(calls)
    assert FAKE_KEY not in json.dumps(calls)


def test_poll_and_results_keep_authentication(monkeypatch):
    transport = CdsTransport(api_url=FAKE_URL, api_key=FAKE_KEY)
    calls = []

    def get(url, headers=None, timeout=None, allow_redirects=None):
        calls.append((url, dict(headers or {}), allow_redirects))
        if url.endswith("/results"):
            return _Response(200, {"asset": {"value": []}})
        return _Response(200, {"status": "running"})

    monkeypatch.setattr(cds_service.requests, "get", get)
    assert transport.poll("job-1") == ("running", None)
    assert transport.results("job-1") == []
    assert len(calls) == 2
    for url, headers, allow_redirects in calls:
        assert headers["PRIVATE-TOKEN"] == FAKE_KEY
        assert allow_redirects is False


def test_api_url_must_be_https_with_host():
    with pytest.raises(CdsError):
        CdsTransport(api_url="http://cds.example.invalid/api", api_key=FAKE_KEY)
    with pytest.raises(CdsError):
        CdsTransport(api_url="cds.example.invalid/api", api_key=FAKE_KEY)
    with pytest.raises(CdsError):
        CdsTransport(api_url="https:///api", api_key=FAKE_KEY)
    with pytest.raises(CdsError):
        CdsTransport(api_url="https://cds.example.invalid:badport/api", api_key=FAKE_KEY)


@pytest.mark.parametrize(
    "url,trusted",
    [
        (f"{FAKE_URL}/retrieve/v1/processes/x", True),
        ("https://cds.example.invalid/api", True),
        ("https://cds.example.invalid/api/", True),
        ("https://cds.example.invalid/api/retrieve/v1/x", True),
        ("https://cds.example.invalid/apix/x", False),
        ("https://cds.example.invalid/other/x", False),
        ("https://cds.example.invalid/", False),
        ("https://cds.example.invalid:443/api/x", True),
        ("https://cds.example.invalid:8443/api/x", False),
        ("http://cds.example.invalid/api/x", False),
        ("https://other.example/api/x", False),
        ("https://cds.example.invalid/api%2Fother/x", False),
        ("https://cds.example.invalid/api%5cx", False),
        ("https://cds.example.invalid/api/../other/x", False),
        ("https://cds.example.invalid/api/./retrieve/x", True),
        ("https://attacker@cds.example.invalid/api/x", True),
        ("https://cds.example.invalid@evil.example/api/x", False),
        ("https://cds.example.invalid:badport/api/x", False),
        ("https://cds.example.invalid/api/x?X-Amz-Signature=zzz", True),
        ("not-a-url", False),
        ("https://", False),
    ],
)
def test_trusted_origin_matrix(url, trusted):
    transport = CdsTransport(api_url=FAKE_URL, api_key=FAKE_KEY)
    assert transport._is_trusted_url(url) is trusted


def test_trusted_origin_trailing_slash_config():
    transport = CdsTransport(api_url="https://cds.example.invalid/api/", api_key=FAKE_KEY)
    assert transport._is_trusted_url("https://cds.example.invalid/api/retrieve/v1/x") is True
    assert transport._is_trusted_url("https://cds.example.invalid/apix/x") is False


def test_trusted_origin_empty_base_path():
    transport = CdsTransport(api_url="https://cds.example.invalid", api_key=FAKE_KEY)
    assert transport._is_trusted_url("https://cds.example.invalid/anything/here") is True
    assert transport._is_trusted_url("https://cds.example.invalid") is True
    assert transport._is_trusted_url("https://cds.example.invalid.evil/api") is False
    assert transport._is_trusted_url("http://cds.example.invalid/x") is False


# ---------------------------------------------------------------------------
# Phase 3.7.5C -- CDS job-state lifecycle evidence
# ---------------------------------------------------------------------------


def test_job_evidence_whitelists_job_state_fields():
    payload = {
        "jobID": "job-1",
        "processID": "reanalysis-era5-land",
        "status": "successful",
        "message": "request completed",
        "created": "2026-10-08T10:00:00Z",
        "started": "2026-10-08T10:00:01Z",
        "finished": "2026-10-08T10:00:09Z",
        "updated": "2026-10-08T10:00:09Z",
        "links": [
            {"rel": "self", "href": "https://cds.example.invalid/jobs/job-1?token=SECRET"}
        ],
        "href": "https://cds.example.invalid/results.nc?jwt=SECRET",
    }
    ev = job_evidence(payload, prefix="poll")
    assert ev == {
        "cds_poll_status": "successful",
        "cds_poll_created": "2026-10-08T10:00:00Z",
        "cds_poll_started": "2026-10-08T10:00:01Z",
        "cds_poll_finished": "2026-10-08T10:00:09Z",
        "cds_poll_updated": "2026-10-08T10:00:09Z",
    }


def test_job_evidence_omits_missing_nonstring_and_non_whitelisted_fields():
    payload = {
        "status": "running",
        "created": None,
        "started": 123456,
        "finished": "",
        "updated": "2026-10-08T10:05:00Z",
        "auth": "SUPERSECRET",
        "X-Amz-Signature": "ZZZ",
    }
    ev = job_evidence(payload, prefix="submit")
    assert ev == {
        "cds_submit_status": "running",
        "cds_submit_updated": "2026-10-08T10:05:00Z",
    }


def test_job_evidence_bounds_values():
    payload = {"status": "x" * 2000, "created": "2026-10-08T10:00:00Z"}
    ev = job_evidence(payload, prefix="poll")
    assert ev["cds_poll_status"] == "x" * 512
    assert ev["cds_poll_created"] == "2026-10-08T10:00:00Z"


def test_submit_with_evidence_returns_job_id_and_evidence(monkeypatch):
    transport = CdsTransport(api_url=FAKE_URL, api_key=FAKE_KEY)
    captured = _fake_post(
        monkeypatch,
        lambda c: _Response(
            201,
            {
                "jobID": "job-1",
                "processID": DATASET,
                "status": "accepted",
                "message": "accepted",
                "created": "2026-10-08T10:00:00Z",
                "started": "2026-10-08T10:00:01Z",
                "updated": "2026-10-08T10:00:02Z",
            },
        ),
    )
    submission = transport.submit_with_evidence(DATASET, INPUTS)
    assert isinstance(submission, CdsSubmission)
    assert submission.job_id == "job-1"
    assert submission.evidence["cds_submit_status"] == "accepted"
    assert submission.evidence["cds_submit_created"] == "2026-10-08T10:00:00Z"
    assert "cds_submit_finished" not in submission.evidence
    assert captured["allow_redirects"] is False
    assert transport.submit(DATASET, INPUTS) == "job-1"


def test_submit_with_evidence_rejects_non_object_payload(monkeypatch):
    transport = CdsTransport(api_url=FAKE_URL, api_key=FAKE_KEY)
    _fake_post(monkeypatch, lambda c: _Response(201, ["not", "an", "object"]))
    with pytest.raises(CdsMalformedResponse):
        transport.submit_with_evidence(DATASET, INPUTS)


def test_poll_evidence_captures_terminal_job_state(monkeypatch):
    transport = CdsTransport(api_url=FAKE_URL, api_key=FAKE_KEY)
    _fake_get(
        monkeypatch,
        {
            f"{FAKE_URL}/retrieve/v1/jobs/job-1": _Response(
                200,
                {
                    "jobID": "job-1",
                    "status": "successful",
                    "message": "request completed",
                    "created": "2026-10-08T10:00:00Z",
                    "started": "2026-10-08T10:00:01Z",
                    "finished": "2026-10-08T10:00:09Z",
                    "updated": "2026-10-08T10:00:09Z",
                },
            ),
        },
    )
    assert transport.poll("job-1") == ("successful", "request completed")
    assert transport.poll_evidence("job-1") == {
        "cds_poll_status": "successful",
        "cds_poll_created": "2026-10-08T10:00:00Z",
        "cds_poll_started": "2026-10-08T10:00:01Z",
        "cds_poll_finished": "2026-10-08T10:00:09Z",
        "cds_poll_updated": "2026-10-08T10:00:09Z",
    }


def test_poll_evidence_rejects_non_object_payload(monkeypatch):
    transport = CdsTransport(api_url=FAKE_URL, api_key=FAKE_KEY)
    _fake_get(monkeypatch, {f"{FAKE_URL}/retrieve/v1/jobs/job-1": _Response(200, 42)})
    with pytest.raises(CdsMalformedResponse):
        transport.poll_evidence("job-1")


def test_acquire_cds_persists_job_lifecycle_evidence(tmp_path, monkeypatch):
    driver, _raw_root, manifest_path = _driver(tmp_path, monkeypatch)
    fake = FakeCds(
        submit_evidence={
            "cds_submit_status": "accepted",
            "cds_submit_created": "2026-10-08T10:00:00Z",
            "cds_submit_started": "2026-10-08T10:00:01Z",
        },
        poll_evidence={
            "cds_poll_status": "successful",
            "cds_poll_created": "2026-10-08T10:00:00Z",
            "cds_poll_started": "2026-10-08T10:00:01Z",
            "cds_poll_finished": "2026-10-08T10:00:09Z",
            "cds_poll_updated": "2026-10-08T10:00:09Z",
        },
    )
    record = driver.acquire_cds(
        dataset=DATASET, inputs=INPUTS, acquisition_key="2026-07-15t0000", cds=fake
    )
    meta = record.provider_metadata
    assert meta["cds_submit_status"] == "accepted"
    assert meta["cds_submit_created"] == "2026-10-08T10:00:00Z"
    assert meta["cds_poll_status"] == "successful"
    assert meta["cds_poll_finished"] == "2026-10-08T10:00:09Z"
    assert meta["cds_poll_updated"] == "2026-10-08T10:00:09Z"
    assert meta["cds_lifecycle_note"].startswith("cds_submit_*/cds_poll_*")
    assert record.available_utc is None
    assert record.availability_classification is None
    assert record.observation_start_utc is None
    assert record.observation_end_utc is None
    assert fake.poll_evidence_calls == [fake.job_id]


def test_acquire_cds_fails_honestly_when_job_evidence_get_fails(tmp_path, monkeypatch):
    driver, raw_root, manifest_path = _driver(tmp_path, monkeypatch)
    fake = FakeCds(poll_evidence_error=CdsApiError("CDS job status GET failed"))
    with pytest.raises(AcquisitionError):
        driver.acquire_cds(dataset=DATASET, inputs=INPUTS, cds=fake)
    failures = _failures_in(load_acquisition_manifest(manifest_path))
    assert len(failures) == 1
    assert failures[0].source_record_id == "job-123"
    assert failures[0].storage_path is None
    assert list(raw_root.rglob("*")) == []


def test_acquire_cds_skipped_existing_keeps_lifecycle_evidence(tmp_path, monkeypatch):
    driver, _raw_root, manifest_path = _driver(tmp_path, monkeypatch)
    first = driver.acquire_cds(
        dataset=DATASET,
        inputs=INPUTS,
        acquisition_key="a1",
        cds=FakeCds(
            job_id="job-1",
            submit_evidence={"cds_submit_status": "accepted"},
            poll_evidence={"cds_poll_status": "successful"},
        ),
    )
    second = driver.acquire_cds(
        dataset=DATASET,
        inputs=INPUTS,
        acquisition_key="a2",
        cds=FakeCds(
            job_id="job-2",
            submit_evidence={"cds_submit_status": "accepted"},
            poll_evidence={},
        ),
    )
    assert second.status == "skipped_existing"
    assert second.provider_metadata["cds_submit_status"] == "accepted"
    assert "cds_poll_status" not in second.provider_metadata
    assert first.provider_metadata["cds_poll_status"] == "successful"