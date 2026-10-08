"""Minimal CDS (Climate Data Store) retrieve-API client (Phase 3.6).

The real CDS API is an asynchronous two-phase job flow -- submit an execution,
poll a job, then download the result reference -- which the synchronous
:class:`AcquisitionTransport` used by direct-download sources cannot express.
This module implements exactly that job-oriented subset, keeping the Personal
Access Token in memory (never logged, never persisted) and raising explicit
errors for every state the acquisition rig must record as an honest failure.

Official endpoints (verified live on the CDS on 2026-10-08):
    POST {base}/retrieve/v1/processes/{id}/execution  -> 201 {jobID, status, ...}
    GET  {base}/retrieve/v1/jobs/{job_id}             -> {status, message, ...}
    GET  {base}/retrieve/v1/jobs/{job_id}/results     -> {asset: {...}} assets
    GET  {href}                                       -> artifact bytes

Authentication: the Personal Access Token is sent as the PRIVATE-TOKEN header
(as declared in the public OpenAPI at ``{base}/retrieve/v1/openapi.json``).
"""

import time
from pathlib import Path
from typing import Any, Iterator

import requests

#: Job statuses that will never transition again.
TERMINAL_STATUSES = frozenset({"successful", "failed", "dismissed", "aborted", "cancelled"})
#: The only status that yields a downloadable artifact.
SUCCESS_STATUS = "successful"


class CdsError(Exception):
    """Base class for CDS client failures."""


class CdsAuthenticationError(CdsError):
    """The CDS API rejected the Personal Access Token."""


class CdsApiError(CdsError):
    """The CDS API returned an unexpected HTTP status for a well-formed request."""


class CdsJobFailed(CdsError):
    """The submitted job reached a terminal non-successful state."""

    def __init__(self, job_id: str, status: str, message: str | None = None):
        self.job_id = job_id
        self.status = status
        self.message = message
        detail = (message or "").strip() or "no provider message"
        super().__init__(f"CDS job {job_id} ended {status}: {detail}")


class CdsTimeout(CdsError):
    """The job did not reach a terminal state within the waiting budget."""


class CdsMalformedResponse(CdsError):
    """A response was parseable JSON but structurally wrong."""


def provider_sha256(asset: dict) -> str | None:
    """Return the provider-declared SHA-256 checksum of an asset, if present."""
    checksum = asset.get("file:checksum")
    if not isinstance(checksum, str) or len(checksum) != 64:
        return None
    try:
        int(checksum, 16)
    except ValueError:
        return None
    return checksum.lower()


def asset_extension(asset: dict) -> str:
    """Extension for storage from the asset filename (href/local_path)."""
    for key in ("file:local_path", "href"):
        raw = asset.get(key) if isinstance(asset.get(key), str) else ""
        name = raw.split("?", 1)[0].split("#", 1)[0].split("/")[-1]
        ext = Path(name).suffix
        if ext and len(ext) <= 12:
            return ext
    return ".bin"


class CdsTransport:
    """Async job-oriented client for the CDS retrieve API (injectable).

    Credentials are held in memory only. Instances are cheap; tests inject a
    deterministic stand-in with the same interface, so no network is touched by
    unit tests.
    """

    def __init__(
        self,
        *,
        api_url: str,
        api_key: str,
        timeout: int = 120,
        poll_interval_seconds: int = 5,
        max_wait_seconds: int = 1800,
    ):
        self._base = api_url.rstrip("/") + "/retrieve/v1"
        self._api_key = api_key
        self.timeout = timeout
        self.poll_interval_seconds = poll_interval_seconds
        self.max_wait_seconds = max_wait_seconds

    def _headers(self, accept: str = "application/json") -> dict:
        return {"PRIVATE-TOKEN": self._api_key, "Accept": accept}

    def submit(self, process_id: str, inputs: dict) -> str:
        """Submit an execution and return its job id (201 -> jobID)."""
        url = f"{self._base}/processes/{process_id}/execution"
        response = requests.post(
            url,
            headers=self._headers(),
            json={"inputs": dict(inputs), "response": "raw"},
            timeout=self.timeout,
        )
        if response.status_code == 401:
            raise CdsAuthenticationError("CDS rejected the Personal Access Token (HTTP 401)")
        if response.status_code != 201:
            raise CdsApiError(
                f"CDS execution POST returned HTTP {response.status_code}: {response.text[:300]}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise CdsMalformedResponse("CDS execution returned a non-JSON body") from exc
        job_id = payload.get("jobID")
        if not isinstance(job_id, str) or not job_id:
            raise CdsMalformedResponse(f"CDS execution response has no jobID: {payload!r}")
        return job_id

    def poll(self, job_id: str) -> tuple[str, str | None]:
        """Return ``(status, message)`` for one job."""
        response = requests.get(
            f"{self._base}/jobs/{job_id}", headers=self._headers(), timeout=self.timeout
        )
        if response.status_code != 200:
            raise CdsApiError(
                f"CDS job status GET returned HTTP {response.status_code}: {response.text[:300]}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise CdsMalformedResponse("CDS job status returned a non-JSON body") from exc
        status = payload.get("status")
        if not isinstance(status, str) or not status:
            raise CdsMalformedResponse(f"CDS job status has no status: {payload!r}")
        message = payload.get("message")
        return status, (message if isinstance(message, str) else None)

    def results(self, job_id: str) -> list[dict]:
        """Return the downloadable asset descriptors of a finished job."""
        response = requests.get(
            f"{self._base}/jobs/{job_id}/results", headers=self._headers(), timeout=self.timeout
        )
        if response.status_code != 200:
            raise CdsApiError(
                f"CDS job results GET returned HTTP {response.status_code}: {response.text[:300]}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise CdsMalformedResponse("CDS job results returned a non-JSON body") from exc
        return list(self._iter_assets(payload))

    @staticmethod
    def _iter_assets(node: Any) -> Iterator[dict]:
        """Depth-first walk collecting result asset descriptors (dicts with href)."""
        if isinstance(node, dict):
            if isinstance(node.get("href"), str):
                yield node
            for value in node.values():
                yield from CdsTransport._iter_assets(value)
        elif isinstance(node, list):
            for item in node:
                yield from CdsTransport._iter_assets(item)

    def download(self, url: str, headers: dict | None = None) -> bytes:
        response = requests.get(url, headers=headers or self._headers(), timeout=self.timeout)
        response.raise_for_status()
        return response.content

    def wait_for_success(self, job_id: str) -> tuple[str, str | None]:
        """Poll until terminal; return ``(status, message)`` on success.

        Raises :class:`CdsJobFailed` on a terminal failure and :class:`CdsTimeout`
        if the waiting budget is exhausted while the job is still running.
        """
        deadline = time.monotonic() + self.max_wait_seconds
        while True:
            status, message = self.poll(job_id)
            if status == SUCCESS_STATUS:
                return status, message
            if status in TERMINAL_STATUSES:
                raise CdsJobFailed(job_id, status, message)
            if time.monotonic() >= deadline:
                raise CdsTimeout(
                    f"CDS job {job_id} not terminal after {self.max_wait_seconds}s "
                    f"(status={status})"
                )
            time.sleep(self.poll_interval_seconds)