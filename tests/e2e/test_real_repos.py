"""Run DocGuard against pinned real OSS repos and assert zero false positives.

Marked ``e2e`` so it runs as a separate gate (``pytest -m e2e`` /
``scripts/pipeline/e2e.sh``) and is excluded from the fast default suite. Every
case skips -- never fails -- when the environment can't reach it (offline, git
missing, ref not yet pinned), so this gate is safe to run on every PR.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.e2e import harness
from tests.e2e.corpus import CORPUS, RepoCase

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.e2e


@pytest.mark.parametrize("case", CORPUS, ids=lambda c: c.name)
def test_no_false_positives_on_real_repo(case: RepoCase, e2e_cache: Path) -> None:
    if case.requires_network and not harness.network_available():
        pytest.skip("network unavailable")
    try:
        result = harness.run_case(case, e2e_cache)
    except harness.HarnessUnavailableError as exc:
        pytest.skip(str(exc))

    assert result.false_positives <= case.max_false_positives, (
        f"{case.name}: docguard reported {result.false_positives} false positive(s) "
        f"against a ground-truth spec (allowed {case.max_false_positives}). "
        f"summary={result.report['summary']}"
    )
