import pytest

from quantify.api import MapCapError, load_ensemble, never_omitted, resolve_map_cap, schedule_length


def test_load_ensemble_missing_first_map_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="First map not found"):
        load_ensemble(tmp_path / "results", "target", map_cap=5)


def test_load_ensemble_missing_map_raises_instead_of_zero_filling(tmp_path):
    results = tmp_path / "results"
    for i in (0, 1, 3):
        mtz = results / f"target_{i}" / f"target_{i}.mtz"
        mtz.parent.mkdir(parents=True)
        mtz.touch()

    with pytest.raises(FileNotFoundError, match=r"1 of 4 maps missing.*\[2\].*--map_cap 2"):
        load_ensemble(results, "target", map_cap=4)


def _touch_maps(results, indices, stem="target"):
    for i in indices:
        mtz = results / f"{stem}_{i}" / f"{stem}_{i}.mtz"
        mtz.parent.mkdir(parents=True, exist_ok=True)
        mtz.touch()


def test_schedule_length_is_highest_map_id_plus_one():
    assert schedule_length({"A|1|ALA": [0, 12, 54], "A|2|GLY": [3, 20]}) == 55
    assert schedule_length({}) is None
    assert schedule_length(None) is None


def test_resolve_map_cap_auto_uses_each_structures_schedule(tmp_path):
    results = tmp_path / "results"
    _touch_maps(results, range(55))
    assert resolve_map_cap(results, "target", None, n_scheduled=55) == 55


def test_resolve_map_cap_auto_without_schedule_counts_consecutive_maps(tmp_path):
    results = tmp_path / "results"
    _touch_maps(results, [0, 1, 2, 4])
    assert resolve_map_cap(results, "target", None, n_scheduled=None) == 3


def test_resolve_map_cap_auto_with_missing_scheduled_map_raises(tmp_path):
    results = tmp_path / "results"
    _touch_maps(results, range(50))
    with pytest.raises(FileNotFoundError, match=r"5 of 55 maps missing.*--map_cap 50"):
        resolve_map_cap(results, "target", None, n_scheduled=55)


def test_resolve_map_cap_above_schedule_raises(tmp_path):
    results = tmp_path / "results"
    _touch_maps(results, range(50))
    with pytest.raises(MapCapError, match=r"--map_cap 55 exceeds the 50 maps"):
        resolve_map_cap(results, "target", 55, n_scheduled=50)


def test_resolve_map_cap_below_schedule_notes_ignored_maps(tmp_path, capsys):
    results = tmp_path / "results"
    _touch_maps(results, range(55))
    assert resolve_map_cap(results, "target", 50, n_scheduled=55) == 50
    assert "using 50 of 55 maps" in capsys.readouterr().out


def test_resolve_map_cap_needs_two_maps(tmp_path):
    results = tmp_path / "results"
    _touch_maps(results, [0])
    with pytest.raises(MapCapError, match="at least 2 maps"):
        resolve_map_cap(results, "target", None, n_scheduled=None)


def test_never_omitted_lists_owners_cut_off_by_the_cap():
    schedule = {"A|1|ALA": [3, 14], "A|2|GLY": [12, 23], "A|3|SER": []}
    assert never_omitted(schedule, 11) == ["A|2|GLY"]
    assert never_omitted(schedule, 20) == []
    assert never_omitted(None, 5) == []
