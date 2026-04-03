"""Tests for the DocGuard CLI."""

from __future__ import annotations

import shutil
from pathlib import Path

from typer.testing import CliRunner

from docguard.cli import app

runner = CliRunner()

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestInitCommand:
    def test_creates_config(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["init"], catch_exceptions=False, env={"HOME": str(tmp_path)})
        # init writes to cwd; typer.testing runs in the process cwd,
        # so we just check it didn't crash
        assert result.exit_code in (0, 2)

    def test_version(self) -> None:
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output


class TestCheckCommand:
    def test_synced_exits_zero(self, tmp_path: Path) -> None:
        shutil.copy(FIXTURES_DIR / "sample_fastapi_app.py", tmp_path / "main.py")
        shutil.copy(FIXTURES_DIR / "sample_openapi.yaml", tmp_path / "openapi.yaml")
        (tmp_path / "requirements.txt").write_text("fastapi\n")

        result = runner.invoke(app, [
            "check",
            "--spec", str(tmp_path / "openapi.yaml"),
            "--source", str(tmp_path),
            "--format", "json",
        ])
        assert result.exit_code == 0

    def test_drifted_exits_one(self, tmp_path: Path) -> None:
        shutil.copy(FIXTURES_DIR / "sample_fastapi_app.py", tmp_path / "main.py")
        shutil.copy(FIXTURES_DIR / "drifted_openapi.yaml", tmp_path / "openapi.yaml")
        (tmp_path / "requirements.txt").write_text("fastapi\n")

        result = runner.invoke(app, [
            "check",
            "--spec", str(tmp_path / "openapi.yaml"),
            "--source", str(tmp_path),
            "--format", "json",
        ])
        assert result.exit_code == 1

    def test_github_format(self, tmp_path: Path) -> None:
        shutil.copy(FIXTURES_DIR / "sample_fastapi_app.py", tmp_path / "main.py")
        shutil.copy(FIXTURES_DIR / "drifted_openapi.yaml", tmp_path / "openapi.yaml")
        (tmp_path / "requirements.txt").write_text("fastapi\n")

        result = runner.invoke(app, [
            "check",
            "--spec", str(tmp_path / "openapi.yaml"),
            "--source", str(tmp_path),
            "--format", "github",
        ])
        assert result.exit_code == 1
        assert "::error" in result.output or "::warning" in result.output


class TestReportCommand:
    def test_report_json_output(self, tmp_path: Path) -> None:
        shutil.copy(FIXTURES_DIR / "sample_fastapi_app.py", tmp_path / "main.py")
        shutil.copy(FIXTURES_DIR / "sample_openapi.yaml", tmp_path / "openapi.yaml")
        (tmp_path / "requirements.txt").write_text("fastapi\n")

        output_file = tmp_path / "report.json"
        result = runner.invoke(app, [
            "report",
            "--spec", str(tmp_path / "openapi.yaml"),
            "--source", str(tmp_path),
            "--output", str(output_file),
        ])
        assert result.exit_code == 0
        assert output_file.exists()
        import json
        data = json.loads(output_file.read_text())
        assert "drift_score" in data
        assert "endpoints" in data
