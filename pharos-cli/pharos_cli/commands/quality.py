"""Quality commands for Pharos CLI."""

import json
from typing import Optional

import typer
from rich import print
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.box import Box
from rich.style import Style
from rich.color import Color
from rich.console import Console
from rich.json import JSON

from pharos_cli.client.quality_client import QualityClient
from pharos_cli.utils.console import get_console
from pharos_cli.utils.helpers import format_score, format_number

quality_app = typer.Typer(
    name="quality",
    help="Quality assessment commands",
    add_completion=False,
)


@quality_app.callback()
def quality_callback():
    """Quality assessment commands."""
    pass


def get_quality_client() -> QualityClient:
    """Get a quality client instance.

    Returns:
        QualityClient instance.
    """
    from pharos_cli.client import SyncAPIClient

    api_client = SyncAPIClient()
    return QualityClient(api_client)


def draw_ascii_bar(
    value: float,
    width: int = 30,
    color: str = "green",
) -> str:
    """Draw an ASCII progress bar for a quality score.

    Args:
        value: Quality score (0.0 to 1.0).
        width: Width of the bar in characters.
        color: Color name (green, yellow, red).

    Returns:
        ASCII bar string.
    """
    filled = int(value * width)
    empty = width - filled

    # Color mapping
    color_map = {
        "green": ("[green]█[/green]", "[green]░[/green]"),
        "yellow": ("[yellow]█[/yellow]", "[yellow]░[/yellow]"),
        "red": ("[red]█[/red]", "[red]░[/red]"),
    }

    fill_char, empty_char = color_map.get(color, color_map["green"])

    return f"{fill_char * filled}{empty_char * empty}"


def get_score_color(score: float) -> str:
    """Get color based on quality score.

    Args:
        score: Quality score (0.0 to 1.0).

    Returns:
        Color name.
    """
    if score >= 0.8:
        return "green"
    elif score >= 0.5:
        return "yellow"
    else:
        return "red"


def format_quality_visual(
    score: float,
    label: str,
    width: int = 20,
) -> str:
    """Format a quality score with visual bar.

    Args:
        score: Quality score (0.0 to 1.0).
        label: Label for the score.
        width: Width of the bar.

    Returns:
        Formatted string with bar.
    """
    color = get_score_color(score)
    bar = draw_ascii_bar(score, width, color)
    return f"{label:15} {bar} {score:.2%}"


@quality_app.command()
def score(
    resource_id: str = typer.Argument(
        ...,
        help="Resource ID to show quality score for",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show detailed dimension breakdown",
    ),
) -> None:
    """Show quality score for a resource.

    Examples:
        pharos quality score 1
        pharos quality score 1 --verbose
    """
    console = get_console()

    try:
        client = get_quality_client()
        quality_data = client.get_quality_score(resource_id)

        overall_score = quality_data.get("quality_overall", 0.0)
        color = get_score_color(overall_score)

        # Create main score display
        score_text = Text()
        score_text.append(f"Quality Score: ", style="bold")
        score_text.append(f"{overall_score:.2%}", style=f"bold {color}")

        # Create visual bar
        bar = draw_ascii_bar(overall_score, 40, color)

        # Display header
        console.print(Panel(
            f"\n{score_text}\n\n{bar}\n",
            title=f"Resource {resource_id}",
            border_style=color,
        ))

        # Show dimension breakdown if verbose
        if verbose:
            dimensions = quality_data.get("quality_dimensions", {})
            if dimensions:
                console.print("\n[bold]Dimension Breakdown:[/bold]\n")

                table = Table(show_header=True, header_style="bold magenta")
                table.add_column("Dimension", style="bold")
                table.add_column("Score", justify="right")
                table.add_column("Visual", justify="left")
                table.add_column("Status", justify="center")

                for dim, score in dimensions.items():
                    dim_color = get_score_color(score)
                    dim_bar = draw_ascii_bar(score, 15, dim_color)
                    status = "✓" if score >= 0.5 else "✗"

                    table.add_row(
                        dim.title(),
                        f"{score:.2%}",
                        dim_bar,
                        f"[{dim_color}]{status}[/{dim_color}]",
                    )

                console.print(table)

        # Show additional info
        console.print(f"\n[dim]Last computed: {quality_data.get('quality_last_computed', 'N/A')}[/dim]")

        if quality_data.get("is_quality_outlier"):
            console.print("[yellow]⚠ This resource is a quality outlier[/yellow]")

        if quality_data.get("needs_quality_review"):
            console.print("[red]⚠ This resource needs quality review[/red]")

    except Exception as e:
        console.print(f"[red]Error getting quality score: {e}[/red]")
        raise typer.Exit(1)


