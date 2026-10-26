import json
import pytest

from analyse.api import (
    _resolve_map_path,
    _resolve_model_path,
    _load_null_params,
    _infer_resolution,
    _run_from_map_location,
)

def _paths(tmp_path, stem="target"):
    """Minimal paths dict mirroring get_experiment_paths output."""
    return {
        "stem": stem,
        "root": tmp_path,
        "quantify_dir": tmp_path / "quantify_results",
        "processed_pdb": tmp_path / "processed" / f"{stem}_updated.pdb",
        "original_pdb": tmp_path / "processed" / f"{stem}_original.pdb",
        "metadata_dir": tmp_path / "metadata",
        "results_dir": tmp_path / "results",
    }

def test_resolve_map_path_missing_quantify_dir_raises(tmp_path):
    paths = _paths(tmp_path)
    with pytest.raises(FileNotFoundError, match="No quantify_results directory"):
        _resolve_map_path(paths, k_factor=1.0, map_cap=50)


def test_resolve_map_path_explicit_cap_found(tmp_path):
    paths = _paths(tmp_path)
    snr = paths["quantify_dir"] / "k_1.0_cap_50" / "target_snr.ccp4"
    snr.parent.mkdir(parents=True)
    snr.touch()

    result = _resolve_map_path(paths, k_factor=1.0, map_cap=50)
    assert result == (snr, 50)


def test_resolve_map_path_explicit_cap_missing_raises(tmp_path):
    paths = _paths(tmp_path)
    paths["quantify_dir"].mkdir(parents=True)

    with pytest.raises(FileNotFoundError, match="SNR map not found"):
        _resolve_map_path(paths, k_factor=1.0, map_cap=50)


def test_resolve_map_path_auto_detect_picks_highest_cap(tmp_path):
    paths = _paths(tmp_path)
    for cap in [10, 30, 50]:
        snr = paths["quantify_dir"] / f"k_1.0_cap_{cap}" / "target_snr.ccp4"
        snr.parent.mkdir(parents=True)
        snr.touch()

    result = _resolve_map_path(paths, k_factor=1.0, map_cap=None)
    assert result == (paths["quantify_dir"] / "k_1.0_cap_50" / "target_snr.ccp4", 50)


def _touch_snr(paths, run_dir):
    snr = paths["quantify_dir"] / run_dir / f"{paths['stem']}_snr.ccp4"
    snr.parent.mkdir(parents=True, exist_ok=True)
    snr.touch()
    return snr


def test_resolve_map_path_auto_detect_compares_caps_numerically(tmp_path):
    paths = _paths(tmp_path)
    _touch_snr(paths, "k_1.0_cap_50")
    snr_100 = _touch_snr(paths, "k_1.0_cap_100")

    assert _resolve_map_path(paths, k_factor=1.0, map_cap=None) == (snr_100, 100)


def test_resolve_map_path_matches_k_numerically(tmp_path):
    paths = _paths(tmp_path)
    snr = _touch_snr(paths, "k_1_cap_50")  # quantify run from Python with k_factor=1

    assert _resolve_map_path(paths, k_factor=1.0, map_cap=50) == (snr, 50)
    assert _resolve_map_path(paths, k_factor=1.0, map_cap=None) == (snr, 50)


def test_resolve_map_path_ignores_other_k(tmp_path):
    paths = _paths(tmp_path)
    _touch_snr(paths, "k_1.0_cap_50")
    _touch_snr(paths, "k_2.0_cap_100")

    assert _resolve_map_path(paths, k_factor=1.0, map_cap=None)[1] == 50


def test_resolve_map_path_does_not_fall_back_to_other_k(tmp_path):
    paths = _paths(tmp_path)
    _touch_snr(paths, "k_1.0_cap_50")

    with pytest.raises(FileNotFoundError, match=r"No SNR map found.*k=1.0, cap=50"):
        _resolve_map_path(paths, k_factor=2.0, map_cap=None)


