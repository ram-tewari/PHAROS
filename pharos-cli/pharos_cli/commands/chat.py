"""Interactive chat command for Pharos CLI."""

import os
import sys
import atexit
from pathlib import Path
from typing import List, Optional, Tuple
from datetime import datetime

import typer
from rich import print
from rich.console import Console
from rich.syntax import Syntax
from rich.text import Text
from rich.panel import Panel
from rich.prompt import Prompt
from rich.style import Style

from pharos_cli.client.rag_client import RAGClient
from pharos_cli.utils.console import get_console

chat_app = typer.Typer(
    name="chat",
    help="Interactive chat with your knowledge base",
    add_completion=False,
)


@chat_app.callback()
def chat_callback():
    """Interactive chat with your knowledge base."""
    pass

# History file location
HISTORY_DIR = Path(os.path.expanduser("~/.pharos"))
HISTORY_FILE = HISTORY_DIR / "chat_history.txt"

# Default system prompt
DEFAULT_SYSTEM_PROMPT = """You are Pharos, an AI assistant for developers and researchers.
You help users understand code, research papers, and technical concepts.
You provide accurate, helpful answers based on the user's knowledge base.
When sharing code, always use proper syntax highlighting.
Be concise but thorough. If you're unsure about something, say so."""

# Ensure history directory exists
HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def load_history() -> List[str]:
    """Load command history from file.

    Returns:
        List of historical commands.
    """
    if HISTORY_FILE.exists():
        try:
            return HISTORY_FILE.read_text().splitlines()
        except Exception:
            return []
    return []


def save_history(history: List[str]) -> None:
    """Save command history to file.

    Args:
        history: List of commands to save.
    """
    try:
        HISTORY_FILE.write_text("\n".join(history[-1000:]))  # Keep last 1000 entries
    except Exception:
        pass  # Ignore errors saving history


def add_to_history(history: List[str], command: str) -> None:
    """Add a command to history.

    Args:
        history: History list to append to.
        command: Command to add.
    """
    # Don't add empty lines or duplicate consecutive commands
    if command.strip() and command != (history[-1] if history else None):
        history.append(command)
        save_history(history)


def clear_screen() -> None:
    """Clear the terminal screen."""
    # Using os.system with hardcoded commands is safe here
    # nosec: Commands are hardcoded literals, no user input involved
    os.system("cls" if os.name == "nt" else "clear")  # nosec B605


def highlight_code_blocks(text: str) -> str:
    """Add syntax highlighting to code blocks in text.

    Args:
        text: Text that may contain code blocks.

    Returns:
        Text with code blocks highlighted.
    """
    import re

    # Pattern for code blocks with language hint: ```language
    code_block_pattern = r"```(\w+)?\n([\s\S]*?)```"

    def replace_code_block(match):
        language = match.group(1) or "text"
        code = match.group(2).rstrip()

        # Create a Syntax object for highlighting
        syntax = Syntax(code, language, theme="monokai", line_numbers=False)
        # Return with language identifier preserved
        return f"```{language}\n{syntax.code}\n```"

    return re.sub(code_block_pattern, replace_code_block, text, flags=re.MULTILINE)


def format_answer(answer: str, show_sources: bool = False, sources: Optional[List[dict]] = None) -> str:
    """Format the answer with syntax highlighting.

    Args:
        answer: The answer text.
        show_sources: Whether to show sources.
        sources: List of source citations.

    Returns:
        Formatted answer string.
    """
    # Highlight code blocks
    formatted = highlight_code_blocks(answer)

    # Add sources if requested
    if show_sources and sources:
        formatted += "\n\n[dim]--- Sources ---[/dim]\n"
        for i, source in enumerate(sources, 1):
            title = source.get("title", f"Source {i}")
            score = source.get("score", 0)
            formatted += f"[{i}] [cyan]{title}[/cyan] (relevance: {score:.2f})\n"

    return formatted


