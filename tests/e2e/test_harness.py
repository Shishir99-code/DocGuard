"""Offline, deterministic self-tests for the E2E harness machinery.

These do NOT touch the network: they build a throwaway local git repo from the
existing fixtures and drive the full harness (clone-at-ref -> resolve spec ->
real ``docguard report`` CLI -> false-positive count) against it. They are not
marked ``e2e``, so they run in the fast default suite and guarantee the harness
itself keeps working even when the real-repo corpus is skipped offline.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from tests.e2e import harness
from tests.e2e.corpus import RepoCase

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

requires_git = pytest.mark.skipif(not harness.git_available(), reason="git not available")
requires_docguard = pytest.mark.skipif(
    not harness.docguard_available(), reason="docguard CLI not on PATH"
)


def _make_local_repo(tmp_path: Path, app_src: Path, spec_src: Path) -> RepoCase:
    """Build a one-commit local git repo holding a FastAPI app and a spec."""
    work = tmp_path / "repo"
    work.mkdir()
    shutil.copy(app_src, work / "app.py")
    shutil.copy(spec_src, work / "openapi.yaml")
    git = ["git", "-C", str(work), "-c", "user.email=e2e@docguard.test", "-c", "user.name=e2e"]
    subprocess.run([*git, "init", "-q"], check=True, capture_output=True)
    subprocess.run([*git, "add", "-A"], check=True, capture_output=True)
    subprocess.run([*git, "commit", "-q", "-m", "fixture"], check=True, capture_output=True)
    sha = subprocess.run(
        [*git, "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    return RepoCase(
        name="local-fixture",
        url=str(work),
        ref=sha,
        framework="fastapi",
        committed_spec="openapi.yaml",
        requires_network=False,
    )


@requires_git
@requires_docguard
def test_harness_reports_zero_false_positives_when_spec_matches(tmp_path: Path) -> None:
    case = _make_local_repo(
        tmp_path,
        FIXTURES_DIR / "sample_fastapi_app.py",
        FIXTURES_DIR / "sample_openapi.yaml",
    )
    result = harness.run_case(case, tmp_path / "cache")
    assert result.false_positives == 0, result.report["summary"]
    assert result.report["summary"]["total_endpoints_in_code"] > 0


@requires_git
@requires_docguard
def test_harness_counts_drift_as_false_positives(tmp_path: Path) -> None:
    # A deliberately drifted spec proves the harness *detects* false positives,
    # not just that it returns zero on a happy path.
    case = _make_local_repo(
        tmp_path,
        FIXTURES_DIR / "sample_fastapi_app.py",
        FIXTURES_DIR / "drifted_openapi.yaml",
    )
    result = harness.run_case(case, tmp_path / "cache")
    assert result.false_positives > 0, result.report["summary"]


def test_unpinned_corpus_entry_is_skipped(tmp_path: Path) -> None:
    case = RepoCase(
        name="unpinned", url="https://example.invalid/x.git", ref="", framework="fastapi"
    )
    with pytest.raises(harness.HarnessUnavailableError, match="ref not pinned"):
        harness.clone_at_ref(case, tmp_path)


def test_false_positive_count_sums_drift_categories() -> None:
    report = {"summary": {"drifted": 2, "missing_in_spec": 1, "missing_in_code": 3}}
    assert harness.false_positive_count(report) == 6
