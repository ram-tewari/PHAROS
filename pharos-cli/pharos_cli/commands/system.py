"""System commands for Pharos CLI - health, stats, version, and system management."""

import json
from pathlib import Path
from typing import Optional

import typer
from rich import print
from rich.panel import Panel
from rich.table import Table
from rich.json import JSON
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn
from rich.text import Text
from rich.style import Style
from rich.color import Color

from pharos_cli.client.system_client import SystemClient
from pharos_cli.formatters import get_formatter
from pharos_cli.utils.console import get_console
from pharos_cli.utils.helpers import format_number, format_score
from pharos_cli.version import __version__

system_app = typer.Typer(
    name="system",
    help="System management commands for Pharos CLI",
    add_completion=False,
)


@system_app.callback()
def system_callback():
    """System management commands for Pharos CLI."""
    pass


def get_system_client() -> SystemClient:
    """Get a system client instance.

    Returns:
        SystemClient instance.
    """
    from pharos_cli.client import SyncAPIClient

    api_client = SyncAPIClient()
    return SystemClient(api_client)


def get_health_status_color(status: str) -> str:
    """Get color for health status.

    Args:
        status: Health status string.

    Returns:
        Color string for Rich.
    """
    status_lower = status.lower() if status else ""
    if status_lower in ("healthy", "ok", "ready", "up"):
        return "green"
    elif status_lower in ("degraded", "warning"):
        return "yellow"
    elif status_lower in ("unhealthy", "error", "down", "failed"):
        return "red"
    else:
        return "blue"


@system_app.command()
def health(
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show detailed health information",
    ),
    output_format: str = typer.Option(
        "panel",
        "--format",
        "-f",
        help="Output format (panel, json, table)",
    ),
) -> None:
    """Check system health.

    Examples:
        pharos health
        pharos health --verbose
        pharos health --format json
    """
    console = get_console()

    try:
        client = get_system_client()
        health_data = client.health_check()

        # Handle error response from health_check
        if isinstance(health_data, dict) and health_data.get("status") == "error":
            status = "unhealthy"
            status_color = "red"
            message = health_data.get("message", "Unknown error")
        else:
            status = health_data.get("status", "unknown")
            status_color = get_health_status_color(status)
            message = health_data.get("message", "")

        if output_format == "json":
            print(JSON(json.dumps(health_data, indent=2, default=str)).text)
            return

        if output_format == "table":
            table = Table(title="Health Status")
            table.add_column("Component", style="bold")
            table.add_column("Status", justify="center")
            table.add_column("Details")

            # Add main status row
            table.add_row(
                "Overall",
                f"[{status_color}]{status.upper()}[/{status_color}]",
                message or "System is running",
            )

            # Add component details if available
            components = health_data.get("components", health_data.get("checks", {}))
            if isinstance(components, dict):
                for component, component_status in components.items():
                    if isinstance(component_status, dict):
                        comp_status = component_status.get("status", "unknown")
                        comp_color = get_health_status_color(comp_status)
                        comp_message = component_status.get("message", "")
                        table.add_row(
                            component,
                            f"[{comp_color}]{comp_status.upper()}[/{comp_color}]",
                            comp_message,
                        )
                    else:
                        comp_color = get_health_status_color(str(component_status))
                        table.add_row(
                            component,
                            f"[{comp_color}]{str(component_status).upper()}[/{comp_color}]",
                            "",
                        )

            console.print(table)
            return

        # Panel format (default)
        if verbose:
            # Detailed health panel
            details = []
            for key, value in health_data.items():
                if key not in ("status", "message"):
                    if isinstance(value, dict):
                        details.append(f"[bold]{key}:[/bold]")
                        for k, v in value.items():
                            details.append(f"  {k}: {v}")
                    else:
                        details.append(f"[bold]{key}:[/bold] {value}")

            panel = Panel(
                f"[bold]Status:[/bold] [green]{status.upper()}[/green]\n\n" +
                "\n".join(details),
                title="System Health",
                border_style=status_color,
            )
        else:
            # Simple status panel
            status_text = Text()
            status_text.append("System Status: ", style="bold")
            status_text.append(status.upper(), style=f"bold {status_color}")

            panel = Panel(
                status_text,
                title="System Health",
                border_style=status_color,
            )

        console.print(panel)

    except Exception as e:
        console.print(f"[red]Error checking health: {e}[/red]")
        raise typer.Exit(1)


