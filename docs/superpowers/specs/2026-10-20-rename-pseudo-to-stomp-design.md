# Rename PSEUDO → STOMP — Design Spec

- **Date:** 2026-10-20
- **Status:** Draft — awaiting review
- **Scope:** naming only. No behavioural changes to debias / quantify / analyse.

## 1. Goal

Rebrand the project, the Python distribution, the CLI commands, the docs and the
GitHub repository from **PSEUDO** to **STOMP**, without breaking existing users'
scripts and SLURM workflows.

### Success criteria

1. `pip install -e .` installs a distribution named `STOMP` exposing `stomp-*` commands.
2. Every old `pseudo-*` command still works, prints a one-line deprecation warning
   to **stderr**, and behaves identically to its `stomp-*` replacement (same
   subcommands, options, exit codes, stdout).
3. No user-facing string in `src/`, `README.md` or `docs/` refers to "PSEUDO" /
   "pseudo-*" except the deprecation aliases and a "formerly PSEUDO" note.
4. CI (ruff + pytest on Linux/macOS/Windows) and the docs deploy are green.
5. Docs are reachable at the new GitHub Pages URL.

### Decisions already made

| Decision | Choice |
|---|---|
| Old commands | **Option A**: keep `pseudo-*` as deprecated aliases forwarding to `stomp-*`, removed in a later release (target: 0.3.0) |
| STOMP map terminology | Unchanged ("STOMP maps", `STOMP_μ`, `STOMP_SNR`). The platform and the method now share a name; that is accepted. |
| Python import packages | Unchanged (`debias`, `quantify`, `analyse`, `common`, `conf`) — they don't contain "pseudo" |

## 2. Inventory (what changes)

### 2.1 Packaging — `pyproject.toml`
- `name = "PSEUDO"` → `name = "stomp"`; description text updated.
- Version bump `0.1.0` → `0.2.0` (the change to the distribution name and commands is visible to users).
- `[project.scripts]`:

| New (primary) | Target | Deprecated alias |
|---|---|---|
| `stomp-debias` | `debias.cli:debias_cli` | `pseudo-debias` |
| `stomp-quantify` | `quantify.cli:quantify_cli` | `pseudo-quantify` |
| `stomp-end` | `quantify.cli:end_cli` | `pseudo-end` |
| `stomp-delta` | `quantify.cli:delta_cli` | `pseudo-delta` |
| `stomp-analyse` | `analyse.cli:analyse_cli` | `pseudo-analyse` |
| `stomp-screen-report` | `analyse.cli:screen_report_cli` | `pseudo-screen-report` |

Aliases point to `common.deprecated:<name>_alias` (see §3), **not** directly to the
click commands, so a warning can be emitted.

### 2.2 Source strings (≈20 hits, all user-facing text)
- `src/analyse/api.py` — error hints ("Run 'pseudo-debias' …", and the space-separated `'pseudo quantify'` / `'pseudo analyse'` forms, which are already wrong and should become `stomp-quantify` / `stomp-analyse`).
- `src/quantify/delta.py`, `src/quantify/end.py` — error hints + docstrings.
- `src/analyse/screen_report.py` — HTML `<title>` and `<h2>` "PSEUDO Screen Results".
- `src/analyse/cli.py` — `--help` text "PSEUDO screening run".
- `src/analyse/muse/config.py`, `src/main.py` — docstrings.

### 2.3 Docs (≈110 hits)
- `README.md`, `docs/index.md`, `docs/guides/*.md`, `docs/reference.md`, `docs/api.md`.
- `docs/_config.yml`: `title`, `logo` path, GitHub link.
- Logo assets `docs/assets/images/pseudo_logo_{light,dark,transparent,circular}.svg`
  → `stomp_logo_*.svg` (`git mv`). **If the SVGs draw the word "PSEUDO", they need
  redrawing. That is a design task outside this spec; until then the renamed files keep the old artwork.**
