"""Provenance-gated prediction-input validation contract (Phase 3.20).

This module defines the response contract for the *provenance gate*: a thin,
auditable layer that validates whether REAL-derived features are eligible to be
used as prediction inputs, without ever invoking the DEMO-trained model.

Design rule (reuse, do not fork)
--------------------------------
The gate adds no new extraction, temporal, or availability semantics. It calls
the existing ``app.services.features.run_extraction`` pipeline unchanged, so the
identity check, leakage gate, availability gate, and decoders are the single
source of truth. The gate only:

* labels the response so a caller can never confuse it with a DEMO prediction
  (``prediction_mode``, ``is_prediction``, ``model_invoked``);
* records the DEMO model's incompatibility as an explicit, tested fact; and
* summarises the per-feature eligibility decisions already produced by the
  pipeline (accepted list, rejected list, reasons).

A provenance-valid input is NOT evidence of predictive accuracy. No real-world
accuracy is claimed and no value is ever fabricated: a rejected feature keeps a
``None`` value and its honest status.
"""
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field

from app.schemas.features import (
    AvailabilityClassification,
    AvailabilityPolicy,
    FeatureExtractionResult,
    FeatureStatus,
)

#: Value of ``prediction_mode`` for every provenance-gate response. It is
#: deliberately distinct from the DEMO prediction mode ("demo") so a client can
#: tell a validated-input report apart from a model prediction.
PROVENANCE_GATE_MODE = "provenance_gated_validation"

#: Statuses that mean a requested feature could not be honestly produced.
REJECTING_STATUSES = frozenset(
    {
        FeatureStatus.MISSING,
        FeatureStatus.INSUFFICIENT_TEMPORAL_COVERAGE,
        FeatureStatus.REJECTED_LEAKAGE,
        FeatureStatus.INVALID_SOURCE_ARTIFACT,
    }
)


class ProvenanceGateFeatureDecision(BaseModel):
    """Per-feature eligibility decision with its traceable source.

    Mirrors the fields a reviewer needs to audit one decision: the honest
    status, the (never fabricated) value, and the exact acquisition record and
    artifact the feature came from.
    """

    feature_name: str
    status: FeatureStatus
    value: float | None = None
    unit: str
    reason: str | None = Field(
        default=None,
        description="Human-readable reason for a non-valid status; None when valid.",
    )
    accepted: bool
    source_record_id: str
    artifact_sha256: str
    observation_start_utc: AwareDatetime
    observation_end_utc: AwareDatetime
    available_utc: AwareDatetime | None = None
    availability_classification: AvailabilityClassification | None = None


class ProvenanceGateResponse(BaseModel):
    """Auditable result of validating REAL inputs for a prediction cutoff.

    This is a validation report, not a prediction: ``is_prediction`` is always
    ``False`` and ``model_invoked`` is always ``False``.
    """

    # --- Mode / explicit labelling -----------------------------------------
    prediction_mode: Literal["provenance_gated_validation"] = PROVENANCE_GATE_MODE
    is_prediction: Literal[False] = False
    model_invoked: Literal[False] = False
    model: str = Field(
        default="none (DEMO model deliberately not invoked)",
        description="Identifies that no model ran; only provenance gates did.",
    )
    model_compatibility: Literal["incompatible"] = "incompatible"
    model_compatibility_reason: str = Field(
        description="Why the REAL feature vocabulary cannot feed the DEMO model."
    )
    disclaimer: str = Field(
        description="Explicit: provenance-valid inputs are not evidence of accuracy."
    )
    production_readiness: Literal["NO-GO"] = "NO-GO"
    production_readiness_reason: str = Field(
        description="The frozen subsystem stance (Q6 CLOSED), independent of the "
        "per-request availability policy."
    )

    # --- Gate decision ------------------------------------------------------
    availability_policy: AvailabilityPolicy
    verdict: Literal["accepted_for_research", "accepted_for_production", "rejected"]
    verdict_reason: str
    checksum_verification: Literal["verified"] = "verified"
    temporal_eligibility: Literal["eligible", "rejected"]
    accepted_features: list[str] = Field(default_factory=list)
    rejected_features: list[ProvenanceGateFeatureDecision] = Field(default_factory=list)
    feature_decisions: list[ProvenanceGateFeatureDecision] = Field(default_factory=list)

    # --- Traceability (full pipeline output, unchanged) --------------------
    result: FeatureExtractionResult
