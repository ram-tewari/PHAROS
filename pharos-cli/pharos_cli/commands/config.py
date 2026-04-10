"""Configuration commands for Pharos CLI."""

import typer
from typing import Optional
from pathlib import Path

from rich import print
from rich.panel import Panel
from rich.table import Table

from pharos_cli.config.settings import (
    load_config,
    save_config,
    get_config_path,
    get_config_dir,
    Config,
    Profile,
    apply_env_overrides,
)
from pharos_cli.utils.console import get_console

config_app = typer.Typer(
    name="config",
    help="Configuration commands for Pharos CLI",
)


@config_app.callback()
def config_callback():
    """Configuration commands for Pharos CLI."""
    pass


def prompt_api_url() -> str:
    """Prompt for API URL."""
    console = get_console()
    console.print("\n[bold]API Configuration[/bold]")
    console.print("Enter your Pharos API URL (or press Enter for default):")
    console.print("  [dim]Default: http://localhost:8000[/dim]")
    console.print("  [dim]Production: https://pharos.onrender.com[/dim]")

    url = typer.prompt("API URL", default="http://localhost:8000")
    return url.strip()


def prompt_api_key() -> Optional[str]:
    """Prompt for API key."""
    console = get_console()
    console.print("\n[bold]Authentication[/bold]")
    console.print("Enter your API key (leave empty to skip for now):")
    console.print("  [dim]Get your API key from: https://pharos.onrender.com/settings/api-keys[/dim]")

    api_key = typer.prompt("API Key", default=None, hide_input=True)
    return api_key.strip() if api_key else None


def prompt_timeout() -> int:
    """Prompt for timeout."""
    console = get_console()
    console.print("\n[bold]Timeout Settings[/bold]")
    console.print("Enter request timeout in seconds (default: 30):")

    timeout = typer.prompt("Timeout", default=30, type=int)
    return max(5, timeout)


def prompt_output_format() -> str:
    """Prompt for output format."""
    console = get_console()
    console.print("\n[bold]Output Preferences[/bold]")
    console.print("Choose output format:")
    console.print("  1. [cyan]table[/cyan] - Rich table output (default)")
    console.print("  2. [cyan]json[/cyan] - JSON output")
    console.print("  3. [cyan]csv[/cyan] - CSV output")
    console.print("  4. [cyan]tree[/cyan] - Tree output for hierarchical data")

    choice = typer.prompt("Choice", default="1", type=int)
    formats = ["table", "json", "csv", "tree"]
    return formats[min(max(choice - 1, 0), 3)]


def prompt_color() -> str:
    """Prompt for color preference."""
    console = get_console()
    console.print("\n[bold]Color Output[/bold]")
    console.print("Choose color preference:")
    console.print("  1. [cyan]auto[/cyan] - Auto-detect terminal capability (default)")
    console.print("  2. [cyan]always[/cyan] - Always use colors")
    console.print("  3. [cyan]never[/cyan] - Never use colors")

    choice = typer.prompt("Choice", default="1", type=int)
    options = ["auto", "always", "never"]
    return options[min(max(choice - 1, 0), 2)]


@config_app.command("init")
def init_config(
    url: Optional[str] = typer.Option(
        None,
        "--url",
        "-u",
        help="API URL to use",
    ),
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key",
        "-k",
        help="API key for authentication",
    ),
    non_interactive: bool = typer.Option(
        False,
        "--non-interactive",
        "-n",
        help="Run in non-interactive mode (use defaults or provided options)",
    ),
) -> None:
    """Initialize Pharos CLI configuration."""
    console = get_console()

    config_path = get_config_path()

    # Check if config already exists
    if config_path.exists():
        console.print("[yellow]Configuration already exists.[/yellow]")
        console.print(f"  Config file: {config_path}")
        console.print("  Use 'pharos config show' to view current configuration")
        console.print("  Use 'pharos config edit' to modify (not implemented yet)")
        raise typer.Exit(0)

    # Load or create config
    config = load_config()

    # Apply environment variable overrides
    config = apply_env_overrides(config)

    if non_interactive:
        # Non-interactive mode: use provided values or defaults
        if url:
            profile = config.get_active_profile()
            profile.api_url = url
        if api_key:
            profile = config.get_active_profile()
            profile.api_key = api_key
    else:
        # Interactive mode: prompt for values
        api_url = url or prompt_api_url()
        profile = config.get_active_profile()
        profile.api_url = api_url

        timeout = prompt_timeout()
        profile.timeout = timeout

        output_format = prompt_output_format()
        config.output.format = output_format

        color_pref = prompt_color()
        config.output.color = color_pref

        # API key is optional
        key_input = api_key or prompt_api_key()
        if key_input:
            profile.api_key = key_input

    # Save config
    save_config(config)

    console.print("\n[green]✓ Configuration initialized successfully![/green]")
    console.print(f"  Config file: {config_path}")
    console.print(f"  Active profile: {config.active_profile}")
    console.print(f"  API URL: {config.get_active_profile().api_url}")

    if config.get_active_profile().api_key:
        console.print("  API key: [green]Set[/green]")
    else:
        console.print("  API key: [yellow]Not set[/yellow]")
        console.print("\n[bold]Next steps:[/bold]")
        console.print("  1. Run 'pharos auth login --api-key YOUR_KEY' to authenticate")
        console.print("  2. Run 'pharos health' to verify connection")