@quality_app.command()
def outliers(
    page: int = typer.Option(
        1,
        "--page",
        "-p",
        help="Page number",
    ),
    limit: int = typer.Option(
        20,
        "--limit",
        "-l",
        help="Results per page (1-100)",
    ),
    min_score: Optional[float] = typer.Option(
        None,
        "--min-score",
        "-s",
        help="Minimum outlier score (0.0-1.0)",
    ),
    output_format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (json, table)",
    ),
) -> None:
    """List quality outliers.

    Examples:
        pharos quality outliers
        pharos quality outliers --page 2 --limit 50
        pharos quality outliers --min-score 0.5 --format json
    """
    console = get_console()

    if limit < 1 or limit > 100:
        console.print("[red]Error: --limit must be between 1 and 100[/red]")
        raise typer.Exit(1)

    if min_score is not None and (min_score < -1.0 or min_score > 1.0):
        console.print("[red]Error: --min-score must be between -1.0 and 1.0[/red]")
        raise typer.Exit(1)

    try:
        client = get_quality_client()
        result = client.get_outliers(
            page=page,
            limit=limit,
            min_outlier_score=min_score,
        )

        if output_format == "json":
            print(JSON(json.dumps({
                "total": result.total,
                "page": result.page,
                "per_page": result.per_page,
                "has_more": result.has_more,
                "outliers": result.items,
            }, indent=2, default=str)).text)
            return

        if not result.items:
            console.print("[green]No quality outliers found.[/green]")
            return

        console.print(f"[bold]Quality Outliers[/bold] (Page {page}, {len(result.items)} of {result.total})\n")

        # Create table
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Resource ID", style="bold")
        table.add_column("Title", style="dim")
        table.add_column("Quality", justify="right")
        table.add_column("Outlier Score", justify="right")
        table.add_column("Status")

        for item in result.items:
            quality = item.get("quality_overall", 0.0)
            outlier_score = item.get("outlier_score", 0.0)
            color = get_score_color(quality)

            status = ""
            if item.get("needs_quality_review"):
                status = "[yellow]Review[/yellow]"

            table.add_row(
                str(item.get("resource_id", "N/A")),
                str(item.get("title", "N/A"))[:40],
                f"[{color}]{quality:.2%}[/{color}]",
                f"{outlier_score:.2%}",
                status,
            )

        console.print(table)

        if result.has_more:
            console.print(f"\n[dim]Use --page {page + 1} for more results[/dim]")

    except Exception as e:
        console.print(f"[red]Error getting outliers: {e}[/red]")
        raise typer.Exit(1)


@quality_app.command()
def recompute(
    resource_id: str = typer.Argument(
        ...,
        help="Resource ID to recompute quality for",
    ),
    async_mode: bool = typer.Option(
        False,
        "--async",
        "-a",
        help="Queue task asynchronously (if Celery is available)",
    ),
) -> None:
    """Recompute quality score for a resource.

    Examples:
        pharos quality recompute 1
        pharos quality recompute 1 --async
    """
    console = get_console()

    try:
        client = get_quality_client()
        result = client.recompute_quality(resource_id=resource_id)

        status = result.get("status", "unknown")
        message = result.get("message", "")

        if status == "accepted":
            console.print(f"[yellow]Quality computation queued: {message}[/yellow]")
        elif status == "completed":
            console.print(f"[green]Quality computation completed: {message}[/green]")
        else:
            console.print(f"[blue]Status: {status} - {message}[/blue]")

    except Exception as e:
        console.print(f"[red]Error recomputing quality: {e}[/red]")
        raise typer.Exit(1)


