"""Shared redaction helpers (Phase 3.7.3B.5).

Single source of truth for stripping secrets from URLs, error messages and
provider-supplied metadata *before* anything reaches the committed ledger.

Standard-library only, so both ``app.schemas.acquisition`` and
``app.services.acquisition`` can import it without an import cycle.

All helpers fail closed: input that cannot be parsed safely is conservatively
stripped (fragments/queries/userinfo removed) rather than returned unchanged.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

#: Hard cap on any string persisted from provider-controlled input (response
#: headers, provider metadata). Prevents a hostile server bloating the ledger.
MAX_HEADER_VALUE_LENGTH = 512

#: Limits for the free-form ``provider_metadata`` mapping.
MAX_PROVIDER_METADATA_KEYS = 32
MAX_PROVIDER_METADATA_KEY_LENGTH = 128

#: Substrings that mark a key as credential-like. Matched case-insensitively as
#: a substring so ``X-Amz-Signature``, ``access_token`` and ``api_key`` all
#: match. Over-redaction (e.g. ``keywords``) is accepted as the safe default.
SENSITIVE_KEY_SUBSTRINGS: tuple[str, ...] = (
    "token",
    "jwt",
    "key",
    "api_key",
    "apikey",
    "secret",
    "password",
    "auth",
    "sig",
    "signature",
    "credential",
)

#: Query-parameter names whose values are credentials/signatures.
_SENSITIVE_QUERY_RE = re.compile(
    r"(token|jwt|key|api_key|apikey|secret|password|auth|sig|signature|credential|expires)",
    re.IGNORECASE,
)

#: Control characters are never valid in a header/metadata value and can hide
#: log-injection payloads, so they are stripped.
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")

#: URL-like substrings embedded in free text (error messages).
_URL_IN_TEXT_RE = re.compile(r"(?:https?|ftp)://[^\s<>\"'`]+", re.IGNORECASE)

#: ``key=value`` / ``key: value`` secrets embedded in free text.
_KV_IN_TEXT_RE = re.compile(
    r"(?i)\b([A-Za-z0-9_.\-]*"
    r"(?:token|jwt|api[_-]?key|apikey|secret|password|auth|sig|signature|credential)"
    r"[A-Za-z0-9_.\-]*)"
    r"\s*[=:]\s*([^\s&,;]+)"
)

#: Scheme credentials in an authorization field, e.g.
#: ``Authorization: Bearer <token>`` / ``Proxy-Authorization: Basic <b64>``.
#: Case-insensitive; the field name and scheme are preserved for diagnostics.
_AUTH_SCHEME_RE = re.compile(
    r"(?i)\b((?:proxy-)?authorization)\s*[:=]\s*"
    r"(bearer|basic|digest|token|apikey|api[_-]?key|hmac)\b\s+(\S+)"
)

#: Bare ``Bearer``/``Basic``/``Digest`` scheme credentials with no field name.
_BARE_SCHEME_RE = re.compile(r"(?i)\b(bearer|basic|digest)\s+(\S+)")

#: A credential-shaped token: at least eight chars and containing a digit or a
#: symbol typical of tokens/keys (so prose like ``basic authentication`` is not
#: redacted, while real tokens are).
_CREDENTIAL_SHAPE_RE = re.compile(r"[0-9._~+/=-]")

#: Candidate tokens scanned for percent-encoded URLs.
_ENCODED_TOKEN_RE = re.compile(r"[^\s<>\"'`]{8,}")

#: A real URL scheme anywhere inside a decoded token. Unlike an anchored match
#: this tolerates a literal prefix (``(``, ``[``, ``url=``, ``url:`` ...) glued
#: directly to a percent-encoded URL.
_URL_ANYWHERE_RE = re.compile(r"(?i)(?:https?|ftp)://")

#: Closing punctuation that may immediately trail an embedded URL. Preserved
#: verbatim so ordinary surrounding text survives redaction.
_TRAILING_URL_CLOSERS = ")]}"

#: Bound on iterative (never recursive) percent-decoding of candidate tokens.
_MAX_UNQUOTE_ROUNDS = 4


def strip_control_chars(text: str) -> str:
    """Remove control characters (including CR/LF) from ``text``."""
    return _CONTROL_RE.sub("", text)


def bound_string(value: object, max_length: int = MAX_HEADER_VALUE_LENGTH) -> str:
    """Stringify ``value``, strip control characters and truncate to a bound."""
    return strip_control_chars(str(value))[:max_length]


def is_sensitive_key(key: object) -> bool:
    """True when ``key`` looks like it names a credential/signature."""
    lowered = str(key).lower()
    return any(token in lowered for token in SENSITIVE_KEY_SUBSTRINGS)


def _conservative_url_strip(url: str) -> str:
    """Fail-closed best effort for a URL that could not be parsed.

    Drops the ``#fragment`` and the entire query string, then removes any
    userinfo. Coarse -- it discards non-secret query values too -- but never
    lets a secret survive an unparseable URL.
    """
    stripped = url.split("#", 1)[0].split("?", 1)[0]
    scheme_sep = stripped.find("://")
    prefix = ""
    rest = stripped
    if scheme_sep != -1:
        prefix = stripped[: scheme_sep + 3]
        rest = stripped[scheme_sep + 3 :]
    end = len(rest)
    for delim in ("/", "\\"):
        idx = rest.find(delim)
        if idx != -1:
            end = min(end, idx)
    authority = rest[:end]
    tail = rest[end:]
    if "@" in authority:
        authority = authority.rsplit("@", 1)[1]
    return prefix + authority + tail


def redact_url(url: str | None) -> tuple[str | None, list[str]]:
    """Return ``(redacted_url, redacted_param_names)``; never leaks a secret.

    Strips ``user:pass@`` userinfo, drops the ``#fragment`` and replaces the
    value of any sensitive query parameter with ``REDACTED``. Scheme, host, path
    and non-sensitive query keys are preserved. The returned names make the
    redaction auditable from the ledger alone. Unparseable input fails closed
    through :func:`_conservative_url_strip`.
    """
    if not isinstance(url, str) or not url:
        return url, []
    try:
        parts = urlsplit(url)
    except ValueError:
        return _conservative_url_strip(url), []
    netloc = parts.netloc
    if "@" in netloc:
        netloc = netloc.rsplit("@", 1)[1]
    redacted_names: list[str] = []
    new_pairs: list[tuple[str, str]] = []
    for name, value in parse_qsl(parts.query, keep_blank_values=True):
        if _SENSITIVE_QUERY_RE.search(name):
            new_pairs.append((name, "REDACTED"))
            redacted_names.append(name)
        else:
            new_pairs.append((name, value))
    redacted = urlunsplit((parts.scheme, netloc, parts.path, urlencode(new_pairs), ""))
    return redacted, redacted_names


def _bounded_unquote(value: str, rounds: int = _MAX_UNQUOTE_ROUNDS) -> str:
    """Percent-decode at most ``rounds`` times; iterative, never recursive.

    Bounded so nested encoding is handled a known number of times, and the result
    is only ever used for detection/redaction -- never fed back into a URL or a
    filesystem path -- so there is no double-decoding vulnerability.
    """
    for _ in range(rounds):
        decoded = unquote(value)
        if decoded == value:
            break
        value = decoded
    return value


def _looks_like_credential(value: str) -> bool:
    """True when a bare scheme suffix looks like a credential, not prose.

    Requires at least eight characters and a digit or token symbol, so
    ``basic authentication`` is left intact while real tokens are redacted.
    """
    core = value.strip(".,;:)]}'\"").strip()
    return len(core) >= 8 and bool(_CREDENTIAL_SHAPE_RE.search(core))


def redact_text(text: str | None) -> tuple[str | None, list[str]]:
    """Redact secrets embedded in a free-text message (e.g. an exception str).

    Handles, in order: literal URLs (query/userinfo/fragment), percent-encoded
    URLs (bounded decoding, including when a literal prefix such as ``url=`` or
    ``(`` is glued to the encoded URL), ``Authorization``/scheme credentials
    (case-insensitive), and generic ``key=value``/``key: value`` secrets. Returns
    the sanitised text and the names of everything redacted. Control characters
    are stripped from the result.
    """
    if not isinstance(text, str) or not text:
        return text, []
    names: list[str] = []

    def _url_sub(match: re.Match) -> str:
        redacted, url_names = redact_url(match.group(0))
        names.extend(url_names)
        return redacted or ""

    def _encoded_url_sub(match: re.Match) -> str:
        token = match.group(0)
        if "%" not in token:
            return token
        decoded = _bounded_unquote(token)
        if decoded == token:
            return token
        found = _URL_ANYWHERE_RE.search(decoded)
        if found is None:
            return token
        prefix = decoded[: found.start()]
        url_part = decoded[found.start():]
        trailing = ""
        while url_part and url_part[-1] in _TRAILING_URL_CLOSERS:
            trailing = url_part[-1] + trailing
            url_part = url_part[:-1]
        if not url_part:
            return token
        redacted, url_names = redact_url(url_part)
        names.extend(url_names)
        return prefix + (redacted or "REDACTED") + trailing

    def _auth_scheme_sub(match: re.Match) -> str:
        field, scheme = match.group(1), match.group(2)
        names.append(scheme)
        return f"{field}: {scheme} REDACTED"

    def _bare_scheme_sub(match: re.Match) -> str:
        scheme, value = match.group(1), match.group(2)
        if not _looks_like_credential(value):
            return match.group(0)
        names.append(scheme)
        return f"{scheme} REDACTED"

    def _kv_sub(match: re.Match) -> str:
        names.append(match.group(1))
        return f"{match.group(1)}=REDACTED"

    redacted_text = _URL_IN_TEXT_RE.sub(_url_sub, text)
    redacted_text = _ENCODED_TOKEN_RE.sub(_encoded_url_sub, redacted_text)
    redacted_text = _AUTH_SCHEME_RE.sub(_auth_scheme_sub, redacted_text)
    redacted_text = _BARE_SCHEME_RE.sub(_bare_scheme_sub, redacted_text)
    redacted_text = _KV_IN_TEXT_RE.sub(_kv_sub, redacted_text)
    return strip_control_chars(redacted_text), sorted(set(names))