@config_app.command("show")
def show_config(
    profile: Optional[str] = typer.Option(
        None,
        "--profile",
        "-p",
        help="Profile to show (default: active profile)",
    ),
    show_api_key: bool = typer.Option(
        False,
        "--show-api-key",
        "-s",
        help="Show API key (use with caution - sensitive)",
    ),
    output_format: str = typer.Option(
        "rich",
        "--format",
        "-f",
        help="Output format: rich, json, yaml",
    ),
) -> None:
    """Show current configuration."""
    console = get_console()

    # Load config
    config = load_config()

    # Apply environment variable overrides
    config = apply_env_overrides(config)

    # Get profile to show
    profile_name = profile or config.active_profile
    profile_config = config.get_profile(profile_name)

    if profile_config is None:
        console.print(f"[red]Error:[/red] Profile '{profile_name}' not found")
        raise typer.Exit(1)

    if output_format == "json":
        import json

        data = {
            "active_profile": config.active_profile,
            "profile": profile_name,
            "api_url": profile_config.api_url,
            "api_key": "***hidden***" if profile_config.api_key and not show_api_key else profile_config.api_key,
            "timeout": profile_config.timeout,
            "verify_ssl": profile_config.verify_ssl,
            "output": {
                "format": config.output.format,
                "color": config.output.color,
                "pager": config.output.pager,
            },
            "behavior": {
                "confirm_destructive": config.behavior.confirm_destructive,
                "show_progress": config.behavior.show_progress,
                "parallel_batch": config.behavior.parallel_batch,
                "max_workers": config.behavior.max_workers,
            },
        }
        console.print(json.dumps(data, indent=2))
        return

    if output_format == "yaml":
        import yaml

        data = {
            "active_profile": config.active_profile,
            "profile": profile_name,
            "api_url": profile_config.api_url,
            "api_key": "***hidden***" if profile_config.api_key and not show_api_key else profile_config.api_key,
            "timeout": profile_config.timeout,
            "verify_ssl": profile_config.verify_ssl,
            "output": config.output.model_dump(),
            "behavior": config.behavior.model_dump(),
        }
        console.print(yaml.dump(data, default_flow_style=False))
        return

    # Rich format (default)
    console.print(f"\n[bold]Pharos CLI Configuration[/bold]")
    console.print(f"  Config file: {get_config_path()}")
    console.print(f"  Active profile: [cyan]{config.active_profile}[/cyan]")
    console.print(f"  Showing profile: [cyan]{profile_name}[/cyan]")

    console.print("\n[bold]API Settings[/bold]")
    table = Table(show_header=False, box=None)
    table.add_row("API URL", profile_config.api_url)
    table.add_row(
        "API Key",
        "[green]Set[/green]" if profile_config.api_key else "[yellow]Not set[/yellow]"
    )
    table.add_row("Timeout", f"{profile_config.timeout}s")
    table.add_row("Verify SSL", "Yes" if profile_config.verify_ssl else "No")
    console.print(table)

    console.print("\n[bold]Output Settings[/bold]")
    table2 = Table(show_header=False, box=None)
    table2.add_row("Format", config.output.format)
    table2.add_row("Color", config.output.color)
    table2.add_row("Pager", config.output.pager)
    console.print(table2)

    console.print("\n[bold]Behavior Settings[/bold]")
    table3 = Table(show_header=False, box=None)
    table3.add_row("Confirm Destructive", "Yes" if config.behavior.confirm_destructive else "No")
    table3.add_row("Show Progress", "Yes" if config.behavior.show_progress else "No")
    table3.add_row("Parallel Batch", "Yes" if config.behavior.parallel_batch else "No")
    table3.add_row("Max Workers", str(config.behavior.max_workers))
    console.print(table3)

    # Show all profiles
    if len(config.profiles) > 1:
        console.print("\n[bold]Available Profiles[/bold]")
        profile_table = Table()
        profile_table.add_column("Name")
        profile_table.add_column("API URL")
        profile_table.add_column("Active")

        for name, prof in config.profiles.items():
            active = "[green]✓[/green]" if name == config.active_profile else ""
            profile_table.add_row(name, prof.api_url, active)

        console.print(profile_table)

    console.print("\n[dim]Tip: Use 'pharos config show --profile NAME' to view a specific profile[/dim]")
    console.print("[dim]Tip: Use 'pharos config show --show-api-key' to display the API key[/dim]")


@config_app.command("path")
def config_path() -> None:
    """Show configuration file path."""
    console = get_console()
    path = get_config_path()
    console.print(str(path))


@config_app.command("dir")
def config_directory() -> None:
    """Show configuration directory path."""
    console = get_console()
    path = get_config_dir()
    console.print(str(path))