@quality_app.command()
def report(
    collection_id: str = typer.Argument(
        ...,
        help="Collection ID to generate quality report for",
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file path (JSON format)",
    ),
) -> None:
    """Generate quality report for a collection.

    Examples:
        pharos quality report 1
        pharos quality report 1 --output report.json
    """
    console = get_console()

    try:
        client = get_quality_client()
        report_data = client.get_collection_quality_report(collection_id)

        if output:
            with open(output, "w") as f:
                json.dump(report_data, f, indent=2, default=str)
            console.print(f"[green]Report saved to {output}[/green]")
            return

        # Display report
        console.print(f"\n[bold]Quality Report for Collection {collection_id}[/bold]\n")

        # Summary stats
        if "summary" in report_data:
            summary = report_data["summary"]
            table = Table(title="Summary", show_header=False)
            table.add_column("Metric", style="bold")
            table.add_column("Value", justify="right")

            for key, value in summary.items():
                if isinstance(value, float):
                    table.add_row(key.title(), f"{value:.2%}")
                else:
                    table.add_row(key.title(), str(value))

            console.print(table)

        # Distribution
        if "distribution" in report_data:
            dist = report_data["distribution"]
            console.print("\n[bold]Quality Distribution:[/bold]\n")

            for dim, data in dist.items():
                if isinstance(data, dict) and "mean" in data:
                    mean = data["mean"]
                    color = get_score_color(mean)
                    bar = draw_ascii_bar(mean, 30, color)
                    console.print(f"{dim:15} {bar} {mean:.2%}")

        # Recommendations
        if "recommendations" in report_data and report_data["recommendations"]:
            console.print("\n[bold]Recommendations:[/bold]")
            for i, rec in enumerate(report_data["recommendations"], 1):
                console.print(f"  {i}. {rec}")

        # Outliers in collection
        if "outliers" in report_data:
            outliers = report_data["outliers"]
            console.print(f"\n[bold]Outliers in Collection:[/bold] {len(outliers)}")

            if outliers:
                table = Table(show_header=True, header_style="bold red")
                table.add_column("Resource ID")
                table.add_column("Quality", justify="right")
                table.add_column("Issue")

                for item in outliers[:10]:  # Show top 10
                    table.add_row(
                        str(item.get("resource_id", "N/A")),
                        f"{item.get('quality_overall', 0):.2%}",
                        str(item.get("issue", "N/A"))[:50],
                    )

                console.print(table)

    except Exception as e:
        console.print(f"[red]Error generating report: {e}[/red]")
        raise typer.Exit(1)


@quality_app.command()
def distribution(
    dimension: str = typer.Option(
        "overall",
        "--dimension",
        "-d",
        help="Quality dimension (overall, accuracy, completeness, consistency, timeliness, relevance)",
    ),
    bins: int = typer.Option(
        10,
        "--bins",
        "-b",
        help="Number of histogram bins (5-50)",
    ),
) -> None:
    """Show quality score distribution.

    Examples:
        pharos quality distribution
        pharos quality distribution --dimension accuracy --bins 20
    """
    console = get_console()

    valid_dimensions = ["overall", "accuracy", "completeness", "consistency", "timeliness", "relevance"]
    if dimension not in valid_dimensions:
        console.print(f"[red]Error: Invalid dimension. Must be one of: {', '.join(valid_dimensions)}[/red]")
        raise typer.Exit(1)

    if bins < 5 or bins > 50:
        console.print("[red]Error: --bins must be between 5 and 50[/red]")
        raise typer.Exit(1)

    try:
        client = get_quality_client()
        dist_data = client.get_distribution(bins=bins, dimension=dimension)

        console.print(f"\n[bold]Quality Distribution ({dimension})[/bold]\n")

        # Statistics
        stats = dist_data.get("statistics", {})
        table = Table(show_header=False)
        table.add_column("Metric", style="bold")
        table.add_column("Value", justify="right")

        table.add_row("Mean", f"{stats.get('mean', 0):.2%}")
        table.add_row("Median", f"{stats.get('median', 0):.2%}")
        table.add_row("Std Dev", f"{stats.get('std_dev', 0):.2%}")

        console.print(table)

        # Histogram
        console.print("\n[bold]Histogram:[/bold]\n")
        distribution = dist_data.get("distribution", [])

        for bin_data in distribution:
            bin_range = bin_data.get("range", "N/A")
            count = bin_data.get("count", 0)
            bar = "█" * min(count, 50)  # Cap at 50 characters
            console.print(f"{bin_range:>10} │ {bar} {count}")

    except Exception as e:
        console.print(f"[red]Error getting distribution: {e}[/red]")
        raise typer.Exit(1)


