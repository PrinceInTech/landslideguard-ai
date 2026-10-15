"""Phase 3.7.2: real-artifact pixel extraction tests.

Proves that the committed feature contract consumes the *actual* CHIRPS
``.tif.gz`` and ERA5-Land ``.nc`` artifacts on disk: built-in readers verify the
artifact geometry, CRS, encoding, nodata and declared units BEFORE interpreting
a pixel, sampling remains nearest-cell with no resampling, and the extraction
pipeline verifies identity before the leakage gate.

Real-artifact tests are skip-guarded on local file presence (nothing is
downloaded) and are deterministic. Synthetic GeoTIFFs exercise every geometry
deviation; according to the contract a deviating artifact is refused, never
guessed at.
"""
import gzip
import struct
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from app.schemas.features import (
    CANONICAL_CRS,
    CHIRPS_NODATA,
    CHIRPS_PIXEL_SIZE,
    CHIRPS_RASTER_HEIGHT,
    CHIRPS_RASTER_WIDTH,
    ERA5_GRID_SPACING,
    ERA5_LATITUDE_COUNT,
    ERA5_LAND_UNITS,
    ERA5_LAND_VARIABLE_MAP,
    ERA5_LONGITUDE_COUNT,
    FeatureStatus,
    Position,
    StudyRegion,
    STUDY_REGION_EAST,
    STUDY_REGION_NORTH,
    STUDY_REGION_SOUTH,
    STUDY_REGION_WEST,
)
from app.services.features import (
    ArtifactReadError,
    FeatureContractError,
    _product_version_compatible,
    _require_era5_units,
    _verify_era5_axes,
    read_chirps_grid,
    read_era5_land_variables,
    run_extraction,
    sample_grid,
)
from app.services.provenance import sha256_of

from test_feature_contract import (
    CHIRPS_SHA,
    ERA5_SHA,
    REAL_CHIRPS,
    REAL_ERA5,
    VALID_CUTOFF,
    _chirps_record,
    _era5_record,
    _manifest,
    _request,
    raw_root,
)

CHIRPS_MISSING = pytest.mark.skipif(
    not REAL_CHIRPS.is_file(), reason="real CHIRPS artifact not present"
)
ERA5_MISSING = pytest.mark.skipif(
    not REAL_ERA5.is_file(), reason="real ERA5-Land artifact not present"
)

# Reference nearest-cell values read from the real artifacts (float32/float64
# round-tripped); they pin the exact byte interpretation of each artifact.
CHIRPS_REFERENCE = {
    (28.02, 90.03): 6.044244766235352,
    (26.00, 94.00): 15.454428672790527,
    (27.02, 96.03): 35.90074920654297,
    (24.00, 95.00): 10.429475784301758,
}
ERA5_REFERENCE = {
    "t2m": 298.893310546875,
    "tp": 0.01135566271841526,
    "swvl1": 0.4433135986328125,
    "sro": 0.0004792064428329468,
}


# ---------------------------------------------------------------------------
# Synthetic classic-TIFF writer (geometry verification, no raster backend)
# ---------------------------------------------------------------------------


