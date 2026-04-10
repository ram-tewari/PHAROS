"""Collection commands for Pharos CLI."""

import json
from typing import Optional

import typer
from rich import print
from rich.panel import Panel
from rich.table import Table
from rich.console import Console

from pharos_cli.client.api_client import get_api_client
from pharos_cli.client.collection_client import CollectionClient
from pharos_cli.client.exceptions import (
    CollectionNotFoundError,
    ResourceNotFoundError,
    APIError,
    NetworkError,
)
from pharos_cli.config.settings import load_config
from pharos_cli.formatters.base import get_formatter
from pharos_cli.utils.console import get_console
from pharos_cli.utils.helpers import format_number, format_score, truncate


collection_app = typer.Typer(
    name="collection",
    help="Collection management commands for Pharos CLI",
)


@collection_app.callback()
def collection_callback():
    """Collection management commands for Pharos CLI."""
    pass


def get_collection_client() -> CollectionClient:
    """Get a CollectionClient instance."""
    config = load_config()
    api_client = get_api_client(config)
    return CollectionClient(api_client)


@collection_app.command("create")
def create_collection(
    name: str = typer.Argument(
        ...,
        help="Name for the new collection",
    ),
    description: Optional[str] = typer.Option(
        None,
        "--description",
        "-d",
        help="Description for the collection",
    ),
    public: bool = typer.Option(
        False,
        "--public",
        help="Make the collection public",
    ),
    output_format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (json, table)",
    ),
) -> None:
    """Create a new collection.

    Examples:
        pharos collection create "ML Papers"
        pharos collection create "My Collection" --description "Research papers"
        pharos collection create "Public Docs" --public
    """
    console = get_console()

    try:
        client = get_collection_client()
        result = client.create(
            name=name,
            description=description,
            is_public=public,
        )

        console.print(f"[green]Collection created successfully![/green]")
        console.print(f"  ID: {result['id']}")
        console.print(f"  Name: {result['name']}")
        if result.get('description'):
            console.print(f"  Description: {result['description']}")
        console.print(f"  Public: {result.get('is_public', False)}")

    except APIError as e:
        console.print(f"[red]API Error:[/red] {e.message}")
        raise typer.Exit(1)
    except NetworkError as e:
        console.print(f"[red]Network Error:[/red] {e}")
        raise typer.Exit(1)


@collection_app.command("list")
def list_collections(
    query: Optional[str] = typer.Option(
        None,
        "--query",
        "-q",
        help="Search query for collection name/description",
    ),
    page: int = typer.Option(
        1,
        "--page",
        "-p",
        help="Page number",
    ),
    per_page: int = typer.Option(
        25,
        "--per-page",
        help="Items per page (1-100)",
    ),
    output_format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (json, table, csv, quiet)",
    ),
) -> None:
    """List collections.

    Examples:
        pharos collection list
        pharos collection list --query "machine learning"
        pharos collection list --page 2 --per-page 50
    """
    console = get_console()

    # Validate pagination
    if per_page < 1 or per_page > 100:
        console.print("[red]Error:[/red] Per page must be between 1 and 100")
        raise typer.Exit(1)

    try:
        client = get_collection_client()
        skip = (page - 1) * per_page

        result = client.list(
            skip=skip,
            limit=per_page,
            query=query,
        )

        # Format output
        formatter = get_formatter(output_format)

        if output_format == "quiet":
            # Just print IDs
            for item in result.items:
                print(item.get("id", ""))
        elif output_format == "json":
            output = {
                "items": result.items,
                "total": result.total,
                "page": result.page,
                "per_page": result.per_page,
                "has_more": result.has_more,
            }
            print(formatter.format(output))
        else:
            # Table or CSV
            if not result.items:
                console.print("[yellow]No collections found.[/yellow]")
                return

            # Add computed fields for display
            display_items = []
            for item in result.items:
                display_item = dict(item)
                # Format resource count
                if "resource_count" in display_item:
                    display_item["resources"] = format_number(display_item["resource_count"])
                    del display_item["resource_count"]
                # Format visibility
                if "is_public" in display_item:
                    display_item["public"] = "Yes" if display_item["is_public"] else "No"
                    del display_item["is_public"]
                # Truncate description
                if "description" in display_item and display_item["description"]:
                    display_item["description"] = truncate(display_item["description"], 50)
                display_items.append(display_item)

            print(formatter.format_list(display_items))

            # Show pagination info
            console.print(f"\n[dim]Showing {len(result.items)} of {result.total} collections[/dim]")
            if result.has_more:
                console.print(f"[dim]Use --page {page + 1} for next page[/dim]")

    except APIError as e:
        console.print(f"[red]API Error:[/red] {e.message}")
        raise typer.Exit(1)
    except NetworkError as e:
        console.print(f"[red]Network Error:[/red] {e}")
        raise typer.Exit(1)


