"""Annotation commands for Pharos CLI."""

import json
import sys
from pathlib import Path
from typing import Optional, List

import typer
from rich import print
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from rich.console import Console

from pharos_cli.client.api_client import get_api_client
from pharos_cli.client.annotation_client import AnnotationClient
from pharos_cli.client.exceptions import AnnotationNotFoundError, APIError, NetworkError
from pharos_cli.config.settings import load_config
from pharos_cli.formatters.base import get_formatter
from pharos_cli.utils.console import get_console
from pharos_cli.utils.validators import validate_limit, validate_per_page
from pharos_cli.utils.helpers import truncate, format_duration

annotation_app = typer.Typer(
    name="annotate",
    help="Annotation management commands for Pharos CLI",
)


@annotation_app.callback()
def annotation_callback():
    """Annotation management commands for Pharos CLI."""
    pass


def get_annotation_client() -> AnnotationClient:
    """Get an AnnotationClient instance."""
    config = load_config()
    api_client = get_api_client(config)
    return AnnotationClient(api_client)


@annotation_app.command("create")
def create_annotation(
    resource_id: int = typer.Argument(
        ...,
        help="Resource ID to annotate",
    ),
    text: str = typer.Option(
        ...,
        "--text",
        "-t",
        help="Annotation text (note or highlighted text)",
    ),
    annotation_type: str = typer.Option(
        "highlight",
        "--type",
        "-T",
        help="Annotation type (highlight, note, tag)",
    ),
    start_offset: Optional[int] = typer.Option(
        None,
        "--start",
        help="Start character offset in the resource (for highlights)",
    ),
    end_offset: Optional[int] = typer.Option(
        None,
        "--end",
        help="End character offset in the resource (for highlights)",
    ),
    tags: Optional[str] = typer.Option(
        None,
        "--tags",
        help="Tags for the annotation (comma-separated)",
    ),
) -> None:
    """Create a new annotation on a resource.

    Examples:
        pharos annotate create 1 --text "Important insight"
        pharos annotate create 1 --text "Key concept" --type note --tags important,review
        pharos annotate create 1 --text "Highlighted text" --start 100 --end 150
    """
    console = get_console()

    # Parse tags
    tag_list = None
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    try:
        client = get_annotation_client()
        result = client.create(
            resource_id=resource_id,
            text=text,
            annotation_type=annotation_type,
            start_offset=start_offset,
            end_offset=end_offset,
            tags=tag_list,
        )
        console.print(f"[green]Annotation created successfully![/green]")
        console.print(f"  ID: {result['id']}")
        console.print(f"  Resource ID: {result['resource_id']}")
        console.print(f"  Type: {result['annotation_type']}")
        if result.get('tags'):
            console.print(f"  Tags: {', '.join(result['tags'])}")
    except APIError as e:
        console.print(f"[red]API Error:[/red] {e.message}")
        raise typer.Exit(1)
    except NetworkError as e:
        console.print(f"[red]Network Error:[/red] {e}")
        raise typer.Exit(1)


