"""REAL-data feature-extraction contract tests (Phase 3.7.1).

Covers the typed feature contract and its leakage-safe, honest extraction from
the acquired REAL artifacts: CHIRPS daily precipitation and ERA5-Land t2m / tp
/ swvl1 / sro. Grids are bounded fixtures that mirror the real artifact
geometry (0.05 deg CHIRPS with -9999 fill; 0.1 deg ERA5-Land NetCDF with
_FillValue); real-artifact integration is skip-guarded on local file presence
so the suite never needs to download or depend on network access.

Every listed contract property gets at least one direct test: the leakage
gate, nodata semantics, CRS/bbox enforcement, rolling-window honesty, artifact
identity (SHA-256), and provenance propagation.
"""
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from app.schemas.acquisition import (
    AcquisitionManifest,
    AcquisitionRecord,
    AcquisitionStatus,
)
from app.schemas.features import (
    CANONICAL_CRS,
    CHIRPS_NODATA,
COORDINATE_PRECISION_BY_SOURCE,
    FEATURE_SPECS,
    FeatureDayProvenance,
    FeatureExtractionRequest,
    FeatureProvenance,
    FeatureStatus,
    Position,
    StudyRegion,
    STUDY_REGION_EAST,
    STUDY_REGION_NORTH,
    STUDY_REGION_SOUTH,
    STUDY_REGION_WEST,
    supported_features,
)
from app.services.features import (
    FeatureContractError,
    _leakage_rejected_note,
    artifact_path,
    build_feature_provenance,
    chirps_daily_coverage_days,
coerce_to_missing,
    evaluate_leakage,
    evaluate_availability_policy,
    require_epsg4326,
    resolve_acquired_record,
    run_extraction,
    sample_grid,
)
from app.services.provenance import sha256_of

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
REAL_ERA5 = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "real"
    / "era5-land"
    / "era5-land__operational-consolidated-2-months-era5-land-t-5-days__2026-07-15t0000.nc"
)
REAL_CHIRPS = (
    PROJECT_ROOT / "data" / "raw" / "real" / "chirps" / "chirps__v2.x__2026-08-31.tif.gz"
)
LEDGER = PROJECT_ROOT / "data" / "provenance" / "acquisition_manifest.json"

CHIRPS_SHA = "449346515d840eeb4bf5c613a344777afe317800269386f2e93fdb3943a8d9a6"
ERA5_SHA = "af53a81a84460ab9abaf209f4535584e4c85404dbbb89b39e06db8f9c0824ac9"

VALID_CUTOFF = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)


def _chirps_record(**overrides) -> AcquisitionRecord:
    values = {
        "record_id": "REAL-chirps-v2.0-2026-08-31",
        "source": "chirps",
        "product": "CHIRPS v2 quasi-global precipitation (0.05 deg, daily/pentad/monthly)",
        "product_version": "v2.0",
        "kind": "REAL",
        "status": AcquisitionStatus.DOWNLOADED,
        "access_reference": "https://data.chc.ucsb.edu/products/CHIRPS-2.0/",
        "source_record_id": "chirps-v2.0.2026.08.31.tif.gz",
        "retrieval_params": {"url": "https://data.chc.ucsb.edu/…/chirps-v2.0.2026.08.31.tif.gz"},
        "retrieved_utc": datetime(2026, 10, 8, 9, 28, 3, tzinfo=UTC),
        "acquired_utc": datetime(2026, 10, 8, 9, 28, 21, tzinfo=UTC),
        "observation_start_utc": datetime(2026, 8, 31, 0, 0, tzinfo=UTC),
        "observation_end_utc": datetime(2026, 9, 1, 0, 0, tzinfo=UTC),
        "available_utc": datetime(2026, 9, 11, 21, 10, 59, tzinfo=UTC),
        "geographic_coverage": None,
        "crs": "EPSG:4326 (WGS84)",
        "license_attribution": "Per CHC CHIRPS data use policy (public dataset).",
        "sha256": CHIRPS_SHA,
        "file_size_bytes": 10288665,
        "storage_path": "chirps/chirps__v2.x__2026-08-31.tif.gz",
        "known_limitations": [],
        "error": None,
    }
    values.update(overrides)
    return AcquisitionRecord(**values)


def _era5_record(**overrides) -> AcquisitionRecord:
    values = {
        "record_id": "REAL-era5-land-operational-consolidated-2-months-era5-land-t-5-days-2026-07-15t0000",
        "source": "era5-land",
        "product": "ERA5-Land hourly reanalysis (land surface)",
        "product_version": "operational (consolidated ~2 months; ERA5-Land-T ~5 days)",
        "kind": "REAL",
        "status": AcquisitionStatus.DOWNLOADED,
        "access_reference": "Copernicus Climate Data Store (CDS). DOI 10.24381/cds.e2161bac",
        "source_record_id": "4548c91f-9c24-48c3-8e55-12c4ab786ae6",
        "retrieval_params": {"dataset": "reanalysis-era5-land"},
        "retrieved_utc": datetime(2026, 10, 8, 11, 9, 48, tzinfo=UTC),
        "acquired_utc": datetime(2026, 10, 8, 11, 9, 48, tzinfo=UTC),
        "observation_start_utc": datetime(2026, 7, 15, 0, 0, tzinfo=UTC),
        "observation_end_utc": datetime(2026, 7, 15, 1, 0, tzinfo=UTC),
        "available_utc": datetime(2026, 9, 15, 0, 0, tzinfo=UTC),
        "geographic_coverage": None,
        "crs": "EPSG:4326 (WGS84 lat/lon grid)",
        "license_attribution": "Copernicus licence; CC-BY attribution required.",
        "sha256": ERA5_SHA,
        "file_size_bytes": 127970,
        "storage_path": "era5-land/era5-land__operational-consolidated-2-months-era5-land-t-5-days__2026-07-15t0000.nc",
        "known_limitations": [],
        "error": None,
    }
    values.update(overrides)
    return AcquisitionRecord(**values)


def _manifest(*records: AcquisitionRecord) -> AcquisitionManifest:
    return AcquisitionManifest(
        generated_at_utc=datetime(2026, 10, 8, 12, 0, tzinfo=UTC), records=list(records)
    )


# ---------------------------------------------------------------------------
# Fixture scratch artifacts + grids
# ---------------------------------------------------------------------------


@pytest.fixture()
def raw_root(tmp_path_factory):
    """Scratch raw root: per-test temp dir with checksummed fake artifacts."""
    root = tmp_path_factory.mktemp("raw")
    chirp_bytes = b"fake-chirps-bytes"
    era_bytes = b"fake-era5-bytes"
    (root / "chirps").mkdir(exist_ok=True)
    (root / "era5-land").mkdir(exist_ok=True)
    (root / "chirps" / "chirps__v2.x__2026-08-31.tif.gz").write_bytes(chirp_bytes)
    (root / "era5-land" / "era5-land__op.nc").write_bytes(era_bytes)
    return root, sha256_of(root / "chirps" / "chirps__v2.x__2026-08-31.tif.gz"), sha256_of(
        root / "era5-land" / "era5-land__op.nc"
    )


def _chirps_grid():
    """Bounded 0.5-deg fixture grid mirroring CHIRPS semantics (descending lat)."""
    lats = np.arange(29.5, 20.99, -0.5)
    lons = np.arange(88.0, 97.51, 0.5)
    raw = np.full((lats.size, lons.size), CHIRPS_NODATA, dtype=float)
    raw[3, 4] = 42.5  # position (28.0, 90.0) -> wet
    raw[1, 8] = 0.0  # position (29.0, 92.0) -> measured zero (dry day)
    raw[5, 16] = 17.0  # position (27.0, 96.0) -> wet
    return raw, lats, lons


@pytest.fixture()
def chirps_decoder():
    return lambda _path: _chirps_grid()


def _era5_grids():
    """Bounded 0.1-deg fixture grids with NaN _FillValue mirrors."""
    lats = np.arange(29.5, 20.999, -0.1)
    lons = np.arange(88.0, 97.59999, 0.1)
    shape = (lats.size, lons.size)
    grids = {}
    for short, value in {
        "t2m": 293.5,
        "tp": 0.012,
        "swvl1": 0.42,
        "sro": 0.001,
    }.items():
        raw = np.full(shape, np.nan)
        raw[35, 60] = value
        raw[0, 0] = np.nan  # a fill cell for the missing test
        grids[short] = (raw, lats, lons)
    return grids


@pytest.fixture()
def era5_grids():
    return _era5_grids()


def _request(
    source: str,
    position: Position,
    *,
    cutoff: datetime = VALID_CUTOFF,
    features: list[str] | None = None,
    region: StudyRegion | None = None,
    sha: str | None = None,
    policy: str = "research_replay",
) -> FeatureExtractionRequest:
    return FeatureExtractionRequest(
        source=source,
        position=position,
        prediction_cutoff_utc=cutoff,
        requested_features=features,
        region=region or StudyRegion(north=29.5, west=88.0, south=21.0, east=97.5, crs=CANONICAL_CRS),
        artifact_sha256=sha,
        availability_policy=policy,
    )


# ---------------------------------------------------------------------------
# 3.7.8F. Multi-day CHIRPS rolling aggregation (approved A/A1/A2/B/C1-C4/D)
# ---------------------------------------------------------------------------

