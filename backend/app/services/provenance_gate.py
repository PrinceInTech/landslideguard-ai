"""Provenance-gated prediction-input validation (Phase 3.20).

This service is the single integration point between the REAL-data feature
subsystem and the prediction workflow. It answers one question -- *are these
REAL-derived inputs eligible to be used for a prediction at this cutoff?* -- and
it answers it by calling the existing ``run_extraction`` pipeline unchanged.

What it deliberately does NOT do
--------------------------------
* It never calls ``app.ml.predictor`` (the DEMO-trained Random Forest). The
  DEMO model is trained on a synthetic dataset whose label leakage is documented
  (``docs/model.md``), so it cannot be fed REAL features and cannot produce a
  real-world prediction.
* It never fabricates a value. A feature the pipeline could not honestly produce
  keeps its honest status and ``None`` value.
* It adds no temporal, availability, identity, or decoding rule of its own: the
  protected ``app.services.features`` pipeline remains the single source of
  truth for every gate.
"""
from app.schemas.features import (
    FEATURE_SPECS,
    FeatureExtractionRequest,
    FeatureExtractionResult,
    FeatureStatus,
    FeatureValue,
)
from app.schemas.provenance_gate import (
    ProvenanceGateFeatureDecision,
    ProvenanceGateResponse,
)
from app.services.features import run_extraction

#: The feature columns the DEMO Random Forest consumes, in the vocabulary built
#: by ``app.ml.predictor`` (base_features + the saved label-encoder columns).
#: Kept here as an explicit, reviewed constant; ``test_provenance_gate.py``
#: cross-checks it against the shipped model bundle when the artifact loads.
DEMO_MODEL_FEATURE_COLUMNS = frozenset(
    {
        "rainfall",
        "rainfall_intensity",
        "soil_moisture",
        "temperature",
        "humidity",
        "elevation",
        "slope",
        "historical_occurrence",
        "distance_to_drain",
        "land_cover_enc",
        "soil_type_enc",
        "rock_type_enc",
    }
)

#: Concept pairs that *look* similar but are not interchangeable: the DEMO model
#: input and the REAL contract feature differ in unit and/or semantics, so a
#: mapping could only be produced by inventing one. Recorded so the incompatibility
#: reason is concrete rather than a bare assertion.
_UNIT_OR_SEMANTIC_MISMATCHES = (
    ("temperature", "temperature_2m_K", "DEMO input in degrees Celsius; REAL in kelvin"),
    ("soil_moisture", "soil_water_layer1_m3m3", "DEMO input a percentage; REAL a volumetric fraction"),
    ("rainfall", "precipitation_daily_mm", "DEMO input an event total; REAL a source-native daily accumulation"),
)

_DISCLAIMER = (
    "This is a provenance/availability validation report, not a landslide "
    "prediction. Passing the provenance gates means the inputs are traceable and "
    "eligible for the requested policy at the given cutoff; it is NOT evidence of "
    "predictive accuracy. No model was invoked and no real-world accuracy is claimed."
)

_PRODUCTION_READINESS_REASON = (
    "Frozen subsystem stance: the Q6 production gate remains CLOSED and the "
    "REAL-data subsystem stays production-ineligible until the external-evidence "
    "requirements are genuinely satisfied. A provenance-valid input does not "
    "change this."
)