@quality_app.command()
def dimensions() -> None:
    """Show average quality dimensions across all resources.

    Examples:
        pharos quality dimensions
    """
    console = get_console()

    try:
        client = get_quality_client()
        dims_data = client.get_dimension_averages()

        console.print("\n[bold]Quality Dimension Averages[/bold]\n")

        dimensions = dims_data.get("dimensions", {})
        overall = dims_data.get("overall", {})

        # Overall score
        overall_score = overall.get("avg", 0.0)
        color = get_score_color(overall_score)
        bar = draw_ascii_bar(overall_score, 40, color)

        console.print(f"[bold]Overall Average:[/bold]\n{bar} {overall_score:.2%}\n")

        # Dimension breakdown
        table = Table(title="Dimension Breakdown", show_header=True, header_style="bold magenta")
        table.add_column("Dimension", style="bold")
        table.add_column("Average", justify="right")
        table.add_column("Min", justify="right")
        table.add_column("Max", justify="right")
        table.add_column("Visual", justify="left")

        for dim_name, stats in dimensions.items():
            avg = stats.get("avg", 0.0)
            dim_color = get_score_color(avg)
            bar = draw_ascii_bar(avg, 15, dim_color)

            table.add_row(
                dim_name.title(),
                f"{avg:.2%}",
                f"{stats.get('min', 0):.2%}",
                f"{stats.get('max', 0):.2%}",
                bar,
            )

        console.print(table)

        total = dims_data.get("total_resources", 0)
        console.print(f"\n[dim]Based on {total} resources with quality scores[/dim]")

    except Exception as e:
        console.print(f"[red]Error getting dimensions: {e}[/red]")
        raise typer.Exit(1)


@quality_app.command()
def trends(
    granularity: str = typer.Option(
        "weekly",
        "--granularity",
        "-g",
        help="Time granularity (daily, weekly, monthly)",
    ),
    dimension: str = typer.Option(
        "overall",
        "--dimension",
        "-d",
        help="Quality dimension",
    ),
    start_date: Optional[str] = typer.Option(
        None,
        "--start-date",
        help="Start date (YYYY-MM-DD)",
    ),
    end_date: Optional[str] = typer.Option(
        None,
        "--end-date",
        help="End date (YYYY-MM-DD)",
    ),
) -> None:
    """Show quality trends over time.

    Examples:
        pharos quality trends
        pharos quality trends --granularity monthly --start-date 2024-01-01
    """
    console = get_console()

    valid_granularities = ["daily", "weekly", "monthly"]
    if granularity not in valid_granularities:
        console.print(f"[red]Error: Invalid granularity. Must be one of: {', '.join(valid_granularities)}[/red]")
        raise typer.Exit(1)

    try:
        client = get_quality_client()
        trends_data = client.get_trends(
            granularity=granularity,
            dimension=dimension,
            start_date=start_date,
            end_date=end_date,
        )

        console.print(f"\n[bold]Quality Trends ({dimension})[/bold]\n")

        data_points = trends_data.get("data_points", [])

        if not data_points:
            console.print("[yellow]No trend data available for the specified period.[/yellow]")
            return

        # Show recent trends
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Period", style="bold")
        table.add_column("Avg Quality", justify="right")
        table.add_column("Resources", justify="right")
        table.add_column("Visual", justify="left")

        # Show last 10 data points
        for dp in data_points[-10:]:
            period = dp.get("period", "N/A")
            avg_quality = dp.get("avg_quality", 0.0)
            count = dp.get("resource_count", 0)
            color = get_score_color(avg_quality)
            bar = draw_ascii_bar(avg_quality, 20, color)

            table.add_row(
                str(period),
                f"{avg_quality:.2%}",
                str(count),
                bar,
            )

        console.print(table)

        # Show summary
        if len(data_points) > 1:
            first = data_points[0].get("avg_quality", 0)
            last = data_points[-1].get("avg_quality", 0)
            change = last - first

            if change > 0:
                console.print(f"\n[green]Trend: +{change:.1%} over period[/green]")
            elif change < 0:
                console.print(f"\n[red]Trend: {change:.1%} over period[/red]")
            else:
                console.print(f"\n[dim]Trend: No change over period[/dim]")

    except Exception as e:
        console.print(f"[red]Error getting trends: {e}[/red]")
        raise typer.Exit(1)