@annotation_app.command("list")
def list_annotations(
    resource_id: Optional[int] = typer.Option(
        None,
        "--resource",
        "-r",
        help="Resource ID to list annotations for (if not specified, lists all annotations)",
    ),
    include_shared: bool = typer.Option(
        False,
        "--shared",
        help="Include shared annotations from other users",
    ),
    tags: Optional[str] = typer.Option(
        None,
        "--tags",
        help="Filter by tags (comma-separated)",
    ),
    page: int = typer.Option(
        1,
        "--page",
        "-p",
        help="Page number (for all annotations)",
    ),
    per_page: int = typer.Option(
        25,
        "--per-page",
        help="Items per page (1-100, for all annotations)",
    ),
    output_format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (json, table, quiet)",
    ),
) -> None:
    """List annotations for a resource or all annotations.

    Examples:
        pharos annotate list --resource 1
        pharos annotate list --resource 1 --tags important,review
        pharos annotate list --page 2 --per-page 50
    """
    console = get_console()

    # Validate pagination
    try:
        page = validate_per_page(page)
        per_page = validate_per_page(per_page)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    # Parse tags
    tag_list = None
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    try:
        client = get_annotation_client()

        if resource_id is not None:
            # List annotations for a specific resource
            annotations = client.list_for_resource(
                resource_id=resource_id,
                include_shared=include_shared,
                tags=tag_list,
            )

            if not annotations:
                console.print(f"[yellow]No annotations found for resource {resource_id}.[/yellow]")
                return

            # Format output
            formatter = get_formatter(output_format)

            if output_format == "quiet":
                # Just print IDs
                for ann in annotations:
                    print(ann.get("id", ""))
            elif output_format == "json":
                print(formatter.format(annotations))
            else:
                # Table format
                display_items = []
                for ann in annotations:
                    display_item = dict(ann)
                    # Truncate long text
                    if "text" in display_item:
                        display_item["text"] = truncate(display_item["text"], 50)
                    display_items.append(display_item)

                print(formatter.format_list(display_items))
                console.print(f"\n[dim]Total annotations: {len(annotations)}[/dim]")

        else:
            # List all annotations with pagination
            offset = (page - 1) * per_page
            result = client.list_all(
                limit=per_page,
                offset=offset,
                sort_by="recent",
            )

            if not result.items:
                console.print("[yellow]No annotations found.[/yellow]")
                return

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
                # Table format
                display_items = []
                for item in result.items:
                    display_item = dict(item)
                    # Truncate long text
                    if "text" in display_item:
                        display_item["text"] = truncate(display_item["text"], 50)
                    display_items.append(display_item)

                print(formatter.format_list(display_items))

                # Show pagination info
                console.print(f"\n[dim]Showing {len(result.items)} of {result.total} annotations[/dim]")
                if result.has_more:
                    console.print(f"[dim]Use --page {page + 1} for next page[/dim]")

    except APIError as e:
        console.print(f"[red]API Error:[/red] {e.message}")
        raise typer.Exit(1)
    except NetworkError as e:
        console.print(f"[red]Network Error:[/red] {e}")
        raise typer.Exit(1)


@annotation_app.command("get")
def get_annotation(
    annotation_id: int = typer.Argument(
        ...,
        help="Annotation ID to retrieve",
    ),
    output_format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (json, table)",
    ),
) -> None:
    """Get annotation details by ID.

    Examples:
        pharos annotate get 1
        pharos annotate get 1 --format json
    """
    console = get_console()

    try:
        client = get_annotation_client()
        annotation = client.get(annotation_id=annotation_id)

        # Format output
        formatter = get_formatter(output_format)

        if output_format == "json":
            print(formatter.format(annotation.model_dump()))
            return

        # Create display data
        display_data = {
            "ID": annotation.id,
            "Resource ID": annotation.resource_id,
            "Text": annotation.text,
            "Type": annotation.annotation_type,
            "Tags": ", ".join(annotation.tags) if annotation.tags else "-",
            "Created At": annotation.created_at or "-",
            "Updated At": annotation.updated_at or "-",
        }

        if annotation.start_offset is not None:
            display_data["Start Offset"] = annotation.start_offset
        if annotation.end_offset is not None:
            display_data["End Offset"] = annotation.end_offset

        print(formatter.format(display_data))

    except AnnotationNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except APIError as e:
        console.print(f"[red]API Error:[/red] {e.message}")
        raise typer.Exit(1)
    except NetworkError as e:
        console.print(f"[red]Network Error:[/red] {e}")
        raise typer.Exit(1)


