"""Taxonomy commands for Pharos CLI."""

import json
from typing import Optional

import typer
from rich import print
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree
from rich.json import JSON
from rich.text import Text

from pharos_cli.client.taxonomy_client import TaxonomyClient
from pharos_cli.formatters import get_formatter
from pharos_cli.utils.console import get_console
from pharos_cli.utils.helpers import format_number, format_score

taxonomy_app = typer.Typer(
    name="taxonomy",
    help="Taxonomy and classification commands",
    add_completion=False,
)


@taxonomy_app.callback()
def taxonomy_callback():
    """Taxonomy and classification commands."""
    pass


def get_taxonomy_client() -> TaxonomyClient:
    """Get a taxonomy client instance.

    Returns:
        TaxonomyClient instance.
    """
    from pharos_cli.client import SyncAPIClient

    api_client = SyncAPIClient()
    return TaxonomyClient(api_client)


def build_category_tree(
    categories: list,
    parent_id: Optional[str] = None,
) -> list:
    """Build a tree structure from flat category list.

    Args:
        categories: Flat list of categories.
        parent_id: Parent ID to filter by.

    Returns:
        Hierarchical list of categories.
    """
    result = []
    for cat in categories:
        if cat.get("parent_id") == parent_id:
            children = build_category_tree(categories, cat.get("id"))
            if children:
                cat["_children"] = children
            result.append(cat)
    return result


def format_category_tree(
    categories: list,
    prefix: str = "",
    is_last: bool = True,
) -> str:
    """Format categories as a tree string.

    Args:
        categories: List of categories.
        prefix: Current prefix for indentation.
        is_last: Whether this is the last item at current level.

    Returns:
        Formatted tree string.
    """
    lines = []
    connector = "└── " if is_last else "├── "
    branch = "    " if is_last else "│   "

    for i, cat in enumerate(categories):
        is_item_last = (i == len(categories) - 1)
        name = cat.get("name", cat.get("id", "Unknown"))
        count = cat.get("resource_count", 0)

        if count > 0:
            lines.append(f"{prefix}{connector}[bold]{name}[/bold] ({format_number(count)})")
        else:
            lines.append(f"{prefix}{connector}[dim]{name}[/dim]")

        if cat.get("_children"):
            lines.append(
                format_category_tree(
                    cat["_children"],
                    prefix + branch,
                    is_item_last,
                )
            )

    return "\n".join(lines)


@taxonomy_app.command()
def list_categories(
    parent_id: Optional[str] = typer.Option(
        None,
        "--parent",
        "-p",
        help="Parent category ID to list children from",
    ),
    depth: Optional[int] = typer.Option(
        None,
        "--depth",
        "-d",
        help="Maximum depth to traverse (1-10)",
    ),
    output_format: str = typer.Option(
        "tree",
        "--format",
        "-f",
        help="Output format (tree, json, table)",
    ),
) -> None:
    """List taxonomy categories.

    Examples:
        pharos taxonomy list
        pharos taxonomy list --parent cat-1
        pharos taxonomy list --depth 2 --format table
    """
    console = get_console()

    if depth is not None and (depth < 1 or depth > 10):
        console.print("[red]Error: --depth must be between 1 and 10[/red]")
        raise typer.Exit(1)

    try:
        client = get_taxonomy_client()
        result = client.list_categories(
            parent_id=parent_id,
            depth=depth,
            include_counts=True,
        )

        categories = result.get("categories", result.get("items", []))

        # Check output format first for JSON
        if output_format == "json":
            print(JSON(json.dumps(result, indent=2, default=str)).text)
            return

        if not categories:
            console.print("[yellow]No categories found.[/yellow]")
            return

        if output_format == "tree":
            # Build tree structure
            tree_data = build_category_tree(categories)
            tree_str = format_category_tree(tree_data)

            if parent_id:
                console.print(f"[bold]Categories under {parent_id}[/bold]\n")
            else:
                console.print("[bold]Taxonomy Categories[/bold]\n")

            print(tree_str)

            # Show summary
            total = result.get("total_categories", len(categories))
            console.print(f"\n[dim]Total categories: {format_number(total)}[/dim]")
            return

        # Table format
        formatter = get_formatter(output_format)
        display_items = []
        for cat in categories:
            item = {
                "id": cat.get("id", "N/A"),
                "name": cat.get("name", "N/A"),
                "parent_id": cat.get("parent_id", "-"),
                "resource_count": cat.get("resource_count", 0),
                "depth": cat.get("depth", 0),
            }
            display_items.append(item)

        print(formatter.format_list(display_items))

    except Exception as e:
        console.print(f"[red]Error listing categories: {e}[/red]")
        raise typer.Exit(1)