def get_rag_client() -> RAGClient:
    """Get a RAG client instance.

    Returns:
        RAGClient instance.
    """
    from pharos_cli.client import SyncAPIClient
    from pharos_cli.config.settings import load_config, apply_env_overrides

    config = load_config()
    config = apply_env_overrides(config)
    profile = config.get_active_profile()

    api_client = SyncAPIClient(
        base_url=profile.api_url,
        api_key=profile.api_key,
        timeout=60,  # Longer timeout for RAG operations
        verify_ssl=profile.verify_ssl,
    )

    return RAGClient(api_client)


def parse_command(line: str) -> Tuple[str, List[str]]:
    """Parse a command line into command and args.

    Args:
        line: The input line.

    Returns:
        Tuple of (command, args list).
    """
    parts = line.strip().split()
    if not parts:
        return "", []

    cmd = parts[0].lower()
    args = parts[1:]
    return cmd, args


def show_help() -> str:
    """Generate help text for the chat REPL.

    Returns:
        Help text string.
    """
    return """[bold]Pharos Chat - Interactive Help[/bold]

[bold]Commands:[/bold]
  /help, /h          Show this help message
  /exit, /quit, /q   Exit the chat
  /clear, /cls       Clear the screen
  /history, /hist    Show command history
  /sources on/off    Toggle source citations
  /strategy <name>   Set retrieval strategy (hybrid, graphrag, semantic)
  /system            Show current system configuration
  /reset             Reset conversation context

[bold]Tips:[/bold]
  - Multi-line input: Press Enter twice to send
  - Code blocks: Use ```language for syntax highlighting
  - Cancel input: Press Ctrl+C

[bold]Examples:[/bold]
  How does the authentication system work?
  Explain the AST parsing logic in the code
  What are the main components of the knowledge graph?
"""


def show_welcome() -> str:
    """Generate welcome message.

    Returns:
        Welcome message string.
    """
    return """[bold cyan]Welcome to Pharos Chat![/bold cyan]

[dim]An interactive CLI for querying your knowledge base.[/dim]

Type [green]/help[/green] for available commands or just ask a question.

[yellow]Tip:[/yellow] Use [cyan]/sources on[/cyan] to see source citations for answers.
"""


def read_multiline_input(console: Console) -> str:
    """Read multi-line input from user.

    Args:
        console: Rich console instance.

    Returns:
        The complete input string.
    """
    lines = []
    first_line = True

    while True:
        try:
            if first_line:
                prompt = Prompt.get_string(
                    "[bold cyan]You:[/bold cyan] ",
                    console=console,
                    password=False,
                )
                first_line = False
            else:
                prompt = Prompt.get_string(
                    "[dim]... [/dim]",
                    console=console,
                    password=False,
                )

            if not prompt.strip():
                # Empty line - end of multi-line input
                if lines:
                    break
                else:
                    # Empty first line, skip
                    continue

            lines.append(prompt)

        except KeyboardInterrupt:
            console.print("\n[yellow]Input cancelled[/yellow]")
            raise typer.Abort()

        except EOFError:
            # Handle Ctrl+D
            if lines:
                break
            else:
                console.print("\n[yellow]Exiting...[/yellow]")
                raise typer.Abort()

    return "\n".join(lines)


