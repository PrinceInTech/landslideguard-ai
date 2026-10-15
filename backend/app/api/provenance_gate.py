"""Provenance-gated prediction-input validation route (Phase 3.20).

This route exposes the provenance gate: it takes the same request as
``/api/extract`` (an explicit prediction cutoff + position + source + requested
features) and returns an explicit *validation* report -- never a prediction. It
reuses ``app.services.provenance_gate.run_provenance_gate``, which calls the
protected ``run_extraction`` pipeline unchanged, so no gate can be bypassed and
no value is ever fabricated.

The DEMO model is never invoked here. Error handling mirrors ``/api/extract``:
reader/decoder failures become a path-free ``409``; contract violations become a
``422`` with any absolute filesystem path redacted.
"""
import re

from fastapi import APIRouter, Depends, HTTPException

from app.api.auth import get_current_user
from app.schemas.features import FeatureExtractionRequest
from app.schemas.provenance_gate import ProvenanceGateResponse
from app.services.features import ArtifactReadError, FeatureContractError
from app.services.provenance_gate import run_provenance_gate

router = APIRouter(prefix="/api", tags=["provenance"])

#: Absolute filesystem paths (drive-letter, UNC, or POSIX-rooted) that must never
#: appear in an API error detail.
_ABSOLUTE_PATH = re.compile(r"[A-Za-z]:\\[^\s'\"]*|\\\\[^\s'\"]*|/[^\s'\"]*")


def _public_detail(exc: FeatureContractError) -> str:
    """The contract message with any absolute filesystem path redacted."""
    text = str(exc).strip() or exc.__class__.__name__
    return _ABSOLUTE_PATH.sub("<path>", text)


@router.post("/provenance/validate", response_model=ProvenanceGateResponse)
def validate_provenance(
    request: FeatureExtractionRequest,
    _user: object = Depends(get_current_user),
) -> ProvenanceGateResponse:
    """Validate REAL inputs for one prediction cutoff without invoking a model.

    The response is explicitly labelled ``prediction_mode =
    "provenance_gated_validation"`` with ``is_prediction = False`` and
    ``model_invoked = False``. A rejection is an honest ``200`` report with the
    per-feature reasons, not an error and never a fabricated value.
    """
    try:
        return run_provenance_gate(request)
    except ArtifactReadError as exc:
        raise HTTPException(
            status_code=409,
            detail=(
                "the REAL artifact referenced by the selected record is "
                "unavailable or does not satisfy the feature contract; "
                "validation was aborted"
            ),
        ) from exc
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=409,
            detail=(
                "the REAL artifact referenced by the selected record is "
                "unavailable; validation was aborted"
            ),
        ) from exc
    except FeatureContractError as exc:
        raise HTTPException(status_code=422, detail=_public_detail(exc)) from exc
