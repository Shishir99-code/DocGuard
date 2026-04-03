"""Configuration loader for .docguard.yaml."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class CheckConfig(BaseModel):
    fail_on: str = "any"  # any | drift-only | missing
    severity_threshold: str = "error"  # error | warning | info


class FixConfig(BaseModel):
    model: str = "gpt-4o-mini"
    api_key_env: str = "OPENAI_API_KEY"


class OutputConfig(BaseModel):
    format: str = "text"  # text | json | github
    report_path: str | None = None


class DocGuardConfig(BaseModel):
    spec: str = "openapi.yaml"
    source: str = "."
    framework: str = "auto"
    ignore: list[str] = Field(default_factory=list)
    check: CheckConfig = Field(default_factory=CheckConfig)
    fix: FixConfig = Field(default_factory=FixConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)


_CONFIG_FILENAME = ".docguard.yaml"


def find_config(project_root: Path) -> Path | None:
    """Locate .docguard.yaml in *project_root* or its parents."""
    current = project_root.resolve()
    for _ in range(10):  # max depth
        candidate = current / _CONFIG_FILENAME
        if candidate.exists():
            return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def load_config(config_path: Path | None = None, project_root: Path | None = None) -> DocGuardConfig:
    """Load configuration from a file, or return defaults."""
    if config_path is None and project_root is not None:
        config_path = find_config(project_root)
    if config_path is None or not config_path.exists():
        return DocGuardConfig()
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return DocGuardConfig()
    return DocGuardConfig(**raw)


def default_config_yaml() -> str:
    """Return the default .docguard.yaml content for `docguard init`."""
    return """\
# DocGuard configuration
# https://docs.docguard.dev/configuration

spec: openapi.yaml
source: "."
framework: auto

ignore:
  - "*/tests/*"
  - "*/migrations/*"

check:
  fail_on: any               # any | drift-only | missing
  severity_threshold: error   # error | warning | info

fix:
  model: gpt-4o-mini
  api_key_env: OPENAI_API_KEY

output:
  format: text                # text | json | github
  # report_path: null         # Uncomment to write JSON report to a file
"""
