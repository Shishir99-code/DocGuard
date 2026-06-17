"""Rich-powered terminal output formatter."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from docguard.core.models import DriftReport, EndpointStatus, Severity


def render(report: DriftReport, console: Console | None = None) -> None:
    """Print a human-readable drift report to the terminal."""
    console = console or Console()

    # Header
    score_pct = f"{report.drift_score * 100:.1f}%"
    colour = "green" if report.drift_score == 0 else "yellow" if report.drift_score < 0.5 else "red"
    console.print(Panel(
        f"[bold]Drift Score:[/bold] [{colour}]{score_pct}[/{colour}]",
        title="[bold blue]DocGuard Drift Report[/bold blue]",
        subtitle=report.metadata.framework_detected or "unknown framework",
    ))

    # Summary table
    s = report.summary
    summary_table = Table(title="Summary", show_header=False, padding=(0, 2))
    summary_table.add_column("Metric", style="bold")
    summary_table.add_column("Value", justify="right")
    summary_table.add_row("Endpoints in code", str(s.total_endpoints_in_code))
    summary_table.add_row("Endpoints in spec", str(s.total_endpoints_in_spec))
    summary_table.add_row("Synced", f"[green]{s.synced}[/green]")
    summary_table.add_row("Drifted", f"[red]{s.drifted}[/red]" if s.drifted else "0")
    summary_table.add_row(
        "Missing in spec", f"[red]{s.missing_in_spec}[/red]" if s.missing_in_spec else "0"
    )
    summary_table.add_row(
        "Missing in code", f"[yellow]{s.missing_in_code}[/yellow]" if s.missing_in_code else "0"
    )
    console.print(summary_table)

    # Endpoint details (only non-synced)
    for ep in report.endpoints:
        if ep.status == EndpointStatus.SYNCED:
            continue

        status_style = {
            EndpointStatus.DRIFT: "[red]DRIFT[/red]",
            EndpointStatus.MISSING_IN_SPEC: "[red]MISSING IN SPEC[/red]",
            EndpointStatus.MISSING_IN_CODE: "[yellow]MISSING IN CODE[/yellow]",
        }.get(ep.status, ep.status.value)

        header = f"{ep.method} {ep.path}  {status_style}"
        if ep.source_location:
            header += (
                f"  [dim]{ep.source_location.get('file', '')}:"
                f"{ep.source_location.get('line', '')}[/dim]"
            )

        console.print(f"\n  {header}")

        for diff in ep.diffs:
            severity_style = {
                Severity.ERROR: "[bold red]ERROR[/bold red]",
                Severity.WARNING: "[yellow]WARN[/yellow]",
                Severity.INFO: "[dim]INFO[/dim]",
            }.get(diff.severity, diff.severity.value)
            console.print(f"    {severity_style}  {diff.message}")

    if report.drift_score == 0:
        console.print("\n[bold green]All endpoints are in sync.[/bold green]")
    else:
        console.print(
            f"\n[bold red]{s.drifted + s.missing_in_spec + s.missing_in_code} "
            "issue(s) found.[/bold red]"
        )
