"""Search commands for Pharos CLI."""

import json
from pathlib import Path
from typing import Optional

import typer
from rich import print

from pharos_cli.client.search_client import SearchClient
from pharos_cli.formatters import get_formatter
from pharos_cli.utils.console import get_console

search_app = typer.Typer(
    name="search",
    help="Search for resources in your knowledge base",
    add_completion=False,
)


@search_app.callback()
def search_callback():
    """Search for resources in your knowledge base."""
    pass


def get_search_client() -> SearchClient:
    """Get a search client instance.

    Returns:
        SearchClient instance.
    """
    from pharos_cli.client import SyncAPIClient

    api_client = SyncAPIClient()
    return SearchClient(api_client)


def format_search_results(
    results: list,
    output_format: str = "table",
) -> str:
    """Format search results for output.

    Args:
        results: List of search result dictionaries.
        output_format: Output format (table, json, csv, tree, quiet).

    Returns:
        Formatted string.
    """
    if output_format == "quiet":
        # Return just the IDs, one per line
        return "\n".join(str(r.get("id", "")) for r in results)

    formatter = get_formatter(output_format)
    return formatter.format_list(results)


@search_app.command("search")
def search(
    query: str = typer.Argument(
        ...,
        help="Search query",
    ),
    semantic: bool = typer.Option(
        False,
        "--semantic",
        "-s",
        help="Use semantic search instead of keyword search",
    ),
    hybrid: bool = typer.Option(
        False,
        "--hybrid",
        "-h",
        help="Use hybrid search combining keyword and semantic",
    ),
    weight: Optional[float] = typer.Option(
        None,
        "--weight",
        "-w",
        help="Weight for hybrid search (0.0-1.0, where 1.0 is fully semantic)",
    ),
    resource_type: Optional[str] = typer.Option(
        None,
        "--type",
        "-t",
        help="Filter by resource type (code, paper, documentation, etc.)",
    ),
    language: Optional[str] = typer.Option(
        None,
        "--language",
        "-l",
        help="Filter by programming language or natural language",
    ),
    min_quality: Optional[float] = typer.Option(
        None,
        "--min-quality",
        "-q",
        help="Minimum quality score filter (0.0-1.0)",
    ),
    max_quality: Optional[float] = typer.Option(
        None,
        "--max-quality",
        help="Maximum quality score filter (0.0-1.0)",
    ),
    tags: Optional[str] = typer.Option(
        None,
        "--tags",
        help="Filter by tags (comma-separated list)",
    ),
    collection_id: Optional[int] = typer.Option(
        None,
        "--collection",
        "-c",
        help="Filter by collection ID",
    ),
    page: int = typer.Option(
        1,
        "--page",
        "-p",
        help="Page number for pagination",
    ),
    per_page: int = typer.Option(
        25,
        "--per-page",
        help="Number of results per page",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Save results to file",
    ),
    format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (table, json, csv, tree, quiet)",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show verbose output with more details",
    ),
) -> None:
    """Search for resources in your knowledge base.

    Examples:
        pharos search "machine learning"
        pharos search "neural networks" --semantic
        pharos search "python" --type code --language python
        pharos search "AI" --hybrid --weight 0.7
        pharos search "documentation" --min-quality 0.8 --output results.json
    """
    console = get_console()

    # Determine search type
    if hybrid:
        search_type = "hybrid"
    elif semantic:
        search_type = "semantic"
    else:
        search_type = "keyword"

    # Validate weight
    if weight is not None and not hybrid:
        print(
            "[yellow]Warning: --weight is only used with --hybrid search, ignoring[/yellow]"
        )
        weight = None

    if weight is not None and (weight < 0.0 or weight > 1.0):
        print("[red]Error: --weight must be between 0.0 and 1.0[/red]")
        raise typer.Exit(1)

    # Parse tags
    tag_list = None
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    # Calculate skip for pagination
    skip = (page - 1) * per_page

    try:
        client = get_search_client()

        # Perform search
        result = client.search(
            query=query,
            search_type=search_type,
            weight=weight,
            resource_type=resource_type,
            language=language,
            min_quality=min_quality,
            max_quality=max_quality,
            tags=tag_list,
            collection_id=collection_id,
            skip=skip,
            limit=per_page,
        )

        # Convert results to list of dicts
        results = []
        for item in result.items:
            if hasattr(item, "dict"):
                item_dict = item.dict()
            elif hasattr(item, "model_dump"):
                item_dict = item.model_dump()
            else:
                item_dict = dict(item)

            # Add verbose details if requested
            if verbose:
                item_dict["_verbose"] = True

            results.append(item_dict)

        # Format output
        output_str = format_search_results(results, format)

        # Print results
        if output_str.strip():
            console.print(output_str)

        # Print summary
        if result.total > 0:
            console.print(
                f"\n[dim]Found {result.total} result(s), showing page {page} of "
                f"{(result.total + per_page - 1) // per_page}[/dim]"
            )

        # Save to file if requested
        if output:
            if format == "json":
                output_content = json.dumps(
                    {
                        "query": query,
                        "search_type": search_type,
                        "total": result.total,
                        "page": page,
                        "per_page": per_page,
                        "results": results,
                    },
                    indent=2,
                    default=str,
                )
            elif format == "quiet":
                output_content = "\n".join(str(r.get("id", "")) for r in results)
            else:
                output_content = output_str

            output.write_text(output_content)
            console.print(f"\n[green]Results saved to {output}[/green]")

    except Exception as e:
        console.print(f"[red]Error performing search: {e}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app = typer.Typer()
    app.add_typer(search_app, name="search")
    app()