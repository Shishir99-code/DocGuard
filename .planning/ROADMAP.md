# Roadmap: DocGuard — Correctness & Consistency

## Overview

Four phases fix every known correctness issue in DocGuard v0.1.0. Phase 1 makes failures visible so everything else is debuggable. Phase 2 fixes spec-side false positives at the comparison layer. Phase 3 fixes source-side false negatives by teaching the parser to find endpoints from any router variable name. Phase 4 implements the missing include_router prefix architecture so mounted sub-routers report correct paths.

## Phases

- [ ] **Phase 1: Diagnostics & Threshold** - Silent failures become visible; severity_threshold works as documented
- [ ] **Phase 2: Spec Comparison Correctness** - $ref parameters and Union types stop producing false drift
- [ ] **Phase 3: Router Detection** - Any router variable name is detected; zero-endpoint cases are caught
- [ ] **Phase 4: include_router Prefix Support** - Sub-router paths reflect their mounted prefix

## Phase Details

### Phase 1: Diagnostics & Threshold
**Goal:** DocGuard surfaces failures instead of hiding them — parse errors appear in output, zero-endpoint runs warn loudly, and severity_threshold actually filters the exit code
**Mode:** mvp
**Depends on:** Nothing (first phase)
**Requirements:** DIAG-01, DIAG-02, DIAG-03
**Success Criteria** (what must be TRUE):
  1. Running `docguard check` on a file with a SyntaxError prints a warning to stderr naming the skipped file — it does not silently continue
  2. Running `docguard check` when source files exist but zero endpoints are detected exits with a non-zero code and a human-readable warning explaining the likely configuration issue
  3. Setting `severity_threshold: warning` in `.docguard.yaml` causes items below the threshold to be shown but not affect the exit code — the exit code is 0 when only sub-threshold items exist
  4. JSON output (`--format json`) includes a `source_warnings` field listing any files that were skipped due to parse errors
**Plans:** TBD

### Phase 2: Spec Comparison Correctness
**Goal:** DocGuard stops producing false drift for $ref parameters and Union-typed fields — parameters defined in components are resolved, and Union[A, B] fields no longer collapse to the wrong type
**Mode:** mvp
**Depends on:** Phase 1
**Requirements:** SPEC-01, TYPE-01
**Success Criteria** (what must be TRUE):
  1. An OpenAPI spec that uses `$ref: '#/components/parameters/X'` for a parameter produces no false PARAM_ADDED_IN_CODE drift when the parameter exists in the Python source
  2. A FastAPI endpoint with a `Union[str, int]` field reports `"object"` in the drift comparison — it does not silently collapse to `"string"` and produce a false TYPE_MISMATCH
  3. Running `docguard check` twice on the same codebase with the same spec produces byte-for-byte identical output (determinism preserved)
**Plans:** TBD

### Phase 3: Router Detection
**Goal:** DocGuard finds endpoints from any router variable name in the codebase — projects using `api`, `v1`, `users_router`, or any custom name see their endpoints detected correctly
**Mode:** mvp
**Depends on:** Phase 2
**Requirements:** ROUT-01, ROUT-02
**Success Criteria** (what must be TRUE):
  1. A FastAPI app using `api = APIRouter()` and `@api.get("/items")` has its endpoints detected without any configuration change
  2. A FastAPI app using an unconventional router name not auto-detected can add `router_names: [my_router]` to `.docguard.yaml` and have its endpoints detected
  3. An existing `.docguard.yaml` without a `router_names` key continues to work without error — backwards compatibility is preserved
  4. The zero-endpoint warning from Phase 1 is not triggered on a correctly-configured app that uses auto-detected router names
**Plans:** TBD

### Phase 4: include_router Prefix Support
**Goal:** DocGuard resolves the full mounted path for routes registered via `app.include_router(sub_router, prefix="/prefix")` — drift reports show `/prefix/items` not `/items`
**Mode:** mvp
**Depends on:** Phase 3
**Requirements:** ROUT-03
**Success Criteria** (what must be TRUE):
  1. A FastAPI app with `app.include_router(users_router, prefix="/users")` and `@users_router.get("/{id}")` shows the path `/users/{id}` in drift output — not `/{id}`
  2. Two sub-routers mounted under different prefixes each report their own correct full path — prefixes do not bleed across routers
  3. A sub-router with no prefix argument behaves identically to pre-Phase-4 behavior — no regression on apps without prefixes
**Plans:** TBD

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Diagnostics & Threshold | 0/TBD | Not started | - |
| 2. Spec Comparison Correctness | 0/TBD | Not started | - |
| 3. Router Detection | 0/TBD | Not started | - |
| 4. include_router Prefix Support | 0/TBD | Not started | - |