@taxonomy_app.command()
def classify(
    resource_id: str = typer.Argument(
        ...,
        help="Resource ID to classify",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Force reclassification even if already classified",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show detailed classification information",
    ),
) -> None:
    """Classify a resource using the taxonomy.

    Examples:
        pharos taxonomy classify 1
        pharos taxonomy classify 1 --force
        pharos taxonomy classify 1 --verbose
    """
    console = get_console()

    try:
        client = get_taxonomy_client()
        result = client.classify_resource(resource_id, force=force)

        status = result.get("status", "unknown")
        categories = result.get("categories", [])

        if status == "success" or status == "completed":
            console.print(f"[green]✓ Classification completed for resource {resource_id}[/green]\n")

            if categories:
                # Show primary category
                primary = categories[0]
                primary_name = primary.get("name", primary.get("category_id", "Unknown"))
                confidence = primary.get("confidence", 0.0)

                # Create summary panel
                panel = Panel(
                    f"[bold]Primary Category:[/bold] {primary_name}\n"
                    f"[bold]Confidence:[/bold] {confidence:.2%}",
                    title=f"Resource {resource_id}",
                    border_style="green",
                )
                console.print(panel)

                if verbose and len(categories) > 1:
                    console.print("\n[bold]All Categories:[/bold]\n")

                    table = Table(show_header=True, header_style="bold magenta")
                    table.add_column("Category", style="bold")
                    table.add_column("Confidence", justify="right")
                    table.add_column("Path", style="dim")

                    for cat in categories:
                        path = cat.get("path", [])
                        path_str = " > ".join(path) if path else "-"
                        table.add_row(
                            cat.get("name", cat.get("category_id", "Unknown")),
                            f"{cat.get('confidence', 0):.2%}",
                            path_str[:50],
                        )

                    console.print(table)

            else:
                console.print("[yellow]No categories assigned.[/yellow]")

        elif status == "pending":
            console.print(f"[yellow]Classification pending for resource {resource_id}[/yellow]")
        elif status == "failed":
            error_msg = result.get("error", "Unknown error")
            console.print(f"[red]Classification failed: {error_msg}[/red]")
        else:
            console.print(f"[blue]Status: {status}[/blue]")

    except Exception as e:
        console.print(f"[red]Error classifying resource: {e}[/red]")
        raise typer.Exit(1)


