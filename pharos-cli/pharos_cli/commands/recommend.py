"""Recommendation commands for Pharos CLI."""

import json
from pathlib import Path
from typing import Optional

import typer
from rich import print
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown

from pharos_cli.client.api_client import get_api_client
from pharos_cli.client.recommendation_client import RecommendationClient
from pharos_cli.formatters import get_formatter
from pharos_cli.utils.console import get_console
from pharos_cli.utils.helpers import format_score

recommend_app = typer.Typer(
    name="recommend",
    help="Get recommendations for resources",
    add_completion=False,
)


@recommend_app.callback()
def recommend_callback():
    """Get recommendations for resources."""
    pass


def get_recommendation_client() -> RecommendationClient:
    """Get a RecommendationClient instance."""
    from pharos_cli.config.settings import load_config

    config = load_config()
    api_client = get_api_client(config)
    return RecommendationClient(api_client)


def format_recommendations(
    recommendations: list,
    output_format: str = "table",
    include_scores: bool = True,
) -> str:
    """Format recommendations for output.

    Args:
        recommendations: List of recommendation dictionaries.
        output_format: Output format (table, json, csv, tree, quiet).
        include_scores: Whether to include recommendation scores.

    Returns:
        Formatted string.
    """
    if output_format == "quiet":
        # Return just the IDs, one per line
        return "\n".join(str(r.get("id", "")) for r in recommendations)

    # Add score formatting for display
    display_items = []
    for item in recommendations:
        display_item = dict(item)
        if include_scores and "score" in display_item:
            display_item["score"] = format_score(display_item["score"])
        display_items.append(display_item)

    formatter = get_formatter(output_format)
    return formatter.format_list(display_items)