- Badge/links: `github.com/hamlet-khachatryan/PSEUDO` → `…/STOMP`,
  `hamlet-khachatryan.github.io/PSEUDO/…` → `…/STOMP/…`.
- Add a short "STOMP was formerly called PSEUDO; `pseudo-*` commands are deprecated
  aliases" note to README and `docs/index.md`.
- Citation paragraph: "the PSEUDO platform" → "the STOMP platform" (co-author sign-off, R12).

### 2.4 Out-of-repo
- GitHub repository rename `PSEUDO` → `STOMP` (done by the repo owner in GitHub settings).
- Local clone folder `PSEUDO/` → `STOMP/` (optional, done last, see R6).

### 2.5 Explicitly NOT changed
- Untracked `experiments/**` and `docs/theory.md`. The hits in `experiments/pdb_sampling/*` are PDB metadata
  (e.g. "pseudo-symmetry"), not the project name. `docs/theory.md` should be checked by hand
  once it is committed.
- Any scientific use of "pseudo" as an ordinary word.
- Output file names and on-disk run layout (no "pseudo" in them today).
- Generated SLURM scripts (`src/common/slurm.py`) — they call only `phenix.*`, never `pseudo-*`.

## 3. Deprecation alias design

New module `src/common/deprecated.py`:

```python
import click
from debias.cli import debias_cli
# … other imports

def _forward(cmd: click.Command, old: str, new: str):
    def alias():
        click.echo(
            f"Warning: '{old}' is deprecated and will be removed in STOMP 0.3.0; "
            f"use '{new}' instead.",
            err=True,
        )
        cmd(prog_name=old)   # same argv, same subcommands, same exit code
    return alias

debias_alias = _forward(debias_cli, "pseudo-debias", "stomp-debias")
# … one per command
```

Properties:
- The warning goes to **stderr only**, so piped stdout and the files the commands write are unaffected.
- `prog_name=old` keeps `--help` / usage lines consistent with what the user typed.
- Click's standalone mode already calls `sys.exit` with the command's exit code.

## 4. Testing

- `tests/test_cli_aliases.py` (new), parametrised over the 6 pairs, using `click.testing.CliRunner`:
  - `stomp-*` `--help` exits 0.
  - The alias `--help` exits 0, stdout matches the new command's help (prog name aside),
    stderr contains "deprecated".
  - The alias forwards a subcommand (e.g. `pseudo-debias generate-params --help`).
- Entry-point test: `importlib.metadata.entry_points(group="console_scripts")`
  contains all 12 names and they resolve. This catches typos in `pyproject.toml`.
- Guard test: the case-insensitive search for "pseudo" across `src/`, `README.md`, `docs/` and
  `pyproject.toml` returns only allowlisted lines (`deprecated.py`, the "formerly PSEUDO"
  notes, the alias entries).
- Existing suite and ruff unchanged and green.
- Manual: `pip uninstall PSEUDO && pip install -e ".[dev]"`, then run one `stomp-*` and one
  `pseudo-*` command in a shell; build the docs locally with Jekyll and check the logo and links.

## 5. Risks / things that might fail