ANCHOR_DATE = date(2026, 8, 31)


def _day_record(
    day: date,
    *,
    sha: str,
    storage_path: str,
    product_version: str = "v2.0",
    availability_classification: str | None = "provider_issued",
    available_utc: datetime | None = datetime(2026, 9, 11, 21, 10, 59, tzinfo=UTC),
    seed: str = "",
) -> AcquisitionRecord:
    """A synthetic kept REAL daily CHIRPS record for ``day``.

    The referenced file must exist under the rollup root and ``sha`` must be its
    recomputed digest. ``acquired_utc`` increases with day, so the anchor record
    (max acquired_utc) is always ANCHOR_DATE regardless of manifest ordering.
    """
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    return _chirps_record(
        record_id=(
            f"REAL-chirps-v2.0-{day.isoformat()}" + (f"-{seed}" if seed else "")
        ),
        source_record_id=(
            f"chirps-v2.0.{day.strftime('%Y.%m.%d')}.tif.gz"
            + (f"-{seed}" if seed else "")
        ),
        product_version=product_version,
        observation_start_utc=start,
        observation_end_utc=start + timedelta(days=1),
        storage_path=storage_path,
        sha256=sha,
        acquired_utc=datetime(2026, 10, 8, 12, 0, tzinfo=UTC)
        + timedelta(hours=30 - (ANCHOR_DATE - day).days),
        available_utc=available_utc,
        availability_classification=availability_classification,
    )


def _window_days(window_days: int) -> list[date]:
    """Ascending inclusive [D-(N-1), D] for the anchor day."""
    return [
        ANCHOR_DATE - timedelta(days=offset)
        for offset in range(window_days - 1, -1, -1)
    ]


def _records_for_days(
    days: list[date],
    written: dict[date, tuple[str, str]],
    *,
    product_version: str = "v2.0",
    availability_classification: str | None = "provider_issued",
    available_utc: datetime | None = datetime(2026, 9, 11, 21, 10, 59, tzinfo=UTC),
) -> list[AcquisitionRecord]:
    return [
        _day_record(
            day,
            sha=written[day][1],
            storage_path=written[day][0],
            product_version=product_version,
            availability_classification=availability_classification,
            available_utc=available_utc,
        )
        for day in days
    ]


@pytest.fixture()
def rollup_root(tmp_path_factory):
    """Scratch raw root holding checksummed per-day fake CHIRPS artifacts."""
    root = tmp_path_factory.mktemp("rollup")
    written: dict[date, tuple[str, str]] = {}
    for offset in range(0, 35):
        day = ANCHOR_DATE - timedelta(days=offset)
        rel = f"chirps/chirps__v2.x__{day.isoformat()}.tif.gz"
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"fake-chirps-day-{day.isoformat()}".encode())
        written[day] = (rel, sha256_of(path))
    return root, written


def _grid_for_day(wet: float | None):
    """Bounded 0.5-deg fixture grid; ``wet`` None leaves (28.0, 90.0) nodata."""
    lats = np.arange(29.5, 20.99, -0.5)
    lons = np.arange(88.0, 97.51, 0.5)
    raw = np.full((lats.size, lons.size), CHIRPS_NODATA, dtype=float)
    if wet is not None:
        raw[3, 4] = wet
    raw[1, 8] = 0.0
    raw[5, 16] = 17.0
    return raw, lats, lons


def _decoder_for(values: dict[date, float | None]):
    """Per-day fixture decoder; the day is read from the artifact filename."""

    def decode(path: Path):
        slug = Path(path).name.split(".tif.gz")[0].split("__")[-1]
        return _grid_for_day(values[date.fromisoformat(slug)])

    return decode


# ---------------------------------------------------------------------------
# 1-4. Provenance / leakage gate
# ---------------------------------------------------------------------------


def test_valid_provenance_passes():
    record = _chirps_record()
    provenance = build_feature_provenance(
        record, prediction_cutoff_utc=VALID_CUTOFF, transform="direct"
    )
    assert provenance.source == "chirps"
    assert provenance.prediction_cutoff_utc == VALID_CUTOFF
    assert provenance.observation_end_utc <= VALID_CUTOFF
    assert evaluate_leakage(
        record.observation_start_utc,
        record.observation_end_utc,
        record.available_utc,
        VALID_CUTOFF,
    ) is FeatureStatus.VALID


def test_naive_datetime_rejected():
    with pytest.raises(FeatureContractError):
        evaluate_leakage(
            datetime(2026, 8, 31),
            datetime(2026, 9, 1),
            datetime(2026, 9, 11, 21, 10, 59),
            datetime(2026, 10, 8, 12, 0),
        )
    with pytest.raises(ValidationError):
        _request("chirps", Position(latitude=28.0, longitude=90.0), cutoff=datetime(2026, 10, 8, 12, 0))


def test_observation_after_cutoff_rejected(raw_root):
    root, chirp_sha, _ = raw_root
    record = _chirps_record(
        sha256=chirp_sha, storage_path="chirps/chirps__v2.x__2026-08-31.tif.gz"
    )
    result = run_extraction(
        _request("chirps", Position(latitude=28.0, longitude=90.0), cutoff=datetime(2026, 8, 31, 0, 0, tzinfo=UTC)),
        manifest=_manifest(record),
        raw_root=root,
    )
    assert all(f.status is FeatureStatus.REJECTED_LEAKAGE for f in result.features)


def test_observation_after_cutoff_rejected_at_gate():
    record = _chirps_record()
    status = evaluate_leakage(
        record.observation_start_utc,
        record.observation_end_utc,
        record.available_utc,
        datetime(2026, 8, 30, 0, 0, tzinfo=UTC),
    )
    assert status is FeatureStatus.REJECTED_LEAKAGE


def test_available_after_cutoff_rejected():
    record = _chirps_record()
    status = evaluate_leakage(
        record.observation_start_utc,
        record.observation_end_utc,
        record.available_utc,
        datetime(2026, 9, 5, 0, 0, tzinfo=UTC),
    )
    assert status is FeatureStatus.REJECTED_LEAKAGE


@pytest.mark.parametrize(
    "start,end",
    [
        (datetime(2026, 8, 31, tzinfo=UTC), None),
        (None, datetime(2026, 9, 1, tzinfo=UTC)),
        (None, None),
    ],
)
def test_leakage_gate_fails_closed_on_missing_observation_window(start, end):
    # Phase 3.7.11 hardening of audit finding F1: a record with no observable
    # window is not provably non-leaky, so the gate must fail closed instead of
    # comparing a None against the cutoff (which raised an untyped TypeError).
    status = evaluate_leakage(start, end, datetime(2026, 9, 11, tzinfo=UTC), VALID_CUTOFF)
    assert status is FeatureStatus.REJECTED_LEAKAGE


def test_leakage_rejected_note_explains_missing_window():
    record = _chirps_record(observation_start_utc=None, observation_end_utc=None)
    note = _leakage_rejected_note(record, VALID_CUTOFF)
    assert "not fully recorded" in note


def test_run_extraction_missing_observation_window_fails_typed_without_decode(raw_root):
    # Phase 3.7.11 F1: the public entry point must surface a typed contract
    # error (never a pydantic ValidationError or a TypeError) and must not read
    # any pixel from an artifact whose observation window is unrecorded.
    root, chirp_sha, _ = raw_root
    record = _chirps_record(
        sha256=chirp_sha,
        storage_path="chirps/chirps__v2.x__2026-08-31.tif.gz",
        observation_start_utc=None,
        observation_end_utc=None,
    )
    calls = []

    def recorder(path):
        calls.append(path)
        return _chirps_grid()

    with pytest.raises(FeatureContractError, match="no observation window"):
        run_extraction(
            _request(
                "chirps",
                Position(latitude=28.0, longitude=90.0),
                features=["precipitation_daily_mm"],
            ),
            manifest=_manifest(record),
            chirps_decoder=recorder,
            raw_root=root,
        )
    assert calls == []


def test_production_policy_rejects_unverified_availability():
    # Phase 3.7.4B resolution of G-4. This supersedes the Phase 3.7.4A pinned
    # ``test_available_utc_can_be_unclassified_and_gate_is_classification_blind``:
    # that test pinned the classification-blind behavior (identical outcomes for
    # derived/unclassified/provider_issued). Under the new one-dimensional policy
    # rule, a derived or unknown/unclassified timestamp can never clear a
    # production-grade gate.
    for classification in ("derived", "unknown", None):
        record = _chirps_record(availability_classification=classification)
        assert (
            evaluate_availability_policy(record, availability_policy="production")
            is FeatureStatus.REJECTED_LEAKAGE
        )


def test_production_policy_rejects_missing_timestamp():
    record = _chirps_record(available_utc=None, availability_classification=None)
    assert record.available_utc is None
    assert (
        evaluate_availability_policy(record, availability_policy="production")
        is FeatureStatus.REJECTED_LEAKAGE
    )


def test_production_policy_accepts_provider_issued_before_cutoff():
    record = _chirps_record(availability_classification="provider_issued")
    assert (
        evaluate_availability_policy(record, availability_policy="production")
        is FeatureStatus.VALID
    )
    # the pure time gate still applies on top of the evidence gate
    assert evaluate_leakage(
        record.observation_start_utc,
        record.observation_end_utc,
        record.available_utc,
        datetime(2026, 9, 5, 0, 0, tzinfo=UTC),
    ) is FeatureStatus.REJECTED_LEAKAGE