@recommend_app.command()
def for_user(
    user_id: int = typer.Argument(
        ...,
        help="User ID to get recommendations for",
    ),
    limit: int = typer.Option(
        10,
        "--limit",
        "-l",
        help="Maximum number of recommendations",
    ),
    page: int = typer.Option(
        1,
        "--page",
        "-p",
        help="Page number for pagination",
    ),
    explain: bool = typer.Option(
        False,
        "--explain",
        "-e",
        help="Include explanation for each recommendation",
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
) -> None:
    """Get recommendations for a specific user.

    Examples:
        pharos recommend for-user 1
        pharos recommend for-user 1 --limit 20
        pharos recommend for-user 1 --explain
        pharos recommend for-user 1 --format json --output recommendations.json
    """
    console = get_console()

    # Calculate skip for pagination
    skip = (page - 1) * limit

    try:
        client = get_recommendation_client()

        result = client.get_user_recommendations(
            user_id=user_id,
            limit=limit,
            skip=skip,
            include_explanation=explain,
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
            results.append(item_dict)

        # Format output
        output_str = format_recommendations(results, format)

        # Print results
        if output_str.strip():
            console.print(output_str)

        # Print summary
        if result.total > 0:
            console.print(
                f"\n[dim]Showing {len(results)} of {result.total} recommendations[/dim]"
            )
            if result.has_more:
                console.print(f"[dim]Use --page {page + 1} for next page[/dim]")

        # Save to file if requested
        if output:
            if format == "json":
                output_content = json.dumps(
                    {
                        "user_id": user_id,
                        "total": result.total,
                        "page": page,
                        "per_page": limit,
                        "recommendations": results,
                    },
                    indent=2,
                    default=str,
                )
            elif format == "quiet":
                output_content = "\n".join(str(r.get("id", "")) for r in results)
            else:
                # For table/CSV/tree formats, create a simple text representation for file
                if results:
                    # Create a simple table-like text representation
                    lines = []
                    # Header
                    if results:
                        headers = list(results[0].keys())
                        # Calculate column widths
                        col_widths = {h: len(h) for h in headers}
                        for item in results:
                            for k, v in item.items():
                                col_widths[k] = max(col_widths[k], len(str(v)))
                        
                        # Header row
                        header_row = " | ".join(h.ljust(col_widths[h]) for h in headers)
                        lines.append(header_row)
                        # Separator
                        separator = "-+-".join("-" * col_widths[h] for h in headers)
                        lines.append(separator)
                        
                        # Data rows
                        for item in results:
                            row = " | ".join(str(item.get(h, "")).ljust(col_widths[h]) for h in headers)
                            lines.append(row)
                    
                    output_content = "\n".join(lines)
                else:
                    output_content = "No recommendations found."

            output.write_text(output_content, encoding="utf-8")
            console.print(f"\n[green]Recommendations saved to {output}[/green]")

    except Exception as e:
        console.print(f"[red]Error getting recommendations: {e}[/red]")
        raise typer.Exit(1)


@recommend_app.command("similar")
def similar_resources(
    resource_id: int = typer.Argument(
        ...,
        help="Resource ID to find similar resources for",
    ),
    limit: int = typer.Option(
        10,
        "--limit",
        "-l",
        help="Maximum number of similar resources",
    ),
    page: int = typer.Option(
        1,
        "--page",
        "-p",
        help="Page number for pagination",
    ),
    explain: bool = typer.Option(
        False,
        "--explain",
        "-e",
        help="Include explanation for each similarity",
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
) -> None:
    """Find resources similar to the specified resource.

    Examples:
        pharos recommend similar 1
        pharos recommend similar 1 --limit 20
        pharos recommend similar 1 --explain
        pharos recommend similar 1 --format json --output similar.json
    """
    console = get_console()

    # Calculate skip for pagination
    skip = (page - 1) * limit

    try:
        client = get_recommendation_client()

        result = client.get_similar_resources(
            resource_id=resource_id,
            limit=limit,
            skip=skip,
            include_explanation=explain,
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
            results.append(item_dict)

        # Format output
        output_str = format_recommendations(results, format)

        # Print results
        if output_str.strip():
            console.print(output_str)

        # Print summary
        if result.total > 0:
            console.print(
                f"\n[dim]Found {result.total} similar resources, showing page {page}[/dim]"
            )
            if result.has_more:
                console.print(f"[dim]Use --page {page + 1} for next page[/dim]")
        else:
            console.print("\n[yellow]No similar resources found.[/yellow]")

        # Save to file if requested
        if output:
            if format == "json":
                output_content = json.dumps(
                    {
                        "resource_id": resource_id,
                        "total": result.total,
                        "page": page,
                        "per_page": limit,
                        "similar_resources": results,
                    },
                    indent=2,
                    default=str,
                )
            elif format == "quiet":
                output_content = "\n".join(str(r.get("id", "")) for r in results)
            else:
                output_content = output_str

            output.write_text(output_content)
            console.print(f"\n[green]Similar resources saved to {output}[/green]")

    except Exception as e:
        console.print(f"[red]Error finding similar resources: {e}[/red]")
        raise typer.Exit(1)


@recommend_app.command("explain")
def explain_recommendation(
    resource_id: int = typer.Argument(
        ...,
        help="Resource ID to explain recommendation for",
    ),
    user_id: Optional[int] = typer.Option(
        None,
        "--user",
        "-u",
        help="User ID for personalized explanation",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Save explanation to file",
    ),
    format: str = typer.Option(
        "markdown",
        "--format",
        "-f",
        help="Output format (markdown, json, text)",
    ),
) -> None:
    """Get explanation for why a resource is recommended.

    Examples:
        pharos recommend explain 1
        pharos recommend explain 1 --user 1
        pharos recommend explain 1 --output explanation.md --format markdown
    """
    console = get_console()

    try:
        client = get_recommendation_client()

        explanation = client.explain_recommendation(
            resource_id=resource_id,
            user_id=user_id,
        )

        # Format output based on format option
        if format == "json":
            output_content = json.dumps(explanation, indent=2, default=str)
            console.print(output_content)
        elif format == "markdown":
            # Create a nice markdown representation
            md_content = f"# Recommendation Explanation\n\n"
            md_content += f"**Resource ID:** {resource_id}\n\n"

            if user_id:
                md_content += f"**User ID:** {user_id}\n\n"

            if "score" in explanation:
                md_content += f"**Recommendation Score:** {format_score(explanation['score'])}\n\n"

            if "reasons" in explanation:
                md_content += "## Reasons\n\n"
                for i, reason in enumerate(explanation["reasons"], 1):
                    md_content += f"{i}. {reason}\n"
                md_content += "\n"

            if "factors" in explanation:
                md_content += "## Factors\n\n"
                md_content += "| Factor | Weight |\n"
                md_content += "|--------|--------|\n"
                for factor, weight in explanation["factors"].items():
                    md_content += f"| {factor} | {weight:.2f} |\n"
                md_content += "\n"

            if "similar_users" in explanation:
                md_content += "## Similar Users\n\n"
                md_content += f"Found {explanation['similar_users']} similar users who engaged with this resource.\n\n"

            if "related_resources" in explanation:
                md_content += "## Related Resources\n\n"
                for related in explanation["related_resources"][:5]:
                    md_content += f"- [{related.get('title', 'Unknown')}](id:{related.get('id', 'N/A')})\n"
                md_content += "\n"

            console.print(Markdown(md_content))
            output_content = md_content
        else:
            # Text format
            output_content = f"Recommendation Explanation for Resource {resource_id}\n"
            output_content += "=" * 50 + "\n\n"

            if user_id:
                output_content += f"User ID: {user_id}\n\n"

            if "score" in explanation:
                output_content += f"Recommendation Score: {format_score(explanation['score'])}\n\n"

            if "reasons" in explanation:
                output_content += "Reasons:\n"
                for i, reason in enumerate(explanation["reasons"], 1):
                    output_content += f"  {i}. {reason}\n"
                output_content += "\n"

            if "factors" in explanation:
                output_content += "Factors:\n"
                for factor, weight in explanation["factors"].items():
                    output_content += f"  - {factor}: {weight:.2f}\n"
                output_content += "\n"

            console.print(output_content)

        # Save to file if requested
        if output:
            output.write_text(output_content)
            console.print(f"\n[green]Explanation saved to {output}[/green]")

    except Exception as e:
        console.print(f"[red]Error getting explanation: {e}[/red]")
        raise typer.Exit(1)


@recommend_app.command("trending")
def trending_resources(
    limit: int = typer.Option(
        10,
        "--limit",
        "-l",
        help="Maximum number of trending resources",
    ),
    time_range: str = typer.Option(
        "week",
        "--time-range",
        "-t",
        help="Time range (day, week, month)",
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
) -> None:
    """Get trending resources.

    Examples:
        pharos recommend trending
        pharos recommend trending --limit 20
        pharos recommend trending --time-range day
        pharos recommend trending --format json --output trending.json
    """
    console = get_console()

    # Validate time_range
    valid_ranges = ["day", "week", "month"]
    if time_range not in valid_ranges:
        console.print(f"[red]Error:[/red] Invalid time range '{time_range}'. Valid options: {', '.join(valid_ranges)}")
        raise typer.Exit(1)

    try:
        client = get_recommendation_client()

        result = client.get_trending_resources(
            limit=limit,
            time_range=time_range,
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
            results.append(item_dict)

        # Format output
        output_str = format_recommendations(results, format)

        # Print results
        if output_str.strip():
            console.print(output_str)

        # Print summary
        if result.total > 0:
            console.print(f"\n[dim]Showing {len(results)} trending resources ({time_range})[/dim]")
        else:
            console.print("\n[yellow]No trending resources found.[/yellow]")

        # Save to file if requested
        if output:
            if format == "json":
                output_content = json.dumps(
                    {
                        "time_range": time_range,
                        "total": result.total,
                        "trending_resources": results,
                    },
                    indent=2,
                    default=str,
                )
            elif format == "quiet":
                output_content = "\n".join(str(r.get("id", "")) for r in results)
            else:
                output_content = output_str

            output.write_text(output_content)
            console.print(f"\n[green]Trending resources saved to {output}[/green]")

    except Exception as e:
        console.print(f"[red]Error getting trending resources: {e}[/red]")
        raise typer.Exit(1)


@recommend_app.command("feed")
def personalized_feed(
    user_id: int = typer.Argument(
        ...,
        help="User ID to get personalized feed for",
    ),
    limit: int = typer.Option(
        20,
        "--limit",
        "-l",
        help="Maximum number of feed items",
    ),
    offset: int = typer.Option(
        0,
        "--offset",
        "-o",
        help="Number of items to skip",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-O",
        help="Save results to file",
    ),
    format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (table, json, csv, tree, quiet)",
    ),
) -> None:
    """Get a personalized feed of recommendations for a user.

    Examples:
        pharos recommend feed 1
        pharos recommend feed 1 --limit 50
        pharos recommend feed 1 --offset 20
        pharos recommend feed 1 --format json --output feed.json
    """
    console = get_console()

    try:
        client = get_recommendation_client()

        result = client.get_personalized_feed(
            user_id=user_id,
            limit=limit,
            offset=offset,
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
            results.append(item_dict)

        # Format output
        output_str = format_recommendations(results, format)

        # Print results
        if output_str.strip():
            console.print(output_str)

        # Print summary
        if result.total > 0:
            console.print(
                f"\n[dim]Showing {len(results)} of {result.total} feed items[/dim]"
            )
        else:
            console.print("\n[yellow]No feed items found.[/yellow]")

        # Save to file if requested
        if output:
            if format == "json":
                output_content = json.dumps(
                    {
                        "user_id": user_id,
                        "total": result.total,
                        "offset": offset,
                        "feed_items": results,
                    },
                    indent=2,
                    default=str,
                )
            elif format == "quiet":
                output_content = "\n".join(str(r.get("id", "")) for r in results)
            else:
                output_content = output_str

            output.write_text(output_content)
            console.print(f"\n[green]Feed saved to {output}[/green]")

    except Exception as e:
        console.print(f"[red]Error getting personalized feed: {e}[/red]")
        raise typer.Exit(1)