def test_resolve_map_path_missing_cap_lists_available_runs(tmp_path):
    paths = _paths(tmp_path)
    _touch_snr(paths, "k_1.0_cap_30")

    with pytest.raises(FileNotFoundError, match=r"SNR map not found.*k=1.0, cap=30"):
        _resolve_map_path(paths, k_factor=1.0, map_cap=50)


def test_run_from_map_location_reads_quantify_folder(tmp_path):
    map_path = tmp_path / "quantify_results" / "k_2.0_cap_30" / "target_snr.ccp4"
    assert _run_from_map_location(map_path, k_factor=1.0, map_cap=50) == (2.0, 30)


def test_run_from_map_location_outside_quantify_uses_flags(tmp_path):
    map_path = tmp_path / "maps" / "custom.ccp4"
    assert _run_from_map_location(map_path, k_factor=1.0, map_cap=50) == (1.0, 50)


def test_resolve_map_path_auto_detect_no_maps_raises(tmp_path):
    paths = _paths(tmp_path)
    paths["quantify_dir"].mkdir(parents=True)

    with pytest.raises(FileNotFoundError, match="No SNR map found"):
        _resolve_map_path(paths, k_factor=1.0, map_cap=None)

def test_resolve_model_path_missing_raises(tmp_path):
    paths = _paths(tmp_path)
    with pytest.raises(FileNotFoundError, match="Original model not found"):
        _resolve_model_path(paths)


def test_resolve_model_path_exists_returns_path(tmp_path):
    paths = _paths(tmp_path)
    paths["original_pdb"].parent.mkdir(parents=True)
    paths["original_pdb"].touch()

    result = _resolve_model_path(paths)
    assert result == paths["original_pdb"]

def test_load_null_params_exact_file_present(tmp_path):
    paths = _paths(tmp_path)
    paths["metadata_dir"].mkdir(parents=True)
    null_file = paths["metadata_dir"] / "target_null_params_k1.0_cap50.json"
    null_file.write_text(json.dumps({"df": 5.0, "loc": 0.0, "scale": 1.0}))

    result = _load_null_params(paths, k_factor=1.0, map_cap=50)
    assert result == {"df": 5.0, "loc": 0.0, "scale": 1.0}


def test_load_null_params_ignores_other_k_and_cap(tmp_path):
    paths = _paths(tmp_path)
    paths["metadata_dir"].mkdir(parents=True)
    for name in ["target_null_params_k2.0_cap50.json", "target_null_params_k1.0_cap30.json"]:
        (paths["metadata_dir"] / name).write_text(json.dumps({"df": 3.0, "loc": 0.5, "scale": 0.8}))

    assert _load_null_params(paths, k_factor=1.0, map_cap=50) is None


def test_load_null_params_matches_k_numerically(tmp_path):
    paths = _paths(tmp_path)
    paths["metadata_dir"].mkdir(parents=True)
    (paths["metadata_dir"] / "target_null_params_k1_cap50.json").write_text(
        json.dumps({"df": 5.0, "loc": 0.0, "scale": 1.0})
    )

    assert _load_null_params(paths, k_factor=1.0, map_cap=50) == {"df": 5.0, "loc": 0.0, "scale": 1.0}


def test_load_null_params_ignores_other_stem(tmp_path):
    paths = _paths(tmp_path)
    paths["metadata_dir"].mkdir(parents=True)
    (paths["metadata_dir"] / "other_null_params_k1.0_cap50.json").write_text(
        json.dumps({"df": 5.0, "loc": 0.0, "scale": 1.0})
    )

    assert _load_null_params(paths, k_factor=1.0, map_cap=50) is None


def test_load_null_params_absent_returns_none(tmp_path):
    paths = _paths(tmp_path)
    paths["metadata_dir"].mkdir(parents=True)

    result = _load_null_params(paths, k_factor=1.0, map_cap=50)
    assert result is None

def test_infer_resolution_no_mtz_raises(tmp_path):
    paths = _paths(tmp_path)
    paths["results_dir"].mkdir(parents=True)

    with pytest.raises(FileNotFoundError, match="No MTZ files found"):
        _infer_resolution(paths)