@annotation_app.command("update")
def update_annotation(
    annotation_id: int = typer.Argument(
        ...,
        help="Annotation ID to update",
    ),
    text: Optional[str] = typer.Option(
        None,
        "--text",
        "-t",
        help="New text for the annotation",
    ),
    annotation_type: Optional[str] = typer.Option(
        None,
        "--type",
        "-T",
        help="New annotation type",
    ),
    tags: Optional[str] = typer.Option(
        None,
        "--tags",
        help="New tags for the annotation (comma-separated)",
    ),
) -> None:
    """Update annotation metadata.

    Examples:
        pharos annotate update 1 --text "Updated note"
        pharos annotate update 1 --tags important,review,updated
    """
    console = get_console()

    # Check if at least one update field is provided
    if all(x is None for x in [text, annotation_type, tags]):
        console.print("[red]Error:[/red] Must specify at least one field to update (--text, --type, --tags)")
        raise typer.Exit(1)

    # Parse tags
    tag_list = None
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    try:
        client = get_annotation_client()
        annotation = client.update(
            annotation_id=annotation_id,
            text=text,
            annotation_type=annotation_type,
            tags=tag_list,
        )

        console.print(f"[green]Annotation updated successfully![/green]")
        console.print(f"  ID: {annotation.id}")
        console.print(f"  Resource ID: {annotation.resource_id}")
        console.print(f"  Text: {annotation.text}")
        console.print(f"  Type: {annotation.annotation_type}")
        if annotation.tags:
            console.print(f"  Tags: {', '.join(annotation.tags)}")

    except AnnotationNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except APIError as e:
        console.print(f"[red]API Error:[/red] {e.message}")
        raise typer.Exit(1)
    except NetworkError as e:
        console.print(f"[red]Network Error:[/red] {e}")
        raise typer.Exit(1)


@annotation_app.command("delete")
def delete_annotation(
    annotation_id: int = typer.Argument(
        ...,
        help="Annotation ID to delete",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Skip confirmation prompt",
    ),
) -> None:
    """Delete an annotation by ID.

    Examples:
        pharos annotate delete 1
        pharos annotate delete 1 --force
    """
    console = get_console()

    # Get annotation info for confirmation
    try:
        client = get_annotation_client()
        annotation = client.get(annotation_id=annotation_id)
        annotation_text = truncate(annotation.text, 50)
    except AnnotationNotFoundError:
        console.print(f"[red]Error:[/red] Annotation {annotation_id} not found")
        raise typer.Exit(1)
    except (APIError, NetworkError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    # Confirmation prompt
    if not force:
        console.print(Panel(
            f"[yellow]Are you sure you want to delete annotation {annotation_id}?[/yellow]\n\n"
            f"  Text: {annotation_text}\n"
            f"  Type: {annotation.annotation_type}\n"
            f"  Resource ID: {annotation.resource_id}\n\n"
            f"[red]This action cannot be undone![/red]",
            title="Confirm Deletion",
            border_style="red",
        ))

        if not typer.confirm("Do you want to continue?"):
            console.print("[yellow]Deletion cancelled.[/yellow]")
            raise typer.Exit(0)

    try:
        result = client.delete(annotation_id=annotation_id)
        console.print(f"[green]Annotation {annotation_id} deleted successfully![/green]")

    except AnnotationNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except APIError as e:
        console.print(f"[red]API Error:[/red] {e.message}")
        raise typer.Exit(1)
    except NetworkError as e:
        console.print(f"[red]Network Error:[/red] {e}")
        raise typer.Exit(1)


@annotation_app.command("search")
def search_annotations(
    query: str = typer.Argument(
        ...,
        help="Search query",
    ),
    search_type: str = typer.Option(
        "fulltext",
        "--type",
        "-T",
        help="Search type (fulltext, semantic, tags)",
    ),
    limit: int = typer.Option(
        50,
        "--limit",
        "-l",
        help="Maximum results (1-100 for fulltext, 1-50 for semantic)",
    ),
    match_all: bool = typer.Option(
        False,
        "--match-all",
        help="Match ALL tags (for tag search only)",
    ),
    output_format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (json, table, quiet)",
    ),
) -> None:
    """Search annotations by text, semantic meaning, or tags.

    Examples:
        pharos annotate search "machine learning"
        pharos annotate search "deep learning concepts" --type semantic
        pharos annotate search "important,review" --type tags --match-all
    """
    console = get_console()

    # Validate limit based on search type
    if search_type == "semantic" and (limit < 1 or limit > 50):
        console.print("[red]Error:[/red] Limit must be between 1 and 50 for semantic search")
        raise typer.Exit(1)
    elif search_type != "semantic" and (limit < 1 or limit > 100):
        console.print("[red]Error:[/red] Limit must be between 1 and 100")
        raise typer.Exit(1)

    try:
        client = get_annotation_client()

        if search_type == "fulltext":
            result = client.search_fulltext(query=query, limit=limit)
        elif search_type == "semantic":
            result = client.search_semantic(query=query, limit=limit)
        elif search_type == "tags":
            # Parse tags from query (comma-separated)
            tags = [t.strip() for t in query.split(",") if t.strip()]
            if not tags:
                console.print("[red]Error:[/red] Must specify at least one tag for tag search")
                raise typer.Exit(1)
            result = client.search_tags(tags=tags, match_all=match_all)
        else:
            console.print(f"[red]Error:[/red] Invalid search type: {search_type}")
            console.print("[yellow]Valid search types: fulltext, semantic, tags[/yellow]")
            raise typer.Exit(1)

        if not result.get("items"):
            console.print(f"[yellow]No annotations found for query: {query}[/yellow]")
            return

        # Format output
        formatter = get_formatter(output_format)

        if output_format == "quiet":
            # Just print IDs
            for item in result["items"]:
                print(item.get("id", ""))
        elif output_format == "json":
            print(formatter.format(result))
        else:
            # Table format
            display_items = []
            for item in result["items"]:
                display_item = dict(item)
                # Truncate long text
                if "text" in display_item:
                    display_item["text"] = truncate(display_item["text"], 50)
                if "highlighted_text" in display_item:
                    display_item["highlighted_text"] = truncate(display_item["highlighted_text"], 50)
                display_items.append(display_item)

            print(formatter.format_list(display_items))
            console.print(f"\n[dim]Found {len(result['items'])} annotations[/dim]")

    except APIError as e:
        console.print(f"[red]API Error:[/red] {e.message}")
        raise typer.Exit(1)
    except NetworkError as e:
        console.print(f"[red]Network Error:[/red] {e}")
        raise typer.Exit(1)