@taxonomy_app.command()
def train(
    categories: Optional[str] = typer.Option(
        None,
        "--categories",
        "-c",
        help="Comma-separated list of category IDs to train (default: all)",
    ),
    wait: bool = typer.Option(
        True,
        "--wait/--no-wait",
        help="Wait for training to complete",
    ),
) -> None:
    """Train or retrain the taxonomy classification model.

    Examples:
        pharos taxonomy train
        pharos taxonomy train --categories cat-1,cat-2,cat-3
        pharos taxonomy train --no-wait
    """
    console = get_console()

    try:
        client = get_taxonomy_client()

        # Parse categories if provided
        category_list = None
        if categories:
            category_list = [c.strip() for c in categories.split(",") if c.strip()]

        # Start training
        result = client.train_model(categories=category_list)

        status = result.get("status", "unknown")
        message = result.get("message", "")

        if status == "started" or status == "queued":
            console.print(f"[yellow]Training started: {message}[/yellow]")

            if wait:
                console.print("[dim]Waiting for training to complete...[/dim]")

                # Poll for status
                import time
                max_wait = 300  # 5 minutes
                elapsed = 0

                while elapsed < max_wait:
                    status_result = client.get_training_status()
                    train_status = status_result.get("status", "unknown")

                    if train_status == "completed":
                        console.print("\n[green]✓ Training completed successfully![/green]")

                        # Show metrics if available
                        metrics = result.get("metrics", {})
                        if metrics:
                            console.print("\n[bold]Training Metrics:[/bold]")
                            table = Table(show_header=False)
                            table.add_column("Metric", style="bold")
                            table.add_column("Value", justify="right")

                            for key, value in metrics.items():
                                if isinstance(value, float):
                                    table.add_row(key, f"{value:.2%}")
                                else:
                                    table.add_row(key, str(value))

                            console.print(table)
                        return
                    elif train_status == "failed":
                        error = status_result.get("error", "Unknown error")
                        console.print(f"\n[red]Training failed: {error}[/red]")
                        return
                    elif train_status == "training":
                        progress = status_result.get("progress", 0)
                        console.print(f"\r[dim]Training progress: {progress:.0%}[/dim]", end="")
                    else:
                        console.print(f"\r[dim]Status: {train_status}[/dim]", end="")

                    time.sleep(5)
                    elapsed += 5

                console.print("\n[yellow]Training is still in progress. Check status with 'pharos taxonomy train --no-wait'[/yellow]")

        elif status == "completed":
            console.print("[green]✓ Training completed successfully![/green]")
            metrics = result.get("metrics", {})
            if metrics:
                console.print("\n[bold]Training Metrics:[/bold]")
                for key, value in metrics.items():
                    console.print(f"  {key}: {value}")

        elif status == "no_changes":
            console.print("[blue]No changes detected. Model is up to date.[/blue]")

        else:
            console.print(f"[blue]Status: {status} - {message}[/blue]")

    except Exception as e:
        console.print(f"[red]Error training model: {e}[/red]")
        raise typer.Exit(1)


@taxonomy_app.command()
def stats(
    output_format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (json, table)",
    ),
) -> None:
    """Show taxonomy statistics.

    Examples:
        pharos taxonomy stats
        pharos taxonomy stats --format json
    """
    console = get_console()

    try:
        client = get_taxonomy_client()
        stats_data = client.get_stats()

        if output_format == "json":
            print(JSON(json.dumps(stats_data, indent=2, default=str)).text)
            return

        # Create stats table
        table = Table(title="Taxonomy Statistics")
        table.add_column("Metric", style="bold")
        table.add_column("Value", justify="right")

        # Add stats
        stats_mapping = [
            ("Total Categories", stats_data.get("total_categories", 0)),
            ("Total Resources", stats_data.get("total_resources", 0)),
            ("Classified Resources", stats_data.get("classified_resources", 0)),
            ("Unclassified Resources", stats_data.get("unclassified_resources", 0)),
            ("Classification Rate", stats_data.get("classification_rate", 0)),
            ("Model Version", stats_data.get("model_version", "N/A")),
            ("Last Trained", stats_data.get("last_trained", "Never")),
        ]

        for metric, value in stats_mapping:
            if isinstance(value, float):
                value = f"{value:.2%}"
            elif isinstance(value, int):
                value = format_number(value)
            else:
                value = str(value)
            table.add_row(metric, str(value))

        console.print(table)

        # Show additional info if available
        if stats_data.get("top_categories"):
            console.print("\n[bold]Top Categories by Resource Count:[/bold]")
            top_table = Table(show_header=False)
            top_table.add_column("Category", style="bold")
            top_table.add_column("Count", justify="right")

            for cat in stats_data["top_categories"][:5]:
                top_table.add_row(
                    cat.get("name", cat.get("id", "Unknown")),
                    format_number(cat.get("resource_count", 0)),
                )

            console.print(top_table)

        if stats_data.get("confidence_distribution"):
            console.print("\n[bold]Confidence Distribution:[/bold]")
            dist = stats_data["confidence_distribution"]
            for level, count in dist.items():
                console.print(f"  {level}: {format_number(count)}")

    except Exception as e:
        console.print(f"[red]Error getting taxonomy stats: {e}[/red]")
        raise typer.Exit(1)


