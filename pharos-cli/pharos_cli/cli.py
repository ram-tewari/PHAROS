"""Main CLI application for Pharos CLI."""

import sys
from typing import Optional

import typer

from pharos_cli.version import __version__
from pharos_cli.utils.console import get_console, set_color_mode
from pharos_cli.utils.color import ColorMode
from pharos_cli.utils.pager import PagerMode, get_pager_manager

# Import command modules directly
from pharos_cli.commands.auth import auth_app
from pharos_cli.commands.config import config_app
from pharos_cli.commands.resource import resource_app
from pharos_cli.commands.collection import collection_app
from pharos_cli.commands.search import search_app
from pharos_cli.commands.graph import graph_app
from pharos_cli.commands.batch import batch_app
from pharos_cli.commands.chat import chat_app
from pharos_cli.commands.recommend import recommend_app
from pharos_cli.commands.annotation import annotation_app
from pharos_cli.commands.quality import quality_app
from pharos_cli.commands.taxonomy import taxonomy_app
from pharos_cli.commands.code import code_app
from pharos_cli.commands.rag import rag_app
from pharos_cli.commands.system import system_app
from pharos_cli.commands.backup import backup_app
from pharos_cli.commands.rules import rules_app

# Global color mode variable
_color_option: ColorMode = ColorMode.AUTO
# Global pager mode variable
_pager_option: PagerMode = PagerMode.AUTO


app = typer.Typer(
    name="pharos",
    help="Pharos CLI - Command-line interface for Pharos knowledge management system",
    add_completion=False,
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)

# Register subcommands
app.add_typer(auth_app)
app.add_typer(config_app)
app.add_typer(resource_app)
app.add_typer(collection_app)
app.add_typer(search_app)
app.add_typer(graph_app)
app.add_typer(batch_app)
app.add_typer(chat_app)
app.add_typer(recommend_app)
app.add_typer(annotation_app)
app.add_typer(quality_app)
app.add_typer(taxonomy_app)
app.add_typer(code_app)
app.add_typer(rag_app)
app.add_typer(system_app)
app.add_typer(backup_app)
app.add_typer(rules_app)


@app.callback()
def main_callback(
    color: str = typer.Option(
        "auto",
        "--color",
        "-c",
        help="Color output: auto, always, never",
        case_sensitive=False,
    ),
    no_color: bool = typer.Option(
        False,
        "--no-color",
        help="Disable color output (equivalent to --color never)",
    ),
    pager: str = typer.Option(
        "auto",
        "--pager",
        "-p",
        help="Pager mode: auto, always, never",
        case_sensitive=False,
    ),
    no_pager: bool = typer.Option(
        False,
        "--no-pager",
        help="Disable pager output (equivalent to --pager never)",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose output",
    ),
) -> None:
    """Pharos CLI - Command-line interface for Pharos knowledge management system."""
    global _color_option, _pager_option
    
    # --no-color takes precedence
    if no_color:
        _color_option = ColorMode.NEVER
    else:
        # Parse color option
        try:
            _color_option = ColorMode(color.lower())
        except ValueError:
            console = get_console()
            console.print(f"[yellow]Warning:[/yellow] Invalid --color value '{color}'. Using 'auto'.")
            _color_option = ColorMode.AUTO
    
    # Apply color mode to console
    set_color_mode(_color_option)
    
    # --no-pager takes precedence
    if no_pager:
        _pager_option = PagerMode.NEVER
    else:
        # Parse pager option
        try:
            _pager_option = PagerMode(pager.lower())
        except ValueError:
            console = get_console()
            console.print(f"[yellow]Warning:[/yellow] Invalid --pager value '{pager}'. Using 'auto'.")
            _pager_option = PagerMode.AUTO
    
    # Apply pager mode to pager manager
    pager_manager = get_pager_manager()
    pager_manager.mode = _pager_option
    
    if verbose:
        console = get_console()
        console.print(f"[dim]Verbose mode enabled[/dim]")


@app.command()
def version() -> None:
    """Show version information."""
    console = get_console()
    console.print(f"[bold]Pharos CLI[/bold] version [cyan]{__version__}[/cyan]")


@app.command("completion")
def completion(
    shell: str = typer.Argument(
        None,
        help="Shell type: bash, zsh, or fish",
    ),
) -> None:
    """Generate shell completion script."""
    from typer.completion import get_completion_script

    if shell:
        try:
            # Validate shell type
            valid_shells = ["bash", "zsh", "fish", "powershell"]
            if shell.lower() not in valid_shells:
                console = get_console()
                console.print(f"[red]Error:[/red] Invalid shell '{shell}'. Valid options: {', '.join(valid_shells)}")
                raise typer.Exit(1)
            
            # Generate completion script
            prog_name = "pharos"
            complete_var = f"_{prog_name.upper()}_COMPLETE"
            completion_script = get_completion_script(
                prog_name=prog_name,
                complete_var=complete_var,
                shell=shell.lower()  # nosec B604: Validated shell type from whitelist
            )
            
            # Print the completion script
            console = get_console()
            console.print(completion_script)
            
        except Exception as e:
            console = get_console()
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)
    else:
        console = get_console()
        console.print("Please specify a shell: bash, zsh, or fish")
        console.print("Example: pharos completion bash")
        console.print("")
        console.print("To install completion, run:")
        console.print("  Bash: pharos completion bash >> ~/.bashrc")
        console.print("  Zsh:  pharos completion zsh >> ~/.zshrc")
        console.print("  Fish: pharos completion fish > ~/.config/fish/completions/pharos.fish")
        raise typer.Exit(0)


@app.command()
def info() -> None:
    """Show terminal and color information."""
    from pharos_cli.utils.color import get_terminal_info
    from pharos_cli.utils.pager import get_pager_manager
    
    console = get_console()
    info = get_terminal_info()
    pager_info = get_pager_manager().get_pager_info()
    
    console.print("[bold]Terminal Information[/bold]")
    console.print(f"  Is TTY: {info['is_tty']}")
    console.print(f"  Is CI Environment: {info['is_ci']}")
    console.print(f"  Supports Color: {info['supports_color']}")
    console.print(f"  TERM: {info['term']}")
    console.print(f"  NO_COLOR set: {info['no_color']}")
    console.print(f"  Current color mode: {_color_option.value}")
    console.print("")
    console.print("[bold]Pager Information[/bold]")
    console.print(f"  Pager Available: {pager_info['pager_available']}")
    console.print(f"  Pager Executable: {pager_info['pager_executable'] or 'None'}")
    console.print(f"  Should Use Pager: {pager_info['should_use_pager']}")
    console.print(f"  Current pager mode: {_pager_option.value}")


if __name__ == "__main__":
    app()
