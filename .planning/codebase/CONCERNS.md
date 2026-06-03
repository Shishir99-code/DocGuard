# Concerns & Risks
_Last updated: 2026-06-02_

## Technical Debt

**Magic strings for config enum values:**
- `cfg.check.fail_on` accepts `"any"`, `"drift-only"`, `"missing"` but these are raw strings, not an enum. Same for `cfg.output.format` (`"text"`, `"json"`, `"github"`) and `cfg.check.severity_threshold`.
- Files: `src/docguard/config.py` (lines 12-22), `src/docguard/cli.py` (lines 187-192)
- Impact: Typos in `.docguard.yaml` silently fall through to the `else` branch in `check`, producing no output format and no error message. Pydantic validation does not reject unknown strings here.
- Fix: Use `Literal["any", "drift-only", "missing"]` or a `StrEnum` for these fields.

**Hardcoded magic number for config search depth:**
- `find_config` iterates `range(10)` to walk up the directory tree.
- File: `src/docguard/config.py` line 43
- Fix: Extract constant `_MAX_CONFIG_SEARCH_DEPTH = 10` or use `Path.parents`.

**`_ROUTER_NAMES` is a small, hardcoded set:**
- Only `{"app", "router"}` are treated as FastAPI router objects.
- File: `src/docguard/parsers/fastapi_parser.py` line 30
- Impact: Any project that names its router `api`, `v1`, `prefix_router`, etc. will produce zero detected endpoints with no warning to the user.

**`Optional` mapped to `"string"` in type map:**
- `_PYTHON_TYPE_TO_JSON["Optional"] = "string"` is a rough fallback; the inner type resolution in `_resolve_annotation` handles real `Optional[X]` subscripts. This entry is only hit when `Optional` appears as a bare name (unusual), but the comment "fallback; inner type resolved separately" implies it may mask resolution failures.
- File: `src/docguard/parsers/fastapi_parser.py` line 25

**Duplicated parse-and-run logic across CLI commands:**
- `check`, `fix`, and `report` each repeat the same pattern: `_resolve_config_and_spec` → detect parser → collect source files → `extract_endpoints` → `load_spec` → `normalize_spec` → `compare`. No shared helper wraps this pipeline.
- Files: `src/docguard/cli.py` lines 133-167, 207-224, 261-285
- Fix: Extract a `_run_pipeline(cfg, spec_path, source_path) -> DriftReport` helper.

**`InferredField.default` is always `str | None`:**
- Default values are coerced to `str` at parse time (`_const_to_str`), losing type information. This makes it impossible to distinguish `default=0` from `default=""` in comparisons.
- File: `src/docguard/parsers/fastapi_parser.py` lines 62, 327-329

---

## Known Gaps

**No validation of the LLM output in `fix`:**
- `suggest_fix` returns the raw string from the LLM and `--apply` writes it directly to disk without YAML parsing, schema validation, or a backup of the original.
- File: `src/docguard/fixers/llm_fixer.py` lines 62-70; `src/docguard/cli.py` lines 243-244
- Risk: A malformed LLM response can corrupt the spec file with no recovery path.
- Fix: Parse with `yaml.safe_load`, validate with `openapi-spec-validator` (already a dependency), and write the original to a `.bak` file before overwriting.

**`can_handle` only checks dependency files, never imports:**
- `FastAPIParser.can_handle` reads `requirements.txt`, `pyproject.toml`, etc. for the string `"fastapi"`. If a project uses inline script metadata, `uv.lock`, or vendor-installs FastAPI without a manifest entry, detection returns `False` silently.
- File: `src/docguard/parsers/fastapi_parser.py` lines 359-370
- The fallback in `can_handle` does not check Python source imports, so `--framework fastapi` is the only workaround.

**No support for `$ref` parameters in OpenAPI spec:**
- `_extract_parameters` iterates raw parameter dicts. If a parameter uses `$ref: '#/components/parameters/...'`, `param.get("name")` returns `None` and the parameter is silently dropped.
- File: `src/docguard/core/spec_loader.py` lines 117-131

**No handling of external `$ref` in spec loader:**
- `_resolve_ref` explicitly skips any `$ref` that does not start with `"#/components/schemas/"`.
- File: `src/docguard/core/spec_loader.py` lines 232-238
- Impact: Specs that split schemas into separate files or use remote refs produce no fields for those schemas, making every field appear as drift.

**`severity_threshold` config key is loaded but never applied:**
- `DocGuardConfig.check.severity_threshold` is documented and settable, but no code in `cli.py` filters diffs by this threshold before deciding exit code or rendering output.
- File: `src/docguard/config.py` line 14; `src/docguard/cli.py` lines 180-195

**`output.report_path` is never used:**
- `OutputConfig.report_path` exists in the config model and default YAML, but no CLI command reads or acts on it.
- File: `src/docguard/config.py` line 23

**No test coverage for `llm_fixer.py`:**
- `src/docguard/fixers/llm_fixer.py` has zero tests. `build_fix_prompt` is pure and trivially testable; `suggest_fix` can be tested with a mocked `openai.OpenAI` client.

