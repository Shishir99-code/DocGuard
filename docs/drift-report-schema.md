# Drift Report Schema

The drift report is the single data contract between the DocGuard CLI, the GitHub Action, and any downstream dashboards or integrations. It is output by `docguard report` and `docguard check --format json`.

## Schema Version

Current version: **1.0.0**

The report follows semantic versioning. Backward-compatible additions (new fields) increment the minor version. Breaking changes increment the major version.

## Top-Level Structure

| Field | Type | Description |
|-------|------|-------------|
| `$schema` | string | URL to the JSON Schema definition |
| `version` | string | Schema version (semver) |
| `metadata` | object | Scan metadata (repo, commit, timing) |
| `drift_score` | float | 0.0 (synced) to 1.0 (fully drifted) |
| `summary` | object | Aggregate counts |
| `endpoints` | array | Per-endpoint comparison results |

## Example Report

```json
{
  "$schema": "https://docguard.dev/schemas/drift-report-v1.json",
  "version": "1.0.0",
  "metadata": {
    "repository": "acme-corp/payments-api",
    "commit_sha": "a1b2c3d",
    "branch": "feature/add-refunds",
    "timestamp": "2026-04-03T14:22:00Z",
    "spec_path": "openapi.yaml",
    "framework_detected": "fastapi",
    "scan_duration_ms": 1240
  },
  "drift_score": 0.35,
  "summary": {
    "total_endpoints_in_code": 12,
    "total_endpoints_in_spec": 10,
    "synced": 7,
    "drifted": 3,
    "missing_in_spec": 2,
    "missing_in_code": 0
  },
  "endpoints": [
    {
      "path": "/payments/{payment_id}/refund",
      "method": "POST",
      "status": "missing_in_spec",
      "source_location": { "file": "src/routes/payments.py", "line": 87 },
      "spec_location": null,
      "diffs": []
    },
    {
      "path": "/users/{user_id}",
      "method": "GET",
      "status": "drift",
      "source_location": { "file": "src/routes/users.py", "line": 23 },
      "spec_location": { "json_path": "#/paths/~1users~1{user_id}/get" },
      "diffs": [
        {
          "type": "field_added_in_code",
          "location": "response.body.email_verified",
          "code_value": { "type": "boolean", "required": true },
          "spec_value": null,
          "severity": "error",
          "message": "Field 'email_verified' (boolean) exists in code response but is missing from the spec."
        },
        {
          "type": "type_mismatch",
          "location": "response.body.age",
          "code_value": { "type": "string" },
          "spec_value": { "type": "integer" },
          "severity": "error",
          "message": "Field 'age' is 'string' in code but 'integer' in spec."
        }
      ]
    }
  ]
}
```

## Field Reference

### `metadata`

| Field | Type | Description |
|-------|------|-------------|
| `repository` | string | Repository identifier (e.g. `org/repo`) |
| `commit_sha` | string | Short Git commit hash at scan time |
| `branch` | string | Git branch name |
| `timestamp` | string | ISO 8601 timestamp |
| `spec_path` | string | Path to the OpenAPI spec file used |
| `framework_detected` | string | Framework parser that was used |
| `scan_duration_ms` | integer | Total scan time in milliseconds |

### `summary`

| Field | Type | Description |
|-------|------|-------------|
| `total_endpoints_in_code` | integer | Endpoints discovered in source code |
| `total_endpoints_in_spec` | integer | Endpoints defined in the OpenAPI spec |
| `synced` | integer | Endpoints that match perfectly |
| `drifted` | integer | Endpoints present in both but with differences |
| `missing_in_spec` | integer | Endpoints in code but not in spec |
| `missing_in_code` | integer | Endpoints in spec but not in code |

### `endpoints[]`

| Field | Type | Description |
|-------|------|-------------|
| `path` | string | URL path (e.g. `/users/{user_id}`) |
| `method` | string | HTTP method (GET, POST, PUT, DELETE, PATCH) |
| `status` | enum | `synced`, `drift`, `missing_in_spec`, `missing_in_code` |
| `source_location` | object/null | `{ "file": string, "line": integer }` |
| `spec_location` | object/null | `{ "json_path": string }` |
| `diffs` | array | List of field-level differences |

### `endpoints[].diffs[]`

| Field | Type | Description |
|-------|------|-------------|
| `type` | enum | Diff type (see table below) |
| `location` | string | Dot-path to the field (e.g. `response.body.email`) |
| `code_value` | object/null | Value as found in source code |
| `spec_value` | object/null | Value as defined in the spec |
| `severity` | enum | `error`, `warning`, `info` |
| `message` | string | Human-readable description |

### Diff Types

| Type | Description | Default Severity |
|------|-------------|-----------------|
| `field_added_in_code` | Field exists in code but not in spec | error (if required), warning (if optional) |
| `field_removed_in_code` | Field exists in spec but not in code | warning |
| `type_mismatch` | Same field, different types | error |
| `required_mismatch` | Required in one, optional in the other | warning |
| `status_code_mismatch` | Different HTTP status codes | error |
| `param_added_in_code` | Parameter in code but not in spec | error |
| `param_removed_in_code` | Parameter in spec but not in code | warning |
| `param_type_mismatch` | Same parameter, different types | error |

## Drift Score Formula

```
drift_score = (drifted * 1.0 + missing_in_spec * 1.0 + missing_in_code * 0.5) / total_unique_endpoints
```

- **Drifted** and **missing_in_spec** carry full weight (1.0) -- these are active integration risks
- **missing_in_code** carries half weight (0.5) -- stale documentation, less urgent

A score of `0.0` means perfect sync. A score of `1.0` means every endpoint is out of sync.

## Severity Levels

| Severity | Meaning | Default CI Behavior |
|----------|---------|-------------------|
| `error` | Breaking: type mismatch, missing required field, missing endpoint | Fails the build |
| `warning` | Non-breaking: optional field difference, required/optional mismatch | Configurable |
| `info` | Cosmetic: tag changes, summary text differences | Never fails |