@collection_app.command("show")
def show_collection(
    collection_id: int = typer.Argument(
        ...,
        help="Collection ID to show",
    ),
    output_format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (json, table, tree)",
    ),
    show_contents: bool = typer.Option(
        False,
        "--contents",
        "-c",
        help="Show resources in the collection",
    ),
    contents_limit: int = typer.Option(
        10,
        "--contents-limit",
        help="Number of resources to show when using --contents",
    ),
) -> None:
    """Show collection details.

    Examples:
        pharos collection show 1
        pharos collection show 1 --format json
        pharos collection show 1 --contents
    """
    console = get_console()

    try:
        client = get_collection_client()
        collection = client.get(collection_id=collection_id)

        # Format output
        formatter = get_formatter(output_format)

        if output_format == "json":
            print(formatter.format(collection.model_dump()))
            return

        # Create display data
        display_data = {
            "ID": collection.id,
            "Name": collection.name,
            "Description": collection.description or "-",
            "Public": "Yes" if collection.is_public else "No",
            "Resources": format_number(collection.resource_count),
            "Created At": collection.created_at or "-",
            "Updated At": collection.updated_at or "-",
        }

        if output_format == "tree":
            print(formatter.format({"Collection": display_data}))
        else:
            print(formatter.format(display_data))

        # Show contents if requested
        if show_contents:
            console.print(f"\n[bold]Resources in Collection:[/bold]")

            contents = client.get_contents(
                collection_id=collection_id,
                limit=contents_limit,
            )

            if not contents.items:
                console.print("[yellow]No resources in this collection.[/yellow]")
            else:
                # Create resources table
                table = Table(show_header=True, header_style="bold magenta")
                table.add_column("ID", justify="right", style="dim")
                table.add_column("Title")
                table.add_column("Type", style="dim")
                table.add_column("Quality", justify="right")

                for item in contents.items:
                    quality = item.get("quality_score")
                    quality_str = format_score(quality) if quality else "-"
                    table.add_row(
                        str(item.get("id", "")),
                        truncate(item.get("title", ""), 40),
                        item.get("resource_type", "-") or "-",
                        quality_str,
                    )

                console.print(table)

                if contents.has_more:
                    console.print(f"\n[dim]Showing {len(contents.items)} of {contents.total} resources[/dim]")
                    console.print(f"[dim]Use --contents-limit {contents_limit * 2} to see more[/dim]")

    except CollectionNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except APIError as e:
        console.print(f"[red]API Error:[/red] {e.message}")
        raise typer.Exit(1)
    except NetworkError as e:
        console.print(f"[red]Network Error:[/red] {e}")
        raise typer.Exit(1)


@collection_app.command("add")
def add_resource_to_collection(
    collection_id: int = typer.Argument(
        ...,
        help="Collection ID",
    ),
    resource_id: int = typer.Argument(
        ...,
        help="Resource ID to add",
    ),
) -> None:
    """Add a resource to a collection.

    Examples:
        pharos collection add 1 5
        pharos collection add 1 5 --collection 2
    """
    console = get_console()

    try:
        client = get_collection_client()
        result = client.add_resource(
            collection_id=collection_id,
            resource_id=resource_id,
        )

        console.print(f"[green]Resource {resource_id} added to collection {collection_id} successfully![/green]")

    except CollectionNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except ResourceNotFoundError as e:
        console.print(f"[red]Error:[/red] Resource {resource_id} not found")
        raise typer.Exit(1)
    except APIError as e:
        console.print(f"[red]API Error:[/red] {e.message}")
        raise typer.Exit(1)
    except NetworkError as e:
        console.print(f"[red]Network Error:[/red] {e}")
        raise typer.Exit(1)


@collection_app.command("remove")
def remove_resource_from_collection(
    collection_id: int = typer.Argument(
        ...,
        help="Collection ID",
    ),
    resource_id: int = typer.Argument(
        ...,
        help="Resource ID to remove",
    ),
) -> None:
    """Remove a resource from a collection.

    Examples:
        pharos collection remove 1 5
    """
    console = get_console()

    try:
        client = get_collection_client()
        result = client.remove_resource(
            collection_id=collection_id,
            resource_id=resource_id,
        )

        console.print(f"[green]Resource {resource_id} removed from collection {collection_id} successfully![/green]")

    except CollectionNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except APIError as e:
        console.print(f"[red]API Error:[/red] {e.message}")
        raise typer.Exit(1)
    except NetworkError as e:
        console.print(f"[red]Network Error:[/red] {e}")
        raise typer.Exit(1)


@collection_app.command("update")
def update_collection(
    collection_id: int = typer.Argument(
        ...,
        help="Collection ID to update",
    ),
    name: Optional[str] = typer.Option(
        None,
        "--name",
        "-n",
        help="New name for the collection",
    ),
    description: Optional[str] = typer.Option(
        None,
        "--description",
        "-d",
        help="New description for the collection",
    ),
    public: Optional[bool] = typer.Option(
        None,
        "--public/--private",
        help="Make the collection public or private",
    ),
) -> None:
    """Update collection metadata.

    Examples:
        pharos collection update 1 --name "New Name"
        pharos collection update 1 --description "New description" --public
    """
    console = get_console()

    # Check if at least one update field is provided
    if all(x is None for x in [name, description, public]):
        console.print("[red]Error:[/red] Must specify at least one field to update (--name, --description, --public/--private)")
        raise typer.Exit(1)

    try:
        client = get_collection_client()
        collection = client.update(
            collection_id=collection_id,
            name=name,
            description=description,
            is_public=public,
        )

        console.print(f"[green]Collection updated successfully![/green]")
        console.print(f"  ID: {collection.id}")
        console.print(f"  Name: {collection.name}")
        if collection.description:
            console.print(f"  Description: {collection.description}")
        console.print(f"  Public: {collection.is_public}")

    except CollectionNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except APIError as e:
        console.print(f"[red]API Error:[/red] {e.message}")
        raise typer.Exit(1)
    except NetworkError as e:
        console.print(f"[red]Network Error:[/red] {e}")
        raise typer.Exit(1)


