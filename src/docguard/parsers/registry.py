"""Parser registry -- auto-detects the framework and returns the right parser.

Framework detection is **AST-only**: source files are parsed with :mod:`ast` and
their imports/symbols are inspected.  The analyzed project is never imported or
executed.  Detection is deterministic -- given the same source tree it always
returns the same result, with a documented tie-break order when signals are
mixed -- and it never raises on unknown input (it returns ``None``).
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from docguard.parsers.fastapi_parser import FastAPIParser
from docguard.parsers.flask_parser import FlaskParser

if TYPE_CHECKING:
    from pathlib import Path

    from docguard.parsers.base import FrameworkParser

# ---------------------------------------------------------------------------
# Framework names (the canonical, human-readable identifiers)
# ---------------------------------------------------------------------------

FASTAPI = "FastAPI"
FLASK = "Flask"
STARLETTE = "Starlette"
REST_FRAMEWORK = "REST Framework"

# Deterministic tie-break order, applied when two frameworks score equally.
# Earlier entries win.  FastAPI precedes Starlette because FastAPI is built on
# top of Starlette, so a project importing both is treated as a FastAPI app.
_TIE_BREAK_ORDER: tuple[str, ...] = (FASTAPI, FLASK, STARLETTE, REST_FRAMEWORK)

# Map an imported top-level module name to the framework it signals.
# Django REST Framework is imported as ``rest_framework``.
_IMPORT_SIGNALS: dict[str, str] = {
    "fastapi": FASTAPI,
    "flask": FLASK,
    "starlette": STARLETTE,
    "rest_framework": REST_FRAMEWORK,
}

# Directories that never contain first-party application code; skipped while
# walking the source tree so vendored dependencies cannot skew detection.
_SKIP_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".tox",
        ".nox",
        ".venv",
        "venv",
        "env",
        ".env",
        "__pycache__",
        "node_modules",
        "site-packages",
        "build",
        "dist",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
    }
)

# Upper bound on the number of files parsed during detection.  Detection only
# needs a representative sample, and this keeps the scan fast on large repos.
_MAX_FILES = 500

_PARSERS: list[FrameworkParser] = [
    FastAPIParser(),
    FlaskParser(),
]


def register_parser(parser: FrameworkParser) -> None:
    """Add a custom parser to the global registry."""
    _PARSERS.append(parser)


def _iter_python_files(project_root: Path) -> list[Path]:
    """Yield up to ``_MAX_FILES`` first-party ``.py`` files under *project_root*.

    Vendored/virtualenv directories are skipped so third-party code never
    influences framework detection.  Results are sorted for determinism.
    """
    found: list[Path] = []
    try:
        candidates = sorted(project_root.rglob("*.py"))
    except OSError:
        return found
    for path in candidates:
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        found.append(path)
        if len(found) >= _MAX_FILES:
            break
    return found


def _root_module(name: str) -> str:
    """Return the top-level package of a dotted module path."""
    return name.split(".", 1)[0]


def _score_file(path: Path, scores: dict[str, int]) -> None:
    """Accumulate framework import signals found in *path* into *scores*.

    The file is parsed with :mod:`ast` only -- never imported or executed.
    Syntax errors and OS errors are ignored so a single bad file cannot break
    detection for the whole project.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, OSError, ValueError):
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                framework = _IMPORT_SIGNALS.get(_root_module(alias.name))
                if framework is not None:
                    scores[framework] += 1
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:  # relative import: ``from . import x``
                continue
            framework = _IMPORT_SIGNALS.get(_root_module(node.module))
            if framework is not None:
                scores[framework] += 1


def detect_framework_name(project_root: Path) -> str | None:
    """Infer the framework name from AST imports under *project_root*.

    Returns one of :data:`FASTAPI`, :data:`FLASK`, :data:`STARLETTE`,
    :data:`REST_FRAMEWORK`, or ``None`` when no known framework is detected.

    Detection is deterministic.  The framework with the most import signals
    wins; ties are broken by :data:`_TIE_BREAK_ORDER` (FastAPI, Flask,
    Starlette, REST Framework).  Because FastAPI re-exports Starlette, a project
    importing both is reported as FastAPI.  This function never raises.
    """
    scores: dict[str, int] = {name: 0 for name in _IMPORT_SIGNALS.values()}
    for path in _iter_python_files(project_root):
        _score_file(path, scores)

    best_score = max(scores.values(), default=0)
    if best_score == 0:
        return None
    winners = [name for name, score in scores.items() if score == best_score]
    for candidate in _TIE_BREAK_ORDER:
        if candidate in winners:
            return candidate
    return None


def _detect_via_dependency_files(project_root: Path) -> FrameworkParser | None:
    """Fallback: ask each parser's ``can_handle`` (dependency-file heuristic)."""
    for parser in _PARSERS:
        if parser.can_handle(project_root):
            return parser
    return None


def detect_framework(project_root: Path) -> FrameworkParser | None:
    """Return the parser for the framework detected in *project_root*.

    AST import detection is attempted first.  If it identifies a framework that
    has a registered parser, that parser is returned.  Otherwise we fall back to
    the dependency-file heuristic (``requirements.txt``/``pyproject.toml`` etc.).
    Returns ``None`` -- never raises -- when no supported framework is found.

    Frameworks such as Starlette and Django REST Framework can be *detected*
    (see :func:`detect_framework_name`) even though no parser ships for them
    yet; in that case this returns ``None`` rather than guessing a wrong parser.
    """
    detected = detect_framework_name(project_root)
    if detected is not None:
        parser = get_parser_by_name(detected)
        if parser is not None:
            return parser
    return _detect_via_dependency_files(project_root)


def get_parser_by_name(name: str) -> FrameworkParser | None:
    """Look up a parser by its framework name (case-insensitive)."""
    name_lower = name.lower()
    for parser in _PARSERS:
        if parser.name.lower() == name_lower:
            return parser
    return None


def available_parsers() -> list[str]:
    """Return the names of all registered parsers."""
    return [p.name for p in _PARSERS]
