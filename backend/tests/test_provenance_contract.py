"""Provenance / data-contract tests (Phase 2.2).

Covers the typed record + source schemas, the DEMO/REAL kind coupling, and the
committed manifest: it must parse, every artifact checksum must match the file
on disk, and it must agree with ml/model/model_meta.json on the training data.
"""
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.provenance import (
    DataQualityFlags,
    FieldMapping,
    GeographicCoverage,
    ManifestArtifact,
    ProvenanceManifest,
    RecordProvenance,
    SourceProvenance,
    TemporalCoverage,
)
from app.services.provenance import (
    ProvenanceContractError,
    load_manifest,
    sha256_of,
    validate_record_source_match,
    verify_artifact_checksums,
)

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
MANIFEST_PATH = PROJECT_ROOT / "data" / "provenance" / "manifest.json"
MODEL_META = PROJECT_ROOT / "ml" / "model" / "model_meta.json"
DATASET = PROJECT_ROOT / "data" / "historical_landslide_data.csv"

UTC = timezone.utc


def _real_record(**overrides) -> RecordProvenance:
    values = {
        "event_id": "evt-0001",
        "prediction_cutoff_utc": datetime(2026, 10, 8, 3, 30, tzinfo=UTC),
        "latitude": 25.67,
        "longitude": 94.11,
        "coordinate_precision": 0.01,
        "source": "openweathermap-current",
        "source_record_id": "owm-1234",
        "feature_source": "ECMWF-ERA5",
        "feature_source_version": "5",
        "data_quality": DataQualityFlags(note="test fixture"),
    }
    values.update(overrides)
    return RecordProvenance(**values)


def _demo_source(**overrides) -> SourceProvenance:
    values = {
        "name": "landslideguard-demo-generator",
        "kind": "DEMO",
        "access_reference": "ml/data/generate_data.py",
        "license_attribution": "None - generated in-repo",
        "retrieved_utc": None,
        "source_checksum": "3bdd9e9cf1d907d149f8ba1d7e58094e22727a5672299bc0c2c2346b383bdabb",
        "file_size_bytes": 223559,
        "geographic_coverage": GeographicCoverage(
            min_latitude=22.882,
            max_latitude=27.999,
            min_longitude=88.2238,
            max_longitude=95.04,
        ),
        "temporal_coverage": TemporalCoverage(start=date(2018, 1, 1), end=date(2025, 11, 20)),
        "field_mapping": [FieldMapping(source_column="rainfall", contract_field="rainfall")],
        "known_limitations": ["DEMO/synthetic data"],
    }
    values.update(overrides)
    return SourceProvenance(**values)


# ---------- Record schema ----------


def test_complete_real_record_validates_and_roundtrips():
    record = _real_record()
    raw = record.model_dump_json()
    assert RecordProvenance.model_validate_json(raw) == record
    assert record.kind == "REAL"


@pytest.mark.parametrize("field,bad", [("latitude", 91.0), ("latitude", -91.0), ("longitude", 181.0), ("longitude", -181.0)])
def test_record_rejects_out_of_range_coordinates(field, bad):
    with pytest.raises(ValidationError):
        _real_record(**{field: bad})


def test_record_rejects_naive_cutoff_datetime():
    with pytest.raises(ValidationError):
        _real_record(prediction_cutoff_utc=datetime(2026, 10, 8, 3, 30))


def test_record_accepts_utc_cutoff_datetime():
    record = _real_record(prediction_cutoff_utc=datetime(2026, 10, 8, 3, 30, tzinfo=UTC))
    assert record.prediction_cutoff_utc.tzinfo is not None


@pytest.mark.parametrize("precision", [0.0, -0.1, 361.0])
def test_record_rejects_invalid_coordinate_precision(precision):
    with pytest.raises(ValidationError):
        _real_record(coordinate_precision=precision)


def test_data_quality_flags_default_to_clean():
    flags = DataQualityFlags()
    assert flags.missing_fields == []
    assert flags.interpolated is False
    assert flags.schema_conformance is True


# ---------- Source schema ----------


