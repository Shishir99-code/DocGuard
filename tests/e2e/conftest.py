"""Fixtures for the end-to-end real-repo suite."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(scope="session")
def e2e_cache(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Session-scoped scratch dir for cloned repos (auto-cleaned by pytest)."""
    return tmp_path_factory.mktemp("docguard-e2e")