def test_research_policy_accepts_labelled_availability():
    # research/replay accepts any present, labelled timestamp -- including the
    # committed REAL record state (an available_utc with no classification).
    for classification in ("provider_issued", "derived", "unknown", None):
        record = _chirps_record(availability_classification=classification)
        assert (
            evaluate_availability_policy(record, availability_policy="research_replay")
            is FeatureStatus.VALID
        )


def test_research_policy_rejects_missing_timestamp():
    # Supersedes the Phase 3.7.4A pinned
    # ``test_unknown_availability_is_not_fabricated_and_not_rejected``: absent
    # availability evidence can no longer clear any cutoff (there is no timestamp
    # to place against it), and it is still never fabricated into a verified
    # timestamp -- the record keeps available_utc None.
    record = _chirps_record(available_utc=None, availability_classification=None)
    assert record.available_utc is None
    assert (
        evaluate_availability_policy(record, availability_policy="research_replay")
        is FeatureStatus.REJECTED_LEAKAGE
    )


def test_provenance_carries_availability_classification():
    derived = build_feature_provenance(
        _chirps_record(availability_classification="derived"),
        prediction_cutoff_utc=VALID_CUTOFF,
        transform="direct",
    )
    assert derived.availability_classification == "derived"
    unclassified = build_feature_provenance(
        _chirps_record(), prediction_cutoff_utc=VALID_CUTOFF, transform="direct"
    )
    assert unclassified.available_utc is not None
    assert unclassified.availability_classification is None


def test_run_extraction_default_research_policy_labels_output(raw_root, chirps_decoder):
    # The committed REAL record state (available_utc, no classification) still
    # extracts under the default request policy; the output carries the honest
    # (unclassified) label instead of being presented as provider-issued.
    root, chirp_sha, _ = raw_root
    record = _chirps_record(
        sha256=chirp_sha, storage_path="chirps/chirps__v2.x__2026-08-31.tif.gz"
    )
    assert record.availability_classification is None
    result = run_extraction(
        _request(
            "chirps",
            Position(latitude=28.0, longitude=90.0),
            features=["precipitation_daily_mm"],
        ),
        manifest=_manifest(record),
        chirps_decoder=chirps_decoder,
        raw_root=root,
    )
    assert all(f.status is FeatureStatus.VALID for f in result.features)
    assert result.features[0].provenance.availability_classification is None


def test_run_extraction_production_gate_rejects_unverified(raw_root, chirps_decoder):
    root, chirp_sha, _ = raw_root
    record = _chirps_record(
        sha256=chirp_sha,
        storage_path="chirps/chirps__v2.x__2026-08-31.tif.gz",
        availability_classification="derived",
    )
    result = run_extraction(
        _request("chirps", Position(latitude=28.0, longitude=90.0), policy="production"),
        manifest=_manifest(record),
        chirps_decoder=chirps_decoder,
        raw_root=root,
    )
    assert all(f.status is FeatureStatus.REJECTED_LEAKAGE for f in result.features)
    assert all("provider_issued" in (f.note or "") for f in result.features)


def test_run_extraction_production_gate_accepts_provider_issued(raw_root, chirps_decoder):
    root, chirp_sha, _ = raw_root
    record = _chirps_record(
        sha256=chirp_sha,
        storage_path="chirps/chirps__v2.x__2026-08-31.tif.gz",
        availability_classification="provider_issued",
    )
    result = run_extraction(
        _request(
            "chirps",
            Position(latitude=28.0, longitude=90.0),
            features=["precipitation_daily_mm"],
            policy="production",
        ),
        manifest=_manifest(record),
        chirps_decoder=chirps_decoder,
        raw_root=root,
    )
    assert all(f.status is FeatureStatus.VALID for f in result.features)
    assert result.features[0].provenance.availability_classification == "provider_issued"


def test_invalid_availability_policy_rejected_at_schema():
    # fail-closed at the typed boundary: a typo / wrong casing is never read as
    # the permissive research default, it is a validation error.
    with pytest.raises(ValidationError):
        _request(
            "chirps",
            Position(latitude=28.0, longitude=90.0),
            policy="PRODUCTION",
        )
    with pytest.raises(ValidationError):
        _request(
            "chirps",
            Position(latitude=28.0, longitude=90.0),
            policy="prod",
        )


def test_evaluate_availability_policy_fails_closed_on_unknown_policy():
    # fail-closed at the gate even for a direct (schema-bypassed) call with a
    # present timestamp: an unknown policy raises instead of being treated as
    # research_replay.
    record = _chirps_record()  # available_utc present
    assert record.available_utc is not None
    with pytest.raises(FeatureContractError):
        evaluate_availability_policy(record, availability_policy="bogus")


def test_provenance_and_policy_survive_serialization():
    # Persisted provenance and request policy must retain the actual
    # classification / policy verbatim through a dump/reload round trip --
    # a derived label can never be lost (and thereby silently promoted) on
    # serialization.
    record = _chirps_record(availability_classification="derived")
    provenance = build_feature_provenance(
        record, prediction_cutoff_utc=VALID_CUTOFF, transform="direct"
    )
    loaded = FeatureProvenance.model_validate(provenance.model_dump())
    assert loaded.availability_classification == "derived"
    assert loaded.model_dump_json() == provenance.model_dump_json()
    unclassified = build_feature_provenance(
        _chirps_record(), prediction_cutoff_utc=VALID_CUTOFF, transform="direct"
    )
    assert FeatureProvenance.model_validate(
        unclassified.model_dump()
    ).availability_classification is None
    req = _request(
        "chirps", Position(latitude=28.0, longitude=90.0), policy="production"
    )
    assert (
        FeatureExtractionRequest.model_validate(req.model_dump()).availability_policy
        == "production"
    )


# ---------------------------------------------------------------------------
# 5-6. Nodata semantics
# ---------------------------------------------------------------------------


def test_chirps_nodata_becomes_missing_never_zero():
    assert coerce_to_missing(CHIRPS_NODATA, sentinels=(CHIRPS_NODATA,)) is None
    assert coerce_to_missing(-9999.0 - 1e-12, sentinels=(CHIRPS_NODATA,)) is None
    dry = coerce_to_missing(0.0, sentinels=(CHIRPS_NODATA,))
    assert dry == 0.0  # a measured zero is valid data, not nodata

    raw, lats, lons = _chirps_grid()
    assert sample_grid(raw, lats, lons, 24.0, 95.0, sentinels=(CHIRPS_NODATA,)) is None


def test_chirps_nodata_feature_missing_not_zero(raw_root, chirps_decoder):
    root, chirp_sha, _ = raw_root
    record = _chirps_record(sha256=chirp_sha, storage_path="chirps/chirps__v2.x__2026-08-31.tif.gz")
    result = run_extraction(
        _request("chirps", Position(latitude=24.0, longitude=95.0), features=["precipitation_daily_mm"]),
        manifest=_manifest(record),
        chirps_decoder=chirps_decoder,
        raw_root=root,
    )
    feature = result.features[0]
    assert feature.value is None
    assert feature.status is FeatureStatus.MISSING
    assert "never converted to zero" in feature.note


def test_netcdf_fillvalue_becomes_missing():
    assert coerce_to_missing(np.nan) is None
    assert coerce_to_missing(np.float32(np.nan)) is None
    grids = _era5_grids()
    raw, lats, lons = grids["t2m"]
    assert sample_grid(raw, lats, lons, 29.5, 88.0) is None  # the fill cell


def test_netcdf_fillvalue_feature_missing_not_zero(raw_root, era5_grids):
    root, _, era5_sha = raw_root
    record = _era5_record(
        sha256=era5_sha, storage_path="era5-land/era5-land__op.nc", file_size_bytes=13
    )
    result = run_extraction(
        _request("era5-land", Position(latitude=29.5, longitude=88.0), features=["soil_water_layer1_m3m3"]),
        manifest=_manifest(record),
        era5_grids=era5_grids,
        raw_root=root,
    )
    feature = result.features[0]
    assert feature.value is None
    assert feature.status is FeatureStatus.MISSING
    assert feature.value != 0.0


# ---------------------------------------------------------------------------
# 7. CHIRPS direct feature extraction
# ---------------------------------------------------------------------------


def test_valid_chirps_direct_feature_extraction(raw_root, chirps_decoder):
    root, chirp_sha, _ = raw_root
    record = _chirps_record(sha256=chirp_sha, storage_path="chirps/chirps__v2.x__2026-08-31.tif.gz")
    result = run_extraction(
        _request("chirps", Position(latitude=28.0, longitude=90.0), features=["precipitation_daily_mm"]),
        manifest=_manifest(record),
        chirps_decoder=chirps_decoder,
        raw_root=root,
    )
    assert len(result.features) == 1
    feature = result.features[0]
    assert feature.status is FeatureStatus.VALID
    assert feature.value == pytest.approx(42.5)
    assert feature.unit == "mm"
    prov = feature.provenance
    assert prov.source == "chirps"
    assert prov.product_version == "v2.0"
    assert "direct extraction" in prov.transform
    assert prov.crs.startswith("EPSG:4326")
    assert prov.coordinate_precision == 0.025