@system_app.command()
def stats(
    output_format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (json, table, quiet)",
    ),
) -> None:
    """Show system statistics.

    Examples:
        pharos stats
        pharos stats --format json
    """
    console = get_console()

    try:
        client = get_system_client()
        stats_data = client.get_stats()

        if output_format == "json":
            print(JSON(json.dumps(stats_data, indent=2, default=str)).text)
            return

        if output_format == "quiet":
            # Just print key numbers
            if "resource_count" in stats_data:
                print(stats_data["resource_count"])
            return

        # Table format
        table = Table(title="System Statistics")
        table.add_column("Metric", style="bold")
        table.add_column("Value", justify="right")

        # Define common stats to display
        stats_mapping = [
            ("Resource Count", stats_data.get("resource_count", 0)),
            ("Collection Count", stats_data.get("collection_count", 0)),
            ("Annotation Count", stats_data.get("annotation_count", 0)),
            ("Graph Nodes", stats_data.get("graph_node_count", 0)),
            ("Graph Edges", stats_data.get("graph_edge_count", 0)),
            ("Database Size (MB)", stats_data.get("database_size_mb", 0)),
            ("Uptime (seconds)", stats_data.get("uptime_seconds", 0)),
        ]

        for metric, value in stats_mapping:
            if isinstance(value, float):
                if value >= 1:
                    value = f"{value:.1f}"
                else:
                    value = f"{value:.2f}"
            else:
                value = format_number(value)
            table.add_row(metric, value)

        console.print(table)

        # Show additional info if available
        if stats_data.get("last_activity"):
            console.print(f"\n[dim]Last activity: {stats_data['last_activity']}[/dim]")

    except Exception as e:
        console.print(f"[red]Error getting stats: {e}[/red]")
        raise typer.Exit(1)


@system_app.command()
def version(
    extended: bool = typer.Option(
        False,
        "--extended",
        "-e",
        help="Show extended version information",
    ),
) -> None:
    """Show version information.

    Examples:
        pharos version
        pharos version --extended
    """
    console = get_console()

    try:
        client = get_system_client()
        version_data = client.get_version()

        # CLI version
        console.print(f"[bold]Pharos CLI[/bold] version [cyan]{__version__}[/cyan]")

        # Backend version
        backend_version = version_data.get("version", "unknown")
        console.print(f"[bold]Pharos Backend[/bold] version [cyan]{backend_version}[/cyan]")

        if extended:
            console.print("\n[bold]Extended Information:[/bold]")

            table = Table()
            table.add_column("Component", style="bold")
            table.add_column("Version")

            # Add all version info
            for key, value in version_data.items():
                if key != "version":
                    table.add_row(key, str(value))

            console.print(table)

    except Exception as e:
        console.print(f"[red]Error getting version: {e}[/red]")
        # Still show CLI version even if backend fails
        console.print(f"\n[bold]Pharos CLI[/bold] version [cyan]{__version__}[/cyan]")


@system_app.command()
def backup(
    output: Path = typer.Option(
        ...,
        "--output",
        "-o",
        help="Output file path for backup",
        dir_okay=False,
        writable=True,
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show verbose output",
    ),
) -> None:
    """Create a database backup.

    Examples:
        pharos backup --output backup.json
        pharos backup --output backup.json --verbose
    """
    console = get_console()

    # Ensure output directory exists
    output.parent.mkdir(parents=True, exist_ok=True)

    try:
        client = get_system_client()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            task = progress.add_task("Creating backup...", total=1)

            result = client.backup_create(output)

            progress.update(task, completed=1)

        console.print(f"[green]Backup created successfully![/green]")
        console.print(f"  File: {result['file_path']}")
        console.print(f"  Size: {format_number(result['size_bytes'])} bytes")

        if verbose:
            console.print(f"\n[dim]Backup details:[/dim]")
            console.print(f"  Status: {result.get('status', 'success')}")

    except Exception as e:
        console.print(f"[red]Error creating backup: {e}[/red]")
        raise typer.Exit(1)