@annotation_app.command("export")
def export_annotations(
    resource_id: Optional[int] = typer.Option(
        None,
        "--resource",
        "-r",
        help="Resource ID to export annotations for (exports all annotations if not specified)",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file path (default: prints to stdout)",
    ),
    format: str = typer.Option(
        "markdown",
        "--format",
        "-f",
        help="Export format (markdown, json)",
    ),
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        help="Overwrite existing file",
    ),
) -> None:
    """Export annotations to a file or stdout.

    Examples:
        pharos annotate export --resource 1
        pharos annotate export --resource 1 --output ./annotations.md
        pharos annotate export --format json --output ./annotations.json
    """
    console = get_console()

    try:
        client = get_annotation_client()

        if format == "markdown":
            content = client.export_markdown(resource_id=resource_id)
        elif format == "json":
            data = client.export_json(resource_id=resource_id)
            content = json.dumps(data, indent=2, default=str)
        else:
            console.print(f"[red]Error:[/red] Invalid format: {format}")
            console.print("[yellow]Valid formats: markdown, json[/yellow]")
            raise typer.Exit(1)

        # Handle output
        if output is None:
            # Print to stdout
            print(content)
        else:
            # Write to file
            if output.exists() and not overwrite:
                console.print(f"[red]Error:[/red] File already exists: {output}")
                console.print("[yellow]Use --overwrite to replace existing file[/yellow]")
                raise typer.Exit(1)

            output.write_text(content, encoding="utf-8")
            console.print(f"[green]Annotations exported successfully![/green]")
            console.print(f"  Output file: {output}")
            if resource_id:
                console.print(f"  Resource ID: {resource_id}")
            console.print(f"  Format: {format}")

    except APIError as e:
        console.print(f"[red]API Error:[/red] {e.message}")
        raise typer.Exit(1)
    except NetworkError as e:
        console.print(f"[red]Network Error:[/red] {e}")
        raise typer.Exit(1)
    except IOError as e:
        console.print(f"[red]Error:[/red] Could not write to file: {e}")
        raise typer.Exit(1)