def _write_synthetic_chirps_tiff(path: Path, **overrides) -> Path:
    """Write a minimal, structurally valid classic TIFF (gzipped).

    Defaults are the *correct* contracted geometry, so a single keyword
    override isolates exactly one deviation. Strip bytes are a small dummy
    block: every deviation aborts during header verification, before pixels.
    """
    width = overrides.get("width", CHIRPS_RASTER_WIDTH)
    height = overrides.get("height", CHIRPS_RASTER_HEIGHT)
    bits = overrides.get("bits", 32)
    compression = overrides.get("compression", 1)
    samples = overrides.get("samples", 1)
    sample_format = overrides.get("sample_format", 3)
    pixel_scale = overrides.get("pixel_scale", (CHIRPS_PIXEL_SIZE, CHIRPS_PIXEL_SIZE, 0.0))
    tiepoint = overrides.get("tiepoint", (0.0, 0.0, 0.0, -180.0, 50.0, 0.0))
    epsg = overrides.get("epsg", 4326)
    nodata = overrides.get("nodata", None)
    endian = overrides.get("endian", "<")

    row_bytes = width * (bits // 8)
    strip_area = b"\x00" * 16  # dummy: geometry verification never reads pixels
    offsets = [8 + i for i in range(height)]
    geokeys = (1, 1, 0, 4, 1024, 0, 1, 2, 1025, 0, 1, 1, 2048, 0, 1, epsg)

    specs = [
        (256, 3, (width,)),
        (257, 3, (height,)),
        (258, 3, (bits,)),
        (259, 3, (compression,)),
        (262, 3, (1,)),
        (273, 4, tuple(offsets)),
        (277, 3, (samples,)),
        (278, 3, (1,)),
        (279, 4, tuple([row_bytes] * height)),
        (339, 3, (sample_format,)),
        (33550, 12, tuple(pixel_scale)),
        (33922, 12, tuple(tiepoint)),
        (34735, 3, tuple(geokeys)),
    ]
    if nodata is not None:
        specs.append((42113, 2, nodata))

    type_fmt = {2: "B", 3: "H", 4: "I", 12: "d"}
    ifd_start = 8 + len(strip_area)
    entries_start = ifd_start + 2
    value_cursor = entries_start + 12 * len(specs)

    entries = b""
    blobs = b""
    for tag, typ, values in specs:
        if isinstance(values, str):
            raw = values.encode("ascii") + b"\x00"
            count = len(raw)
        else:
            raw = struct.pack(endian + type_fmt[typ] * len(values), *values)
            count = len(values)
        if len(raw) <= 4:
            entries += (
                struct.pack(endian + "HHI", tag, typ, count)
                + raw
                + b"\x00" * (4 - len(raw))
            )
        else:
            if value_cursor % 2:
                blobs += b"\x00"
                value_cursor += 1
            entries += struct.pack(endian + "HHI", tag, typ, count) + struct.pack(
                endian + "I", value_cursor
            )
            blobs += raw
            value_cursor += len(raw)

    header = (b"II" if endian == "<" else b"MM")
    header += struct.pack(endian + "H", 42) + struct.pack(endian + "I", ifd_start)
    directory = struct.pack(endian + "H", len(specs)) + entries
    path.write_bytes(gzip.compress(header + strip_area + directory + blobs))
    return path


# ---------------------------------------------------------------------------
# Contract geometry constants
# ---------------------------------------------------------------------------


def test_contract_geometry_constants_are_self_consistent():
    assert CHIRPS_RASTER_WIDTH * CHIRPS_PIXEL_SIZE == pytest.approx(360.0)
    assert CHIRPS_RASTER_HEIGHT * CHIRPS_PIXEL_SIZE == pytest.approx(100.0)
    assert ERA5_LATITUDE_COUNT == round(
        (STUDY_REGION_NORTH - STUDY_REGION_SOUTH) / ERA5_GRID_SPACING
    ) + 1
    assert ERA5_LONGITUDE_COUNT == round(
        (STUDY_REGION_EAST - STUDY_REGION_WEST) / ERA5_GRID_SPACING
    ) + 1
    assert set(ERA5_LAND_UNITS) == set(ERA5_LAND_VARIABLE_MAP)
    assert CHIRPS_SHA[:8] == "44934651"
    assert ERA5_SHA[:8] == "af53a81a"


# ---------------------------------------------------------------------------
# CHIRPS reader: real artifact
# ---------------------------------------------------------------------------


@CHIRPS_MISSING
def test_real_chirps_reader_returns_verified_study_window():
    raw, lats, lons = read_chirps_grid(REAL_CHIRPS)
    assert raw.shape == (171, 191)
    assert raw.dtype == np.float64
    assert lats[0] == pytest.approx(29.475, abs=1e-5)
    assert lats[-1] == pytest.approx(20.975, abs=1e-5)
    assert lons[0] == pytest.approx(88.025, abs=1e-5)
    assert lons[-1] == pytest.approx(97.525, abs=1e-5)
    assert np.all(np.diff(lats) < 0) and np.all(np.diff(lons) > 0)
    assert np.allclose(np.diff(lats), -CHIRPS_PIXEL_SIZE, rtol=0, atol=1e-6)
    assert np.allclose(np.diff(lons), CHIRPS_PIXEL_SIZE, rtol=0, atol=1e-6)
    # Window statistics tie back to the Phase 3.5 ledger note for this file.
    fill = raw == CHIRPS_NODATA
    valid = raw[~fill]
    assert fill.mean() == pytest.approx(0.0458, abs=0.01)
    assert valid.min() >= 0.0
    assert valid.max() == pytest.approx(186.0284, abs=0.01)
    assert valid.mean() == pytest.approx(19.1763, abs=0.05)
    assert (valid == 0.0).any()


@CHIRPS_MISSING
def test_real_chirps_nearest_cell_reference_values_and_missing_semantics():
    raw, lats, lons = read_chirps_grid(REAL_CHIRPS)
    for (lat, lon), expected in CHIRPS_REFERENCE.items():
        value = sample_grid(raw, lats, lons, lat, lon, sentinels=(CHIRPS_NODATA,))
        assert value == pytest.approx(expected, rel=1e-12), (lat, lon)
    # A -9999 cell is missing, never 0.0; a measured 0.0 stays 0.0.
    assert sample_grid(raw, lats, lons, 21.425, 91.075, sentinels=(CHIRPS_NODATA,)) is None
    assert sample_grid(raw, lats, lons, 21.175, 95.875, sentinels=(CHIRPS_NODATA,)) == 0.0


@CHIRPS_MISSING
def test_chirps_region_outside_raster_extent_rejected_by_reader():
    far = StudyRegion(north=60.0, west=0.0, south=55.0, east=5.0, crs=CANONICAL_CRS)
    with pytest.raises(FeatureContractError, match="outside the verified CHIRPS raster"):
        read_chirps_grid(REAL_CHIRPS, region=far)


# ---------------------------------------------------------------------------
# CHIRPS reader: synthetic geometry deviations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides, pattern",
    [
        ({"width": 100}, "dimensions"),
        ({"height": 100}, "dimensions"),
        ({"pixel_scale": (0.1, 0.1, 0.0)}, "pixel size"),
        ({"tiepoint": (0.0, 0.0, 0.0, 0.0, 50.0, 0.0)}, "origin"),
        ({"epsg": 3857}, "EPSG:4326"),
        ({"bits": 16}, "BitsPerSample"),
        ({"sample_format": 1}, "SampleFormat"),
        ({"compression": 5}, "Compression"),
        ({"samples": 3}, "SamplesPerPixel"),
        ({"nodata": "-1.0"}, "GDAL_NODATA"),
    ],
    ids=[
        "width",
        "height",
        "pixel-scale",
        "origin",
        "crs",
        "bits",
        "sample-format",
        "compression",
        "samples",
        "nodata",
    ],
)
def test_chirps_reader_refuses_geometry_deviations(tmp_path, overrides, pattern):
    artifact = _write_synthetic_chirps_tiff(tmp_path / "bad.tif.gz", **overrides)
    with pytest.raises(FeatureContractError, match=pattern):
        read_chirps_grid(artifact)