def test_chirps_measured_zero_is_a_valid_value(raw_root, chirps_decoder):
    root, chirp_sha, _ = raw_root
    record = _chirps_record(sha256=chirp_sha, storage_path="chirps/chirps__v2.x__2026-08-31.tif.gz")
    result = run_extraction(
        _request("chirps", Position(latitude=29.0, longitude=92.0), features=["precipitation_daily_mm"]),
        manifest=_manifest(record),
        chirps_decoder=chirps_decoder,
        raw_root=root,
    )
    assert result.features[0].value == 0.0
    assert result.features[0].status is FeatureStatus.VALID


# ---------------------------------------------------------------------------
# 8-11. ERA5-Land direct feature extraction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "feature,short,expected,unit",
    [
        ("temperature_2m_K", "t2m", 293.5, "K"),
        ("precipitation_hourly_m", "tp", 0.012, "m"),
        ("soil_water_layer1_m3m3", "swvl1", 0.42, "m3/m3"),
        ("surface_runoff_m", "sro", 0.001, "m"),
    ],
)
def test_valid_era5_direct_extraction(raw_root, era5_grids, feature, short, expected, unit):
    root, _, era5_sha = raw_root
    record = _era5_record(
        sha256=era5_sha, storage_path="era5-land/era5-land__op.nc", file_size_bytes=13
    )
    result = run_extraction(
        _request("era5-land", Position(latitude=26.0, longitude=94.0), features=[feature]),
        manifest=_manifest(record),
        era5_grids=era5_grids,
        raw_root=root,
    )
    feature_value = result.features[0]
    assert feature_value.status is FeatureStatus.VALID
    assert feature_value.value == pytest.approx(expected)
    assert feature_value.unit == unit
    assert f"{short} direct extraction" in feature_value.provenance.transform
    assert feature_value.provenance.product == "ERA5-Land hourly reanalysis (land surface)"


def test_era5_hourly_precipitation_unit_is_metres(raw_root, era5_grids):
    root, _, era5_sha = raw_root
    record = _era5_record(sha256=era5_sha, storage_path="era5-land/era5-land__op.nc", file_size_bytes=13)
    result = run_extraction(
        _request("era5-land", Position(latitude=26.0, longitude=94.0), features=["precipitation_hourly_m"]),
        manifest=_manifest(record),
        era5_grids=era5_grids,
        raw_root=root,
    )
    assert result.features[0].unit == "m"  # raw NetCDF unit preserved, no silent conversion


# ---------------------------------------------------------------------------
# 12-13. CRS / bounds
# ---------------------------------------------------------------------------


def test_wrong_crs_rejected():
    with pytest.raises(ValidationError):
        StudyRegion(north=29.5, west=88.0, south=21.0, east=97.5, crs="EPSG:3857 (WebMercator)")
    with pytest.raises(FeatureContractError):
        require_epsg4326("EPSG:3857")


def test_out_of_bounds_coordinates_rejected():
    with pytest.raises(FeatureContractError):
        run_extraction(
            _request("chirps", Position(latitude=35.0, longitude=90.0)),
            manifest=_manifest(_chirps_record()),
            raw_root=None,
        )
    with pytest.raises(FeatureContractError):
        run_extraction(
            _request("chirps", Position(latitude=28.0, longitude=80.0)),
            manifest=_manifest(_chirps_record()),
            raw_root=None,
        )


# ---------------------------------------------------------------------------
# 14-15, 20. Rolling windows / temporal coverage honesty
# ---------------------------------------------------------------------------


def test_missing_temporal_coverage_reported_honestly(raw_root, chirps_decoder):
    root, chirp_sha, _ = raw_root
    record = _chirps_record(sha256=chirp_sha, storage_path="chirps/chirps__v2.x__2026-08-31.tif.gz")
    result = run_extraction(
        _request("chirps", Position(latitude=28.0, longitude=90.0), features=["precipitation_7d_mm"]),
        manifest=_manifest(record),
        chirps_decoder=chirps_decoder,
        raw_root=root,
    )
    feature = result.features[0]
    assert feature.status is FeatureStatus.INSUFFICIENT_TEMPORAL_COVERAGE
    assert feature.value is None
    assert "requires additional temporal coverage" in feature.note


def test_rolling_window_cannot_generate_without_sufficient_files(raw_root, chirps_decoder):
    root, chirp_sha, _ = raw_root
    record = _chirps_record(sha256=chirp_sha, storage_path="chirps/chirps__v2.x__2026-08-31.tif.gz")
    manifest = _manifest(record)
    assert chirps_daily_coverage_days(manifest, record) == 1
    result = run_extraction(
        _request(
            "chirps",
            Position(latitude=28.0, longitude=90.0),
            features=["precipitation_3d_mm", "precipitation_7d_mm", "precipitation_30d_mm"],
        ),
        manifest=manifest,
        chirps_decoder=chirps_decoder,
        raw_root=root,
    )
    assert all(f.status is FeatureStatus.INSUFFICIENT_TEMPORAL_COVERAGE for f in result.features)
    assert all(f.value is None for f in result.features)
    assert "3 contiguous daily artifacts" in result.features[0].note
    assert "30 contiguous daily artifacts" in result.features[2].note


def test_no_fabricated_zero_values_for_missing_history(raw_root, chirps_decoder):
    root, chirp_sha, _ = raw_root
    record = _chirps_record(sha256=chirp_sha, storage_path="chirps/chirps__v2.x__2026-08-31.tif.gz")
    result = run_extraction(
        _request(
            "chirps",
            Position(latitude=28.0, longitude=90.0),
            features=["precipitation_3d_mm", "precipitation_7d_mm", "precipitation_14d_mm", "precipitation_30d_mm"],
        ),
        manifest=_manifest(record),
        chirps_decoder=chirps_decoder,
        raw_root=root,
    )
    assert all(f.value is None for f in result.features)  # None, never 0.0
    assert all(f.status is FeatureStatus.INSUFFICIENT_TEMPORAL_COVERAGE for f in result.features)


def test_rolling_1d_equals_daily_value(raw_root, chirps_decoder):
    root, chirp_sha, _ = raw_root
    record = _chirps_record(sha256=chirp_sha, storage_path="chirps/chirps__v2.x__2026-08-31.tif.gz")
    result = run_extraction(
        _request("chirps", Position(latitude=28.0, longitude=90.0),
                 features=["precipitation_daily_mm", "precipitation_1d_mm"]),
        manifest=_manifest(record),
        chirps_decoder=chirps_decoder,
        raw_root=root,
    )
    daily, one_day = result.features
    assert daily.status is FeatureStatus.VALID
    assert one_day.status is FeatureStatus.VALID
    assert one_day.value == daily.value
    assert one_day.value == pytest.approx(42.5)
    # The equality is justified purely as a one-day window over this day --
    # it never implies coverage beyond the single acquired file.
    assert "no multi-day coverage" in one_day.note
    assert "a single day only" in one_day.provenance.transform


# ---------------------------------------------------------------------------
# 16. Artifact SHA-256 mismatch
# ---------------------------------------------------------------------------


def test_artifact_sha256_mismatch_rejected(raw_root, chirps_decoder):
    root, chirp_sha, _ = raw_root
    record = _chirps_record(sha256=chirp_sha, storage_path="chirps/chirps__v2.x__2026-08-31.tif.gz")
    # The on-disk bytes must differ from the ledger checksum.
    artifact = artifact_path(record, raw_root=root)
    artifact.write_bytes(b"tampered-bytes")
    assert sha256_of(artifact) != record.sha256
    with pytest.raises(FeatureContractError, match="SHA-256 mismatch"):
        run_extraction(
            _request("chirps", Position(latitude=28.0, longitude=90.0), features=["precipitation_daily_mm"]),
            manifest=_manifest(record),
            chirps_decoder=chirps_decoder,
            raw_root=root,
        )


def test_artifact_sha256_pinned_record_resolution(raw_root):
    root, chirp_sha, _ = raw_root
    record = _chirps_record(sha256=chirp_sha, storage_path="chirps/chirps__v2.x__2026-08-31.tif.gz")
    manifest = _manifest(record)
    assert resolve_acquired_record(manifest, "chirps", chirp_sha).record_id == record.record_id
    with pytest.raises(FeatureContractError, match="no kept REAL acquisition record"):
        resolve_acquired_record(manifest, "chirps", ERA5_SHA)


# ---------------------------------------------------------------------------
# 17-18. Feature provenance propagation
# ---------------------------------------------------------------------------


def test_feature_provenance_preserves_source_record_id(raw_root, chirps_decoder):
    root, chirp_sha, _ = raw_root
    record = _chirps_record(sha256=chirp_sha, storage_path="chirps/chirps__v2.x__2026-08-31.tif.gz")
    result = run_extraction(
        _request("chirps", Position(latitude=28.0, longitude=90.0), features=["precipitation_daily_mm"]),
        manifest=_manifest(record),
        chirps_decoder=chirps_decoder,
        raw_root=root,
    )
    prov = result.features[0].provenance
    assert prov.source_record_id == "chirps-v2.0.2026.08.31.tif.gz"
    assert prov.acquisition_record_id == record.record_id
    assert prov.observation_start_utc == record.observation_start_utc
    assert prov.available_utc == record.available_utc
    assert prov.prediction_cutoff_utc == VALID_CUTOFF