@system_app.command()
def restore(
    backup_file: Path = typer.Argument(
        ...,
        help="Backup file to restore from",
        exists=True,
        readable=True,
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Skip confirmation prompt",
    ),
) -> None:
    """Restore database from backup.

    Examples:
        pharos restore backup.json
        pharos restore backup.json --force
    """
    console = get_console()

    # Confirmation prompt
    if not force:
        console.print(Panel(
            f"[yellow]Are you sure you want to restore from backup?[/yellow]\n\n"
            f"  File: {backup_file}\n"
            f"  Size: {format_number(backup_file.stat().st_size)} bytes\n\n"
            f"[red]This will overwrite all existing data![/red]",
            title="Confirm Restore",
            border_style="red",
        ))

        if not typer.confirm("Do you want to continue?"):
            console.print("[yellow]Restore cancelled.[/yellow]")
            raise typer.Exit(0)

    try:
        client = get_system_client()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            task = progress.add_task("Restoring backup...", total=1)

            result = client.restore(backup_file)

            progress.update(task, completed=1)

        console.print(f"[green]Database restored successfully![/green]")

    except Exception as e:
        console.print(f"[red]Error restoring backup: {e}[/red]")
        raise typer.Exit(1)


@system_app.command()
def verify_backup(
    backup_file: Path = typer.Argument(
        ...,
        help="Backup file to verify",
        exists=True,
        readable=True,
    ),
) -> None:
    """Verify a backup file.

    Examples:
        pharos verify-backup backup.json
    """
    console = get_console()

    try:
        client = get_system_client()
        result = client.backup_verify(backup_file)

        if result["valid"]:
            console.print(f"[green]Backup is valid![/green]")
            console.print(f"  File: {result['file_path']}")
            console.print(f"  Size: {format_number(result['size_bytes'])} bytes")
            console.print(f"  Format: {result.get('format', 'unknown')}")
        else:
            console.print(f"[red]Backup verification failed![/red]")
            console.print(f"  File: {result['file_path']}")
            console.print(f"  Error: {result['error']}")

    except Exception as e:
        console.print(f"[red]Error verifying backup: {e}[/red]")
        raise typer.Exit(1)


@system_app.command()
def cache_clear(
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Skip confirmation prompt",
    ),
) -> None:
    """Clear the system cache.

    Examples:
        pharos cache clear
        pharos cache clear --force
    """
    console = get_console()

    # Confirmation prompt
    if not force:
        console.print(Panel(
            f"[yellow]Are you sure you want to clear the cache?[/yellow]\n\n"
            f"[red]This may slow down subsequent operations until the cache rebuilds.[/red]",
            title="Confirm Cache Clear",
            border_style="yellow",
        ))

        if not typer.confirm("Do you want to continue?"):
            console.print("[yellow]Cache clear cancelled.[/yellow]")
            raise typer.Exit(0)

    try:
        client = get_system_client()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            task = progress.add_task("Clearing cache...", total=1)

            result = client.clear_cache()

            progress.update(task, completed=1)

        console.print(f"[green]Cache cleared successfully![/green]")

    except Exception as e:
        console.print(f"[red]Error clearing cache: {e}[/red]")
        raise typer.Exit(1)


@system_app.command()
def migrate(
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Skip confirmation prompt for database migrations",
    ),
) -> None:
    """Run database migrations.

    Examples:
        pharos migrate
        pharos migrate --force
    """
    console = get_console()

    # Confirmation prompt
    if not force:
        console.print(Panel(
            f"[yellow]Are you sure you want to run database migrations?[/yellow]\n\n"
            f"[red]This may take a while and could lock the database temporarily.[/red]",
            title="Confirm Migration",
            border_style="yellow",
        ))

        if not typer.confirm("Do you want to continue?"):
            console.print("[yellow]Migration cancelled.[/yellow]")
            raise typer.Exit(0)

    try:
        client = get_system_client()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            task = progress.add_task("Running migrations...", total=1)

            result = client.run_migrations()

            progress.update(task, completed=1)

        console.print(f"[green]Migrations completed successfully![/green]")

        if result.get("migrations_applied"):
            console.print(f"  Migrations applied: {result['migrations_applied']}")

    except Exception as e:
        console.print(f"[red]Error running migrations: {e}[/red]")
        raise typer.Exit(1)