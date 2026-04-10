"""Backup and restore commands for Pharos CLI."""

import json
import time
from pathlib import Path
from typing import Optional

import typer
from rich import print
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn
from rich.console import Console

from pharos_cli.client.system_client import SystemClient
from pharos_cli.client.api_client import get_api_client
from pharos_cli.client.exceptions import APIError, NetworkError
from pharos_cli.config.settings import load_config, apply_env_overrides
from pharos_cli.utils.console import get_console
from pharos_cli.utils.helpers import format_duration, format_number


backup_app = typer.Typer(
    name="backup",
    help="Backup and restore commands for Pharos CLI",
)


@backup_app.callback()
def backup_callback():
    """Backup and restore commands for Pharos CLI."""
    pass


def get_system_client() -> SystemClient:
    """Get a SystemClient instance."""
    config = load_config()
    config = apply_env_overrides(config)
    api_client = get_api_client(config)
    return SystemClient(api_client)


@backup_app.command("create")
def backup_create(
    output: Path = typer.Option(
        ...,
        "--output",
        "-o",
        help="Output file path for the backup",
        dir_okay=False,
        writable=True,
    ),
    format: str = typer.Option(
        "json",
        "--format",
        "-f",
        help="Backup format (json, sql)",
    ),
    verify: bool = typer.Option(
        True,
        "--verify/--no-verify",
        help="Verify the backup file after creation",
    ),
) -> None:
    """Create a backup of the Pharos database.
    
    Examples:
        pharos backup create --output ./backup.json
        pharos backup create --output ./backup.json --format json
        pharos backup create --output ./backup.sql --format sql
        pharos backup create --output ./backup.json --no-verify
    """
    console = get_console()
    start_time = time.time()

    # Validate output file
    if output.exists():
        console.print(f"[red]Error:[/red] Output file already exists: {output}")
        console.print("[yellow]Use a different filename or remove the existing file.[/yellow]")
        raise typer.Exit(1)

    try:
        client = get_system_client()

        # Create backup with progress
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
            console=console,
        ) as progress:
            task = progress.add_task("Creating backup...", total=1)
            
            result = client.backup_create(output)
            progress.update(task, advance=1)

        elapsed_time = time.time() - start_time

        # Verify backup if requested
        verify_result = None
        if verify:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                transient=True,
                console=console,
            ) as progress:
                task = progress.add_task("Verifying backup...", total=1)
                
                verify_result = client.backup_verify(output)
                progress.update(task, advance=1)

            if not verify_result["valid"]:
                console.print(f"[red]Error:[/red] Backup verification failed: {verify_result.get('error')}")
                console.print("[yellow]The backup file may be corrupted.[/yellow]")
                raise typer.Exit(1)

        # Print success message
        if verify_result:
            size_info = f"  Size: [bold]{format_number(verify_result['size_bytes'])} bytes[/bold]\n"
            f"  Format: [bold]{verify_result.get('format', 'unknown')}[/bold]\n"
        else:
            size_info = ""
        
        console.print(Panel(
            f"[green]Backup created successfully![/green]\n\n"
            f"  File: [bold]{output}[/bold]\n"
            f"{size_info}"
            f"  Time: [bold]{format_duration(elapsed_time)}[/bold]",
            title="Backup Complete",
            border_style="green",
        ))

    except APIError as e:
        console.print(f"[red]API Error:[/red] {e.message}")
        raise typer.Exit(1)
    except NetworkError as e:
        console.print(f"[red]Network Error:[/red] {e}")
        raise typer.Exit(1)
    except IOError as e:
        console.print(f"[red]Error:[/red] Could not write backup file: {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@backup_app.command("verify")
def backup_verify(
    backup_file: Path = typer.Argument(
        ...,
        help="Path to the backup file to verify",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    detailed: bool = typer.Option(
        False,
        "--detailed",
        "-d",
        help="Show detailed verification information",
    ),
) -> None:
    """Verify a backup file.
    
    Examples:
        pharos backup verify ./backup.json
        pharos backup verify ./backup.json --detailed
    """
    console = get_console()

    try:
        client = get_system_client()
        result = client.backup_verify(backup_file)

        if result["valid"]:
            console.print(Panel(
                f"[green]Backup file is valid![/green]\n\n"
                f"  File: [bold]{backup_file}[/bold]\n"
                f"  Size: [bold]{format_number(result['size_bytes'])} bytes[/bold]\n"
                f"  Format: [bold]{result.get('format', 'unknown')}[/bold]",
                title="Backup Verified",
                border_style="green",
            ))
        else:
            console.print(Panel(
                f"[red]Backup file verification failed![/red]\n\n"
                f"  File: [bold]{backup_file}[/bold]\n"
                f"  Error: [bold]{result.get('error', 'Unknown error')}[/bold]",
                title="Verification Failed",
                border_style="red",
            ))
            raise typer.Exit(1)

        # Show detailed information if requested
        if detailed and result["valid"]:
            console.print("\n[bold]Detailed Information:[/bold]")
            
            table = Table()
            table.add_column("Property", style="cyan")
            table.add_column("Value", style="white")
            
            table.add_row("File Path", str(backup_file))
            table.add_row("File Size", f"{result['size_bytes']} bytes")
            table.add_row("Format", result.get("format", "unknown"))
            table.add_row("Exists", "Yes" if result["exists"] else "No")
            
            console.print(table)

    except APIError as e:
        console.print(f"[red]API Error:[/red] {e.message}")
        raise typer.Exit(1)
    except NetworkError as e:
        console.print(f"[red]Network Error:[/red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@backup_app.command("restore")
def backup_restore(
    backup_file: Path = typer.Argument(
        ...,
        help="Path to the backup file to restore",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Skip confirmation prompt",
    ),
    verify_before: bool = typer.Option(
        True,
        "--verify/--no-verify",
        help="Verify the backup file before restoring",
    ),
) -> None:
    """Restore the Pharos database from a backup file.
    
    Examples:
        pharos restore ./backup.json
        pharos restore ./backup.json --force
        pharos restore ./backup.json --no-verify
    """
    console = get_console()

    # Verify backup file first if requested
    if verify_before:
        try:
            client = get_system_client()
            verify_result = client.backup_verify(backup_file)

            if not verify_result["valid"]:
                console.print(f"[red]Error:[/red] Backup file is invalid: {verify_result.get('error')}")
                console.print("[yellow]Restoring from an invalid backup may cause data corruption.[/yellow]")
                if not force:
                    if not typer.confirm("Do you want to continue anyway?"):
                        console.print("[yellow]Restore cancelled.[/yellow]")
                        raise typer.Exit(0)
        except Exception as e:
            console.print(f"[yellow]Warning:[/yellow] Could not verify backup: {e}")
            if not force:
                if not typer.confirm("Do you want to continue anyway?"):
                    console.print("[yellow]Restore cancelled.[/yellow]")
                    raise typer.Exit(0)

    # Confirmation prompt
    if not force:
        console.print(Panel(
            f"[yellow]Are you sure you want to restore from this backup?[/yellow]\n\n"
            f"  File: [bold]{backup_file}[/bold]\n"
            f"  Size: [bold]{format_number(backup_file.stat().st_size)} bytes[/bold]\n\n"
            f"[red]WARNING: This will overwrite all existing data![/red]\n"
            f"[red]This action cannot be undone![/red]",
            title="Confirm Restore",
            border_style="red",
        ))

        if not typer.confirm("Do you want to continue?"):
            console.print("[yellow]Restore cancelled.[/yellow]")
            raise typer.Exit(0)

    start_time = time.time()

    try:
        client = get_system_client()

        # Restore with progress
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
            console=console,
        ) as progress:
            task = progress.add_task("Restoring database...", total=1)
            
            result = client.restore(backup_file)
            progress.update(task, advance=1)

        elapsed_time = time.time() - start_time

        # Print success message
        console.print(Panel(
            f"[green]Database restored successfully![/green]\n\n"
            f"  Backup File: [bold]{backup_file}[/bold]\n"
            f"  Time: [bold]{format_duration(elapsed_time)}[/bold]",
            title="Restore Complete",
            border_style="green",
        ))

    except APIError as e:
        console.print(f"[red]API Error:[/red] {e.message}")
        raise typer.Exit(1)
    except NetworkError as e:
        console.print(f"[red]Network Error:[/red] {e}")
        raise typer.Exit(1)
    except IOError as e:
        console.print(f"[red]Error:[/red] Could not read backup file: {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@backup_app.command("info")
def backup_info(
    backup_file: Path = typer.Argument(
        ...,
        help="Path to the backup file",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
) -> None:
    """Show information about a backup file.
    
    Examples:
        pharos backup info ./backup.json
    """
    console = get_console()

    try:
        # Read and parse the backup file
        content = backup_file.read_text(encoding="utf-8")
        file_size = backup_file.stat().st_size

        # Try to parse as JSON
        try:
            data = json.loads(content)
            format_type = "JSON"
            is_json = True
        except json.JSONDecodeError:
            data = None
            format_type = "SQL" if content.strip().upper().startswith("BEGIN") or "CREATE TABLE" in content.upper() else "Unknown"
            is_json = False

        # Create info table
        table = Table(title=f"Backup Information: {backup_file.name}")
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="white")

        table.add_row("File Path", str(backup_file))
        table.add_row("File Size", f"{format_number(file_size)} bytes ({format_number(file_size / 1024)} KB)")
        table.add_row("Format", format_type)
        table.add_row("Last Modified", str(backup_file.stat().st_mtime))

        if is_json:
            # Show JSON structure info
            if isinstance(data, dict):
                table.add_row("Type", "Object (Dictionary)")
                table.add_row("Top-level Keys", str(len(data)))
                table.add_row("Keys", ", ".join(list(data.keys())[:10]))
                if len(data) > 10:
                    table.add_row("", f"... and {len(data) - 10} more")
            elif isinstance(data, list):
                table.add_row("Type", "Array (List)")
                table.add_row("Item Count", str(len(data)))
                if len(data) > 0:
                    if isinstance(data[0], dict):
                        table.add_row("First Item Keys", str(list(data[0].keys())[:10]))
                    else:
                        table.add_row("Item Type", type(data[0]).__name__)

        console.print(table)

    except IOError as e:
        console.print(f"[red]Error:[/red] Could not read backup file: {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


# Alias commands for convenience
backup_app.command("check")(backup_verify)
backup_app.command("validate")(backup_verify)