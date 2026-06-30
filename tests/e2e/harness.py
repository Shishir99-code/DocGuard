"""End-to-end test harness: run DocGuard against a real repository checkout.

The harness clones a pinned commit of a repo, obtains a *ground-truth* OpenAPI
spec for it, runs the real ``docguard report`` CLI against the checked-out
source, and counts how many endpoints DocGuard reports as drifted or missing.
Because the ground-truth spec is authoritative for the pinned source, every such
report is a **false positive**.

Failure handling is deliberate and split into two kinds:

* :class:`HarnessUnavailable` -- the environment can't run the case (offline,
  ``git`` missing, ref not pinned, clone failed). Callers translate this into a
  pytest *skip*, so the suite degrades gracefully and never goes red offline.
* :class:`HarnessError` -- the harness reached DocGuard and something went wrong
  that is a genuine finding (e.g. ``docguard report`` crashed on real code, or
  emitted non-JSON). Callers let this *fail* the suite.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

    from tests.e2e.corpus import RepoCase

CLONE_TIMEOUT_S = 300
INSTALL_TIMEOUT_S = 900
REPORT_TIMEOUT_S = 180


class HarnessUnavailableError(Exception):
    """The environment can't run this case -- translate to a pytest skip."""


class HarnessError(Exception):
    """The harness reached DocGuard and hit a genuine failure -- let it fail."""


@dataclass
class CaseResult:
    """Outcome of running one :class:`RepoCase` through DocGuard."""

    case: RepoCase
    report: dict[str, Any]
    false_positives: int


def git_available() -> bool:
    return shutil.which("git") is not None


def docguard_available() -> bool:
    return shutil.which("docguard") is not None


def network_available(host: str = "github.com", port: int = 443) -> bool:
    """Cheap, dependency-free reachability check via a short-timeout TCP connect."""
    try:
        with socket.create_connection((host, port), timeout=5):
            return True
    except OSError:
        return False


def _run(
    cmd: list[str], *, cwd: Path | None = None, timeout: int = 60
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess; nonzero exit / failure to launch becomes HarnessUnavailable."""
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HarnessUnavailableError(f"command failed to run: {' '.join(cmd)} ({exc})") from exc
    if proc.returncode != 0:
        raise HarnessUnavailableError(
            f"command exited {proc.returncode}: {' '.join(cmd)}\n{proc.stderr.strip()}"
        )
    return proc


def clone_at_ref(case: RepoCase, cache_dir: Path) -> Path:
    """Clone ``case.url`` at the pinned commit into ``cache_dir/<name>``."""
    if not case.ref:
        raise HarnessUnavailableError(f"{case.name}: ref not pinned (set a verified commit SHA)")
    repo_dir = cache_dir / case.name
    if (repo_dir / ".git").is_dir():
        return repo_dir
    repo_dir.mkdir(parents=True, exist_ok=True)
    try:
        _run(["git", "init", "-q"], cwd=repo_dir)
        _run(["git", "remote", "add", "origin", case.url], cwd=repo_dir)
        try:
            # Fast path: fetch just the pinned commit when the server allows it.
            _run(
                ["git", "fetch", "--depth", "1", "-q", "origin", case.ref],
                cwd=repo_dir,
                timeout=CLONE_TIMEOUT_S,
            )
        except HarnessUnavailableError:
            # Some servers reject fetch-by-SHA; fall back to a full fetch.
            _run(["git", "fetch", "-q", "origin"], cwd=repo_dir, timeout=CLONE_TIMEOUT_S)
        _run(["git", "checkout", "-q", case.ref], cwd=repo_dir)
    except HarnessUnavailableError:
        shutil.rmtree(repo_dir, ignore_errors=True)
        raise
    return repo_dir


def resolve_spec(case: RepoCase, repo_dir: Path) -> Path:
    """Return the ground-truth OpenAPI spec path for a checked-out repo."""
    if case.committed_spec:
        spec = repo_dir / case.committed_spec
        if not spec.is_file():
            raise HarnessError(f"{case.name}: committed_spec not found at {spec}")
        return spec
    if case.app_import:
        return _generate_fastapi_spec(case, repo_dir)
    raise HarnessError(
        f"{case.name}: no spec strategy configured (set committed_spec or app_import)"
    )


def _generate_fastapi_spec(case: RepoCase, repo_dir: Path) -> Path:
    """Install the repo in an isolated venv and dump ``app.openapi()`` as the spec.

    Heavy (network + build) and opt-in via ``DOCGUARD_E2E_GENERATE=1``. The app is
    imported only here, inside the test harness's throwaway venv -- DocGuard's own
    parser stays AST-only and never imports user code.
    """
    if os.environ.get("DOCGUARD_E2E_GENERATE") != "1":
        raise HarnessUnavailableError(
            f"{case.name}: spec generation needs DOCGUARD_E2E_GENERATE=1 (installs the repo)"
        )
    assert case.app_import is not None  # narrowed by caller
    venv = repo_dir / ".e2e-venv"
    _run(["python", "-m", "venv", str(venv)], timeout=INSTALL_TIMEOUT_S)
    py = venv / "bin" / "python"
    _run([str(py), "-m", "pip", "install", "-q", "--upgrade", "pip"], timeout=INSTALL_TIMEOUT_S)
    targets = list(case.pip_install) or ["."]
    _run([str(py), "-m", "pip", "install", "-q", *targets], cwd=repo_dir, timeout=INSTALL_TIMEOUT_S)

    module, _, var = case.app_import.partition(":")
    out = repo_dir / ".e2e-openapi.json"
    dump = (
        "import json, importlib;"
        f"m = importlib.import_module({module!r});"
        f"app = getattr(m, {var!r});"
        f"open({str(out)!r}, 'w').write(json.dumps(app.openapi()))"
    )
    _run([str(py), "-c", dump], cwd=repo_dir / case.source_subdir, timeout=REPORT_TIMEOUT_S)
    return out


def run_report(spec: Path, source: Path, framework: str) -> dict[str, Any]:
    """Invoke the real ``docguard report`` CLI and parse its JSON output."""
    if not docguard_available():
        raise HarnessUnavailableError("docguard CLI not on PATH")
    cmd = [
        "docguard",
        "report",
        "--spec",
        str(spec),
        "--source",
        str(source),
        "--framework",
        framework,
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=REPORT_TIMEOUT_S, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HarnessError(f"docguard report failed to run: {exc}") from exc
    if proc.returncode != 0:
        # By now clone + spec succeeded, so a docguard failure is a real finding.
        raise HarnessError(
            f"docguard report exited {proc.returncode} on real source\n{proc.stderr.strip()}"
        )
    try:
        report: dict[str, Any] = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise HarnessError(
            f"docguard report did not emit JSON: {exc}\n{proc.stdout[:500]}"
        ) from exc
    return report


def false_positive_count(report: dict[str, Any]) -> int:
    """Count drift against a ground-truth spec; every unit is a false positive."""
    summary = report["summary"]
    return (
        int(summary["drifted"])
        + int(summary["missing_in_spec"])
        + int(summary["missing_in_code"])
    )


def run_case(case: RepoCase, cache_dir: Path) -> CaseResult:
    """Clone, resolve the ground-truth spec, run DocGuard, and count false positives."""
    if not git_available():
        raise HarnessUnavailableError("git not available")
    repo_dir = clone_at_ref(case, cache_dir)
    spec = resolve_spec(case, repo_dir)
    source = repo_dir / case.source_subdir
    report = run_report(spec, source, case.framework)
    return CaseResult(case=case, report=report, false_positives=false_positive_count(report))
