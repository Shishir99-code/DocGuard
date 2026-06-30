"""Curated corpus of real-world OSS repositories for end-to-end drift testing.

Each :class:`RepoCase` pins a real public repository to an immutable commit so
the ground-truth OpenAPI spec is reproducible. The harness clones the repo,
obtains a ground-truth spec (one committed in the repo, or one generated from
the app itself), runs the real ``docguard report`` CLI against the source, and
asserts DocGuard reports **zero** drift. Because the spec is authoritative for
the pinned source, any drift DocGuard reports is a false positive -- the exact
failure mode this milestone exists to eliminate.

Pinning policy: ``ref`` MUST be an immutable commit SHA. Entries with an empty
``ref`` are intentionally skipped until a maintainer pins a verified commit from
a network-enabled run (``scripts/pipeline/e2e.sh``). We never ship a guessed
SHA, because a wrong pin would silently mask the parser instead of exercising
it on real code.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RepoCase:
    """A single real repository to run DocGuard against, with a ground-truth spec."""

    name: str  # stable id, used for the cache dir and the pytest test id
    url: str  # clone URL (https:// for real repos, file:// for local self-tests)
    ref: str  # immutable commit SHA; empty string => skipped until pinned
    framework: str  # parser to force, e.g. "fastapi" | "flask"
    source_subdir: str = "."  # path within the repo to scan

    # Ground-truth spec strategy -- set exactly one:
    committed_spec: str | None = None  # path within the repo to an OpenAPI file
    app_import: str | None = None  # "package.module:app_var" -> generate via app.openapi()

    # Extra pip install targets for the generate strategy (default: the repo itself).
    pip_install: tuple[str, ...] = field(default=())

    # Ratchet: max tolerated false positives for this repo. Lets us adopt a noisy
    # repo and tighten over time without the suite flapping. Default 0 = strict.
    max_false_positives: int = 0

    # Whether running this case needs network (real repos: yes; local file:// : no).
    requires_network: bool = True


# Real repositories. Pin a verified commit SHA in `ref` to activate each entry.
# Until then they are skipped (never failed) so the suite is honest about what it
# actually exercises. See the module docstring for the pinning policy.
CORPUS: list[RepoCase] = [
    RepoCase(
        name="full-stack-fastapi-template",
        url="https://github.com/fastapi/full-stack-fastapi-template.git",
        ref="",  # TODO(maintainer): pin a verified commit SHA from a networked run
        framework="fastapi",
        source_subdir="backend/app",
        app_import="app.main:app",
        pip_install=("./backend",),
    ),
]