def test_feature_provenance_preserves_artifact_sha256(raw_root, chirps_decoder):
    root, chirp_sha, _ = raw_root
    record = _chirps_record(sha256=chirp_sha, storage_path="chirps/chirps__v2.x__2026-08-31.tif.gz")
    result = run_extraction(
        _request("chirps", Position(latitude=28.0, longitude=90.0), features=["precipitation_daily_mm"]),
        manifest=_manifest(record),
        chirps_decoder=chirps_decoder,
        raw_root=root,
    )
    assert result.features[0].provenance.artifact_sha256 == chirp_sha
    assert result.artifact_sha256 == chirp_sha
    assert result.acquisition_record_id == record.record_id


# ---------------------------------------------------------------------------
# 19. Determinism
# ---------------------------------------------------------------------------


def test_leakage_rejection_is_deterministic(raw_root, chirps_decoder):
    record = _chirps_record()
    cutoff = datetime(2026, 9, 5, 0, 0, tzinfo=UTC)
    assert evaluate_leakage(
        record.observation_start_utc, record.observation_end_utc, record.available_utc, cutoff
    ) is evaluate_leakage(
        record.observation_start_utc, record.observation_end_utc, record.available_utc, cutoff
    )
    root, chirp_sha, _ = raw_root
    anchored = _chirps_record(sha256=chirp_sha, storage_path="chirps/chirps__v2.x__2026-08-31.tif.gz")
    manifest = _manifest(anchored)
    req = _request("chirps", Position(latitude=28.0, longitude=90.0), cutoff=cutoff)
    first = run_extraction(req, manifest=manifest, chirps_decoder=chirps_decoder, raw_root=root)
    second = run_extraction(req, manifest=manifest, chirps_decoder=chirps_decoder, raw_root=root)
    assert [f.status for f in first.features] == [f.status for f in second.features]
    assert [f.value for f in first.features] == [f.value for f in second.features]


# ---------------------------------------------------------------------------
# Request/feature vocabulary guards
# ---------------------------------------------------------------------------


def test_request_rejects_unknown_feature_name(raw_root):
    root, chirp_sha, _ = raw_root
    record = _chirps_record(sha256=chirp_sha, storage_path="chirps/chirps__v2.x__2026-08-31.tif.gz")
    with pytest.raises(FeatureContractError, match="unsupported feature"):
        run_extraction(
            _request("chirps", Position(latitude=28.0, longitude=90.0), features=["snow_depth_m"]),
            manifest=_manifest(record),
            raw_root=root,
        )


def test_feature_vocabulary_and_mappings():
    assert set(supported_features("chirps")) == {
        "precipitation_daily_mm",
        "precipitation_1d_mm",
        "precipitation_3d_mm",
        "precipitation_7d_mm",
        "precipitation_14d_mm",
        "precipitation_30d_mm",
    }
    assert set(supported_features("era5-land")) == {
        "temperature_2m_K",
        "precipitation_hourly_m",
        "soil_water_layer1_m3m3",
        "surface_runoff_m",
    }
    assert FEATURE_SPECS["precipitation_hourly_m"].source_variable == "tp"
    assert FEATURE_SPECS["soil_water_layer1_m3m3"].source_variable == "swvl1"
    assert FEATURE_SPECS["surface_runoff_m"].source_variable == "sro"
    assert FEATURE_SPECS["temperature_2m_K"].source_variable == "t2m"


# ---------------------------------------------------------------------------
# Real-artifact integration (skip-guarded: never downloads anything)
# ---------------------------------------------------------------------------


def _load_real_record() -> AcquisitionRecord:
    from app.services.acquisition import load_acquisition_manifest

    manifest = load_acquisition_manifest()
    kept = [
        record
        for record in manifest.records
        if record.kind == "REAL"
        and record.status in (AcquisitionStatus.DOWNLOADED, AcquisitionStatus.SKIPPED_EXISTING)
        and record.storage_path
    ]
    assert kept, "the committed acquisition ledger must contain the acquired artifacts"
    return kept


@pytest.mark.parametrize("record", _load_real_record(), ids=lambda r: r.source)
def test_real_artifacts_match_ledger_sha(record):
    path = PROJECT_ROOT / "data" / "raw" / "real" / record.storage_path
    if not path.is_file():
        pytest.skip("real raw artifact is not present on this machine")
    assert sha256_of(path) == record.sha256


@pytest.mark.skipif(not REAL_ERA5.is_file(), reason="real ERA5-Land artifact not present")
def test_real_era5_netcdf_extraction_values_sane():
    pytest.importorskip("netCDF4")
    record = _era5_record()
    results = run_extraction(
        _request(
            "era5-land",
            Position(latitude=26.0, longitude=94.0),
            features=["temperature_2m_K", "precipitation_hourly_m", "soil_water_layer1_m3m3", "surface_runoff_m"],
        ),
        manifest=_manifest(record),
    )
    by_name = {f.feature_name: f for f in results.features}
    assert by_name["temperature_2m_K"].status is FeatureStatus.VALID
    assert 220 <= by_name["temperature_2m_K"].value <= 320  # plausible K over NE India
    assert by_name["precipitation_hourly_m"].unit == "m"
    assert by_name["soil_water_layer1_m3m3"].unit == "m3/m3"
    assert by_name["surface_runoff_m"].unit == "m"
    assert 0.0 <= by_name["precipitation_hourly_m"].value <= 0.5
    assert 0.0 <= by_name["surface_runoff_m"].value <= 0.5


def test_chirps_decoder_injection_is_honoured(raw_root):
    """The real GeoTIFF bytes are never opened when a decoder is injected."""
    root, chirp_sha, _ = raw_root
    record = _chirps_record(sha256=chirp_sha, storage_path="chirps/chirps__v2.x__2026-08-31.tif.gz")
    called = {"n": 0}

    def decoder(_path):
        called["n"] += 1
        return _chirps_grid()

    run_extraction(
        _request("chirps", Position(latitude=28.0, longitude=90.0), features=["precipitation_daily_mm"]),
        manifest=_manifest(record),
        chirps_decoder=decoder,
        raw_root=root,
    )
    assert called["n"] == 1

# ---------------------------------------------------------------------------
# Spatial-resolution audit: precision vs provider registry vs real artifacts
# ---------------------------------------------------------------------------


def _registered_cell_size(source: str) -> float:
    """First token of the registry's spatial_resolution (e.g. '0.05 degrees')."""
    from app.services.acquisition import get_source_config

    return float(get_source_config(source).spatial_resolution.split()[0])


def test_contract_precision_is_exactly_half_the_registered_cell_size():
    """Regression: coordinate_precision must mirror provider metadata exactly.

    coordinate_precision is the half-cell width, not the resolution. If either
    the registry resolution or COORDINATE_PRECISION_BY_SOURCE changes without
    the other, the contract would silently claim an incorrect source resolution.
    """
    for source, precision in sorted(COORDINATE_PRECISION_BY_SOURCE.items()):
        cell = _registered_cell_size(source)
        assert precision == pytest.approx(cell / 2), (
            f"{source}: claimed precision {precision} != half of registered cell {cell}"
        )


def test_registry_resolution_strings_for_feature_sources_unchanged():
    from app.services.acquisition import get_source_config

    assert get_source_config("chirps").spatial_resolution == "0.05 degrees"
    assert get_source_config("era5-land").spatial_resolution == "0.1 degrees, hourly"


def test_provenance_refuses_unmapped_source_precision():
    """No silent default: a registered source without verified precision fails."""
    record = _chirps_record(source="srtmgl1-v003")  # registered, ~1 arc-second
    with pytest.raises(FeatureContractError, match="coordinate precision"):
        build_feature_provenance(
            record, prediction_cutoff_utc=VALID_CUTOFF, transform="direct"
        )


def test_chirps_daily_feature_is_that_source_day_in_mm(raw_root, chirps_decoder):
    """The daily feature must be the ledger's source day, in millimetres."""
    root, chirp_sha, _ = raw_root
    record = _chirps_record(
        sha256=chirp_sha, storage_path="chirps/chirps__v2.x__2026-08-31.tif.gz"
    )
    result = run_extraction(
        _request(
            "chirps",
            Position(latitude=28.0, longitude=90.0),
            features=["precipitation_daily_mm", "precipitation_1d_mm"],
        ),
        manifest=_manifest(record),
        chirps_decoder=chirps_decoder,
        raw_root=root,
    )
    daily, one_day = result.features
    # Source day: ledger record id and observation window both name 2026-08-31.
    assert daily.provenance.source_record_id == "chirps-v2.0.2026.08.31.tif.gz"
    assert record.observation_start_utc == datetime(2026, 8, 31, 0, 0, tzinfo=UTC)
    assert record.observation_end_utc == datetime(2026, 9, 1, 0, 0, tzinfo=UTC)
    # Units: the contract maps CHIRPS daily precipitation to millimetres.
    assert daily.unit == "mm"
    assert one_day.unit == "mm"
    assert daily.provenance.transform == "CHIRPS daily precipitation (direct extraction)"
    # 1-day window justification: equality follows from the one-day window
    # length alone, never from broader temporal coverage.
    assert "a single day only" in one_day.provenance.transform
    assert "no multi-day coverage" in one_day.note


