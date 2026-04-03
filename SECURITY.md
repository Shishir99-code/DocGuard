# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in DocGuard, please report it responsibly.

**Do not open a public issue.** Instead, send an email to:

**security@docguard.dev**

Include:

- A description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

## Response Timeline

- **Acknowledgment**: Within 48 hours of receiving the report
- **Assessment**: Within 5 business days
- **Fix for critical issues**: Within 14 days
- **Fix for non-critical issues**: Within 30 days

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | Yes       |

## Disclosure Policy

We follow coordinated disclosure. We ask that you:

1. Do not disclose the vulnerability publicly until a fix is released
2. Allow us reasonable time to address the issue
3. Do not exploit the vulnerability beyond what is necessary to demonstrate it

We will credit you in the release notes (unless you prefer to remain anonymous).

## Scope

The following are in scope:

- The `docguard` Python package and its dependencies
- The `docguard/action` GitHub Action
- The DocGuard documentation site

The following are out of scope:

- Third-party LLM APIs (OpenAI, etc.) -- report those to the respective providers
- Issues in the target project being scanned (DocGuard does not execute user code)

## Security Design

DocGuard is designed with security in mind:

- **No code execution**: DocGuard uses static AST parsing and never imports or executes the target project's code
- **No network access**: The core scan is entirely offline. Only `docguard fix` makes network calls (to the configured LLM API)
- **No secrets in config**: API keys are referenced by environment variable name, never stored in `.docguard.yaml`
