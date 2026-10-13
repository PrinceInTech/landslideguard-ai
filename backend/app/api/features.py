"""Feature-extraction routes over the committed REAL artifacts.

This is the minimal HTTP surface for the feature contract implemented in
``app.services.features``. It adds no new extraction semantics: the same
``run_extraction`` pipeline -- identity check, leakage gate, availability gate,
decoders -- runs unchanged, so the route can never bypass a contract gate.

Policy: a valid bearer token is required (any authenticated ``viewer`` or
``admin``), matching the documented authorization model in ``docs/api.md`` and
the frontend, whose dashboard pages are auth-gated but not admin-gated.

Errors are mapped to safe responses. Reader/decoder failures name the on-disk
artifact, so they are reported as a fixed, path-free ``409`` rather than echoing
the exception; contract violations are reported as ``422`` with any absolute
filesystem path redacted. A leakage/availability rejection is **not** an error:
the pipeline returns ``200`` with ``rejected_leakage`` feature statuses, and no
value is ever fabricated.
"""
import re

from fastapi import APIRouter, Depends, HTTPException

from app.api.auth import get_current_user
from app.schemas.features import FeatureExtractionRequest, FeatureExtractionResult
from app.services.features import (
    ArtifactReadError,
    FeatureContractError,
    run_extraction,
)

router = APIRouter(prefix="/api", tags=["features"])

#: Absolute filesystem paths (drive-letter, UNC, or POSIX-rooted) that must never
#: appear in an API error detail.
_ABSOLUTE_PATH = re.compile(r"[A-Za-z]:\\[^\s'\"]*|\\\\[^\s'\"]*|/[^\s'\"]*")


def _public_detail(exc: FeatureContractError) -> str:
    """The contract message with any absolute filesystem path redacted."""
    text = str(exc).strip() or exc.__class__.__name__
    return _ABSOLUTE_PATH.sub("<path>", text)


@router.post("/extract", response_model=FeatureExtractionResult)
def extract_features(
    request: FeatureExtractionRequest,
    _user: object = Depends(get_current_user),
) -> FeatureExtractionResult:
    """Extract contract features for one point from the committed REAL artifacts.

    Returns the honest result: a leakage/availability rejection is reported as
    feature status ``rejected_leakage`` (with a reason note), never a fabricated
    value.
    """
    try:
        return run_extraction(request)
    except ArtifactReadError as exc:
        # The reader/decoder message embeds the on-disk artifact path; never
        # surface it. The identity check that runs first has already confirmed
        # the record matches the ledger, so this is a server-side data state.
        raise HTTPException(
            status_code=409,
            detail=(
                "the REAL artifact referenced by the selected record is "
                "unavailable or does not satisfy the feature contract; "
                "extraction was aborted"
            ),
        ) from exc
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=409,
            detail=(
                "the REAL artifact referenced by the selected record is "
                "unavailable; extraction was aborted"
            ),
        ) from exc
    except FeatureContractError as exc:
        raise HTTPException(status_code=422, detail=_public_detail(exc)) from exc
