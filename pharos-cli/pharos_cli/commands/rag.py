"""RAG (Retrieval-Augmented Generation) commands for Pharos CLI."""

import json
from pathlib import Path
from typing import Optional, List

import typer
from rich import print
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.console import Console

from pharos_cli.client.api_client import get_api_client
from pharos_cli.client.rag_client import RAGClient
from pharos_cli.formatters import get_formatter
from pharos_cli.utils.console import get_console

rag_app = typer.Typer(
    name="ask",
    help="Ask questions and get answers from your knowledge base using RAG",
    add_completion=False,
)


@rag_app.callback()
def rag_callback():
    """Ask questions and get answers from your knowledge base using RAG."""
    pass


def get_rag_client() -> RAGClient:
    """Get a RAGClient instance."""
    from pharos_cli.config.settings import load_config

    config = load_config()
    api_client = get_api_client(config)
    return RAGClient(api_client)


def format_sources(sources: List[dict], output_format: str = "table") -> str:
    """Format sources for output.

    Args:
        sources: List of source dictionaries.
        output_format: Output format (table, json, tree).

    Returns:
        Formatted string.
    """
    if not sources:
        return "No sources found."

    if output_format == "json":
        return json.dumps(sources, indent=2, default=str)

    if output_format == "tree":
        from rich.tree import Tree

        tree = Tree("Sources")
        for source in sources:
            source_tree = tree.add(f"[bold]{source.get('title', 'Unknown')}[/bold]")
            if source.get("score"):
                source_tree.add(f"Score: {source.get('score'):.2f}")
            if source.get("id"):
                source_tree.add(f"ID: {source.get('id')}")
            if source.get("resource_type"):
                source_tree.add(f"Type: {source.get('resource_type')}")
        with Console().capture() as capture:
            Console().print(tree)
        return capture.get()

    # Default to table format
    table = Table(title="Sources")
    table.add_column("Title", style="cyan")
    table.add_column("Score", justify="right", style="green")
    table.add_column("ID", justify="right", style="dim")
    table.add_column("Type", style="dim")

    for source in sources:
        table.add_row(
            source.get("title", "Unknown")[:50] if source.get("title") else "Unknown",
            f"{source.get('score', 0):.2f}" if source.get("score") else "-",
            str(source.get("id", "-")) if source.get("id") else "-",
            source.get("resource_type", "-") if source.get("resource_type") else "-",
        )

    with Console().capture() as capture:
        Console().print(table)
    return capture.get()