@taxonomy_app.command()
def category(
    category_id: str = typer.Argument(
        ...,
        help="Category ID to show details for",
    ),
    show_children: bool = typer.Option(
        False,
        "--children",
        "-c",
        help="Show child categories",
    ),
    show_similar: bool = typer.Option(
        False,
        "--similar",
        "-s",
        help="Show similar categories",
    ),
) -> None:
    """Show details for a specific category.

    Examples:
        pharos taxonomy category cat-1
        pharos taxonomy category cat-1 --children
        pharos taxonomy category cat-1 --similar
    """
    console = get_console()

    try:
        client = get_taxonomy_client()
        category_data = client.get_category(category_id)

        if not category_data:
            console.print(f"[yellow]Category {category_id} not found.[/yellow]")
            return

        # Create details panel
        name = category_data.get("name", category_id)
        description = category_data.get("description", "No description")
        resource_count = category_data.get("resource_count", 0)

        panel = Panel(
            f"[bold]Description:[/bold] {description}\n\n"
            f"[bold]Resource Count:[/bold] {format_number(resource_count)}\n"
            f"[bold]Depth:[/bold] {category_data.get('depth', 'N/A')}\n"
            f"[bold]Parent:[/bold] {category_data.get('parent_id', 'None')}",
            title=f"Category: {name}",
            border_style="blue",
        )
        console.print(panel)

        # Show children if requested
        if show_children:
            children = category_data.get("children", [])
            if children:
                console.print("\n[bold]Child Categories:[/bold]\n")

                table = Table(show_header=True, header_style="bold magenta")
                table.add_column("ID", style="dim")
                table.add_column("Name", style="bold")
                table.add_column("Resources", justify="right")

                for child in children:
                    table.add_row(
                        child.get("id", "N/A")[:20],
                        child.get("name", "Unknown"),
                        format_number(child.get("resource_count", 0)),
                    )

                console.print(table)
            else:
                console.print("[dim]No child categories.[/dim]")

        # Show similar categories if requested
        if show_similar:
            similar_data = client.get_similar_categories(category_id, limit=5)
            similar = similar_data.get("similar_categories", [])

            if similar:
                console.print("\n[bold]Similar Categories:[/bold]\n")

                table = Table(show_header=True, header_style="bold magenta")
                table.add_column("Category", style="bold")
                table.add_column("Similarity", justify="right")

                for cat in similar:
                    table.add_row(
                        cat.get("name", cat.get("id", "Unknown")),
                        f"{cat.get('similarity', 0):.2%}",
                    )

                console.print(table)
            else:
                console.print("[dim]No similar categories found.[/dim]")

    except Exception as e:
        console.print(f"[red]Error getting category: {e}[/red]")
        raise typer.Exit(1)


@taxonomy_app.command()
def search(
    query: str = typer.Argument(
        ...,
        help="Search query for category name or description",
    ),
    limit: int = typer.Option(
        20,
        "--limit",
        "-l",
        help="Maximum results (1-100)",
    ),
    output_format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (json, table)",
    ),
) -> None:
    """Search taxonomy categories.

    Examples:
        pharos taxonomy search "machine learning"
        pharos taxonomy search "neural" --limit 10
    """
    console = get_console()

    if limit < 1 or limit > 100:
        console.print("[red]Error: --limit must be between 1 and 100[/red]")
        raise typer.Exit(1)

    try:
        client = get_taxonomy_client()
        result = client.search_categories(query=query, limit=limit)

        if output_format == "json":
            print(JSON(json.dumps({
                "total": result.total,
                "categories": result.items,
            }, indent=2, default=str)).text)
            return

        if not result.items:
            console.print(f"[yellow]No categories found matching '{query}'.[/yellow]")
            return

        console.print(f"[bold]Search Results for '{query}'[/bold] ({len(result.items)} of {result.total})\n")

        # Table format
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("ID", style="dim")
        table.add_column("Name", style="bold")
        table.add_column("Description", style="dim")
        table.add_column("Resources", justify="right")

        for item in result.items:
            desc = item.get("description", "")
            if len(desc) > 50:
                desc = desc[:50] + "..."

            table.add_row(
                str(item.get("id", "N/A"))[:20],
                item.get("name", "Unknown"),
                desc,
                format_number(item.get("resource_count", 0)),
            )

        console.print(table)

        if result.has_more:
            console.print(f"\n[dim]Use --limit to see more results[/dim]")

    except Exception as e:
        console.print(f"[red]Error searching categories: {e}[/red]")
        raise typer.Exit(1)