def test_chirps_reader_rejects_non_tiff(tmp_path):
    artifact = tmp_path / "garbage.tif.gz"
    artifact.write_bytes(gzip.compress(b"not a tiff file at all, honestly"))
    with pytest.raises(FeatureContractError, match="byte-order marker"):
        read_chirps_grid(artifact)


def test_chirps_reader_rejects_bigtiff(tmp_path):
    artifact = tmp_path / "big.tif.gz"
    blob = b"II" + struct.pack("<H", 43) + struct.pack("<I", 8) + b"\x00" * 32
    artifact.write_bytes(gzip.compress(blob))
    with pytest.raises(FeatureContractError, match="BigTIFF"):
        read_chirps_grid(artifact)


def test_chirps_reader_accepts_valid_header_then_fails_on_truncated_pixels(tmp_path):
    """Correct geometry passes verification; pixel truncation is still loud."""
    artifact = _write_synthetic_chirps_tiff(tmp_path / "ok.tif.gz")
    with pytest.raises(ArtifactReadError, match="truncated strip"):
        read_chirps_grid(artifact)


# ---------------------------------------------------------------------------
# ERA5-Land reader: pure axis / unit verification
# ---------------------------------------------------------------------------


def _contract_axes():
    lats = STUDY_REGION_NORTH - ERA5_GRID_SPACING * np.arange(ERA5_LATITUDE_COUNT)
    lons = STUDY_REGION_WEST + ERA5_GRID_SPACING * np.arange(ERA5_LONGITUDE_COUNT)
    return lats, lons


def test_verify_era5_axes_accepts_contract_geometry():
    lats, lons = _contract_axes()
    _verify_era5_axes(lats, lons, path=Path("era5.nc"))