**No test coverage for `cli.py` commands beyond smoke tests:**
- `tests/test_cli.py` exists but was not loaded during this audit. Integration paths for `fix` and `report` sub-commands, invalid spec paths, and bad `--fail-on` values are likely untested.

**No test for malformed/unparseable Python files:**
- `fastapi_parser.extract_endpoints` silently `continue`s on `SyntaxError` or `OSError`. There is no test that exercises this path or checks that the user receives any indication a file was skipped.
- File: `src/docguard/parsers/fastapi_parser.py` lines 380-384

**`Union[A, B]` (non-nullable) type resolution collapses to left branch:**
- In `_resolve_annotation`, when `X | Y` is encountered and neither side is `None`, the left type is returned without warning. Any `Union[str, int]` field will silently appear as `str`.
- File: `src/docguard/parsers/fastapi_parser.py` lines 115-116

---

## Risks

**`--apply` writes LLM output to disk with no backup or validation:**
- Described above under Known Gaps. This is the highest-impact risk: a single bad LLM call can corrupt the spec file.

**Subprocess call to `git` in `_git_metadata`:**
- `subprocess.check_output(["git", ...])` is invoked on every `check` and `report` run. In adversarial or unusual environments (git not on PATH, inside a container, running on a path with unusual permissions) this silently returns empty strings, which is fine. But if `git` is a malicious binary on PATH, DocGuard would execute it.
- File: `src/docguard/cli.py` lines 88-102
- Mitigation: The `stderr=subprocess.DEVNULL` and `except FileNotFoundError` reduce exposure, but `timeout=` is not set. A hanging `git` process would hang the CLI indefinitely.
- Fix: Add `timeout=5` to both `check_output` calls.

**Unbounded recursion in `_schema_to_fields` / `_compare_fields`:**
- `_schema_to_fields` guards against circular `$ref` via `_visited`, but `_compare_fields` in the comparator has no depth limit. A deeply nested Pydantic model or a hand-crafted spec with many nested objects will produce a deep Python call stack.
- Files: `src/docguard/core/spec_loader.py` line 162; `src/docguard/core/comparator.py` lines 189-194

**`openapi-spec-validator` is a hard dependency but never called at runtime:**
- The package is listed in `dependencies` (not `optional-dependencies`) but no code in the source tree calls it to validate user-supplied specs. It adds install weight without delivering value.
- File: `pyproject.toml` line 31

**Broad `except (SyntaxError, OSError)` swallows parse failures silently:**
- If a file fails AST parsing, it is skipped without any log message, warning, or counter. In a CI run, this could mean real endpoints are invisible to DocGuard with no indication.
- File: `src/docguard/parsers/fastapi_parser.py` lines 382-384
- Fix: At minimum, print a warning to stderr; ideally surface a `source_warnings` list in the report.

**`pyproject.toml` URLs point to `github.com/docguard/docguard`, not the actual repo:**
- The GitHub remote is `Shishir99-code/DocGuard`. The `Homepage`, `Repository`, and `Issues` URLs are placeholder values that resolve to a non-existent org.
- File: `pyproject.toml` lines 43-47

---

## Opportunities

**Extract a `_run_pipeline` helper to eliminate 3x duplicated CLI logic:**
- `check`, `fix`, and `report` share ~15 lines of setup code. A single `_run_pipeline` function would reduce bugs from inconsistent config merging and make it easy to add a future `watch` command.
- File: `src/docguard/cli.py`

**Add `Literal` typing to config string enums:**
- Converting `fail_on`, `format`, `severity_threshold`, and `framework` to `Literal` types in `DocGuardConfig` gives Pydantic free validation and IDE autocomplete. Zero runtime cost.
- File: `src/docguard/config.py`

**Surface skipped-file warnings in the drift report:**
- Add a `source_warnings: list[str]` field to `DriftReportMetadata` or `DriftReport`. Populate it when files are skipped due to parse errors. This costs one field and one append, but gives CI users visibility into silent failures.
- Files: `src/docguard/core/models.py`, `src/docguard/parsers/fastapi_parser.py`

**Configurable router variable names:**
- Expose `router_names` as a config option (default `["app", "router"]`) so projects can declare their own router variable names without forking the parser.
- Files: `src/docguard/parsers/fastapi_parser.py` line 30, `src/docguard/config.py`

**`openapi-spec-validator` is already installed — use it:**
- Call `openapi_spec_validator.validate` on the loaded spec before normalizing. This catches malformed user specs early with a clear error message instead of silent missing-field drift.
- Files: `src/docguard/core/spec_loader.py`, `src/docguard/cli.py`

**Add `git` timeout to prevent CI hangs:**
- A one-line change (`timeout=5`) on both `subprocess.check_output` calls is a trivial, high-value hardening fix.
- File: `src/docguard/cli.py` lines 93, 97

**Test `build_fix_prompt` in isolation:**
- `build_fix_prompt` is a pure function that takes a `DriftReport` and a spec string. A unit test would cost ~10 lines and confirm the prompt structure does not regress as the format evolves.
- File: `src/docguard/fixers/llm_fixer.py` lines 11-29