@taxonomy_app.command()
def distribution(
    dimension: str = typer.Option(
        "category",
        "--dimension",
        "-d",
        help="Distribution dimension (category, confidence, depth)",
    ),
) -> None:
    """Show classification distribution.

    Examples:
        pharos taxonomy distribution
        pharos taxonomy distribution --dimension confidence
    """
    console = get_console()

    valid_dimensions = ["category", "confidence", "depth"]
    if dimension not in valid_dimensions:
        console.print(f"[red]Error: Invalid dimension. Must be one of: {', '.join(valid_dimensions)}[/red]")
        raise typer.Exit(1)

    try:
        client = get_taxonomy_client()
        dist_data = client.get_distribution(dimension=dimension)

        console.print(f"\n[bold]Classification Distribution ({dimension})[/bold]\n")

        if dimension == "category":
            # Show top categories
            distribution = dist_data.get("distribution", [])
            if distribution:
                table = Table(title="Top Categories")
                table.add_column("Category", style="bold")
                table.add_column("Count", justify="right")
                table.add_column("Percentage", justify="right")
                table.add_column("Visual", justify="left")

                total = sum(d.get("count", 0) for d in distribution)

                for item in distribution[:10]:
                    count = item.get("count", 0)
                    pct = count / total if total > 0 else 0
                    bar = "█" * int(pct * 30)

                    table.add_row(
                        item.get("name", item.get("id", "Unknown")),
                        format_number(count),
                        f"{pct:.1%}",
                        bar,
                    )

                console.print(table)

        elif dimension == "confidence":
            # Show confidence distribution
            distribution = dist_data.get("distribution", {})
            if distribution:
                table = Table(title="Confidence Distribution")
                table.add_column("Level", style="bold")
                table.add_column("Count", justify="right")
                table.add_column("Percentage", justify="right")

                total = sum(distribution.values())
                for level, count in distribution.items():
                    pct = count / total if total > 0 else 0
                    table.add_row(
                        level,
                        format_number(count),
                        f"{pct:.1%}",
                    )

                console.print(table)

        elif dimension == "depth":
            # Show depth distribution
            distribution = dist_data.get("distribution", [])
            if distribution:
                table = Table(title="Depth Distribution")
                table.add_column("Depth", justify="right")
                table.add_column("Count", justify="right")
                table.add_column("Percentage", justify="right")
                table.add_column("Visual", justify="left")

                total = sum(d.get("count", 0) for d in distribution)

                for item in distribution:
                    count = item.get("count", 0)
                    pct = count / total if total > 0 else 0
                    bar = "█" * int(pct * 30)

                    table.add_row(
                        str(item.get("depth", 0)),
                        format_number(count),
                        f"{pct:.1%}",
                        bar,
                    )

                console.print(table)

    except Exception as e:
        console.print(f"[red]Error getting distribution: {e}[/red]")
        raise typer.Exit(1)


