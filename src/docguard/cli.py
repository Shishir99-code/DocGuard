"""DocGuard CLI -- the main entry point."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import typer
from rich.console import Console

import docguard
from docguard.config import DocGuardConfig, default_config_yaml, load_config
from docguard.core.comparator import compare
from docguard.core.models import DriftReportMetadata, Severity
from docguard.core.spec_loader import find_spec, load_spec, normalize_spec
from docguard.formatters import github as github_fmt
from docguard.formatters import json_fmt
from docguard.formatters import text as text_fmt
from docguard.parsers.registry import available_parsers, detect_framework, get_parser_by_name

app = typer.Typer(
    name="docguard",
    help="Eliminate API documentation drift. Your OpenAPI spec becomes a test case.",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()


# ── Helpers ──────────────────────────────────────────────────────────────────


def _collect_source_files(source_dir: Path, ignore: list[str]) -> list[Path]:
    """Recursively collect Python source files, respecting ignore globs."""
    import fnmatch

    files: list[Path] = []
    for py_file in source_dir.rglob("*.py"):
        rel = str(py_file.relative_to(source_dir))
        if any(fnmatch.fnmatch(rel, pat) for pat in ignore):
            continue
        files.append(py_file)
    return files


def _resolve_config_and_spec(
    spec: str | None,
    source: str | None,
    framework: str | None,
    fmt: str | None,
    project_root: Path | None = None,
) -> tuple[DocGuardConfig, Path, Path]:
    """Merge CLI flags with the config file and resolve spec/source paths."""
    root = project_root or Path.cwd()
    cfg = load_config(project_root=root)

    if spec:
        cfg.spec = spec
    if source:
        cfg.source = source
    if framework:
        cfg.framework = framework
    if fmt:
        cfg.output.format = fmt

    spec_path = Path(cfg.spec)
    if not spec_path.is_absolute():
        spec_path = root / spec_path
    if not spec_path.exists():
        found = find_spec(root)
        if found is None:
            console.print("[bold red]Error:[/bold red] No OpenAPI spec file found.")
            console.print("Run [bold]docguard init[/bold] or pass --spec explicitly.")
            raise typer.Exit(2)
        spec_path = found

    source_path = Path(cfg.source)
    if not source_path.is_absolute():
        source_path = root / source_path

    return cfg, spec_path, source_path


def _git_metadata() -> tuple[str, str]:
    """Best-effort extraction of current commit SHA and branch."""
    import subprocess

    sha = branch = ""
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    return sha, branch


# ── Commands ─────────────────────────────────────────────────────────────────


@app.command()
def init(
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing config"),
) -> None:
    """Initialize a .docguard.yaml config file in the current directory."""
    config_path = Path.cwd() / ".docguard.yaml"
    if config_path.exists() and not force:
        console.print(f"[yellow]Config already exists at {config_path}[/yellow]")
        console.print("Use [bold]--force[/bold] to overwrite.")
        raise typer.Exit(0)
    config_path.write_text(default_config_yaml(), encoding="utf-8")
    console.print(f"[green]Created {config_path}[/green]")


@app.command()
def check(
    spec: str | None = typer.Option(None, "--spec", "-s", help="Path to OpenAPI spec"),
    source: str | None = typer.Option(None, "--source", "-d", help="Source directory to scan"),
    framework: str | None = typer.Option(None, "--framework", "-f", help="Force framework detection"),
    fmt: str | None = typer.Option(None, "--format", help="Output format: text, json, github"),
    fail_on: str | None = typer.Option(None, "--fail-on", help="Failure threshold: any, drift-only, missing"),
    ignore: list[str] | None = typer.Option(None, "--ignore", help="Glob patterns to ignore"),
) -> None:
    """Run drift detection against the OpenAPI spec."""
    start = time.monotonic()
    cfg, spec_path, source_path = _resolve_config_and_spec(spec, source, framework, fmt)
    if fail_on:
        cfg.check.fail_on = fail_on
    if ignore:
        cfg.ignore = ignore

    # Detect or force framework parser
    if cfg.framework == "auto":
        parser = detect_framework(Path.cwd())
    else:
        parser = get_parser_by_name(cfg.framework)

    if parser is None:
        console.print("[bold red]Error:[/bold red] Could not detect a supported framework.")
        console.print(f"Supported frameworks: {', '.join(available_parsers())}")
        raise typer.Exit(2)

    # Parse source code
    source_files = _collect_source_files(source_path, cfg.ignore)
    code_endpoints = parser.extract_endpoints(source_files)

    # Load and normalise spec
    raw_spec = load_spec(spec_path)
    spec_endpoints = normalize_spec(raw_spec)

    # Compare
    sha, branch = _git_metadata()
    metadata = DriftReportMetadata(
        commit_sha=sha,
        branch=branch,
        spec_path=str(spec_path),
        framework_detected=parser.name,
        scan_duration_ms=int((time.monotonic() - start) * 1000),
    )
    report = compare(code_endpoints, spec_endpoints, metadata)
    report.metadata.scan_duration_ms = int((time.monotonic() - start) * 1000)

    # Output
    output_format = cfg.output.format
    if output_format == "json":
        console.print(json_fmt.render(report))
    elif output_format == "github":
        print(github_fmt.render(report))  # noqa: T201 -- raw print for GH Actions
    else:
        text_fmt.render(report, console)

    # Exit code
    has_errors = any(
        d.severity == Severity.ERROR for ep in report.endpoints for d in ep.diffs
    )
    has_missing = report.summary.missing_in_spec > 0
    has_drift = report.summary.drifted > 0

    should_fail = False
    if cfg.check.fail_on == "any":
        should_fail = has_errors or has_missing or has_drift
    elif cfg.check.fail_on == "drift-only":
        should_fail = has_drift
    elif cfg.check.fail_on == "missing":
        should_fail = has_missing

    if should_fail:
        raise typer.Exit(1)


@app.command()
def fix(
    spec: str | None = typer.Option(None, "--spec", "-s", help="Path to OpenAPI spec"),
    source: str | None = typer.Option(None, "--source", "-d", help="Source directory to scan"),
    framework: str | None = typer.Option(None, "--framework", "-f", help="Force framework"),
    apply: bool = typer.Option(False, "--apply", help="Write fixes directly to the spec file"),
    model: str | None = typer.Option(None, "--model", help="LLM model to use"),
) -> None:
    """Suggest spec updates to resolve drift (LLM-powered)."""
    cfg, spec_path, source_path = _resolve_config_and_spec(spec, source, framework, None)
    if model:
        cfg.fix.model = model

    if cfg.framework == "auto":
        parser = detect_framework(Path.cwd())
    else:
        parser = get_parser_by_name(cfg.framework)

    if parser is None:
        console.print("[bold red]Error:[/bold red] Could not detect a supported framework.")
        raise typer.Exit(2)

    source_files = _collect_source_files(source_path, cfg.ignore)
    code_endpoints = parser.extract_endpoints(source_files)
    raw_spec = load_spec(spec_path)
    spec_endpoints = normalize_spec(raw_spec)
    report = compare(code_endpoints, spec_endpoints)

    if report.drift_score == 0:
        console.print("[bold green]No drift detected -- nothing to fix.[/bold green]")
        raise typer.Exit(0)

    from docguard.fixers.llm_fixer import suggest_fix

    spec_content = spec_path.read_text(encoding="utf-8")

    try:
        with console.status("[bold blue]Asking LLM for fix suggestions...[/bold blue]"):
            fixed_yaml = suggest_fix(
                report, spec_content, model=cfg.fix.model, api_key_env=cfg.fix.api_key_env
            )
    except RuntimeError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(2) from exc

    if apply:
        spec_path.write_text(fixed_yaml, encoding="utf-8")
        console.print(f"[green]Spec updated at {spec_path}[/green]")
    else:
        console.print("\n[bold]Suggested spec (dry-run):[/bold]\n")
        console.print(fixed_yaml)
        console.print("\n[dim]Use --apply to write changes to disk.[/dim]")


@app.command()
def report(
    spec: str | None = typer.Option(None, "--spec", "-s", help="Path to OpenAPI spec"),
    source: str | None = typer.Option(None, "--source", "-d", help="Source directory to scan"),
    framework: str | None = typer.Option(None, "--framework", "-f", help="Force framework"),
    output: str | None = typer.Option(None, "--output", "-o", help="Output file path (default: stdout)"),
) -> None:
    """Generate a full drift report in JSON format."""
    start = time.monotonic()
    cfg, spec_path, source_path = _resolve_config_and_spec(spec, source, framework, None)

    if cfg.framework == "auto":
        parser = detect_framework(Path.cwd())
    else:
        parser = get_parser_by_name(cfg.framework)

    if parser is None:
        console.print("[bold red]Error:[/bold red] Could not detect a supported framework.")
        raise typer.Exit(2)

    source_files = _collect_source_files(source_path, cfg.ignore)
    code_endpoints = parser.extract_endpoints(source_files)
    raw_spec = load_spec(spec_path)
    spec_endpoints = normalize_spec(raw_spec)

    sha, branch = _git_metadata()
    metadata = DriftReportMetadata(
        commit_sha=sha,
        branch=branch,
        spec_path=str(spec_path),
        framework_detected=parser.name,
        scan_duration_ms=int((time.monotonic() - start) * 1000),
    )
    drift_report = compare(code_endpoints, spec_endpoints, metadata)
    drift_report.metadata.scan_duration_ms = int((time.monotonic() - start) * 1000)

    json_output = json_fmt.render(drift_report)

    if output:
        Path(output).write_text(json_output, encoding="utf-8")
        console.print(f"[green]Report written to {output}[/green]")
    else:
        print(json_output)  # noqa: T201


@app.command()
def version() -> None:
    """Print DocGuard version."""
    console.print(f"docguard {docguard.__version__}")


if __name__ == "__main__":
    app()
