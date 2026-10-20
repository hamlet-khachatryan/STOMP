# Rename PSEUDO → STOMP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the distribution, CLI commands, user-facing strings, docs and GitHub repo from PSEUDO to STOMP. The old `pseudo-*` commands keep working as deprecated aliases.

**Architecture:** `pyproject.toml` registers 6 `stomp-*` console scripts that point at the existing click commands. The 6 old `pseudo-*` names point at small forwarders in a new `src/common/deprecated.py`. Each forwarder prints a warning to stderr, lazily imports the real command and runs it under the old program name. Everything else is text edits, protected by a guard test that rejects any leftover project-name reference.

**Tech Stack:** Python ≥3.9, setuptools, click, pytest, ruff, Jekyll (GitHub Pages).

**Spec:** `docs/superpowers/specs/2026-10-20-rename-pseudo-to-stomp-design.md`

## Global Constraints

- Distribution name: `stomp` (lowercase). Version: `0.2.0`. Branding in prose: "STOMP".
- Alias removal target is stated as: `STOMP 0.3.0`.
- Warning text (exact): `Warning: '<old>' is deprecated and will be removed in STOMP 0.3.0; use '<new>' instead.` It goes to **stderr only**.
- No `STOMP_SUPPRESS_DEPRECATION` env var.
- Python import packages (`debias`, `quantify`, `analyse`, `common`, `conf`) are **not** renamed.
- "STOMP maps", `STOMP_μ`, `STOMP_SNR` wording is unchanged. "STOMP" alone = the toolkit; the method is always "STOMP maps" / "STOMP ensemble".
- **Never** run a global find-and-replace for `pseudo`. Edit only the files listed in each task. "pseudo" as an ordinary scientific word (pseudo-symmetry etc.) must survive.
- Do not touch untracked `experiments/**` or `docs/theory.md`.
- Logo artwork: rename files only. The user supplies new SVGs later (Task 5).
- Commit trailer on every commit: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`

## Review Focus

1. **Alias with subcommands/args**: `pseudo-debias generate-params --help` must reach the `generate-params` subcommand, not just the group. Pinned in Task 1 (`test_alias_forwards_subcommand`).
2. **Exit codes through the alias**: a bad option (`pseudo-quantify --no-such-flag`) must exit 2 exactly like `stomp-quantify`. Pinned in Task 1 (`test_alias_preserves_usage_error_exit_code`).
3. **stdout untouched by the warning**: stdout of the alias must equal stdout of the new command, and the warning appears only on stderr. Pinned in Task 1 (`test_alias_stdout_matches_new_command`).
4. **Stale `PSEUDO` distribution still installed alongside `stomp`** (spec R1): this must fail loudly in the test suite, not cause mysterious breakage later. Pinned in Task 1 (`test_old_distribution_not_installed`).
5. **Alias must not import unrelated heavy modules**: importing `common.deprecated` must not import `quantify.cli` or `analyse.cli`, so a broken dependency in one module can't stop another command from running. Pinned in Task 1 (`test_alias_imports_lazily`).

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `src/common/deprecated.py` | Create | The 6 forwarders `pseudo-*` → real click commands |
| `pyproject.toml` | Modify | Name, version, description, 12 console scripts |
| `tests/test_cli_aliases.py` | Create | Alias behaviour + entry-point + install-state tests |
| `tests/test_no_legacy_name.py` | Create | Guard: no leftover PSEUDO / `pseudo-<cmd>` references outside the allowlist |
| `src/analyse/api.py`, `src/analyse/cli.py`, `src/analyse/screen_report.py`, `src/analyse/muse/config.py`, `src/quantify/delta.py`, `src/quantify/end.py`, `src/main.py` | Modify | User-facing strings |
| `README.md`, `docs/index.md`, `docs/guides/*.md`, `docs/reference.md`, `docs/api.md`, `docs/_config.yml` | Modify | Docs |
| `docs/assets/images/pseudo_logo_*.svg` | `git mv` → `stomp_logo_*.svg` | Logo assets |

---

### Task 1: Packaging + deprecated aliases

**Files:**
- Create: `src/common/deprecated.py`
- Modify: `pyproject.toml` (`[project]` name/version/description, `[project.scripts]`)
- Test: `tests/test_cli_aliases.py`

**Interfaces:**
- Consumes: existing click objects `debias.cli:debias_cli` (group, subcommand `generate-params`), `quantify.cli:quantify_cli`, `quantify.cli:end_cli`, `quantify.cli:delta_cli`, `analyse.cli:analyse_cli`, `analyse.cli:screen_report_cli`.
- Produces: `common.deprecated.ALIASES: dict[str, tuple[str, str]]` mapping old name → (new name, `"module:attr"`). Six callables `debias_alias`, `quantify_alias`, `end_alias`, `delta_alias`, `analyse_alias`, `screen_report_alias`, each with signature `(args: list[str] | None = None) -> None`. They raise `SystemExit` like click standalone mode.

- [ ] **Step 1: Check the precondition and create the branch**

`end_maps_stomp` must already be merged into `main` (spec R11). Run:

```bash
git checkout main && git pull
grep -n "def end_cli\|def delta_cli" src/quantify/cli.py
```
Expected: both functions found. **If either is missing, stop. `end_maps_stomp` is not merged yet.**

```bash
git checkout -b rename-to-stomp
pip uninstall -y PSEUDO
rm -rf src/PSEUDO.egg-info build
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_cli_aliases.py`:

```python
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
    ("pseudo-end", "stomp-end", "quantify.cli:end_cli", "end_alias"),
    ("pseudo-delta", "stomp-delta", "quantify.cli:delta_cli", "delta_alias"),
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
    # If this fails: run `pip uninstall PSEUDO` (spec R1).
    with pytest.raises(PackageNotFoundError):
        distribution("PSEUDO")


@pytest.mark.parametrize("old,new,target,alias", PAIRS)
def test_console_scripts_registered(old, new, target, alias):
    eps = {ep.name: ep for ep in entry_points(group="console_scripts")}
    assert eps[new].value == target
    assert eps[old].value == f"common.deprecated:{alias}"
    assert callable(eps[new].load())
    assert callable(eps[old].load())
```

(`entry_points(group=...)` needs Python ≥3.10. If CI or users run 3.9, use `entry_points()["console_scripts"]` behind a `sys.version_info` check. CI uses 3.11.)

- [ ] **Step 3: Run the tests and check they fail**

Run: `pytest tests/test_cli_aliases.py -v`
Expected: FAIL. `ModuleNotFoundError: No module named 'common.deprecated'` / `PackageNotFoundError: stomp`.

- [ ] **Step 4: Create `src/common/deprecated.py`**

```python
"""Deprecated ``pseudo-*`` console-script aliases (STOMP was formerly PSEUDO).

Each alias warns on stderr and forwards to its ``stomp-*`` replacement.
Remove this module and the alias entries in pyproject.toml in STOMP 0.3.0.
"""
import importlib

import click

ALIASES = {
    "pseudo-debias": ("stomp-debias", "debias.cli:debias_cli"),
    "pseudo-quantify": ("stomp-quantify", "quantify.cli:quantify_cli"),
    "pseudo-end": ("stomp-end", "quantify.cli:end_cli"),
    "pseudo-delta": ("stomp-delta", "quantify.cli:delta_cli"),
    "pseudo-analyse": ("stomp-analyse", "analyse.cli:analyse_cli"),
    "pseudo-screen-report": ("stomp-screen-report", "analyse.cli:screen_report_cli"),
}


def _forward(old):
    new, target = ALIASES[old]

    def alias(args=None):
        click.echo(
            f"Warning: '{old}' is deprecated and will be removed in STOMP 0.3.0; "
            f"use '{new}' instead.",
            err=True,
        )
        module, attr = target.split(":")
        command = getattr(importlib.import_module(module), attr)
        command.main(args=args, prog_name=old)

    alias.__name__ = old.replace("-", "_")
    return alias


debias_alias = _forward("pseudo-debias")
quantify_alias = _forward("pseudo-quantify")
end_alias = _forward("pseudo-end")
delta_alias = _forward("pseudo-delta")
analyse_alias = _forward("pseudo-analyse")
screen_report_alias = _forward("pseudo-screen-report")
```

(`command.main(args=None, ...)` reads `sys.argv[1:]`, which is what a console script needs. Click's standalone mode raises `SystemExit` with the command's exit code.)

- [ ] **Step 5: Update `pyproject.toml`**

In `[project]`:

```toml
name = "stomp"
version = "0.2.0"
description = "STOMP is a computational framework for debiasing and uncertainty quantification in protein structural models solved by molecular replacement."
```

Replace the whole `[project.scripts]` table with:

```toml
[project.scripts]
stomp-debias = "debias.cli:debias_cli"
stomp-quantify = "quantify.cli:quantify_cli"
stomp-end = "quantify.cli:end_cli"
stomp-delta = "quantify.cli:delta_cli"
stomp-analyse = "analyse.cli:analyse_cli"
stomp-screen-report = "analyse.cli:screen_report_cli"
# deprecated aliases (STOMP was formerly PSEUDO) — remove in 0.3.0
pseudo-debias = "common.deprecated:debias_alias"  # deprecated
pseudo-quantify = "common.deprecated:quantify_alias"  # deprecated
pseudo-end = "common.deprecated:end_alias"  # deprecated
pseudo-delta = "common.deprecated:delta_alias"  # deprecated
pseudo-analyse = "common.deprecated:analyse_alias"  # deprecated
pseudo-screen-report = "common.deprecated:screen_report_alias"  # deprecated
```

- [ ] **Step 6: Reinstall, then run the tests and check they pass**

```bash
pip install -e ".[dev]"
pytest tests/test_cli_aliases.py -v
```
Expected: all PASS.

Then run a smoke test in a real shell:

```bash
stomp-debias --help
pseudo-debias --help 2>/dev/null | head -1   # "Usage: pseudo-debias ..." with no warning
pseudo-debias --help 2>&1 >/dev/null          # only the warning line
```

- [ ] **Step 7: Run the full suite + lint**

Run: `pytest && ruff check .`
Expected: all PASS, no lint errors.

- [ ] **Step 8: Commit**

```bash
git add src/common/deprecated.py pyproject.toml tests/test_cli_aliases.py
git commit -m "feat: rename distribution to stomp, add stomp-* commands with deprecated pseudo-* aliases

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Source strings + guard test (code scope)

**Files:**
- Create: `tests/test_no_legacy_name.py`
- Modify: `src/analyse/api.py:44,69,80,106,129`, `src/analyse/cli.py:117`, `src/analyse/screen_report.py:562,579`, `src/analyse/muse/config.py:141`, `src/quantify/delta.py:164-165,195,241,277`, `src/quantify/end.py:81,333-334`, `src/main.py:10`

(Line numbers were taken from `end_maps_stomp` on 2026-10-20. Re-check with `git grep -n -i pseudo -- src` before editing.)

**Interfaces:**
- Consumes: `common.deprecated` from Task 1 (allowlisted file).
- Produces: `tests/test_no_legacy_name.py` with module-level `SCAN_TARGETS: list[str]`, `SKIP_NAMES: set[str]`, `LEGACY: re.Pattern`, `ALLOWED_LINE_MARKERS: tuple[str, ...]`. Task 3 extends `SCAN_TARGETS` and `SKIP_NAMES`.

- [ ] **Step 1: Write the failing guard test**

Create `tests/test_no_legacy_name.py`:

```python
"""Guard: no leftover PSEUDO project-name references (STOMP was formerly PSEUDO).

Matches the project name only: uppercase PSEUDO, the old command names, and
the old logo file names. Ordinary scientific words like "pseudo-symmetry"
are not matched.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Task 3 extends these to cover docs.
SCAN_TARGETS = ["src"]
SKIP_NAMES = set()

LEGACY = re.compile(
    r"PSEUDO"
    r"|pseudo[- ](debias|quantify|end|delta|analyse|screen-report)\b"
    r"|pseudo_logo"
)
ALLOWED_FILES = {"src/common/deprecated.py"}
ALLOWED_LINE_MARKERS = ("deprecated", "formerly PSEUDO")
SUFFIXES = {".py", ".md", ".yml", ".yaml", ".toml", ".html", ".json"}
SKIP_PARTS = {"__pycache__", "superpowers"}


def _files():
    for target in SCAN_TARGETS:
        path = ROOT / target
        candidates = [path] if path.is_file() else path.rglob("*")
        for f in candidates:
            if (
                f.is_file()
                and f.suffix in SUFFIXES
                and f.name not in SKIP_NAMES
                and not SKIP_PARTS.intersection(f.parts)
                and not any(p.endswith(".egg-info") for p in f.parts)
            ):
                yield f


def _offenders():
    hits = []
    for f in _files():
        rel = f.relative_to(ROOT).as_posix()
        if rel in ALLOWED_FILES:
            continue
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if LEGACY.search(line) and not any(m in line for m in ALLOWED_LINE_MARKERS):
                hits.append(f"{rel}:{n}: {line.strip()}")
    return hits


def test_no_legacy_project_name():
    hits = _offenders()
    assert not hits, "Leftover PSEUDO references:\n" + "\n".join(hits)


@pytest.mark.parametrize("word", ["pseudo-symmetry", "pseudoatom", "pseudo random"])
def test_ordinary_words_not_flagged(word):
    assert not LEGACY.search(word)
```

- [ ] **Step 2: Run it and check it fails**

Run: `pytest tests/test_no_legacy_name.py -v`
Expected: `test_no_legacy_project_name` FAILS and lists about 20 `src/...` lines. The `test_ordinary_words_not_flagged` cases PASS.

- [ ] **Step 3: Edit the strings, following this table exactly**

| File | Old text | New text |
|---|---|---|
| `src/analyse/api.py` | `Run 'pseudo quantify' before 'pseudo analyse'.` | `Run 'stomp-quantify' before 'stomp-analyse'.` |
| `src/analyse/api.py` | `Run 'pseudo-debias' followed by 'pseudo-quantify'` | `Run 'stomp-debias' followed by 'stomp-quantify'` |
| `src/analyse/api.py` | `Run 'pseudo-debias' first` | `Run 'stomp-debias' first` |
| `src/analyse/api.py` | `Re-run 'pseudo quantify' to generate null params.` | `Re-run 'stomp-quantify' to generate null params.` |
| `src/analyse/api.py` | `Run 'pseudo-debias' to generate omission map ensembles.` | `Run 'stomp-debias' to generate omission map ensembles.` |
| `src/analyse/cli.py` | `Root directory of the PSEUDO screening run` | `Root directory of the STOMP screening run` |
| `src/analyse/screen_report.py` (both lines) | `PSEUDO Screen Results` | `STOMP Screen Results` |
| `src/analyse/muse/config.py` | `produced by pseudo-quantify` | `produced by stomp-quantify` |
| `src/quantify/delta.py` | `` ``pseudo-quantify --delta`` `` / `` ``pseudo-delta`` `` | `` ``stomp-quantify --delta`` `` / `` ``stomp-delta`` `` |
| `src/quantify/delta.py` (2×) | `Run 'pseudo-quantify' for this k/cap first.` | `Run 'stomp-quantify' for this k/cap first.` |
| `src/quantify/delta.py` | `Re-run 'pseudo-quantify --end' or 'pseudo-end' first.` | `Re-run 'stomp-quantify --end' or 'stomp-end' first.` |
| `src/quantify/end.py` | `Re-run 'pseudo-debias generate-params'` | `Re-run 'stomp-debias generate-params'` |
| `src/quantify/end.py` | `` ``pseudo-quantify --end`` `` / `` ``pseudo-end`` `` | `` ``stomp-quantify --end`` `` / `` ``stomp-end`` `` |
| `src/main.py` | `PSEUDO main function for CLI entrypoint` | `STOMP main function for CLI entrypoint` |

- [ ] **Step 4: Check whether any existing test asserts on the old strings**

Run: `git grep -n -E "PSEUDO|pseudo-|pseudo quantify" -- tests`
Expected: hits only in `tests/test_cli_aliases.py` and `tests/test_no_legacy_name.py`. Update any other test assertion to the new text, e.g. a test that checks the "Screen Results" title or an error-hint message.

- [ ] **Step 5: Run the tests and check they pass**

Run: `pytest && ruff check .`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src tests/test_no_legacy_name.py
git commit -m "refactor: rename PSEUDO to STOMP in user-facing source strings

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Docs, docs config, logo files

**Files:**
- Modify: `README.md`, `docs/index.md`, `docs/guides/index.md`, `docs/guides/debias.md`, `docs/guides/quantify.md`, `docs/guides/analyse.md`, `docs/reference.md`, `docs/api.md`, `docs/_config.yml`
- Rename: `docs/assets/images/pseudo_logo_{light,dark,transparent,circular}.svg` → `stomp_logo_*.svg`
- Modify: `tests/test_no_legacy_name.py` (`SCAN_TARGETS`, `SKIP_NAMES`)

**Interfaces:**
- Consumes: `SCAN_TARGETS`, `SKIP_NAMES`, `LEGACY`, `ALLOWED_LINE_MARKERS` from Task 2.
- Produces: final guard coverage over code, docs and packaging.

- [ ] **Step 1: Extend the guard so it fails on the docs**

In `tests/test_no_legacy_name.py`, replace the two lines under `# Task 3 extends these` with:

```python
SCAN_TARGETS = ["src", "docs", "README.md", "pyproject.toml"]
SKIP_NAMES = {"theory.md"}  # untracked, uses "pseudo" scientifically
```

Run: `pytest tests/test_no_legacy_name.py -v`
Expected: FAIL, listing about 110 README/docs lines. The `pyproject.toml` alias lines pass because of their `# deprecated` comments.

- [ ] **Step 2: Rename the logo files**

```bash
for v in light dark transparent circular; do
  git mv docs/assets/images/pseudo_logo_$v.svg docs/assets/images/stomp_logo_$v.svg
done
```

- [ ] **Step 3: Edit `docs/_config.yml`** (3 lines)

```yaml
title: STOMP
```
```yaml
logo: "/assets/images/stomp_logo_transparent.svg"
```
```yaml
    - "https://github.com/hamlet-khachatryan/STOMP"
```

- [ ] **Step 4: Edit the markdown docs, applying these replacements in this order, file by file, and reviewing each hunk**

List the hits first: `git grep -n -E "PSEUDO|pseudo[- _]" -- README.md docs ':!docs/superpowers' ':!docs/theory.md'`

| Old | New |
|---|---|
| `https://github.com/hamlet-khachatryan/PSEUDO` (incl. `.git`, `/actions/...`, `/blob/main/LICENSE`) | `https://github.com/hamlet-khachatryan/STOMP` (same suffix) |
| `img.shields.io/github/license/hamlet-khachatryan/PSEUDO` | `img.shields.io/github/license/hamlet-khachatryan/STOMP` |
| `https://hamlet-khachatryan.github.io/PSEUDO/` (any path) | `https://hamlet-khachatryan.github.io/STOMP/` (same path) |
| `pseudo_logo_` | `stomp_logo_` |
| `pseudo-debias` / `-quantify` / `-end` / `-delta` / `-analyse` / `-screen-report` | `stomp-debias` / … (same suffix) |
| `cd PSEUDO` (clone instructions) | `cd STOMP` |
| `PSEUDO` (prose, headings, citation "the PSEUDO platform") | `STOMP` |

Check every replaced line against the wording rule in Global Constraints: "STOMP" alone means the toolkit; the method is "STOMP maps". For example, "STOMP requires the Phenix Software Suite for STOMP map calculation" is acceptable.

- [ ] **Step 5: Add the migration note**

Directly under the title/badges in `README.md`, **and** at the top of `docs/index.md`, add exactly:

```markdown
> **STOMP was formerly PSEUDO.** The old `pseudo-*` commands still work as
> aliases: they print a deprecation warning on stderr and will be removed in STOMP 0.3.0.
> Before installing, remove the deprecated PSEUDO package: `pip uninstall PSEUDO`.
> Having both installed breaks either one when the other is removed.
> Scripts that treat any stderr output as failure should switch to the `stomp-*` commands.
```

(Every line that mentions `PSEUDO` contains "formerly PSEUDO" or "deprecated", so the guard allows it. `pseudo-*` isn't matched by the guard regex.)

- [ ] **Step 6: Run the guard and the full suite**

Run: `pytest && ruff check .`
Expected: all PASS. If the guard flags a line where "PSEUDO" is genuinely correct, reword it to include "formerly PSEUDO" rather than widening the allowlist.

- [ ] **Step 7: Build the docs locally**

```bash
cd docs && bundle install && bundle exec jekyll build --source . --destination ../_site && cd -
grep -rl "pseudo_logo" _site || echo "no stale logo refs"
ls _site/assets/images/stomp_logo_transparent.svg
rm -rf _site
```
Expected: the build succeeds, prints `no stale logo refs`, and the logo file exists.

- [ ] **Step 8: Commit**

```bash
git add README.md docs/_config.yml docs/index.md docs/guides docs/reference.md docs/api.md docs/assets/images tests/test_no_legacy_name.py
git commit -m "docs: rename PSEUDO to STOMP across README and docs, rename logo assets

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 9: Get co-author sign-off (spec R12)**

Open the PR `rename-to-stomp` → `main` as a **draft**. Confirm the citation wording ("the STOMP platform") with the co-authors before marking it ready.

---

### Task 4: Merge, GitHub rename and environment migration (manual / owner actions)

No code. These are outward-facing steps the repo owner does by hand, in order.

- [ ] **Step 1:** Mark the PR ready, wait for CI to pass on ubuntu/macos/windows, then merge.
- [ ] **Step 2:** Rename the GitHub repo: Settings → General → Repository name → `STOMP`.
  **Do not** create a new repo named `PSEUDO` afterwards (it would break GitHub's redirect, spec R3).
- [ ] **Step 3:** Update the local remote, and ask collaborators to do the same:
```bash
git remote set-url origin https://github.com/hamlet-khachatryan/STOMP.git
git fetch origin
```
- [ ] **Step 4:** Re-run "Deploy docs to GitHub Pages" (Actions → Run workflow). Check that `https://hamlet-khachatryan.github.io/STOMP/` loads with the logo and working guide links. The old `/PSEUDO/` URL will 404 (expected, spec R3), so announce the new URL.
- [ ] **Step 5:** Check repo integrations (Settings → Webhooks, Pages, any Zenodo/DOI link) for references to the old name.
- [ ] **Step 6:** Migrate each environment (laptop, HPC, conda envs):
```bash
pip uninstall -y PSEUDO
pip install -e ".[dev]"
stomp-debias --help
pytest tests/test_cli_aliases.py::test_old_distribution_not_installed
```
- [ ] **Step 7 (optional, last):** Rename the local folder and carry the tooling over:
```bash
mv ~/PycharmProjects/PSEUDO ~/PycharmProjects/STOMP
cp -R ~/.claude/projects/-Users-hamletkhachatryan-PycharmProjects-PSEUDO/memory \
      ~/.claude/projects/-Users-hamletkhachatryan-PycharmProjects-STOMP/
cd ~/PycharmProjects/STOMP && pip install -e ".[dev]"
```
Re-open the project in PyCharm, which will create a new `.idea/*.iml`.

---

### Task 5: Swap in new logo artwork (blocked until the user supplies the SVGs)

**Files:**
- Modify: `docs/assets/images/stomp_logo_{light,dark,transparent,circular}.svg`

- [ ] **Step 1:** Copy the 4 supplied SVGs over the renamed files, keeping these exact file names.
- [ ] **Step 2:** Run `grep -c "PSEUDO" docs/assets/images/stomp_logo_*.svg`. Expected: `0` for each.
- [ ] **Step 3:** Build the docs locally (Task 3 Step 7 commands) and check light and dark rendering of the README on GitHub.
- [ ] **Step 4: Commit**
```bash
git add docs/assets/images/stomp_logo_*.svg
git commit -m "docs: new STOMP logo artwork

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Later (STOMP 0.3.0, separate change — out of scope)

Delete `src/common/deprecated.py`, the 6 `pseudo-*` entries in `pyproject.toml`, the alias tests in `tests/test_cli_aliases.py` and the migration notes in `README.md` and `docs/index.md`.
