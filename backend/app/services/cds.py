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

Job-state evidence: the 201 submission response and each job-status GET both
carry `status` plus the job-state timestamps `created`, `started`, `finished`
and `updated`. Those are retrieval-workflow timestamps, not dataset
vintage/availability, and are kept verbatim (raw strings) by the
job-state-evidence helpers so they can never be mistaken for availability
evidence in the ledger.

Authentication: the Personal Access Token is sent as the PRIVATE-TOKEN header
(as declared in the public OpenAPI at ``{base}/retrieve/v1/openapi.json``).
"""

import posixpath
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import unquote, urljoin, urlsplit

import requests

from app.redaction import bound_string

#: Job statuses that will never transition again.
TERMINAL_STATUSES = frozenset({"successful", "failed", "dismissed", "aborted", "cancelled"})
#: The only status that yields a downloadable artifact.
SUCCESS_STATUS = "successful"

#: GET status codes treated as redirects by the manual artifact-download loop.
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
#: Bound on redirect hops followed for one artifact download.
_MAX_REDIRECTS = 10
#: Default ports, used when a URL omits an explicit port.
_DEFAULT_PORTS = {"http": 80, "https": 443}


def _header_lookup(headers, name: str):
    """Case-insensitive header lookup that also tolerates plain dicts."""
    if not headers:
        return None
    try:
        value = headers.get(name)
    except AttributeError:
        return None
    if value is not None:
        return value
    lowered = name.lower()
    for key, value in headers.items():
        if str(key).lower() == lowered:
            return value
    return None


def _normalized_path(path: str | None) -> str | None:
    """Normalize a URL path for the trusted-origin path check.

    Returns ``None`` when the path cannot be trusted: an encoded path separator
    (``%2f``/``%5c``) may be decoded to ``/`` by a server and is rejected, as is
    any path whose dot segments resolve outside the configured base once
    percent-escapes are decoded. Literal ``.``/``..`` segments are collapsed so
    a crafted path cannot masquerade as sitting under the base while resolving
    elsewhere.
    """
    raw = path or "/"
    lowered = raw.lower()
    if "%2f" in lowered or "%5c" in lowered:
        return None
    decoded = unquote(raw)
    trailing = decoded.endswith("/")
    normalized = posixpath.normpath(decoded)
    if normalized == ".":
        normalized = "/"
    if trailing and not normalized.endswith("/"):
        normalized += "/"
    return normalized


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


@dataclass(frozen=True)
class CdsDownloadResult:
    """Outcome of one artifact download, including HTTP evidence.

    ``headers`` are the raw final-response headers (message casing preserved);
    the acquisition rig keeps only the allowlisted subset. ``final_url`` and
    ``redirect_chain`` are raw here and must be redacted before they reach the
    ledger. ``content`` is the artifact bytes, returned unmodified.
    """

    content: bytes
    status_code: int
    headers: dict[str, str]
    final_url: str
    redirect_chain: tuple[str, ...] = ()


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


#: The single scalar job-state signal kept from a CDS job payload.
_JOB_SCALAR_FIELDS = ("status",)
#: Job-state timestamps (official CDS field names) preserved verbatim from a
#: CDS job payload. They describe the retrieval workflow lifecycle -- when the
#: submission was created and when the processing started/finished/updated --
#: never the vintage or availability of the underlying dataset. Every value is
#: kept exactly as the provider returned it (raw string, no timezone
#: reinterpretation), so they can never be mistaken for availability evidence.
_JOB_TIMING_FIELDS = ("created", "started", "finished", "updated")


def job_evidence(payload: dict, *, prefix: str) -> dict[str, str]:
    """Whitelist the auditable job-state fields of a CDS job payload.

    Keeps ``status`` and the four job-state timestamps verbatim under the keys
    ``cds_{prefix}_{field}``, bounded like any other provider-controlled input.
    Everything else in the payload -- ``jobID``, ``processID``, ``links``,
    ``href``, ``message``, signed URLs, tokens -- is dropped so a secret can
    never reach the ledger through the evidence channel. Fields that are absent
    or not strings are simply omitted (never synthesized).
    """
    evidence: dict[str, str] = {}
    for name in _JOB_SCALAR_FIELDS + _JOB_TIMING_FIELDS:
        value = payload.get(name)
        if isinstance(value, str) and value:
            evidence[f"cds_{prefix}_{name}"] = bound_string(value)
    return evidence


@dataclass(frozen=True)
class CdsSubmission:
    """Outcome of a job submission: the job id plus auditable job evidence.

    ``evidence`` holds the whitelisted job-state fields (see
    :func:`job_evidence`) as raw strings; it is bounded but otherwise verbatim.
    """

    job_id: str
    evidence: dict[str, str] = field(default_factory=dict)


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
        try:
            parts = urlsplit(api_url)
            port = parts.port
        except ValueError as exc:
            raise CdsError(f"CDS API URL is not a valid URL: {api_url!r}") from exc
        scheme = (parts.scheme or "").lower()
        host = (parts.hostname or "").lower()
        if scheme != "https" or not host:
            raise CdsError(
                f"CDS API URL must be an https URL with a host: {api_url!r}"
            )
        self._base = api_url.rstrip("/") + "/retrieve/v1"
        self._api_scheme = scheme
        self._api_host = host
        self._api_port = port if port is not None else _DEFAULT_PORTS.get(scheme)
        self._trusted_path = (_normalized_path(parts.path) or "/").rstrip("/")
        self._api_key = api_key
        self.timeout = timeout
        self.poll_interval_seconds = poll_interval_seconds
        self.max_wait_seconds = max_wait_seconds

    def _headers(self, accept: str = "application/json") -> dict:
        return {"PRIVATE-TOKEN": self._api_key, "Accept": accept}

    def _in_trusted_path(self, path: str | None) -> bool:
        """True when a normalized ``path`` is at or below the API base path."""
        if path is None:
            return False
        base = self._trusted_path
        if not base:
            return True
        return path == base or path.startswith(base + "/")

    def _is_trusted_url(self, url: str) -> bool:
        """True only for an https URL on the configured CDS API origin.

        A URL is trusted only when its scheme, host and effective port exactly
        match the configured API URL *and* its path (percent-decoded and
        dot-segment-normalized) sits at or below the configured API base path.
        A same-host URL on a different port, an unrelated or ``..``-escaped
        path, an encoded path separator, or a plaintext ``http`` downgrade is
        not trusted and never receives the token. Userinfo is handled by
        ``urlsplit`` (hostname excludes it); a malformed URL or port is
        rejected rather than raising.
        """
        try:
            parts = urlsplit(url)
            port = parts.port
        except ValueError:
            return False
        scheme = (parts.scheme or "").lower()
        if scheme != "https" or scheme != self._api_scheme:
            return False
        if not self._api_host or (parts.hostname or "").lower() != self._api_host:
            return False
        effective_port = port if port is not None else _DEFAULT_PORTS.get(scheme)
        if effective_port != self._api_port:
            return False
        return self._in_trusted_path(_normalized_path(parts.path))

    def _download_headers(self, url: str) -> dict:
        """Headers for an artifact GET, scoped to the trusted CDS API origin.

        The Personal Access Token authenticates the CDS control plane. Artifact
        hrefs commonly point at a pre-signed third-party CDN host, so the token
        is attached only when the URL matches the trusted origin (https, exact
        host+port, path at/below the configured API base); otherwise only the
        minimum ``Accept`` header is sent. The token is never sent to an
        unverified external host, an http downgrade, or an off-path URL.
        """
        headers = {"Accept": "*/*"}
        if self._is_trusted_url(url):
            headers["PRIVATE-TOKEN"] = self._api_key
        return headers

    def submit(self, process_id: str, inputs: dict) -> str:
        """Submit an execution and return its job id (201 -> jobID).

        Backward-compatible wrapper: the actual work happens in
        :meth:`submit_with_evidence`, which additionally captures the job-state
        fields of the 201 response as auditable evidence.
        """
        return self.submit_with_evidence(process_id, inputs).job_id

    def submit_with_evidence(self, process_id: str, inputs: dict) -> CdsSubmission:
        """Submit an execution and return its job id plus job-state evidence.

        Redirects are rejected explicitly: the documented CDS endpoint issues
        none, and following one could forward ``PRIVATE-TOKEN`` to another
        origin (``requests`` strips only ``Authorization`` on a host change).
        """
        url = f"{self._base}/processes/{process_id}/execution"
        response = requests.post(
            url,
            headers=self._headers(),
            json={"inputs": dict(inputs), "response": "raw"},
            timeout=self.timeout,
            allow_redirects=False,
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
        if not isinstance(payload, dict):
            raise CdsMalformedResponse(f"CDS execution response is not a JSON object: {payload!r}")
        job_id = payload.get("jobID")
        if not isinstance(job_id, str) or not job_id:
            raise CdsMalformedResponse(f"CDS execution response has no jobID: {payload!r}")
        return CdsSubmission(job_id=job_id, evidence=job_evidence(payload, prefix="submit"))

    def poll(self, job_id: str) -> tuple[str, str | None]:
        """Return ``(status, message)`` for one job.

        Redirects are rejected explicitly (see :meth:`submit_with_evidence`).
        """
        payload = self._poll_payload(job_id)
        status = payload.get("status")
        if not isinstance(status, str) or not status:
            raise CdsMalformedResponse(f"CDS job status has no status: {payload!r}")
        message = payload.get("message")
        return status, (message if isinstance(message, str) else None)

    def _poll_payload(self, job_id: str) -> dict:
        """Fetch and return the parsed JSON payload of one job status GET."""
        response = requests.get(
            f"{self._base}/jobs/{job_id}",
            headers=self._headers(),
            timeout=self.timeout,
            allow_redirects=False,
        )
        if response.status_code != 200:
            raise CdsApiError(
                f"CDS job status GET returned HTTP {response.status_code}: {response.text[:300]}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise CdsMalformedResponse("CDS job status returned a non-JSON body") from exc
        if not isinstance(payload, dict):
            raise CdsMalformedResponse(f"CDS job status is not a JSON object: {payload!r}")
        return payload

    def poll_evidence(self, job_id: str) -> dict[str, str]:
        """Fetch a job status GET and return its whitelisted job-state evidence.

        Backward-compatible with :meth:`poll`; additionally captures the
        job-state fields of the response verbatim (see :func:`job_evidence`).
        """
        return job_evidence(self._poll_payload(job_id), prefix="poll")

    def results(self, job_id: str) -> list[dict]:
        """Return the downloadable asset descriptors of a finished job.

        Redirects are rejected explicitly (see :meth:`submit`).
        """
        response = requests.get(
            f"{self._base}/jobs/{job_id}/results",
            headers=self._headers(),
            timeout=self.timeout,
            allow_redirects=False,
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
        """Download an artifact and return its bytes (backward-compatible)."""
        return self.download_with_evidence(url, headers).content

    def download_with_evidence(
        self, url: str, headers: dict | None = None
    ) -> CdsDownloadResult:
        """Download an artifact, returning bytes plus HTTP evidence.

        Redirects are followed manually so the token is re-scoped on every hop:
        a redirect that leaves the trusted origin (external host, http
        downgrade, different port or off-path URL) drops the ``PRIVATE-TOKEN``
        header and can never carry the credential outwards. Bytes are returned
        exactly as received (never transformed). When ``headers`` is supplied it
        is used verbatim for every hop (caller-owned).
        """
        current = url
        history: list[str] = []
        for _ in range(_MAX_REDIRECTS + 1):
            request_headers = headers if headers is not None else self._download_headers(current)
            response = requests.get(
                current,
                headers=request_headers,
                timeout=self.timeout,
                allow_redirects=False,
            )
            location = _header_lookup(getattr(response, "headers", None), "location")
            if response.status_code in _REDIRECT_STATUSES and location:
                history.append(current)
                current = urljoin(current, location)
                continue
            response.raise_for_status()
            return CdsDownloadResult(
                content=response.content,
                status_code=response.status_code,
                headers=dict(response.headers),
                final_url=current,
                redirect_chain=tuple(history),
            )
        raise CdsApiError(f"CDS artifact download exceeded {_MAX_REDIRECTS} redirects")

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