#!/usr/bin/env bash
# DocGuard end-to-end real-repo gate.
#
# Clones pinned real OSS repositories, derives a ground-truth OpenAPI spec for
# each, runs `docguard report` against the real source, and asserts zero false
# positives. Cases skip cleanly when offline / a tool is missing / a ref is not
# yet pinned, so this is safe to run on every PR.
#
# Usage:
#   scripts/pipeline/e2e.sh                 # run the real-repo gate
#   DOCGUARD_E2E_GENERATE=1 scripts/pipeline/e2e.sh   # also install repos to
#                                                     # generate specs (heavy)
set -euo pipefail
cd "$(dirname "$0")/../.."
exec python -m pytest -m e2e -v "$@"
