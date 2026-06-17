---
phase: 1
reviewers: [ollama]
reviewed_at: 2026-06-16T00:00:00Z
plans_reviewed:
  - 01-01-PLAN.md
  - 01-02-PLAN.md
skipped_reviewers:
  - claude (self — running inside Claude Code)
  - cursor (cursor-agent CLI not installed; only Cursor IDE detected)
---

# Cross-AI Plan Review — Phase 1: Diagnostics & Threshold

## Ollama Review (gemma3:27b)

### Plan 01-01: DIAG-01 — Parse Warning Surfacing

**Summary:** This plan is well-focused and addresses the DIAG-01 requirement directly. The proposed changes are straightforward and logically sound, effectively surfacing parse errors to the user without halting execution. The addition of `source_warnings` to the metadata and its propagation via the `to_dict()` method feels clean and consistent with the existing architecture. The tests appear adequate to verify the core functionality.

**Strengths:**
- Clear objective and focused scope
- Directly addresses the stated requirement
- Good use of existing data structures (DriftReportMetadata) to convey the information
- Sufficient test coverage with specific tests for warning emission, accumulation, and continuation
- Minimal code change impact

**Concerns:**
- **MEDIUM:** The warning message format `"WARNING: skipping {filepath}: {exc}"` could potentially expose internal exception details. Consider sanitizing the exception message (`str(exc)`) to prevent leaking potentially sensitive information.
- **LOW:** The error handling traps `SyntaxError` and `OSError`, but unexpected exceptions could still lead to uncaught errors. Consider a broader `except Exception:` with logging to catch unforeseen issues without crashing.
- **LOW:** The initialization of `self.source_warnings` within `extract_endpoints` is slightly surprising. It might be clearer to initialize it in `__init__`, even if reset each time, for consistency. *(Note: the plan does both — `__init__` initializes it AND `extract_endpoints` resets it.)*

**Suggestions:**
- Sanitize the exception message in the warning output to avoid potentially exposing sensitive information
- Add a comment clarifying the specific exceptions being caught and why a broader `except` is intentionally avoided
- The `__init__` + reset pattern is already in the plan; the concern is partially addressed

**Risk Assessment: LOW** — The plan is focused, straightforward, and well-tested. The potential risks are minor and easily mitigated.

---

### Plan 01-02: DIAG-02/03 + Determinism — CLI Diagnostics & Threshold

**Summary:** This plan integrates parser warnings, zero-endpoint guard, and severity threshold filtering into the CLI. It's more complex than 01-01 as it touches multiple critical areas of the CLI logic. The introduction of a dedicated `CliRunner` for stderr assertions is a welcome addition. The approach of filtering exit codes based on severity threshold while preserving all drift details in the report is reasonable.

**Strengths:**
- Addresses multiple requirements efficiently in a single plan
- The `sorted()` call ensures deterministic output, crucial for CI workflows
- The separate `CliRunner(mix_stderr=False)` for stderr testing isolates assertion failures
- The severity threshold implementation preserves existing behavior while offering finer-grained control
- Good test coverage with dedicated tests for each feature

**Concerns:**
- **MEDIUM:** `_SEVERITY_ORDER` uses string keys and integer values — if severity levels are expanded, the dictionary must be updated manually. A more robust approach might be to derive the ordering from the existing `Severity` enum.
- **MEDIUM:** The zero-endpoint guard raises `typer.Exit(2)` hardcoded. Consider making the exit code configurable, though for a static analysis CI tool this may be over-engineering.
- **LOW:** `test_empty_source_dir_does_not_trigger_zero_endpoints_guard` only checks that the guard doesn't trigger. It might also verify that no erroneous warning is emitted.
- **LOW:** Consider adding a docstring explaining the purpose of the `_SEVERITY_ORDER` dictionary.

**Suggestions:**
- Replace `_SEVERITY_ORDER` dictionary with ordering derived from the existing `Severity` enum (avoids duplication)
- Enhance the empty-dir test to also assert no zero-endpoints warning on stderr
- Add a brief inline comment on `_SEVERITY_ORDER`

**Risk Assessment: MEDIUM** — The complexity of integrating multiple features into the CLI increases the risk of regressions. The brittleness of `_SEVERITY_ORDER` and hardcoded exit code contribute to medium risk, though both are addressable with small changes.

---

## Consensus Summary

Only one reviewer (Ollama/gemma3:27b) completed. Cursor CLI was not installed.

### Agreed Strengths
- Plans are well-scoped and directly address the stated requirements
- Test coverage is adequate with tests for both happy-path and edge cases
- Minimal blast radius — changes are isolated to specific files
- The `sorted()` determinism fix is simple and high-value

### Agreed Concerns
- **MEDIUM (01-02):** `_SEVERITY_ORDER` as a dict of string→int is brittle if `Severity` enum values change. Consider deriving order from the enum itself.
- **LOW (01-01):** Exception message sanitization — the warning includes `str(exc)` which exposes the exception detail. This is likely fine for a developer-facing CLI but worth noting.
- **LOW (01-02):** The empty-source-dir test could be strengthened to assert no false warning is emitted.

### Divergent Views
*(Single reviewer — no divergence to report)*

### Actionable Before Execution
1. **Consider** deriving `_SEVERITY_ORDER` from the existing `Severity` enum in `models.py` instead of a hardcoded dict — reduces duplication and prevents enum/dict drift
2. **Consider** adding a brief comment on the zero-endpoints guard explaining the `source_files and not code_endpoints` short-circuit logic
3. **Non-blocking:** Exception message sanitization (LOW risk, developer-facing tool)

---

*To incorporate this feedback: `/gsd-plan-phase 1 --reviews`*
*To proceed without changes: `/gsd-execute-phase 1`*