def _load_geotiff(path: Path) -> tuple[dict, bytes]:
    """Tag-only GeoTIFF reader: (header dict, full uncompressed bytes).

    Stdlib gzip + struct only (no rasterio, no new dependencies). GDAL stores
    the IFD at the end of the stream, so the whole file is read anyway.
    """
    import gzip as _gzip
    import struct as _struct

    data = _gzip.open(path, "rb").read() if path.suffix == ".gz" else path.read_bytes()
    assert data[:2] == b"II", "little-endian TIFF expected"
    ifd = _struct.unpack("<I", data[4:8])[0]
    count = _struct.unpack("<H", data[ifd : ifd + 2])[0]
    sizes = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 12: 8}
    header: dict = {}
    off = ifd + 2
    for _ in range(count):
        entry = data[off : off + 12]
        off += 12
        tag, typ, cnt = _struct.unpack("<HHI", entry[:8])
        if tag not in (256, 257, 273, 278, 33550, 33922, 34735):
            continue
        total = sizes.get(typ, 1) * cnt
        voff = _struct.unpack("<I", entry[8:12])[0]
        blob = data[voff : voff + total] if total > 4 else entry[8 : 8 + total]
        if tag in (256, 257):
            fmt = "<H" if typ == 3 else "<I"
            value = _struct.unpack(fmt, blob[: _struct.calcsize(fmt)])[0]
            header["width" if tag == 256 else "height"] = value
        elif tag == 273:
            header["strip_offsets"] = _struct.unpack("<" + "I" * cnt, blob[: 4 * cnt])
        elif tag == 278:
            fmt = "<H" if typ == 3 else "<I"
            header["rows_per_strip"] = _struct.unpack(
                fmt, blob[: _struct.calcsize(fmt)]
            )[0]
        elif tag == 33550:
            header["pixel_scale"] = _struct.unpack("<" + "d" * cnt, blob[: 8 * cnt])
        elif tag == 33922:
            header["tiepoint"] = _struct.unpack("<" + "d" * cnt, blob[: 8 * cnt])
        else:  # 34735 GeoKeyDirectory: (key, location, count, value) tuples
            keys = _struct.unpack("<" + "H" * cnt, blob[: 2 * cnt])
            header["epsg"] = next(
                keys[i + 3]
                for i in range(4, len(keys), 4)
                if keys[i] == 2048 and keys[i + 1] == 0
            )
    return header, data


@pytest.mark.skipif(not REAL_CHIRPS.is_file(), reason="real CHIRPS artifact not present")
def test_real_chirps_pixel_size_matches_contract():
    """The acquired GeoTIFF's ModelPixelScale must equal the claimed cell size."""
    header, _ = _load_geotiff(REAL_CHIRPS)
    assert (header["width"], header["height"]) == (7200, 2000)
    assert header["epsg"] == 4326
    assert header["pixel_scale"][0] == pytest.approx(0.05, abs=1e-6)
    assert header["pixel_scale"][1] == pytest.approx(0.05, abs=1e-6)
    # The contract's precision claim is exactly half of the *actual* pixel size,
    # and the provider registry states the same cell size.
    assert COORDINATE_PRECISION_BY_SOURCE["chirps"] == pytest.approx(
        header["pixel_scale"][0] / 2, abs=1e-6
    )
    assert _registered_cell_size("chirps") == pytest.approx(
        header["pixel_scale"][0], abs=1e-6
    )


@pytest.mark.skipif(not REAL_ERA5.is_file(), reason="real ERA5-Land artifact not present")
def test_real_era5_land_spacing_matches_contract():
    """The acquired NetCDF's axis spacing must equal the claimed cell size."""
    netCDF4 = pytest.importorskip("netCDF4")
    ds = netCDF4.Dataset(str(REAL_ERA5))
    try:
        lat = np.asarray(ds.variables["latitude"][:], dtype=float)
        lon = np.asarray(ds.variables["longitude"][:], dtype=float)
    finally:
        ds.close()
    assert (lat.size, lon.size) == (86, 96)
    # Artifact extent equals the contract's study region, exactly.
    assert lat[0] == pytest.approx(STUDY_REGION_NORTH) and lat[-1] == pytest.approx(
        STUDY_REGION_SOUTH
    )
    assert lon[0] == pytest.approx(STUDY_REGION_WEST) and lon[-1] == pytest.approx(
        STUDY_REGION_EAST
    )
    assert np.allclose(np.diff(lat), -0.1, atol=1e-9)
    assert np.allclose(np.diff(lon), 0.1, atol=1e-9)
    spacing = float(-np.diff(lat).mean())  # 0.1 deg cells
    assert COORDINATE_PRECISION_BY_SOURCE["era5-land"] == pytest.approx(
        spacing / 2, abs=1e-9
    )
    assert _registered_cell_size("era5-land") == pytest.approx(spacing, abs=1e-9)


@pytest.mark.skipif(not REAL_CHIRPS.is_file(), reason="real CHIRPS artifact not present")
def test_real_chirps_pixels_confirm_mm_units_nodata_and_day():
    """Decode the study window from the real GeoTIFF: mm scale, -9999, day stats."""
    header, data = _load_geotiff(REAL_CHIRPS)
    assert header["rows_per_strip"] == 1  # row r lives in strip r
    ox, oy = header["tiepoint"][3], header["tiepoint"][4]
    px, py = header["pixel_scale"][0], header["pixel_scale"][1]
    assert (ox, oy) == (-180.0, 50.0)
    col0 = round((STUDY_REGION_WEST - ox) / px)
    col1 = round((STUDY_REGION_EAST - ox) / px)
    row0 = round((oy - STUDY_REGION_NORTH) / py)
    row1 = round((oy - STUDY_REGION_SOUTH) / py)
    assert (row1 - row0 + 1, col1 - col0 + 1) == (171, 191)
    offsets = header["strip_offsets"]
    ncol = col1 - col0 + 1
    window = np.empty((row1 - row0 + 1, ncol), dtype=float)
    for r in range(row0, row1 + 1):
        start = offsets[r] + col0 * 4
        window[r - row0] = np.frombuffer(data[start : start + ncol * 4], dtype="<f4")
    fill = window == CHIRPS_NODATA
    valid = window[~fill]
    # Ledger note (Phase 3.5): 171x191 px, 4.6% fill, 0..186.0 mm, mean 19.2 mm.
    assert fill.any() and 0.02 < fill.mean() < 0.08
    assert valid.min() >= 0.0
    assert valid.max() > 1.0  # millimetres, not metres
    assert valid.max() < 1000.0
    assert (valid == 0.0).any()  # measured dry cells are valid zeros
    assert valid.mean() == pytest.approx(19.2, abs=1.0)


# ---------------------------------------------------------------------------
# Phase 3.7.7E: missing/empty/malformed ledger fail-loud paths
# ---------------------------------------------------------------------------


def test_run_extraction_empty_ledger_fails_loud():
    """An explicitly empty in-memory ledger must never yield silent zero features."""
    manifest = _manifest()
    assert manifest is not None and manifest.records == []
    with pytest.raises(FeatureContractError, match="no kept REAL artifact in the acquisition ledger"):
        run_extraction(
            _request("chirps", Position(latitude=28.0, longitude=90.0)),
            manifest=manifest,
        )


def test_run_extraction_only_failed_records_fails_loud():
    """Records that never reached a kept state are not resolvable artifacts."""
    failed = _chirps_record(
        status=AcquisitionStatus.FAILED,
        sha256=None,
        file_size_bytes=None,
        storage_path=None,
        error="download failed: 503 unavailable",
    )
    manifest = _manifest(failed)
    assert manifest.records and manifest.records[0].storage_path is None
    with pytest.raises(FeatureContractError, match="no kept REAL artifact in the acquisition ledger"):
        run_extraction(
            _request("chirps", Position(latitude=28.0, longitude=90.0)),
            manifest=manifest,
        )


def test_load_manifest_missing_path_returns_empty_ledger(tmp_path):
    """Pins the documented loader bootstrap: missing file -> empty ledger, no I/O."""
    from app.services.acquisition import load_acquisition_manifest

    missing = tmp_path / "no-such-ledger" / "acquisition_manifest.json"
    assert not missing.exists()
    loaded = load_acquisition_manifest(missing)
    assert loaded.records == []
    assert any("initialised empty" in note for note in loaded.notes)
    assert not missing.exists()
    assert not missing.parent.exists()


def test_load_manifest_malformed_raises_manifest_error(tmp_path):
    """Corrupt ledger JSON surfaces as ManifestError, not silent fallback."""
    from app.services.acquisition import ManifestError, load_acquisition_manifest

    bad = tmp_path / "malformed_manifest.json"
    bad.write_text("{ this is not valid json ]", encoding="utf-8")
    with pytest.raises(ManifestError, match="acquisition manifest invalid"):
        load_acquisition_manifest(bad)
    assert bad.exists()  # the malformed test blob is untouched


def test_run_extraction_empty_feature_list_returns_no_features(raw_root, chirps_decoder):
    """requested_features=[] is a schema-valid deliberate zero-output request.

    It must still resolve the record and re-verify artifact identity, returning
    an empty feature list rather than an unverified or REJECTED_LEAKAGE set.
    """
    root, chirp_sha, _ = raw_root
    record = _chirps_record(sha256=chirp_sha, storage_path="chirps/chirps__v2.x__2026-08-31.tif.gz")
    manifest = _manifest(record)
    result = run_extraction(
        _request("chirps", Position(latitude=28.0, longitude=90.0), features=[]),
        manifest=manifest,
        chirps_decoder=chirps_decoder,
        raw_root=root,
    )
    assert result.features == []
    assert result.artifact_sha256 == chirp_sha
    assert result.acquisition_record_id == record.record_id


