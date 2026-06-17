"""Parser registry -- auto-detects the framework and returns the right parser."""

from __future__ import annotations

from typing import TYPE_CHECKING

from docguard.parsers.fastapi_parser import FastAPIParser

if TYPE_CHECKING:
    from pathlib import Path

    from docguard.parsers.base import FrameworkParser

_PARSERS: list[FrameworkParser] = [
    FastAPIParser(),
]


def register_parser(parser: FrameworkParser) -> None:
    """Add a custom parser to the global registry."""
    _PARSERS.append(parser)


def detect_framework(project_root: Path) -> FrameworkParser | None:
    """Return the first parser that can handle *project_root*, or ``None``."""
    for parser in _PARSERS:
        if parser.can_handle(project_root):
            return parser
    return None


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
