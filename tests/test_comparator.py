"""Tests for the comparator engine."""

from __future__ import annotations

from typing import TYPE_CHECKING

from docguard.core.comparator import compare
from docguard.core.models import EndpointStatus
from docguard.core.spec_loader import load_spec, normalize_spec
from docguard.parsers.fastapi_parser import FastAPIParser

if TYPE_CHECKING:
    from pathlib import Path


class TestComparatorSynced:
    """When the spec perfectly matches the code, everything should be SYNCED."""

    def test_all_synced(self, sample_app_path: Path, sample_spec_path: Path) -> None:
        parser = FastAPIParser()
        code_endpoints = parser.extract_endpoints([sample_app_path])
        spec = load_spec(sample_spec_path)
        spec_endpoints = normalize_spec(spec)

        report = compare(code_endpoints, spec_endpoints)
        assert report.drift_score == 0.0
        assert report.summary.drifted == 0
        assert report.summary.missing_in_spec == 0
        assert report.summary.missing_in_code == 0
        assert report.summary.synced == 5

    def test_all_endpoints_present(self, sample_app_path: Path, sample_spec_path: Path) -> None:
        parser = FastAPIParser()
        code_endpoints = parser.extract_endpoints([sample_app_path])
        spec = load_spec(sample_spec_path)
        spec_endpoints = normalize_spec(spec)

        report = compare(code_endpoints, spec_endpoints)
        for ep in report.endpoints:
            assert ep.status == EndpointStatus.SYNCED


class TestComparatorDrifted:
    """When the spec diverges from the code, drift should be detected."""

    def test_drift_score_nonzero(self, sample_app_path: Path, drifted_spec_path: Path) -> None:
        parser = FastAPIParser()
        code_endpoints = parser.extract_endpoints([sample_app_path])
        spec = load_spec(drifted_spec_path)
        spec_endpoints = normalize_spec(spec)

        report = compare(code_endpoints, spec_endpoints)
        assert report.drift_score > 0

    def test_missing_in_spec_detected(self, sample_app_path: Path, drifted_spec_path: Path) -> None:
        """The GET /users/{user_id} endpoint was removed from the drifted spec."""
        parser = FastAPIParser()
        code_endpoints = parser.extract_endpoints([sample_app_path])
        spec = load_spec(drifted_spec_path)
        spec_endpoints = normalize_spec(spec)

        report = compare(code_endpoints, spec_endpoints)
        missing = [ep for ep in report.endpoints if ep.status == EndpointStatus.MISSING_IN_SPEC]
        missing_keys = {f"{ep.method} {ep.path}" for ep in missing}
        assert "GET /users/{user_id}" in missing_keys

    def test_missing_in_code_detected(self, sample_app_path: Path, drifted_spec_path: Path) -> None:
        """The /health endpoint exists in spec but not in the sample app."""
        parser = FastAPIParser()
        code_endpoints = parser.extract_endpoints([sample_app_path])
        spec = load_spec(drifted_spec_path)
        spec_endpoints = normalize_spec(spec)

        report = compare(code_endpoints, spec_endpoints)
        missing = [ep for ep in report.endpoints if ep.status == EndpointStatus.MISSING_IN_CODE]
        missing_keys = {f"{ep.method} {ep.path}" for ep in missing}
        assert "GET /health" in missing_keys

    def test_type_mismatch_detected(self, sample_app_path: Path, drifted_spec_path: Path) -> None:
        """The drifted spec has 'age' as string instead of integer in UserResponseDrifted."""
        parser = FastAPIParser()
        code_endpoints = parser.extract_endpoints([sample_app_path])
        spec = load_spec(drifted_spec_path)
        spec_endpoints = normalize_spec(spec)

        report = compare(code_endpoints, spec_endpoints)
        drifted = [ep for ep in report.endpoints if ep.status == EndpointStatus.DRIFT]
        all_diff_types = {d.type.value for ep in drifted for d in ep.diffs}
        assert "type_mismatch" in all_diff_types

    def test_report_to_dict(self, sample_app_path: Path, drifted_spec_path: Path) -> None:
        parser = FastAPIParser()
        code_endpoints = parser.extract_endpoints([sample_app_path])
        spec = load_spec(drifted_spec_path)
        spec_endpoints = normalize_spec(spec)

        report = compare(code_endpoints, spec_endpoints)
        d = report.to_dict()
        assert "$schema" in d
        assert "endpoints" in d
        assert isinstance(d["drift_score"], float)
        assert isinstance(d["summary"], dict)


class TestDriftScore:
    def test_perfect_sync_is_zero(self, sample_app_path: Path, sample_spec_path: Path) -> None:
        parser = FastAPIParser()
        code_endpoints = parser.extract_endpoints([sample_app_path])
        spec = load_spec(sample_spec_path)
        spec_endpoints = normalize_spec(spec)

        report = compare(code_endpoints, spec_endpoints)
        assert report.drift_score == 0.0

    def test_empty_inputs(self) -> None:
        report = compare([], [])
        assert report.drift_score == 0.0
        assert report.summary.synced == 0