# ---------------------------------------------------------------------------
# 3.7.8F. Multi-day CHIRPS rolling aggregation
# ---------------------------------------------------------------------------


def test_rolling_3d_sums_exact_window(rollup_root):
    root, written = rollup_root
    days = _window_days(3)
    records = _records_for_days(days, written)
    values = {day: float(index + 1) for index, day in enumerate(days)}
    result = run_extraction(
        _request(
            "chirps",
            Position(latitude=28.0, longitude=90.0),
            features=["precipitation_3d_mm"],
        ),
        manifest=_manifest(*records),
        chirps_decoder=_decoder_for(values),
        raw_root=root,
    )
    feature = result.features[0]
    assert feature.status is FeatureStatus.VALID
    assert feature.value == pytest.approx(6.0)
    assert feature.unit == "mm"
    provenance = feature.provenance
    assert provenance.observation_start_utc.date() == ANCHOR_DATE
    assert [entry.observation_start_utc.date() for entry in provenance.days] == days
    assert [entry.artifact_sha256 for entry in provenance.days] == [
        record.sha256 for record in records
    ]
    assert provenance.artifact_sha256 == records[-1].sha256
    assert provenance.acquisition_record_id == records[-1].record_id


@pytest.mark.parametrize("window_days", [7, 14, 30])
def test_rolling_long_windows_sum_each_required_day(rollup_root, window_days):
    root, written = rollup_root
    days = _window_days(window_days)
    records = _records_for_days(days, written)
    values = {day: 1.0 for day in days}
    result = run_extraction(
        _request(
            "chirps",
            Position(latitude=28.0, longitude=90.0),
            features=[f"precipitation_{window_days}d_mm"],
        ),
        manifest=_manifest(*records),
        chirps_decoder=_decoder_for(values),
        raw_root=root,
    )
    feature = result.features[0]
    assert feature.status is FeatureStatus.VALID
    assert feature.value == pytest.approx(float(window_days))
    assert len(feature.provenance.days) == window_days


def test_rolling_float64_sum_is_unrounded(rollup_root):
    root, written = rollup_root
    days = _window_days(3)
    values = {days[0]: 0.1, days[1]: 0.1, days[2]: 0.1}
    records = _records_for_days(days, written)
    result = run_extraction(
        _request(
            "chirps",
            Position(latitude=28.0, longitude=90.0),
            features=["precipitation_3d_mm"],
        ),
        manifest=_manifest(*records),
        chirps_decoder=_decoder_for(values),
        raw_root=root,
    )
    feature = result.features[0]
    assert feature.status is FeatureStatus.VALID
    assert feature.value == sum(values.values())
    assert feature.value != 0.3


@pytest.mark.parametrize("nodata_index", [0, 1, 2])
def test_rolling_nodata_each_position_missing(rollup_root, nodata_index):
    root, written = rollup_root
    days = _window_days(3)
    values = {day: 1.0 for day in days}
    values[days[nodata_index]] = None
    records = _records_for_days(days, written)
    result = run_extraction(
        _request(
            "chirps",
            Position(latitude=28.0, longitude=90.0),
            features=["precipitation_3d_mm"],
        ),
        manifest=_manifest(*records),
        chirps_decoder=_decoder_for(values),
        raw_root=root,
    )
    feature = result.features[0]
    assert feature.status is FeatureStatus.MISSING
    assert feature.value is None
    assert days[nodata_index].isoformat() in feature.note


@pytest.mark.parametrize("missing_index", [0, 3, 5])
def test_rolling_missing_each_position_insufficient(rollup_root, missing_index):
    root, written = rollup_root
    days = _window_days(7)
    present = [day for index, day in enumerate(days) if index != missing_index]
    records = _records_for_days(present, written)
    values = {day: 1.0 for day in present}
    result = run_extraction(
        _request(
            "chirps",
            Position(latitude=28.0, longitude=90.0),
            features=["precipitation_7d_mm"],
        ),
        manifest=_manifest(*records),
        chirps_decoder=_decoder_for(values),
        raw_root=root,
    )
    feature = result.features[0]
    assert feature.status is FeatureStatus.INSUFFICIENT_TEMPORAL_COVERAGE
    assert feature.value is None
    assert days[missing_index].isoformat() in feature.note
    assert "never zero-filled" in feature.note


def test_rolling_same_sha_duplicate_dedupes_to_one_day(rollup_root):
    root, written = rollup_root
    days = _window_days(3)
    records = _records_for_days(days, written)
    records.insert(
        1,
        _day_record(
            days[1],
            sha=written[days[1]][1],
            storage_path=written[days[1]][0],
            seed="dup",
        ),
    )
    values = {day: 1.0 for day in days}
    result = run_extraction(
        _request(
            "chirps",
            Position(latitude=28.0, longitude=90.0),
            features=["precipitation_3d_mm"],
        ),
        manifest=_manifest(*records),
        chirps_decoder=_decoder_for(values),
        raw_root=root,
    )
    feature = result.features[0]
    assert feature.status is FeatureStatus.VALID
    assert feature.value == pytest.approx(3.0)
    assert len(feature.provenance.days) == 3


def test_rolling_conflicting_sha_duplicate_raises_stable_order(rollup_root):
    root, written = rollup_root
    days = _window_days(3)
    records = _records_for_days(days, written)
    dup_rel = "chirps/chirps__v2.x__2026-08-30-dup.tif.gz"
    dup_path = root / dup_rel
    dup_path.parent.mkdir(parents=True, exist_ok=True)
    dup_path.write_bytes(b"fake-chirps-day-2026-08-30-DUPLICATE")
    dup_sha = sha256_of(dup_path)
    records.insert(1, _day_record(days[1], sha=dup_sha, storage_path=dup_rel, seed="a"))
    records.insert(1, _day_record(days[1], sha=dup_sha, storage_path=dup_rel, seed="b"))
    values = {day: 1.0 for day in days}
    with pytest.raises(FeatureContractError) as excinfo:
        run_extraction(
            _request(
                "chirps",
                Position(latitude=28.0, longitude=90.0),
                features=["precipitation_3d_mm"],
            ),
            manifest=_manifest(*records),
            chirps_decoder=_decoder_for(values),
            raw_root=root,
        )
    message = str(excinfo.value)
    assert "2026-08-30" in message
    assert "different SHA-256" in message
    ids = ["REAL-chirps-v2.0-2026-08-30-a", "REAL-chirps-v2.0-2026-08-30-b"]
    assert all(record_id in message for record_id in ids)
    assert message.index(ids[0]) < message.index(ids[1])


def test_rolling_deterministic_under_shuffled_manifest(rollup_root):
    root, written = rollup_root
    days = _window_days(3)
    values = {days[0]: 0.5, days[1]: 1.5, days[2]: 2.5}
    records = _records_for_days(days, written)
    forward = run_extraction(
        _request(
            "chirps",
            Position(latitude=28.0, longitude=90.0),
            features=["precipitation_3d_mm"],
        ),
        manifest=_manifest(*records),
        chirps_decoder=_decoder_for(values),
        raw_root=root,
    ).features[0]
    backward = run_extraction(
        _request(
            "chirps",
            Position(latitude=28.0, longitude=90.0),
            features=["precipitation_3d_mm"],
        ),
        manifest=_manifest(*reversed(records)),
        chirps_decoder=_decoder_for(values),
        raw_root=root,
    ).features[0]
    assert forward.status is FeatureStatus.VALID
    assert backward.status is FeatureStatus.VALID
    assert forward.value == backward.value
    assert forward.value == pytest.approx(4.5)
    assert [entry.observation_start_utc for entry in forward.provenance.days] == [
        entry.observation_start_utc for entry in backward.provenance.days
    ]


def test_rolling_incompatible_product_version_insufficient(rollup_root):
    root, written = rollup_root
    days = _window_days(3)
    records = _records_for_days(days, written)
    records[0] = _day_record(
        days[0],
        sha=written[days[0]][1],
        storage_path=written[days[0]][0],
        product_version="v1.0",
    )
    values = {day: 1.0 for day in days}
    result = run_extraction(
        _request(
            "chirps",
            Position(latitude=28.0, longitude=90.0),
            features=["precipitation_3d_mm"],
        ),
        manifest=_manifest(*records),
        chirps_decoder=_decoder_for(values),
        raw_root=root,
    )
    feature = result.features[0]
    assert feature.status is FeatureStatus.INSUFFICIENT_TEMPORAL_COVERAGE
    assert feature.value is None
    assert days[0].isoformat() in feature.note


def test_rolling_mixed_preliminary_final_vintages_insufficient(rollup_root):
    root, written = rollup_root
    days = _window_days(3)
    records = _records_for_days(days, written)
    records[0] = _day_record(
        days[0],
        sha=written[days[0]][1],
        storage_path=written[days[0]][0],
        product_version="v2.1",
    )
    values = {day: 1.0 for day in days}
    result = run_extraction(
        _request(
            "chirps",
            Position(latitude=28.0, longitude=90.0),
            features=["precipitation_3d_mm"],
        ),
        manifest=_manifest(*records),
        chirps_decoder=_decoder_for(values),
        raw_root=root,
    )
    feature = result.features[0]
    assert feature.status is FeatureStatus.INSUFFICIENT_TEMPORAL_COVERAGE
    assert feature.value is None
    assert "mixed product vintages" in feature.note


