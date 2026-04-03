"""Shared test fixtures for DocGuard."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def sample_app_path() -> Path:
    return FIXTURES_DIR / "sample_fastapi_app.py"


@pytest.fixture
def sample_spec_path() -> Path:
    return FIXTURES_DIR / "sample_openapi.yaml"


@pytest.fixture
def drifted_spec_path() -> Path:
    return FIXTURES_DIR / "drifted_openapi.yaml"