def test_verify_era5_axes_rejects_wrong_dimensions():
    lats = STUDY_REGION_NORTH - ERA5_GRID_SPACING * np.arange(ERA5_LATITUDE_COUNT - 1)
    _, lons = _contract_axes()
    with pytest.raises(FeatureContractError, match="points !="):
        _verify_era5_axes(lats, lons, path=Path("era5.nc"))


def test_verify_era5_axes_rejects_ascending_latitude():
    lats = STUDY_REGION_SOUTH + ERA5_GRID_SPACING * np.arange(ERA5_LATITUDE_COUNT)
    _, lons = _contract_axes()
    with pytest.raises(FeatureContractError, match="descending"):
        _verify_era5_axes(lats, lons, path=Path("era5.nc"))


def test_verify_era5_axes_rejects_wrong_spacing():
    lats = STUDY_REGION_NORTH - (ERA5_GRID_SPACING / 2) * np.arange(ERA5_LATITUDE_COUNT)
    _, lons = _contract_axes()
    with pytest.raises(FeatureContractError, match="spacing"):
        _verify_era5_axes(lats, lons, path=Path("era5.nc"))


def test_verify_era5_axes_rejects_wrong_extent():
    lats = (STUDY_REGION_NORTH + 1.0) - ERA5_GRID_SPACING * np.arange(ERA5_LATITUDE_COUNT)
    _, lons = _contract_axes()
    with pytest.raises(FeatureContractError, match="extent"):
        _verify_era5_axes(lats, lons, path=Path("era5.nc"))


def test_require_era5_units_accepts_contract_units():
    _require_era5_units(dict(ERA5_LAND_UNITS), path=Path("era5.nc"))


def test_require_era5_units_rejects_declared_mismatch():
    units = dict(ERA5_LAND_UNITS)
    units["t2m"] = "hPa"
    with pytest.raises(FeatureContractError, match="units"):
        _require_era5_units(units, path=Path("era5.nc"))


def test_require_era5_units_rejects_missing_unit():
    units = dict(ERA5_LAND_UNITS)
    units["swvl1"] = None
    with pytest.raises(FeatureContractError, match="units"):
        _require_era5_units(units, path=Path("era5.nc"))


def test_era5_reader_rejects_missing_variable(tmp_path):
    netCDF4 = pytest.importorskip("netCDF4")
    path = tmp_path / "era5-partial.nc"
    dataset = netCDF4.Dataset(str(path), "w", format="NETCDF4")
    try:
        dataset.createDimension("latitude", ERA5_LATITUDE_COUNT)
        dataset.createDimension("longitude", ERA5_LONGITUDE_COUNT)
        la = dataset.createVariable("latitude", "f8", ("latitude",))
        la[:] = STUDY_REGION_NORTH - ERA5_GRID_SPACING * np.arange(ERA5_LATITUDE_COUNT)
        lo = dataset.createVariable("longitude", "f8", ("longitude",))
        lo[:] = STUDY_REGION_WEST + ERA5_GRID_SPACING * np.arange(ERA5_LONGITUDE_COUNT)
        t2m = dataset.createVariable("t2m", "f4", ("latitude", "longitude"))
        t2m.units = "K"
        t2m[:] = 293.0
    finally:
        dataset.close()
    with pytest.raises(FeatureContractError, match="missing required variable"):
        read_era5_land_variables(path)


# ---------------------------------------------------------------------------
# ERA5-Land reader: real artifact
# ---------------------------------------------------------------------------


@ERA5_MISSING
def test_real_era5_reader_verifies_grid_and_units():
    pytest.importorskip("netCDF4")
    grids = read_era5_land_variables(REAL_ERA5)
    assert set(grids) == set(ERA5_LAND_VARIABLE_MAP)
    for raw, lats, lons in grids.values():
        assert lats.shape == (ERA5_LATITUDE_COUNT,)
        assert lons.shape == (ERA5_LONGITUDE_COUNT,)
    lats, lons = grids["t2m"][1], grids["t2m"][2]
    assert lats[0] == pytest.approx(STUDY_REGION_NORTH, abs=1e-9)
    assert lats[-1] == pytest.approx(STUDY_REGION_SOUTH, abs=1e-9)
    assert lons[0] == pytest.approx(STUDY_REGION_WEST, abs=1e-9)
    assert lons[-1] == pytest.approx(STUDY_REGION_EAST, abs=1e-9)
    assert np.allclose(np.diff(lats), -ERA5_GRID_SPACING, rtol=0, atol=1e-9)
    assert np.allclose(np.diff(lons), ERA5_GRID_SPACING, rtol=0, atol=1e-9)