| # | Risk | Why it fails | Mitigation |
|---|---|---|---|
| R1 | **Two distributions own the same packages** | Envs already have `PSEUDO 0.1.0` installed (confirmed locally). Installing `STOMP` adds a second dist that owns the same top-level `debias/`, `quantify/`, … Later uninstalling either one deletes files the other needs, and stale `pseudo-*` scripts from the old dist can shadow the aliases. | Release notes and README say: `pip uninstall PSEUDO` before installing. Delete stale `src/PSEUDO.egg-info/` and `build/`. Do the same on HPC/conda envs. |
| R2 | **Blind find-and-replace corrupts content** | "pseudo" is a normal scientific word (pseudo-symmetry, pseudo-atom) and shows up in untracked data. A global `sed s/pseudo/stomp/gi` would also rewrite the alias names themselves. | Edit only the explicit file list in §2. Review the diff by hand. The guard test (§4) checks what is left over. |
| R3 | **GitHub Pages does not redirect** | GitHub redirects git remotes and web URLs after a repo rename, but **not** `*.github.io/PSEUDO/` Pages URLs. Old links in papers, slides and emails will 404. | Accept and announce it, or publish a small redirect page elsewhere. Never create a new repo named `PSEUDO` to host it, because that **breaks** GitHub's git/web redirect for the renamed repo. |
| R4 | Repo-rename side effects | Collaborators' remotes still work through the redirect, but should be updated. Any external CI, Zenodo, or webhooks keyed on the repo name may need reconfiguring. | `git remote set-url origin https://github.com/hamlet-khachatryan/STOMP.git`. Check repo integrations in settings. |
| R5 | Docs base URL | Jekyll gets `--baseurl` from `configure-pages`, so it adapts automatically. Hard-coded absolute `/PSEUDO/` links in markdown do not. | Search docs for `/PSEUDO/` and use relative links where possible. |
| R6 | **Local folder rename breaks tooling** | The editable install points at the old path. PyCharm `.idea/PSEUDO.iml` has the old name. Claude Code project memory is keyed on the folder path (`…-PSEUDO`), so it would not be found after the move. | Do the folder rename last. Reinstall `pip install -e .`. Re-open in PyCharm. Copy `~/.claude/projects/-Users-…-PSEUDO/memory/` to the new path key. |
| R7 | Name clash on PyPI | `STOMP`/`stomp` may already be taken on PyPI (e.g. there are STOMP-messaging packages such as `stomp.py`). Only matters if the package is ever published. | Check PyPI availability before any publish. Fall back to a name like `stomp-xtal` if it is taken. Not blocking for a git-install workflow. |
| R8 | Ambiguity "STOMP" platform vs "STOMP maps" | Prose like "STOMP requires Phenix for STOMP map calculation" can confuse readers. | Docs wording rule: "STOMP" alone means the toolkit; the method is always written "STOMP maps" / "STOMP ensemble". |
| R9 | Alias breaks a scripted user | Some pipelines treat **any** stderr output as failure. | Document it in the README deprecation note; users switch to `stomp-*` to drop the warning. No env var (§7). |
| R10 | Windows CI | Console-script wrappers are generated as `.exe`. Twelve entries is fine, but a broken target only shows up when called. | Entry-point resolution test (§4) runs on all 3 OS in CI. |
| R11 | Branch / merge conflicts | The work is happening on `end_maps_stomp`, and docs edits there (END/delta) will conflict with a repo-wide rename. | Do the rename on its own branch off `main` **after** `end_maps_stomp` merges. |
| R12 | Citation / external naming | The preprint and co-authors may still use "PSEUDO". | Get co-author agreement before merging the README citation change. |

## 6. Rollout order

1. Merge `end_maps_stomp`, then branch `rename-to-stomp` from `main`.
2. Packaging + alias module + tests (§2.1, §3, §4).
3. Source strings (§2.2).
4. Docs + assets (§2.3).
5. Merge, then rename the GitHub repo, update remotes and check that Pages deploys at `/STOMP/`.
6. Optionally rename the local folder and fix up the tooling (R6).
7. In 0.3.0, remove the `pseudo-*` aliases and `common/deprecated.py`.

## 7. Resolved decisions (2026-10-20)

1. Distribution name is lowercase **`stomp`** (`name = "stomp"`; egg-info becomes `stomp.egg-info`).
   Wherever this spec says "distribution `STOMP`", read `stomp`. Prose and branding stay "STOMP".
2. **No** `STOMP_SUPPRESS_DEPRECATION` env var. R9 is mitigated by documentation only.
3. The user will supply new logo SVGs later. The plan renames the asset files now and swaps the artwork when it arrives.
4. `src/main.py` stays as it is apart from its docstring (no umbrella command — YAGNI).