def assess_demo_model_compatibility(
    real_feature_names: frozenset[str] | None = None,
) -> dict[str, object]:
    """Prove and describe why the DEMO model cannot consume REAL features.

    Returns a dict with the DEMO model's expected columns, the REAL contract's
    feature names, their intersection, and a human-readable reason. The
    intersection is empty and the namespace is disjoint, so there is no feature
    the model could accept without an invented mapping.
    """
    real = frozenset(real_feature_names) if real_feature_names is not None else frozenset(FEATURE_SPECS)
    shared = sorted(DEMO_MODEL_FEATURE_COLUMNS & real)
    mismatch_text = "; ".join(
        f"{demo} vs {real_name} ({why})" for demo, real_name, why in _UNIT_OR_SEMANTIC_MISMATCHES
    )
    reason = (
        f"The DEMO model expects {len(DEMO_MODEL_FEATURE_COLUMNS)} feature columns "
        f"({', '.join(sorted(DEMO_MODEL_FEATURE_COLUMNS))}); the REAL contract exposes "
        f"{len(real)} differently-named features ({', '.join(sorted(real))}). The two "
        f"vocabularies share {len(shared)} names, and even the closest pairs differ in "
        f"unit/semantics: {mismatch_text}. No REAL feature can be fed to the DEMO model "
        "without inventing a mapping, so the gate refuses to invoke the model."
    )
    return {
        "compatible": False,
        "demo_expected": sorted(DEMO_MODEL_FEATURE_COLUMNS),
        "real_available": sorted(real),
        "shared_feature_names": shared,
        "reason": reason,
    }


def _decision(feature: FeatureValue) -> ProvenanceGateFeatureDecision:
    prov = feature.provenance
    return ProvenanceGateFeatureDecision(
        feature_name=feature.feature_name,
        status=feature.status,
        value=feature.value,
        unit=feature.unit,
        reason=feature.note,
        accepted=feature.status is FeatureStatus.VALID,
        source_record_id=prov.source_record_id,
        artifact_sha256=prov.artifact_sha256,
        observation_start_utc=prov.observation_start_utc,
        observation_end_utc=prov.observation_end_utc,
        available_utc=prov.available_utc,
        availability_classification=prov.availability_classification,
    )


def _verdict(
    request: FeatureExtractionRequest,
    decisions: list[ProvenanceGateFeatureDecision],
) -> tuple[str, str, str]:
    """Return (verdict, verdict_reason, temporal_eligibility) from decisions."""
    if not decisions:
        return (
            "rejected",
            "no contract features were requested or produced for this source",
            "eligible",
        )

    rejected = [d for d in decisions if not d.accepted]
    leakage = [d for d in decisions if d.status is FeatureStatus.REJECTED_LEAKAGE]
    temporal = "rejected" if leakage else "eligible"

    if rejected:
        parts = [
            f"{d.feature_name}: {d.status.value}" + (f" ({d.reason})" if d.reason else "")
            for d in rejected
        ]
        return "rejected", "rejected by the provenance/availability gates: " + "; ".join(parts), temporal

    policy = request.availability_policy
    if policy == "production":
        return (
            "accepted_for_production",
            "every requested feature is valid and its availability evidence is "
            "provider_issued, so it clears the production availability policy at "
            "this cutoff",
            "eligible",
        )
    return (
        "accepted_for_research",
        "every requested feature is valid and its availability evidence clears the "
        "research_replay policy at this cutoff",
        "eligible",
    )


def run_provenance_gate(
    request: FeatureExtractionRequest,
) -> ProvenanceGateResponse:
    """Validate REAL inputs for a cutoff via the existing extraction pipeline.

    Raises whatever ``run_extraction`` raises (``ArtifactReadError`` /
    ``FeatureContractError`` / ``FileNotFoundError``); the API layer maps those to
    safe statuses. No model is invoked on any path.
    """
    result: FeatureExtractionResult = run_extraction(request)
    decisions = [_decision(f) for f in result.features]
    verdict, verdict_reason, temporal = _verdict(request, decisions)
    compatibility = assess_demo_model_compatibility()

    return ProvenanceGateResponse(
        model_compatibility_reason=compatibility["reason"],
        disclaimer=_DISCLAIMER,
        production_readiness_reason=_PRODUCTION_READINESS_REASON,
        availability_policy=request.availability_policy,
        verdict=verdict,
        verdict_reason=verdict_reason,
        temporal_eligibility=temporal,
        accepted_features=[d.feature_name for d in decisions if d.accepted],
        rejected_features=[d for d in decisions if not d.accepted],
        feature_decisions=decisions,
        result=result,
    )