@ERA5_MISSING
def test_real_era5_nearest_cell_reference_values_and_missing_semantics():
    pytest.importorskip("netCDF4")
    grids = read_era5_land_variables(REAL_ERA5)
    for short, expected in ERA5_REFERENCE.items():
        raw, lats, lons = grids[short]
        assert sample_grid(raw, lats, lons, 26.0, 94.0) == pytest.approx(
            expected, rel=1e-12
        ), short
    # _FillValue/NaN cells are missing; a measured 0.0 stays valid.
    assert sample_grid(*grids["t2m"], 21.5, 90.6) is None
    assert sample_grid(*grids["sro"], 23.7, 90.0) == 0.0


@ERA5_MISSING
def test_era5_region_outside_grid_extent_rejected_by_reader():
    pytest.importorskip("netCDF4")
    far = StudyRegion(north=60.0, west=0.0, south=55.0, east=5.0, crs=CANONICAL_CRS)
    with pytest.raises(FeatureContractError, match="outside the verified ERA5-Land grid"):
        read_era5_land_variables(REAL_ERA5, region=far)


# ---------------------------------------------------------------------------
# Identity: product / version / SHA-256 (before the leakage gate)
# ---------------------------------------------------------------------------


def test_registry_wildcard_product_version_is_accepted():
    from app.services.acquisition import get_source_config

    assert _product_version_compatible("v2.0", get_source_config("chirps").product_version)
    assert _product_version_compatible("v2.x", "v2.x")
    assert not _product_version_compatible("v3.0", "v2.x")
    assert not _product_version_compatible("v2.0", "v1.x")


def test_identity_rejects_product_mismatch(raw_root):
    root, chirp_sha, _ = raw_root
    record = _chirps_record(
        sha256=chirp_sha,
        storage_path="chirps/chirps__v2.x__2026-08-31.tif.gz",
        product="Not the registered CHIRPS product",
    )
    with pytest.raises(FeatureContractError, match="product mismatch"):
        run_extraction(
            _request("chirps", Position(latitude=28.0, longitude=90.0)),
            manifest=_manifest(record),
            raw_root=root,
        )


def test_identity_rejects_product_version_mismatch(raw_root):
    root, chirp_sha, _ = raw_root
    record = _chirps_record(
        sha256=chirp_sha,
        storage_path="chirps/chirps__v2.x__2026-08-31.tif.gz",
        product_version="v3.0",
    )
    with pytest.raises(FeatureContractError, match="version mismatch"):
        run_extraction(
            _request("chirps", Position(latitude=28.0, longitude=90.0)),
            manifest=_manifest(record),
            raw_root=root,
        )


def test_identity_rejects_wrong_checksum_before_leakage(raw_root):
    """A bad ledger checksum aborts even when the request would also leak."""
    root, chirp_sha, _ = raw_root
    record = _chirps_record(
        sha256="0" * 64, storage_path="chirps/chirps__v2.x__2026-08-31.tif.gz"
    )
    with pytest.raises(FeatureContractError, match="SHA-256 mismatch"):
        run_extraction(
            _request(
                "chirps",
                Position(latitude=28.0, longitude=90.0),
                cutoff=datetime(2026, 8, 1, 0, 0, tzinfo=UTC),  # would leak too
            ),
            manifest=_manifest(record),
            raw_root=root,
        )


def test_non_real_source_kind_is_rejected(raw_root, monkeypatch):
    from app.services import features as features_module
    from app.services.acquisition import get_source_config

    demo = get_source_config("chirps").model_copy(update={"kind": "DEMO"})
    monkeypatch.setattr(features_module, "get_source_config", lambda _name: demo)
    root, chirp_sha, _ = raw_root
    record = _chirps_record(
        sha256=chirp_sha, storage_path="chirps/chirps__v2.x__2026-08-31.tif.gz"
    )
    with pytest.raises(FeatureContractError, match="not REAL"):
        run_extraction(
            _request("chirps", Position(latitude=28.0, longitude=90.0)),
            manifest=_manifest(record),
            raw_root=root,
        )


