"""Base protocol and types for framework-specific API parsers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from pathlib import Path

    from docguard.core.models import InferredEndpoint


@runtime_checkable
class FrameworkParser(Protocol):
    """Strategy interface for framework-specific code parsers.

    Each supported framework (FastAPI, Express, Spring Boot, etc.) implements
    this protocol.  The registry auto-detects the correct parser via
    ``can_handle`` and delegates extraction to ``extract_endpoints``.
    """

    @property
    def name(self) -> str:
        """Human-readable framework name, e.g. 'FastAPI'."""
        ...

    def can_handle(self, project_root: Path) -> bool:
        """Return True if this parser recognises the framework in *project_root*."""
        ...

    def extract_endpoints(self, source_files: list[Path]) -> list[InferredEndpoint]:
        """Parse *source_files* and return every discovered API endpoint."""
        ...