# Main ask command using callback
@rag_app.callback(invoke_without_command=True)
def rag_callback(
    ctx: typer.Context,
    question: Optional[str] = typer.Argument(
        None,
        help="The question to ask",
    ),
    show_sources: bool = typer.Option(
        False,
        "--show-sources",
        "-s",
        help="Show source citations",
    ),
    strategy: str = typer.Option(
        "hybrid",
        "--strategy",
        "-t",
        help="Retrieval strategy (hybrid, graphrag, semantic)",
    ),
    collection_id: Optional[int] = typer.Option(
        None,
        "--collection",
        "-c",
        help="Limit search to a specific collection ID",
    ),
    resource_ids: Optional[str] = typer.Option(
        None,
        "--resources",
        "-r",
        help="Comma-separated list of resource IDs to search",
    ),
    max_sources: int = typer.Option(
        5,
        "--max-sources",
        "-m",
        help="Maximum number of sources to return",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Save answer to file",
    ),
    format: str = typer.Option(
        "markdown",
        "--format",
        "-f",
        help="Output format (markdown, text, json)",
    ),
):
    """Ask a question and get an answer from your knowledge base.

    Examples:
        pharos ask "What is gradient descent?"
        pharos ask "Explain neural networks" --show-sources
        pharos ask "How does authentication work?" --strategy graphrag
    """
    # If no question provided and no subcommand, show help
    if question is None:
        if ctx.invoked_subcommand is None:
            # No subcommand and no question - show help
            typer.echo(ctx.get_help())
            raise typer.Exit(0)
        return

    console = get_console()

    # Validate strategy
    valid_strategies = ["hybrid", "graphrag", "semantic"]
    if strategy not in valid_strategies:
        console.print(f"[red]Error:[/red] Invalid strategy '{strategy}'. Valid options: {', '.join(valid_strategies)}")
        raise typer.Exit(1)

    # Parse resource_ids
    parsed_resource_ids = None
    if resource_ids:
        try:
            parsed_resource_ids = [int(rid.strip()) for rid in resource_ids.split(",")]
        except ValueError:
            console.print("[red]Error:[/red] Invalid resource IDs. Use comma-separated integers.")
            raise typer.Exit(1)

    # Validate max_sources
    if max_sources < 1 or max_sources > 20:
        console.print("[red]Error:[/red] --max-sources must be between 1 and 20")
        raise typer.Exit(1)

    try:
        client = get_rag_client()

        # Check health first
        if not client.health_check():
            console.print("[yellow]Warning:[/yellow] RAG service may not be available. Attempting request anyway...")

        result = client.ask(
            question=question,
            show_sources=show_sources,
            strategy=strategy,
            collection_id=collection_id,
            resource_ids=parsed_resource_ids,
            max_sources=max_sources,
        )

        # Format and display answer
        if format == "json":
            answer_data = {
                "answer": result.answer,
                "strategy": result.strategy,
                "confidence": result.confidence,
                "sources": result.sources if show_sources else None,
            }
            output_content = json.dumps(answer_data, indent=2, default=str)
            console.print(output_content)
        elif format == "text":
            output_content = result.answer
            console.print(output_content)
        else:  # markdown
            # Create a nice markdown representation
            md_content = result.answer

            # Check if answer contains code blocks
            if "```" in result.answer:
                console.print(Markdown(result.answer))
            else:
                console.print(Markdown(md_content))

            output_content = md_content

        # Display confidence if available
        if result.confidence is not None:
            confidence_color = "green" if result.confidence >= 0.7 else "yellow" if result.confidence >= 0.4 else "red"
            console.print(f"\n[dim]Confidence:[/dim] [{confidence_color}]{result.confidence:.2f}[/{confidence_color}]")
            console.print(f"[dim]Strategy:[/dim] {result.strategy}")

        # Display sources if requested
        if show_sources and result.sources:
            console.print(f"\n[bold]Sources:[/bold]")
            sources_output = format_sources(result.sources, "table")
            console.print(sources_output)

        # Save to file if requested
        if output:
            if format == "json":
                output_content = json.dumps(
                    {
                        "question": question,
                        "answer": result.answer,
                        "strategy": result.strategy,
                        "confidence": result.confidence,
                        "sources": result.sources if show_sources else None,
                    },
                    indent=2,
                    default=str,
                )
            output.write_text(output_content, encoding="utf-8")
            console.print(f"\n[green]Answer saved to {output}[/green]")

    except Exception as e:
        console.print(f"[red]Error asking question: {e}[/red]")
        raise typer.Exit(1)


@rag_app.command("stream")
def stream_ask(
    question: str = typer.Argument(
        ...,
        help="The question to ask",
    ),
    strategy: str = typer.Option(
        "hybrid",
        "--strategy",
        "-t",
        help="Retrieval strategy (hybrid, graphrag, semantic)",
    ),
    collection_id: Optional[int] = typer.Option(
        None,
        "--collection",
        "-c",
        help="Limit search to a specific collection ID",
    ),
    max_sources: int = typer.Option(
        5,
        "--max-sources",
        "-m",
        help="Maximum number of sources to return",
    ),
) -> None:
    """Ask a question with streaming response.

    Examples:
        pharos ask stream "What is machine learning?"
        pharos ask stream "Explain deep learning" --strategy graphrag
    """
    console = get_console()

    # Validate strategy
    valid_strategies = ["hybrid", "graphrag", "semantic"]
    if strategy not in valid_strategies:
        console.print(f"[red]Error:[/red] Invalid strategy '{strategy}'. Valid options: {', '.join(valid_strategies)}")
        raise typer.Exit(1)

    try:
        client = get_rag_client()

        # Check health first
        if not client.health_check():
            console.print("[yellow]Warning:[/yellow] RAG service may not be available. Attempting request anyway...")

        console.print(f"[dim]Thinking...[/dim]")

        # Stream the response
        answer_chunks = []
        for chunk in client.stream_ask(
            question=question,
            strategy=strategy,
            collection_id=collection_id,
            max_sources=max_sources,
        ):
            answer_chunks.append(chunk)
            console.print(chunk, end="", flush=True)

        console.print()  # New line after streaming

        # Get final response for metadata
        result = client.ask(
            question=question,
            strategy=strategy,
            collection_id=collection_id,
            max_sources=max_sources,
        )

        # Display metadata
        if result.confidence is not None:
            confidence_color = "green" if result.confidence >= 0.7 else "yellow" if result.confidence >= 0.4 else "red"
            console.print(f"\n[dim]Confidence:[/dim] [{confidence_color}]{result.confidence:.2f}[/{confidence_color}]")
            console.print(f"[dim]Strategy:[/dim] {result.strategy}")

    except Exception as e:
        console.print(f"[red]Error streaming answer: {e}[/red]")
        raise typer.Exit(1)