def test_era5_unknown_feature_name_rejected(raw_root):
    root, _, era5_sha = raw_root
    record = _era5_record(
        sha256=era5_sha, storage_path="era5-land/era5-land__op.nc", file_size_bytes=13
    )
    with pytest.raises(FeatureContractError, match="unsupported feature"):
        run_extraction(
            _request("era5-land", Position(latitude=26.0, longitude=94.0), features=["snow_depth_m"]),
            manifest=_manifest(record),
            raw_root=root,
        )


# ---------------------------------------------------------------------------
# End-to-end extraction against the real artifacts
# ---------------------------------------------------------------------------


@CHIRPS_MISSING
def test_run_extraction_real_chirps_preserves_provenance():
    record = _chirps_record()
    result = run_extraction(
        _request(
            "chirps",
            Position(latitude=28.02, longitude=90.03),
            features=["precipitation_daily_mm", "precipitation_1d_mm", "precipitation_7d_mm"],
        ),
        manifest=_manifest(record),
    )
    assert result.contract_version == "1.1.0"
    assert result.source == "chirps"
    assert result.artifact_sha256 == CHIRPS_SHA
    assert result.storage_path == "chirps/chirps__v2.x__2026-08-31.tif.gz"
    by_name = {feature.feature_name: feature for feature in result.features}
    daily = by_name["precipitation_daily_mm"]
    one_day = by_name["precipitation_1d_mm"]
    seven = by_name["precipitation_7d_mm"]
    assert daily.status is FeatureStatus.VALID
    assert daily.value == pytest.approx(CHIRPS_REFERENCE[(28.02, 90.03)], rel=1e-12)
    assert one_day.status is FeatureStatus.VALID and one_day.value == daily.value
    assert seven.status is FeatureStatus.INSUFFICIENT_TEMPORAL_COVERAGE
    assert seven.value is None
    prov = daily.provenance
    assert prov.source_record_id == "chirps-v2.0.2026.08.31.tif.gz"
    assert prov.artifact_sha256 == CHIRPS_SHA
    assert prov.coordinate_precision == 0.025
    assert prov.observation_start_utc == datetime(2026, 8, 31, tzinfo=UTC)
    assert prov.observation_end_utc == datetime(2026, 9, 1, tzinfo=UTC)
    assert prov.available_utc == datetime(2026, 9, 11, 21, 10, 59, tzinfo=UTC)
    assert prov.prediction_cutoff_utc == VALID_CUTOFF
    assert prov.crs.startswith("EPSG:4326")


@CHIRPS_MISSING
def test_run_extraction_real_chirps_missing_and_valid_zero():
    record = _chirps_record()
    missing = run_extraction(
        _request(
            "chirps", Position(latitude=21.425, longitude=91.075), features=["precipitation_daily_mm"]
        ),
        manifest=_manifest(record),
    ).features[0]
    assert missing.status is FeatureStatus.MISSING
    assert missing.value is None
    assert "nodata" in missing.note
    zero = run_extraction(
        _request(
            "chirps", Position(latitude=21.175, longitude=95.875), features=["precipitation_daily_mm"]
        ),
        manifest=_manifest(record),
    ).features[0]
    assert zero.status is FeatureStatus.VALID
    assert zero.value == 0.0


@CHIRPS_MISSING
def test_run_extraction_real_chirps_rejects_region_beyond_extent():
    far = StudyRegion(north=60.0, west=0.0, south=55.0, east=5.0, crs=CANONICAL_CRS)
    with pytest.raises(FeatureContractError, match="outside the verified CHIRPS raster"):
        run_extraction(
            _request(
                "chirps",
                Position(latitude=57.0, longitude=3.0),
                features=["precipitation_daily_mm"],
                region=far,
            ),
            manifest=_manifest(_chirps_record()),
        )


@CHIRPS_MISSING
def test_run_extraction_real_chirps_leakage_gate_still_executes():
    record = _chirps_record()
    result = run_extraction(
        _request(
            "chirps",
            Position(latitude=28.02, longitude=90.03),
            cutoff=datetime(2026, 8, 31, tzinfo=UTC),
            features=["precipitation_daily_mm"],
        ),
        manifest=_manifest(record),
    )
    feature = result.features[0]
    assert feature.status is FeatureStatus.REJECTED_LEAKAGE
    assert feature.value is None
    assert "rejected for leakage" in feature.note