@taxonomy_app.command()
def model() -> None:
    """Show information about the current classification model.

    Examples:
        pharos taxonomy model
    """
    console = get_console()

    try:
        client = get_taxonomy_client()
        model_data = client.get_model_info()

        version = model_data.get("version", "N/A")
        accuracy = model_data.get("accuracy", 0.0)
        last_trained = model_data.get("last_trained", "Never")
        status = model_data.get("status", "unknown")

        # Create model info panel
        panel = Panel(
            f"[bold]Version:[/bold] {version}\n"
            f"[bold]Status:[/bold] {status}\n"
            f"[bold]Accuracy:[/bold] {accuracy:.2%}\n"
            f"[bold]Last Trained:[/bold] {last_trained}",
            title="Classification Model",
            border_style="blue",
        )
        console.print(panel)

        # Show additional info
        if model_data.get("categories_trained"):
            console.print(f"\n[bold]Categories Trained:[/bold] {format_number(model_data['categories_trained'])}")

        if model_data.get("training_samples"):
            console.print(f"[bold]Training Samples:[/bold] {format_number(model_data['training_samples'])}")

        if model_data.get("metrics"):
            console.print("\n[bold]Model Metrics:[/bold]")
            metrics = model_data["metrics"]
            table = Table(show_header=False)
            table.add_column("Metric", style="bold")
            table.add_column("Value", justify="right")

            for key, value in metrics.items():
                if isinstance(value, float):
                    table.add_row(key, f"{value:.4f}")
                else:
                    table.add_row(key, str(value))

            console.print(table)

    except Exception as e:
        console.print(f"[red]Error getting model info: {e}[/red]")
        raise typer.Exit(1)


@taxonomy_app.command()
def health() -> None:
    """Check taxonomy module health.

    Examples:
        pharos taxonomy health
    """
    console = get_console()

    try:
        client = get_taxonomy_client()
        health_data = client.get_health()

        status = health_data.get("status", "unknown")
        db_status = health_data.get("database", False)
        model_status = health_data.get("model_available", False)

        if status == "healthy" and db_status and model_status:
            console.print("[green]✓ Taxonomy module is healthy[/green]")
        elif status == "degraded":
            console.print("[yellow]⚠ Taxonomy module is degraded[/yellow]")
        else:
            console.print("[red]✗ Taxonomy module has issues[/red]")

        console.print(f"\n[dim]Database: {'Connected' if db_status else 'Disconnected'}[/dim]")
        console.print(f"[dim]Model: {'Available' if model_status else 'Not available'}[/dim]")
        console.print(f"[dim]Module: {health_data.get('module', 'N/A')}[/dim]")
        console.print(f"[dim]Timestamp: {health_data.get('timestamp', 'N/A')}[/dim]")

    except Exception as e:
        console.print(f"[red]Error checking health: {e}[/red]")
        raise typer.Exit(1)


@taxonomy_app.command()
def export(
    format: str = typer.Option(
        "json",
        "--format",
        "-f",
        help="Export format (json, csv)",
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file path",
    ),
) -> None:
    """Export taxonomy data.

    Examples:
        pharos taxonomy export
        pharos taxonomy export --format json -o taxonomy.json
        pharos taxonomy export --format csv -o taxonomy.csv
    """
    console = get_console()

    valid_formats = ["json", "csv"]
    if format not in valid_formats:
        console.print(f"[red]Error: Invalid format. Must be one of: {', '.join(valid_formats)}[/red]")
        raise typer.Exit(1)

    try:
        client = get_taxonomy_client()
        export_data = client.export_taxonomy(format=format)

        if output:
            if format == "json":
                content = json.dumps(export_data, indent=2, default=str)
            else:
                # CSV format
                categories = export_data.get("categories", [])
                if categories:
                    headers = ["id", "name", "parent_id", "resource_count"]
                    lines = [",".join(headers)]
                    for cat in categories:
                        lines.append(",".join(str(cat.get(h, "")) for h in headers))
                    content = "\n".join(lines)
                else:
                    content = ""

            with open(output, "w") as f:
                f.write(content)
            console.print(f"[green]Taxonomy exported to {output}[/green]")
        else:
            # Print to console
            if format == "json":
                print(JSON(json.dumps(export_data, indent=2, default=str)).text)
            else:
                console.print("[yellow]CSV output requires --output flag[/yellow]")

    except Exception as e:
        console.print(f"[red]Error exporting taxonomy: {e}[/red]")
        raise typer.Exit(1)