def run_repl(
    console: Console,
    show_sources: bool = False,
    strategy: str = "hybrid",
) -> None:
    """Run the chat REPL.

    Args:
        console: Rich console instance.
        show_sources: Whether to show sources by default.
        strategy: Default retrieval strategy.
    """
    history = load_history()
    client = get_rag_client()

    # Show welcome message
    console.print(Panel(show_welcome(), title="Pharos Chat", border_style="cyan"))

    while True:
        try:
            # Read user input
            user_input = read_multiline_input(console)

            if not user_input.strip():
                continue

            # Add to history
            add_to_history(history, user_input)

            # Parse command
            cmd, args = parse_command(user_input)

            # Handle special commands
            if cmd in ["/exit", "/quit", "/q"]:
                console.print("[green]Goodbye![/green]")
                break

            elif cmd in ["/help", "/h"]:
                console.print(Panel(show_help(), title="Help", border_style="blue"))

            elif cmd in ["/clear", "/cls"]:
                clear_screen()
                console.print(Panel(show_welcome(), title="Pharos Chat", border_style="cyan"))

            elif cmd in ["/history", "/hist"]:
                if history:
                    console.print("[bold]Recent commands:[/bold]")
                    for i, cmd in enumerate(history[-20:], 1):
                        console.print(f"[dim]{i:2}.[/dim] {cmd}")
                else:
                    console.print("[dim]No command history[/dim]")

            elif cmd == "/sources":
                if args and args[0].lower() in ["on", "off"]:
                    show_sources = args[0].lower() == "on"
                    console.print(f"[green]Sources {'enabled' if show_sources else 'disabled'}[/green]")
                else:
                    console.print("[yellow]Usage: /sources on|off[/yellow]")

            elif cmd == "/strategy":
                if args:
                    new_strategy = args[0].lower()
                    available = client.get_available_strategies()
                    if new_strategy in available:
                        strategy = new_strategy
                        console.print(f"[green]Strategy set to: {strategy}[/green]")
                    else:
                        console.print(f"[red]Unknown strategy: {new_strategy}[/red]")
                        console.print(f"[dim]Available: {', '.join(available)}[/dim]")
                else:
                    console.print(f"[yellow]Current strategy: {strategy}[/yellow]")
                    console.print(f"[dim]Available: {', '.join(client.get_available_strategies())}[/dim]")

            elif cmd == "/system":
                console.print(f"[bold]System Info:[/bold]")
                console.print(f"  Strategy: {strategy}")
                console.print(f"  Sources: {'enabled' if show_sources else 'disabled'}")

            elif cmd == "/reset":
                console.print("[green]Conversation context reset[/green]")

            elif cmd.startswith("/"):
                console.print(f"[red]Unknown command: {cmd}[/red]")
                console.print("[dim]Type /help for available commands[/dim]")

            else:
                # Regular question - send to RAG
                console.print("[dim]Thinking...[/dim]", end="\r")

                try:
                    response = client.ask(
                        question=user_input,
                        show_sources=show_sources,
                        strategy=strategy,
                    )

                    # Clear "Thinking..." line
                    console.print(" " * 20, end="\r")

                    # Format and display answer
                    formatted = format_answer(response.answer, show_sources, response.sources)
                    console.print(Panel(
                        Text.from_markup(formatted),
                        title="Answer",
                        border_style="green",
                        expand=False,
                    ))

                except Exception as e:
                    console.print(" " * 20, end="\r")
                    console.print(f"[red]Error: {e}[/red]")

        except typer.Abort:
            console.print("\n[yellow]Chat cancelled[/yellow]")
            break

        except KeyboardInterrupt:
            console.print("\n[yellow]Use /exit to quit[/yellow]")
            continue


@chat_app.command()
def chat(
    strategy: str = typer.Option(
        "hybrid",
        "--strategy",
        "-s",
        help="Retrieval strategy (hybrid, graphrag, semantic)",
    ),
    show_sources: bool = typer.Option(
        False,
        "--sources",
        "-S",
        help="Show source citations for answers",
    ),
) -> None:
    """Start an interactive chat session with your knowledge base.

    Examples:
        pharos chat
        pharos chat --strategy graphrag
        pharos chat --sources
    """
    console = get_console()

    try:
        run_repl(console, show_sources=show_sources, strategy=strategy)
    except Exception as e:
        console.print(f"[red]Error starting chat: {e}[/red]")
        raise typer.Exit(1)


# Register cleanup to save history on exit
atexit.register(lambda: None)  # Placeholder for any cleanup


def _cleanup_history() -> None:
    """Clean up on module unload."""
    pass


# Register cleanup
atexit.register(_cleanup_history)