@quality_app.command()
def review_queue(
    page: int = typer.Option(
        1,
        "--page",
        "-p",
        help="Page number",
    ),
    limit: int = typer.Option(
        20,
        "--limit",
        "-l",
        help="Results per page (1-100)",
    ),
    sort_by: str = typer.Option(
        "outlier_score",
        "--sort",
        "-s",
        help="Sort by (outlier_score, quality_overall, updated_at)",
    ),
) -> None:
    """Show resources needing quality review.

    Examples:
        pharos quality review-queue
        pharos quality review-queue --page 2 --sort quality_overall
    """
    console = get_console()

    if limit < 1 or limit > 100:
        console.print("[red]Error: --limit must be between 1 and 100[/red]")
        raise typer.Exit(1)

    valid_sort = ["outlier_score", "quality_overall", "updated_at"]
    if sort_by not in valid_sort:
        console.print(f"[red]Error: Invalid sort. Must be one of: {', '.join(valid_sort)}[/red]")
        raise typer.Exit(1)

    try:
        client = get_quality_client()
        result = client.get_review_queue(page=page, limit=limit, sort_by=sort_by)

        console.print(f"\n[bold]Quality Review Queue[/bold] (Page {page}, {len(result.items)} of {result.total})\n")

        if not result.items:
            console.print("[green]No resources need quality review.[/green]")
            return

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Resource ID", style="bold")
        table.add_column("Title", style="dim")
        table.add_column("Quality", justify="right")
        table.add_column("Outlier", justify="right")
        table.add_column("Last Computed", style="dim")

        for item in result.items:
            quality = item.get("quality_overall", 0.0)
            outlier = item.get("outlier_score", 0.0)
            color = get_score_color(quality)

            table.add_row(
                str(item.get("resource_id", "N/A")),
                str(item.get("title", "N/A"))[:40],
                f"[{color}]{quality:.2%}[/{color}]",
                f"{outlier:.2%}",
                str(item.get("quality_last_computed", "N/A"))[:10],
            )

        console.print(table)

        if result.has_more:
            console.print(f"\n[dim]Use --page {page + 1} for more results[/dim]")

    except Exception as e:
        console.print(f"[red]Error getting review queue: {e}[/red]")
        raise typer.Exit(1)


@quality_app.command()
def health() -> None:
    """Check quality module health.

    Examples:
        pharos quality health
    """
    console = get_console()

    try:
        client = get_quality_client()
        health_data = client.get_health()

        status = health_data.get("status", "unknown")
        db_status = health_data.get("database", False)

        if status == "healthy" and db_status:
            console.print("[green]✓ Quality module is healthy[/green]")
        else:
            console.print("[red]✗ Quality module has issues[/red]")

        console.print(f"\n[dim]Database: {'Connected' if db_status else 'Disconnected'}[/dim]")
        console.print(f"[dim]Module: {health_data.get('module', 'N/A')}[/dim]")
        console.print(f"[dim]Timestamp: {health_data.get('timestamp', 'N/A')}[/dim]")

    except Exception as e:
        console.print(f"[red]Error checking health: {e}[/red]")
        raise typer.Exit(1)