@annotation_app.command("import")
def import_annotations(
    file: Path = typer.Argument(
        ...,
        help="File containing annotations to import (JSON format)",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    resource_id: Optional[int] = typer.Option(
        None,
        "--resource",
        "-r",
        help="Resource ID to import annotations for (required if annotations don't have resource_id)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be imported without actually importing",
    ),
) -> None:
    """Import annotations from a JSON file.

    Examples:
        pharos annotate import ./annotations.json
        pharos annotate import ./annotations.json --resource 1
        pharos annotate import ./annotations.json --dry-run
    """
    console = get_console()

    try:
        # Read and parse JSON file
        content = file.read_text(encoding="utf-8")
        data = json.loads(content)

        # Handle different JSON formats
        if isinstance(data, list):
            annotations = data
        elif isinstance(data, dict) and "items" in data:
            annotations = data["items"]
        elif isinstance(data, dict) and "annotations" in data:
            annotations = data["annotations"]
        else:
            console.print("[red]Error:[/red] Invalid JSON format. Expected array of annotations or object with 'items' or 'annotations' key.")
            raise typer.Exit(1)

        if not annotations:
            console.print("[yellow]No annotations found in file.[/yellow]")
            return

        if dry_run:
            console.print(f"[yellow]Dry run mode - {len(annotations)} annotations would be imported[/yellow]")
            for i, ann in enumerate(annotations[:10], 1):
                ann_id = ann.get("id", "new")
                text = truncate(ann.get("text", ""), 50)
                console.print(f"  {i}. ID: {ann_id}, Text: {text}")
            if len(annotations) > 10:
                console.print(f"  ... and {len(annotations) - 10} more")
            return

        # Import annotations
        client = get_annotation_client()
        successful = 0
        failed = 0
        errors = []

        console.print(f"[bold]Importing {len(annotations)} annotations...[/bold]")

        for ann in annotations:
            try:
                # Extract annotation data
                ann_text = ann.get("text", "")
                if not ann_text:
                    errors.append(f"Missing 'text' field in annotation: {ann.get('id', 'unknown')}")
                    failed += 1
                    continue

                # Determine resource ID
                ann_resource_id = ann.get("resource_id")
                if ann_resource_id is None:
                    if resource_id is None:
                        errors.append(f"Missing 'resource_id' in annotation and no --resource specified: {ann.get('id', 'unknown')}")
                        failed += 1
                        continue
                    ann_resource_id = resource_id

                # Create annotation
                result = client.create(
                    resource_id=ann_resource_id,
                    text=ann_text,
                    annotation_type=ann.get("annotation_type", "highlight"),
                    start_offset=ann.get("start_offset"),
                    end_offset=ann.get("end_offset"),
                    tags=ann.get("tags"),
                )
                successful += 1

            except APIError as e:
                errors.append(f"API Error for annotation {ann.get('id', 'unknown')}: {e.message}")
                failed += 1
            except Exception as e:
                errors.append(f"Error for annotation {ann.get('id', 'unknown')}: {str(e)}")
                failed += 1

        # Print summary
        console.print(f"\n[bold]Import Summary[/bold]")
        console.print(f"  Total annotations: {len(annotations)}")
        console.print(f"  Successful: [green]{successful}[/green]")
        if failed > 0:
            console.print(f"  Failed: [red]{failed}[/red]")

        if errors:
            console.print(f"\n[yellow]Errors:[/yellow]")
            for error in errors[:5]:  # Show first 5 errors
                console.print(f"  {error}")
            if len(errors) > 5:
                console.print(f"  ... and {len(errors) - 5} more errors")

    except json.JSONDecodeError as e:
        console.print(f"[red]Error:[/red] Invalid JSON file: {e}")
        raise typer.Exit(1)
    except IOError as e:
        console.print(f"[red]Error:[/red] Could not read file: {e}")
        raise typer.Exit(1)
    except APIError as e:
        console.print(f"[red]API Error:[/red] {e.message}")
        raise typer.Exit(1)
    except NetworkError as e:
        console.print(f"[red]Network Error:[/red] {e}")
        raise typer.Exit(1)