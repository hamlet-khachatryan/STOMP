import importlib
import os
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, distribution, entry_points
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"

PAIRS = [
    ("pseudo-debias", "stomp-debias", "debias.cli:debias_cli", "debias_alias"),
    ("pseudo-quantify", "stomp-quantify", "quantify.cli:quantify_cli", "quantify_alias"),
    ("pseudo-analyse", "stomp-analyse", "analyse.cli:analyse_cli", "analyse_alias"),
    ("pseudo-screen-report", "stomp-screen-report",
     "analyse.cli:screen_report_cli", "screen_report_alias"),
]


def _load(target):
    module, attr = target.split(":")
    return getattr(importlib.import_module(module), attr)


def _run_alias(alias_name, args, capsys):
    from common import deprecated
    with pytest.raises(SystemExit) as exc:
        getattr(deprecated, alias_name)(args)
    out, err = capsys.readouterr()
    return exc.value.code, out, err


def _run_new(target, prog, args, capsys):
    with pytest.raises(SystemExit) as exc:
        _load(target).main(args=args, prog_name=prog)
    out, err = capsys.readouterr()
    return exc.value.code, out, err


@pytest.mark.parametrize("old,new,target,alias", PAIRS)
def test_alias_help_warns_on_stderr(old, new, target, alias, capsys):
    code, out, err = _run_alias(alias, ["--help"], capsys)
    assert code == 0
    assert err.strip() == (
        f"Warning: '{old}' is deprecated and will be removed in STOMP 0.3.0; "
        f"use '{new}' instead."
    )
    assert f"Usage: {old}" in out


@pytest.mark.parametrize("old,new,target,alias", PAIRS)
def test_alias_stdout_matches_new_command(old, new, target, alias, capsys):
    _, alias_out, _ = _run_alias(alias, ["--help"], capsys)
    _, new_out, new_err = _run_new(target, new, ["--help"], capsys)
    assert new_err == ""
    assert alias_out.replace(old, new) == new_out


def test_alias_forwards_subcommand(capsys):
    code, out, _ = _run_alias("debias_alias", ["generate-params", "--help"], capsys)
    assert code == 0
    assert "Usage: pseudo-debias generate-params" in out


def test_alias_preserves_usage_error_exit_code(capsys):
    code, _, err = _run_alias("quantify_alias", ["--no-such-flag"], capsys)
    new_code, _, _ = _run_new("quantify.cli:quantify_cli", "stomp-quantify",
                              ["--no-such-flag"], capsys)
    assert code == new_code == 2
    assert "deprecated" in err


def test_alias_imports_lazily():
    # Fresh interpreter so other tests' imports don't leak in.
    code = (
        "import sys, common.deprecated; "
        "print(sorted(m for m in ('debias.cli', 'quantify.cli', 'analyse.cli') "
        "if m in sys.modules))"
    )
    env = {**os.environ, "PYTHONPATH": str(SRC)}
    out = subprocess.run([sys.executable, "-c", code], env=env,
                         capture_output=True, text=True, check=True).stdout
    assert out.strip() == "[]"


def test_aliases_table_matches_pairs():
    from common.deprecated import ALIASES
    assert ALIASES == {old: (new, target) for old, new, target, _ in PAIRS}


def test_distribution_is_stomp():
    assert distribution("stomp").version == "0.2.0"


def test_old_distribution_not_installed():
    # Spec R1. pythonpath=["src"] means a leftover src/PSEUDO.egg-info is also
    # found, so pip uninstall alone may not be enough.
    try:
        distribution("PSEUDO")
    except PackageNotFoundError:
        return
    pytest.fail("Old PSEUDO distribution found: run `pip uninstall PSEUDO` "
                "and delete src/PSEUDO.egg-info")


@pytest.mark.parametrize("doc", ["README.md", "docs/index.md"])
def test_migration_note_mentions_stale_egg_info(doc):
    text = (SRC.parent / doc).read_text(encoding="utf-8")
    assert "src/PSEUDO.egg-info" in text


def _console_scripts():
    eps = entry_points()
    if hasattr(eps, "select"):  # Python >= 3.10
        return eps.select(group="console_scripts")
    return eps.get("console_scripts", [])  # Python 3.9 returns a dict


@pytest.mark.parametrize("old,new,target,alias", PAIRS)
def test_console_scripts_registered(old, new, target, alias):
    eps = {ep.name: ep for ep in _console_scripts()}
    assert eps[new].value == target
    assert eps[old].value == f"common.deprecated:{alias}"
    assert callable(eps[new].load())
    assert callable(eps[old].load())