def test_rolling_production_requires_provider_issued_every_day(rollup_root):
    root, written = rollup_root
    days = _window_days(3)
    records = _records_for_days(days, written)
    records[1] = _day_record(
        days[1],
        sha=written[days[1]][1],
        storage_path=written[days[1]][0],
        availability_classification="derived",
    )
    values = {day: 1.0 for day in days}
    result = run_extraction(
        _request(
            "chirps",
            Position(latitude=28.0, longitude=90.0),
            features=["precipitation_3d_mm"],
            policy="production",
        ),
        manifest=_manifest(*records),
        chirps_decoder=_decoder_for(values),
        raw_root=root,
    )
    feature = result.features[0]
    assert feature.status is FeatureStatus.REJECTED_LEAKAGE
    assert feature.value is None
    assert days[1].isoformat() in feature.note


def test_rolling_research_replay_accepts_derived_labelled_days(rollup_root):
    root, written = rollup_root
    days = _window_days(3)
    records = [
        _day_record(
            day,
            sha=written[day][1],
            storage_path=written[day][0],
            availability_classification="derived",
        )
        for day in days
    ]
    values = {day: 1.0 for day in days}
    result = run_extraction(
        _request(
            "chirps",
            Position(latitude=28.0, longitude=90.0),
            features=["precipitation_3d_mm"],
        ),
        manifest=_manifest(*records),
        chirps_decoder=_decoder_for(values),
        raw_root=root,
    )
    feature = result.features[0]
    assert feature.status is FeatureStatus.VALID
    assert feature.value == pytest.approx(3.0)


@pytest.mark.parametrize("policy", ["research_replay", "production"])
def test_rolling_missing_available_utc_rejects_both_policies(rollup_root, policy):
    root, written = rollup_root
    days = _window_days(3)
    records = _records_for_days(days, written)
    records[0] = _day_record(
        days[0],
        sha=written[days[0]][1],
        storage_path=written[days[0]][0],
        available_utc=None,
    )
    values = {day: 1.0 for day in days}
    result = run_extraction(
        _request(
            "chirps",
            Position(latitude=28.0, longitude=90.0),
            features=["precipitation_3d_mm"],
            policy=policy,
        ),
        manifest=_manifest(*records),
        chirps_decoder=_decoder_for(values),
        raw_root=root,
    )
    feature = result.features[0]
    assert feature.status is FeatureStatus.REJECTED_LEAKAGE
    assert feature.value is None


def test_rolling_rejected_day_rejects_every_overlapping_window(rollup_root):
    root, written = rollup_root
    days = _window_days(7)
    records = _records_for_days(days, written)
    records[4] = _day_record(
        days[4],
        sha=written[days[4]][1],
        storage_path=written[days[4]][0],
        availability_classification="derived",
    )
    values = {day: 1.0 for day in days}
    result = run_extraction(
        _request(
            "chirps",
            Position(latitude=28.0, longitude=90.0),
            features=[
                "precipitation_daily_mm",
                "precipitation_3d_mm",
                "precipitation_7d_mm",
            ],
            policy="production",
        ),
        manifest=_manifest(*records),
        chirps_decoder=_decoder_for(values),
        raw_root=root,
    )
    by_name = {feature.feature_name: feature for feature in result.features}
    assert by_name["precipitation_daily_mm"].status is FeatureStatus.VALID
    assert by_name["precipitation_3d_mm"].status is FeatureStatus.REJECTED_LEAKAGE
    assert by_name["precipitation_7d_mm"].status is FeatureStatus.REJECTED_LEAKAGE
    assert all(
        by_name[name].value is None
        for name in ("precipitation_3d_mm", "precipitation_7d_mm")
    )


def test_rolling_sha_verified_before_any_pixel_decode(rollup_root):
    root, written = rollup_root
    days = _window_days(3)
    records = _records_for_days(days, written)
    (root / written[days[1]][0]).write_bytes(b"tampered-chirps-bytes")
    calls = []

    def recorder(path):
        calls.append(path)
        return _grid_for_day(1.0)

    with pytest.raises(FeatureContractError, match="SHA-256 mismatch"):
        run_extraction(
            _request(
                "chirps",
                Position(latitude=28.0, longitude=90.0),
                features=["precipitation_3d_mm"],
            ),
            manifest=_manifest(*records),
            chirps_decoder=recorder,
            raw_root=root,
        )
    tampered_name = Path(written[days[1]][0]).name
    assert all(Path(call).name != tampered_name for call in calls)


def test_rolling_provenance_per_day_fields_and_anchor(rollup_root):
    root, written = rollup_root
    days = _window_days(3)
    records = _records_for_days(days, written)
    values = {day: 1.0 for day in days}
    result = run_extraction(
        _request(
            "chirps",
            Position(latitude=28.0, longitude=90.0),
            features=["precipitation_3d_mm"],
        ),
        manifest=_manifest(*records),
        chirps_decoder=_decoder_for(values),
        raw_root=root,
    )
    provenance = result.features[0].provenance
    assert len(provenance.days) == 3
    assert isinstance(provenance.days[0], FeatureDayProvenance)
    for entry, record in zip(provenance.days, records):
        assert entry.acquisition_record_id == record.record_id
        assert entry.source_record_id == record.source_record_id
        assert entry.artifact_sha256 == record.sha256
        assert entry.available_utc == record.available_utc
        assert entry.availability_classification == record.availability_classification
    assert provenance.artifact_sha256 == provenance.days[-1].artifact_sha256
    assert provenance.acquisition_record_id == provenance.days[-1].acquisition_record_id
    assert provenance.observation_start_utc == provenance.days[-1].observation_start_utc


def test_single_day_provenance_days_omitted(raw_root, chirps_decoder):
    root, chirp_sha, _ = raw_root
    record = _chirps_record(
        sha256=chirp_sha, storage_path="chirps/chirps__v2.x__2026-08-31.tif.gz"
    )
    result = run_extraction(
        _request(
            "chirps",
            Position(latitude=28.0, longitude=90.0),
            features=["precipitation_daily_mm", "precipitation_1d_mm"],
        ),
        manifest=_manifest(record),
        chirps_decoder=chirps_decoder,
        raw_root=root,
    )
    assert result.features
    for feature in result.features:
        assert feature.provenance.days is None


def test_rolling_anchor_leakage_shortcircuits_all_windows(rollup_root):
    root, written = rollup_root
    days = _window_days(3)
    records = _records_for_days(days, written)
    values = {day: 1.0 for day in days}
    result = run_extraction(
        _request(
            "chirps",
            Position(latitude=28.0, longitude=90.0),
            cutoff=datetime(2026, 8, 31, tzinfo=UTC),
            features=[
                "precipitation_daily_mm",
                "precipitation_1d_mm",
                "precipitation_3d_mm",
                "precipitation_7d_mm",
            ],
        ),
        manifest=_manifest(*records),
        chirps_decoder=_decoder_for(values),
        raw_root=root,
    )
    assert all(
        feature.status is FeatureStatus.REJECTED_LEAKAGE for feature in result.features
    )
    assert all(feature.value is None for feature in result.features)


def test_rolling_anchor_preserved_when_dedupe_would_pick_incompatible_duplicate(rollup_root):
    # Phase 3.7.11 hardening of audit finding F2: the version-agnostic same-day
    # dedupe (lowest record_id) can pick an incompatible duplicate for the
    # anchor day, which previously left the anchor slot empty and later fed a
    # per-day list that did not end on the anchor (a pydantic ValidationError).
    # The identity-verified anchor must always be its own day's selected record.
    root, written = rollup_root
    days = _window_days(3)
    anchor_day = days[-1]
    records = [
        record
        for record in _records_for_days(days, written)
        if record.observation_start_utc.date() != anchor_day
    ]
    good = _day_record(
        anchor_day,
        sha=written[anchor_day][1],
        storage_path=written[anchor_day][0],
        product_version="v2.0",
        seed="zzz",
    ).model_copy(update={"acquired_utc": datetime(2026, 10, 10, tzinfo=UTC)})
    bad = _day_record(
        anchor_day,
        sha=written[anchor_day][1],
        storage_path=written[anchor_day][0],
        product_version="v1.0",
    )
    records.extend([good, bad])
    values = {day: 1.0 for day in days}
    result = run_extraction(
        _request(
            "chirps",
            Position(latitude=28.0, longitude=90.0),
            features=["precipitation_3d_mm"],
        ),
        manifest=_manifest(*records),
        chirps_decoder=_decoder_for(values),
        raw_root=root,
    )
    feature = result.features[0]
    assert feature.status is FeatureStatus.VALID
    assert feature.value == pytest.approx(3.0)
    assert len(feature.provenance.days) == 3
    assert feature.provenance.days[-1].acquisition_record_id == good.record_id
    assert feature.provenance.acquisition_record_id == good.record_id
    assert resolve_acquired_record(_manifest(*records), "chirps").record_id == good.record_id
