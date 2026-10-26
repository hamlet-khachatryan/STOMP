import click
import pytest

from common.cli_types import MAP_CAP


@pytest.mark.parametrize("raw", ["auto", "AUTO", "all", "none", "0", 0, None])
def test_map_cap_auto_words_become_none(raw):
    assert MAP_CAP.convert(raw, None, None) is None


@pytest.mark.parametrize("raw, expected", [("50", 50), (55, 55)])
def test_map_cap_numbers_pass_through(raw, expected):
    assert MAP_CAP.convert(raw, None, None) == expected


@pytest.mark.parametrize("raw", ["fifty", "-3", "2.5"])
def test_map_cap_rejects_bad_values(raw):
    with pytest.raises(click.BadParameter):
        MAP_CAP.convert(raw, None, None)