@ERA5_MISSING
def test_run_extraction_real_era5_all_variables_and_provenance():
    pytest.importorskip("netCDF4")
    record = _era5_record()
    result = run_extraction(
        _request(
            "era5-land",
            Position(latitude=26.0, longitude=94.0),
            features=[
                "temperature_2m_K",
                "precipitation_hourly_m",
                "soil_water_layer1_m3m3",
                "surface_runoff_m",
            ],
        ),
        manifest=_manifest(record),
    )
    expected = {
        "temperature_2m_K": (ERA5_REFERENCE["t2m"], "K"),
        "precipitation_hourly_m": (ERA5_REFERENCE["tp"], "m"),
        "soil_water_layer1_m3m3": (ERA5_REFERENCE["swvl1"], "m3/m3"),
        "surface_runoff_m": (ERA5_REFERENCE["sro"], "m"),
    }
    assert result.artifact_sha256 == ERA5_SHA
    assert len(result.features) == 4
    for feature in result.features:
        value, unit = expected[feature.feature_name]
        assert feature.status is FeatureStatus.VALID
        assert feature.value == pytest.approx(value, rel=1e-12)
        assert feature.unit == unit
        assert feature.provenance.artifact_sha256 == ERA5_SHA
        assert feature.provenance.coordinate_precision == 0.05


@ERA5_MISSING
def test_run_extraction_real_era5_missing_and_valid_zero():
    pytest.importorskip("netCDF4")
    record = _era5_record()
    missing = run_extraction(
        _request(
            "era5-land",
            Position(latitude=21.5, longitude=90.6),
            features=["temperature_2m_K", "soil_water_layer1_m3m3"],
        ),
        manifest=_manifest(record),
    )
    assert all(f.status is FeatureStatus.MISSING for f in missing.features)
    assert all(f.value is None for f in missing.features)
    zero = run_extraction(
        _request("era5-land", Position(latitude=23.7, longitude=90.0), features=["surface_runoff_m"]),
        manifest=_manifest(record),
    ).features[0]
    assert zero.status is FeatureStatus.VALID
    assert zero.value == 0.0


@ERA5_MISSING
def test_run_extraction_real_era5_wrong_checksum_rejected():
    pytest.importorskip("netCDF4")
    record = _era5_record(sha256="0" * 64)
    with pytest.raises(FeatureContractError, match="SHA-256 mismatch"):
        run_extraction(
            _request("era5-land", Position(latitude=26.0, longitude=94.0), features=["temperature_2m_K"]),
            manifest=_manifest(record),
        )


@pytest.mark.skipif(
    not (REAL_CHIRPS.is_file() and REAL_ERA5.is_file()),
    reason="real artifacts not present",
)
def test_extraction_never_modifies_real_artifacts():
    pytest.importorskip("netCDF4")
    before = {path: sha256_of(path) for path in (REAL_CHIRPS, REAL_ERA5)}
    run_extraction(
        _request("chirps", Position(latitude=28.02, longitude=90.03), features=["precipitation_daily_mm"]),
        manifest=_manifest(_chirps_record()),
    )
    run_extraction(
        _request("era5-land", Position(latitude=26.0, longitude=94.0), features=["temperature_2m_K"]),
        manifest=_manifest(_era5_record()),
    )
    after = {path: sha256_of(path) for path in (REAL_CHIRPS, REAL_ERA5)}
    assert before == after


def test_demo_artifacts_still_verify_untouched():
    from app.services.provenance import verify_artifact_checksums

    assert verify_artifact_checksums() == []