@rag_app.command("sources")
def list_sources(
    question: str = typer.Argument(
        ...,
        help="The question to find sources for",
    ),
    strategy: str = typer.Option(
        "hybrid",
        "--strategy",
        "-t",
        help="Retrieval strategy (hybrid, graphrag, semantic)",
    ),
    collection_id: Optional[int] = typer.Option(
        None,
        "--collection",
        "-c",
        help="Limit search to a specific collection ID",
    ),
    max_sources: int = typer.Option(
        10,
        "--max-sources",
        "-m",
        help="Maximum number of sources to return",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Save sources to file",
    ),
    format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (table, json, tree)",
    ),
) -> None:
    """Find relevant sources for a question without generating an answer.

    Examples:
        pharos ask sources "What is neural networks?"
        pharos ask sources "Python tips" --collection 5 --max-sources 10
        pharos ask sources "Code review" --format json --output sources.json
    """
    console = get_console()

    # Validate strategy
    valid_strategies = ["hybrid", "graphrag", "semantic"]
    if strategy not in valid_strategies:
        console.print(f"[red]Error:[/red] Invalid strategy '{strategy}'. Valid options: {', '.join(valid_strategies)}")
        raise typer.Exit(1)

    try:
        client = get_rag_client()

        result = client.ask(
            question=question,
            show_sources=True,
            strategy=strategy,
            collection_id=collection_id,
            max_sources=max_sources,
        )

        if not result.sources:
            console.print("[yellow]No relevant sources found.[/yellow]")
            return

        # Format and display sources
        sources_output = format_sources(result.sources, format)

        if format == "json":
            output_content = json.dumps(result.sources, indent=2, default=str)
            console.print(sources_output)
        else:
            console.print(sources_output)

        console.print(f"\n[dim]Found {len(result.sources)} sources using {result.strategy} strategy[/dim]")

        # Save to file if requested
        if output:
            if format == "json":
                output_content = json.dumps(result.sources, indent=2, default=str)
            else:
                output_content = sources_output
            output.write_text(output_content, encoding="utf-8")
            console.print(f"\n[green]Sources saved to {output}[/green]")

    except Exception as e:
        console.print(f"[red]Error finding sources: {e}[/red]")
        raise typer.Exit(1)


@rag_app.command("strategies")
def list_strategies() -> None:
    """List available RAG strategies.

    Examples:
        pharos ask strategies
    """
    console = get_console()

    try:
        client = get_rag_client()
        strategies = client.get_available_strategies()

        table = Table(title="Available RAG Strategies")
        table.add_column("Strategy", style="bold cyan")
        table.add_column("Description", style="blue")

        strategy_descriptions = {
            "hybrid": "Combines keyword and semantic search",
            "graphrag": "Uses knowledge graph for retrieval",
            "semantic": "Pure semantic similarity search",
            "parent-child": "Hierarchical chunk retrieval",
        }

        for strategy in strategies:
            description = strategy_descriptions.get(strategy, "Custom retrieval strategy")
            table.add_row(strategy, description)

        console.print(table)

        console.print("\n[dim]Use --strategy option to choose retrieval method[/dim]")

    except Exception as e:
        console.print(f"[red]Error getting strategies: {e}[/red]")
        raise typer.Exit(1)


@rag_app.command("health")
def rag_health() -> None:
    """Check RAG service health.

    Examples:
        pharos ask health
    """
    console = get_console()

    try:
        client = get_rag_client()
        is_healthy = client.health_check()

        if is_healthy:
            console.print("[green]✓ RAG service is healthy[/green]")
        else:
            console.print("[red]✗ RAG service is not available[/red]")
            raise typer.Exit(1)

    except Exception as e:
        console.print(f"[red]Error checking health: {e}[/red]")
        raise typer.Exit(1)