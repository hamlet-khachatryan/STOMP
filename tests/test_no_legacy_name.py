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