@pytest.mark.parametrize(
    "checksum",
    [
        "not-hex-" * 8,  # wrong content
        "3bdd9e9cf1d907d149f8ba1d7e58094e22727a5672299bc0c2c2346b383bda",  # 63 hex
        "3bdd9e9cf1d907d149f8ba1d7e58094e22727a5672299bc0c2c2346b383bdabb0",  # 65 hex
    ],
)
def test_source_rejects_malformed_checksum(checksum):
    with pytest.raises(ValidationError):
        _demo_source(source_checksum=checksum)


def test_geographic_coverage_rejects_inverted_bounds():
    with pytest.raises(ValidationError):
        GeographicCoverage(min_latitude=30, max_latitude=20, min_longitude=80, max_longitude=90)


def test_temporal_coverage_rejects_inverted_bounds():
    with pytest.raises(ValidationError):
        TemporalCoverage(start=date(2020, 1, 1), end=date(2019, 1, 1))


# ---------- DEMO/REAL coupling ----------


def test_real_record_cannot_claim_demo_source():
    demo = _demo_source()
    record = _real_record(source=demo.name)
    with pytest.raises(ProvenanceContractError):
        validate_record_source_match(record, demo)


def test_record_source_must_match_registered_source_name():
    demo = _demo_source()
    demo_record = _real_record(source=demo.name, kind="DEMO")
    mismatched = _real_record(source="some-other-source", kind="DEMO")
    validate_record_source_match(demo_record, demo)
    with pytest.raises(ProvenanceContractError):
        validate_record_source_match(mismatched, demo)


# ---------- Manifest ----------


def test_manifest_file_exists_and_parses():
    assert MANIFEST_PATH.exists(), "data/provenance/manifest.json must be committed"
    manifest = load_manifest(MANIFEST_PATH)
    assert isinstance(manifest, ProvenanceManifest)
    assert manifest.contract_version == "1.0.0"
    assert manifest.artifacts, "manifest must register the committed artifacts"
    assert manifest.generated_at_utc.tzinfo is not None


def test_manifest_registers_no_real_source_yet():
    """Honesty guard: nothing fabricated. REAL sources appear only on acquisition."""
    manifest = load_manifest(MANIFEST_PATH)
    assert all(source.kind == "DEMO" for source in manifest.sources)


def test_manifest_artifact_checksums_match_committed_files():
    assert verify_artifact_checksums() == [], "a committed artifact drifted from the manifest"


def test_manifest_training_data_matches_model_meta_and_file():
    manifest = load_manifest(MANIFEST_PATH)
    training = next(a for a in manifest.artifacts if a.role == "training-data")
    assert training.path == "data/historical_landslide_data.csv"
    meta = json.loads(MODEL_META.read_text(encoding="utf-8"))
    assert training.sha256 == meta["dataset_sha256"]
    assert training.sha256 == sha256_of(DATASET)


def test_demo_source_is_registered_honestly():
    manifest = load_manifest(MANIFEST_PATH)
    demo = next(s for s in manifest.sources if s.kind == "DEMO")
    assert demo.name == "landslideguard-demo-generator"
    assert demo.license_attribution
    assert demo.retrieved_utc is None, "synthetic in-repo data is generated, not retrieved"
    limitations = " ".join(demo.known_limitations).lower()
    assert "synthetic" in limitations or "demo" in limitations
    # Coverage box must contain the actual dataset span.
    assert demo.geographic_coverage.min_latitude <= 22.882
    assert demo.geographic_coverage.max_latitude >= 27.999
    assert demo.geographic_coverage.min_longitude <= 88.2238
    assert demo.geographic_coverage.max_longitude >= 95.04
    assert demo.field_mapping, "schema/column mapping is required"


def test_raw_data_directory_is_ignored_and_documented():
    raw_dir = PROJECT_ROOT / "data" / "raw"
    assert (raw_dir / ".gitignore").exists(), "data/raw must be git-ignored"
    assert (raw_dir / "README.md").exists(), "data/raw needs a policy README"
    gitignore = (raw_dir / ".gitignore").read_text(encoding="utf-8")
    assert "*" in gitignore, "data/raw/* must be ignored so raw files never commit"