@collection_app.command("delete")
def delete_collection(
    collection_id: int = typer.Argument(
        ...,
        help="Collection ID to delete",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Skip confirmation prompt",
    ),
) -> None:
    """Delete a collection by ID.

    Examples:
        pharos collection delete 1
        pharos collection delete 1 --force
    """
    console = get_console()

    # Get collection info for confirmation
    try:
        client = get_collection_client()
        collection = client.get(collection_id=collection_id)
        collection_name = collection.name
    except CollectionNotFoundError:
        console.print(f"[red]Error:[/red] Collection {collection_id} not found")
        raise typer.Exit(1)
    except (APIError, NetworkError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    # Confirmation prompt
    if not force:
        console.print(Panel(
            f"[yellow]Are you sure you want to delete collection {collection_id}?[/yellow]\n\n"
            f"  Name: {collection_name}\n"
            f"  Resources: {collection.resource_count}\n\n"
            f"[red]This action cannot be undone![/red]",
            title="Confirm Deletion",
            border_style="red",
        ))

        if not typer.confirm("Do you want to continue?"):
            console.print("[yellow]Deletion cancelled.[/yellow]")
            raise typer.Exit(0)

    try:
        result = client.delete(collection_id=collection_id)
        console.print(f"[green]Collection {collection_id} deleted successfully![/green]")

    except CollectionNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except APIError as e:
        console.print(f"[red]API Error:[/red] {e.message}")
        raise typer.Exit(1)
    except NetworkError as e:
        console.print(f"[red]Network Error:[/red] {e}")
        raise typer.Exit(1)


@collection_app.command("export")
def export_collection(
    collection_id: int = typer.Argument(
        ...,
        help="Collection ID to export",
    ),
    format: str = typer.Option(
        "json",
        "--format",
        "-f",
        help="Export format (json, csv, zip)",
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file path (default: stdout)",
    ),
) -> None:
    """Export a collection.

    Examples:
        pharos collection export 1
        pharos collection export 1 --format zip --output collection.zip
        pharos collection export 1 --format json --output collection.json
    """
    console = get_console()

    try:
        client = get_collection_client()
        result = client.export(collection_id=collection_id, format=format)

        if output:
            # Write to file
            import os
            os.makedirs(os.path.dirname(output) or ".", exist_ok=True)

            if format == "json":
                with open(output, "w") as f:
                    json.dump(result, f, indent=2)
            else:
                # For zip or binary formats, result might be a download URL
                with open(output, "wb") as f:
                    f.write(result.content if hasattr(result, "content") else result)

            console.print(f"[green]Collection exported to {output}[/green]")
        else:
            # Print to stdout
            formatter = get_formatter("json")
            print(formatter.format(result))

    except CollectionNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except APIError as e:
        console.print(f"[red]API Error:[/red] {e.message}")
        raise typer.Exit(1)
    except NetworkError as e:
        console.print(f"[red]Network Error:[/red] {e}")
        raise typer.Exit(1)
    except IOError as e:
        console.print(f"[red]Error:[/red] Could not write to file: {e}")
        raise typer.Exit(1)


@collection_app.command("stats")
def collection_stats(
    collection_id: int = typer.Argument(
        ...,
        help="Collection ID to get stats for",
    ),
    output_format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (json, table)",
    ),
) -> None:
    """Get statistics for a collection.

    Examples:
        pharos collection stats 1
        pharos collection stats 1 --format json
    """
    console = get_console()

    try:
        client = get_collection_client()
        stats = client.get_stats(collection_id=collection_id)

        formatter = get_formatter(output_format)

        if output_format == "json":
            print(formatter.format(stats))
            return

        # Create stats table
        table = Table(title=f"Statistics for Collection {collection_id}")
        table.add_column("Metric", style="bold")
        table.add_column("Value", justify="right")

        for key, value in stats.items():
            # Format key for display
            display_key = key.replace("_", " ").title()
            # Format value
            if isinstance(value, float):
                display_value = f"{value:.2f}"
            else:
                display_value = str(value)
            table.add_row(display_key, display_value)

        console.print(table)

    except CollectionNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except APIError as e:
        console.print(f"[red]API Error:[/red] {e.message}")
        raise typer.Exit(1)
    except NetworkError as e:
        console.print(f"[red]Network Error:[/red] {e}")
        raise typer.Exit(1)