@taxonomy_app.command()
def classification(
    resource_id: str = typer.Argument(
        ...,
        help="Resource ID to get classification for",
    ),
) -> None:
    """Get current classification for a resource.

    Examples:
        pharos taxonomy classification 1
    """
    console = get_console()

    try:
        client = get_taxonomy_client()
        classification_data = client.get_classification(resource_id)

        if not classification_data:
            console.print(f"[yellow]Resource {resource_id} has no classification.[/yellow]")
            return

        categories = classification_data.get("categories", [])

        if not categories:
            console.print(f"[yellow]Resource {resource_id} has no classification.[/yellow]")
            return

        console.print(f"[bold]Classification for Resource {resource_id}[/bold]\n")

        # Show categories
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Category", style="bold")
        table.add_column("Confidence", justify="right")
        table.add_column("Path")

        for cat in categories:
            path = cat.get("path", [])
            path_str = " > ".join(path) if path else "-"

            table.add_row(
                cat.get("name", cat.get("category_id", "Unknown")),
                f"{cat.get('confidence', 0):.2%}",
                path_str,
            )

        console.print(table)

        # Show metadata
        if classification_data.get("classified_at"):
            console.print(f"\n[dim]Classified at: {classification_data['classified_at']}[/dim]")

        if classification_data.get("method"):
            console.print(f"[dim]Method: {classification_data['method']}[/dim]")

    except Exception as e:
        console.print(f"[red]Error getting classification: {e}[/red]")
        raise typer.Exit(1)


@taxonomy_app.command()
def remove(
    resource_id: str = typer.Argument(
        ...,
        help="Resource ID to remove classification from",
    ),
) -> None:
    """Remove classification from a resource.

    Examples:
        pharos taxonomy remove 1
    """
    console = get_console()

    try:
        client = get_taxonomy_client()
        result = client.remove_classification(resource_id)

        status = result.get("status", "unknown")

        if status == "removed":
            console.print(f"[green]✓ Classification removed from resource {resource_id}[/green]")
        else:
            console.print(f"[blue]Status: {status}[/blue]")

    except Exception as e:
        console.print(f"[red]Error removing classification: {e}[/red]")
        raise typer.Exit(1)


@taxonomy_app.command()
def batch_classify(
    resource_ids: str = typer.Argument(
        ...,
        help="Comma-separated list of resource IDs to classify",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Force reclassification even if already classified",
    ),
) -> None:
    """Classify multiple resources.

    Examples:
        pharos taxonomy batch-classify 1,2,3,4,5
        pharos taxonomy batch-classify 1,2,3 --force
    """
    console = get_console()

    # Parse resource IDs
    ids = [i.strip() for i in resource_ids.split(",") if i.strip()]

    if not ids:
        console.print("[red]Error: No resource IDs provided[/red]")
        raise typer.Exit(1)

    if len(ids) > 100:
        console.print("[red]Error: Maximum 100 resource IDs allowed[/red]")
        raise typer.Exit(1)

    try:
        client = get_taxonomy_client()
        result = client.classify_resource_batch(resource_ids=ids, force=force)

        status = result.get("status", "unknown")
        processed = result.get("processed", 0)
        successful = result.get("successful", 0)
        failed = result.get("failed", 0)

        console.print(f"[bold]Batch Classification Complete[/bold]\n")
        console.print(f"  Processed: {processed}")
        console.print(f"  Successful: [green]{successful}[/green]")
        console.print(f"  Failed: [red]{failed}[/red]")

        if failed > 0 and result.get("errors"):
            console.print("\n[bold]Errors:[/bold]")
            for error in result["errors"][:5]:
                console.print(f"  - {error}")

    except Exception as e:
        console.print(f"[red]Error in batch classification: {e}[/red]")
        raise typer.Exit(1)