@CHIRPS_MISSING
def test_run_extraction_real_chirps_production_path():
    """Synthetic test-fixture data only.

    The ``provider_issued`` classification on the in-memory record is fabricated
    for this pipeline-compatibility test and is NOT evidence of real provider
    availability. ``available_utc`` is the committed ledger value (required by
    the production gate to be non-null) and is likewise not a new acquisition.
    The committed manifest and artifact bytes are never written; identity is
    verified against the pinned SHA-256 before any gate runs.
    """
    record = _chirps_record(availability_classification="provider_issued")
    before = {path: sha256_of(path) for path in (REAL_CHIRPS, REAL_ERA5)}
    assert before[REAL_CHIRPS] == CHIRPS_SHA
    assert before[REAL_ERA5] == ERA5_SHA
    result = run_extraction(
        _request(
            "chirps",
            Position(latitude=28.02, longitude=90.03),
            policy="production",
            sha=CHIRPS_SHA,
            features=["precipitation_daily_mm", "precipitation_1d_mm", "precipitation_7d_mm"],
        ),
        manifest=_manifest(record),
    )
    assert result.contract_version == "1.1.0"
    assert result.artifact_sha256 == CHIRPS_SHA
    assert result.storage_path == "chirps/chirps__v2.x__2026-08-31.tif.gz"
    by_name = {feature.feature_name: feature for feature in result.features}
    for feature in result.features:
        assert feature.status is not FeatureStatus.REJECTED_LEAKAGE
        assert feature.provenance.availability_classification == "provider_issued"
        assert feature.provenance.artifact_sha256 == CHIRPS_SHA
        assert feature.provenance.prediction_cutoff_utc == VALID_CUTOFF
    daily = by_name["precipitation_daily_mm"]
    one_day = by_name["precipitation_1d_mm"]
    seven = by_name["precipitation_7d_mm"]
    assert daily.status is FeatureStatus.VALID
    assert daily.value == pytest.approx(CHIRPS_REFERENCE[(28.02, 90.03)], rel=1e-12)
    assert one_day.status is FeatureStatus.VALID and one_day.value == daily.value
    assert seven.status is FeatureStatus.INSUFFICIENT_TEMPORAL_COVERAGE
    assert seven.value is None
    after = {path: sha256_of(path) for path in (REAL_CHIRPS, REAL_ERA5)}
    assert after == before
    blocked = run_extraction(
        _request(
            "chirps",
            Position(latitude=28.02, longitude=90.03),
            policy="production",
            sha=CHIRPS_SHA,
            features=["precipitation_daily_mm"],
        ),
        manifest=_manifest(_chirps_record()),
    )
    assert all(
        feature.status is FeatureStatus.REJECTED_LEAKAGE for feature in blocked.features
    )


@ERA5_MISSING
def test_run_extraction_real_era5_production_path():
    """Synthetic test-fixture data only.

    Same constraints as the CHIRPS production-path test: the in-memory
    ``provider_issued`` classification never leaves this test, the committed
    artifact bytes and ledger are untouched, and the ``available_utc`` is the
    committed ledger value required by the production gate, not evidence.
    """
    pytest.importorskip("netCDF4")
    record = _era5_record(availability_classification="provider_issued")
    before = {path: sha256_of(path) for path in (REAL_CHIRPS, REAL_ERA5)}
    assert before[REAL_CHIRPS] == CHIRPS_SHA
    assert before[REAL_ERA5] == ERA5_SHA
    result = run_extraction(
        _request(
            "era5-land",
            Position(latitude=26.0, longitude=94.0),
            policy="production",
            sha=ERA5_SHA,
            features=[
                "temperature_2m_K",
                "precipitation_hourly_m",
                "soil_water_layer1_m3m3",
                "surface_runoff_m",
            ],
        ),
        manifest=_manifest(record),
    )
    expected = {
        "temperature_2m_K": (ERA5_REFERENCE["t2m"], "K"),
        "precipitation_hourly_m": (ERA5_REFERENCE["tp"], "m"),
        "soil_water_layer1_m3m3": (ERA5_REFERENCE["swvl1"], "m3/m3"),
        "surface_runoff_m": (ERA5_REFERENCE["sro"], "m"),
    }
    assert result.contract_version == "1.1.0"
    assert result.artifact_sha256 == ERA5_SHA
    assert len(result.features) == 4
    for feature in result.features:
        assert feature.status is not FeatureStatus.REJECTED_LEAKAGE
        value, unit = expected[feature.feature_name]
        assert feature.status is FeatureStatus.VALID
        assert feature.value == pytest.approx(value, rel=1e-12)
        assert feature.unit == unit
        assert feature.provenance.availability_classification == "provider_issued"
        assert feature.provenance.artifact_sha256 == ERA5_SHA
        assert feature.provenance.prediction_cutoff_utc == VALID_CUTOFF
    after = {path: sha256_of(path) for path in (REAL_CHIRPS, REAL_ERA5)}
    assert after == before
    blocked = run_extraction(
        _request(
            "era5-land",
            Position(latitude=26.0, longitude=94.0),
            policy="production",
            sha=ERA5_SHA,
            features=["temperature_2m_K"],
        ),
        manifest=_manifest(_era5_record()),
    )
    assert all(
        feature.status is FeatureStatus.REJECTED_LEAKAGE for feature in blocked.features
    )
