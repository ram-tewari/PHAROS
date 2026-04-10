"""Batch operations commands for Pharos CLI."""

import json
import os
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

import typer
from rich import print
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn
from rich.table import Table
from rich.console import Console

from pharos_cli.client.api_client import get_api_client
from pharos_cli.client.resource_client import ResourceClient
from pharos_cli.client.collection_client import CollectionClient
from pharos_cli.client.exceptions import (
    ResourceNotFoundError,
    CollectionNotFoundError,
    APIError,
    NetworkError,
)
from pharos_cli.config.settings import load_config
from pharos_cli.formatters.base import get_formatter
from pharos_cli.utils.console import get_console
from pharos_cli.utils.helpers import format_number, format_score, format_duration


@dataclass
class BatchResult:
    """Result of a batch operation."""
    total: int = 0
    successful: int = 0
    failed: int = 0
    skipped: int = 0
    errors: List[Dict] = field(default_factory=list)
    duration_seconds: float = 0.0


@dataclass
class DeleteResult:
    """Result of deleting a single resource."""
    resource_id: int
    success: bool
    error: Optional[str] = None


@dataclass
class UpdateResult:
    """Result of updating a single resource."""
    resource_id: int
    success: bool
    error: Optional[str] = None
    data: Optional[Dict] = None


batch_app = typer.Typer(
    name="batch",
    help="Batch operations for resources and collections",
)


@batch_app.callback()
def batch_callback():
    """Batch operations for resources and collections."""
    pass


def get_resource_client() -> ResourceClient:
    """Get a ResourceClient instance."""
    config = load_config()
    api_client = get_api_client(config)
    return ResourceClient(api_client)


def get_collection_client() -> CollectionClient:
    """Get a CollectionClient instance."""
    config = load_config()
    api_client = get_api_client(config)
    return CollectionClient(api_client)


def parse_ids(ids_string: str) -> List[int]:
    """Parse comma-separated IDs into a list of integers."""
    if not ids_string:
        return []
    
    ids = []
    for part in ids_string.split(","):
        part = part.strip()
        if part:
            try:
                ids.append(int(part))
            except ValueError:
                raise typer.BadParameter(f"Invalid ID: {part}. Must be an integer.")
    return ids


def load_update_file(file_path: Path) -> List[Dict[int, Dict[str, Any]]]:
    """Load update file and return list of (id, updates) tuples.
    
    File format:
    {
        "updates": [
            {"id": 1, "title": "New Title", "content": "New content"},
            {"id": 2, "title": "Another Title"}
        ]
    }
    
    Or:
    [
        {"id": 1, "title": "New Title"},
        {"id": 2, "title": "Another Title"}
    ]
    """
    if not file_path.exists():
        raise typer.BadParameter(f"Update file not found: {file_path}")
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise typer.BadParameter(f"Invalid JSON in update file: {e}")
    
    # Handle both formats
    if isinstance(data, dict) and "updates" in data:
        updates = data["updates"]
    elif isinstance(data, list):
        updates = data
    else:
        raise typer.BadParameter(
            "Update file must be a JSON object with 'updates' array or a JSON array."
        )
    
    # Validate and parse updates
    parsed = []
    for item in updates:
        if not isinstance(item, dict):
            raise typer.BadParameter("Each update must be a JSON object.")
        if "id" not in item:
            raise typer.BadParameter("Each update must have an 'id' field.")
        
        resource_id = item.pop("id")
        if not isinstance(resource_id, int):
            raise typer.BadParameter(f"Invalid ID type: {resource_id}. Must be an integer.")
        
        parsed.append((resource_id, item))
    
    return parsed


@batch_app.command("delete")
def batch_delete(
    ids: str = typer.Argument(
        ...,
        help="Comma-separated list of resource IDs to delete (e.g., '1,2,3' or '1 2 3')",
    ),
    workers: int = typer.Option(
        4,
        "--workers",
        "-w",
        help="Number of parallel workers (1-10)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be deleted without actually deleting",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Skip confirmation prompt for destructive operations",
    ),
    output_format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (json, table, quiet)",
    ),
) -> None:
    """Delete multiple resources in batch.
    
    Examples:
        pharos batch delete "1,2,3"
        pharos batch delete "1 2 3" --workers 8
        pharos batch delete "1,2,3" --dry-run
        pharos batch delete "1,2,3" --force
    """
    console = get_console()
    
    # Parse IDs
    resource_ids = parse_ids(ids)
    
    if not resource_ids:
        console.print("[red]Error:[/red] No valid resource IDs provided")
        raise typer.Exit(1)
    
    # Validate workers
    if workers < 1 or workers > 10:
        console.print("[red]Error:[/red] Workers must be between 1 and 10")
        raise typer.Exit(1)
    
    # Show what will be deleted in dry-run mode
    if dry_run:
        console.print(Panel(
            f"[bold]Dry Run - Resources to Delete:[/bold]\n\n"
            f"  Total: {len(resource_ids)}\n"
            f"  IDs: {', '.join(map(str, resource_ids))}\n\n"
            f"[dim]No changes will be made.[/dim]",
            title="Batch Delete (Dry Run)",
            border_style="yellow",
        ))
        return
    
    # Confirmation prompt
    if not force:
        console.print(Panel(
            f"[yellow]Are you sure you want to delete {len(resource_ids)} resources?[/yellow]\n\n"
            f"  IDs: {', '.join(map(str, resource_ids[:10]))}"
            f"{'...' if len(resource_ids) > 10 else ''}\n\n"
            f"[red]This action cannot be undone![/red]",
            title="Confirm Batch Delete",
            border_style="red",
        ))
        
        if not typer.confirm("Do you want to continue?"):
            console.print("[yellow]Batch delete cancelled.[/yellow]")
            raise typer.Exit(0)
    
    # Perform batch delete
    start_time = datetime.now()
    results: List[DeleteResult] = []
    
    def delete_single(resource_id: int) -> DeleteResult:
        """Delete a single resource."""
        try:
            client = get_resource_client()
            client.delete(resource_id=resource_id)
            return DeleteResult(resource_id=resource_id, success=True)
        except Exception as e:
            return DeleteResult(
                resource_id=resource_id,
                success=False,
                error=str(e)
            )
    
    # Execute with progress
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        transient=True,
    ) as progress:
        task = progress.add_task(
            f"Deleting {len(resource_ids)} resources...",
            total=len(resource_ids)
        )
        
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(delete_single, rid): rid
                for rid in resource_ids
            }
            
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                progress.update(task, advance=1)
    
    # Calculate results
    duration = (datetime.now() - start_time).total_seconds()
    successful = [r for r in results if r.success]
    failed = [r for r in results if not r.success]
    
    # Display results
    formatter = get_formatter(output_format)
    
    if output_format == "json":
        output = {
            "total": len(results),
            "successful": len(successful),
            "failed": len(failed),
            "duration_seconds": duration,
            "errors": [
                {"resource_id": r.resource_id, "error": r.error}
                for r in failed
            ]
        }
        print(formatter.format(output))
    elif output_format == "quiet":
        for r in successful:
            print(f"Deleted: {r.resource_id}")
        for r in failed:
            print(f"Failed: {r.resource_id} - {r.error}")
    else:
        # Table format
        if not results:
            console.print("[yellow]No results to display.[/yellow]")
            return
        
        table = Table(title="Batch Delete Results")
        table.add_column("Resource ID", justify="right", style="dim")
        table.add_column("Status", justify="center")
        table.add_column("Error", style="red")
        
        for r in results:
            if r.success:
                table.add_row(
                    str(r.resource_id),
                    "[green]✓ Deleted[/green]",
                    "-"
                )
            else:
                table.add_row(
                    str(r.resource_id),
                    "[red]✗ Failed[/red]",
                    r.error or "Unknown error"
                )
        
        console.print(table)
        
        # Summary
        console.print(f"\n[bold]Summary:[/bold]")
        console.print(f"  Total: {len(results)}")
        console.print(f"  [green]Successful: {len(successful)}[/green]")
        if failed:
            console.print(f"  [red]Failed: {len(failed)}[/red]")
        console.print(f"  Duration: {format_duration(duration)}")
        
        if failed:
            console.print(f"\n[yellow]Some resources could not be deleted.[/yellow]")
            console.print("[dim]They may have already been deleted or you may not have permission.[/dim]")


@batch_app.command("update")
def batch_update(
    file: Path = typer.Argument(
        ...,
        help="JSON file containing updates (see help for format)",
        exists=True,
        readable=True,
        file_okay=True,
        dir_okay=False,
    ),
    workers: int = typer.Option(
        4,
        "--workers",
        "-w",
        help="Number of parallel workers (1-10)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be updated without actually updating",
    ),
    output_format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (json, table, quiet)",
    ),
) -> None:
    """Update multiple resources from a JSON file.
    
    File format:
    {
        "updates": [
            {"id": 1, "title": "New Title", "content": "New content"},
            {"id": 2, "title": "Another Title", "language": "python"}
        ]
    }
    
    Or:
    [
        {"id": 1, "title": "New Title"},
        {"id": 2, "title": "Another Title"}
    ]
    
    Examples:
        pharos batch update updates.json
        pharos batch update updates.json --dry-run
        pharos batch update updates.json --workers 8
    """
    console = get_console()
    
    # Load updates from file
    try:
        updates = load_update_file(file)
    except typer.BadParameter as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    
    if not updates:
        console.print("[yellow]No updates found in file.[/yellow]")
        raise typer.Exit(0)
    
    # Validate workers
    if workers < 1 or workers > 10:
        console.print("[red]Error:[/red] Workers must be between 1 and 10")
        raise typer.Exit(1)
    
    # Show what will be updated in dry-run mode
    if dry_run:
        preview_items = []
        for resource_id, update_data in updates[:10]:
            preview_items.append({
                "id": resource_id,
                "updates": ", ".join(update_data.keys()) if update_data else "no changes"
            })
        
        preview_table = Table(title="Batch Update (Dry Run)")
        preview_table.add_column("Resource ID", justify="right", style="dim")
        preview_table.add_column("Fields to Update")
        
        for item in preview_items:
            preview_table.add_row(str(item["id"]), item["updates"])
        
        if len(updates) > 10:
            preview_table.add_row("...", f"... and {len(updates) - 10} more")
        
        console.print(Panel(
            f"[bold]Dry Run - Resources to Update:[/bold]\n\n",
            title="Batch Update (Dry Run)",
            border_style="yellow",
        ))
        console.print(preview_table)
        console.print(f"\n[dim]Total: {len(updates)} resources[/dim]")
        console.print(f"[dim]No changes will be made.[/dim]")
        return
    
    # Perform batch update
    start_time = datetime.now()
    results: List[UpdateResult] = []
    
    def update_single(resource_id: int, update_data: Dict[str, Any]) -> UpdateResult:
        """Update a single resource."""
        try:
            client = get_resource_client()
            result = client.update(resource_id=resource_id, **update_data)
            return UpdateResult(
                resource_id=resource_id,
                success=True,
                data=dict(result) if result else None
            )
        except Exception as e:
            return UpdateResult(
                resource_id=resource_id,
                success=False,
                error=str(e)
            )
    
    # Execute with progress
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        transient=True,
    ) as progress:
        task = progress.add_task(
            f"Updating {len(updates)} resources...",
            total=len(updates)
        )
        
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(update_single, rid, data): rid
                for rid, data in updates
            }
            
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                progress.update(task, advance=1)
    
    # Calculate results
    duration = (datetime.now() - start_time).total_seconds()
    successful = [r for r in results if r.success]
    failed = [r for r in results if not r.success]
    
    # Display results
    formatter = get_formatter(output_format)
    
    if output_format == "json":
        output = {
            "total": len(results),
            "successful": len(successful),
            "failed": len(failed),
            "duration_seconds": duration,
            "results": [
                {
                    "resource_id": r.resource_id,
                    "success": r.success,
                    "error": r.error,
                    "data": r.data
                }
                for r in results
            ]
        }
        print(formatter.format(output))
    elif output_format == "quiet":
        for r in successful:
            print(f"Updated: {r.resource_id}")
        for r in failed:
            print(f"Failed: {r.resource_id} - {r.error}")
    else:
        # Table format
        if not results:
            console.print("[yellow]No results to display.[/yellow]")
            return
        
        table = Table(title="Batch Update Results")
        table.add_column("Resource ID", justify="right", style="dim")
        table.add_column("Status", justify="center")
        table.add_column("Error", style="red")
        
        for r in results:
            if r.success:
                table.add_row(
                    str(r.resource_id),
                    "[green]✓ Updated[/green]",
                    "-"
                )
            else:
                table.add_row(
                    str(r.resource_id),
                    "[red]✗ Failed[/red]",
                    r.error or "Unknown error"
                )
        
        console.print(table)
        
        # Summary
        console.print(f"\n[bold]Summary:[/bold]")
        console.print(f"  Total: {len(results)}")
        console.print(f"  [green]Successful: {len(successful)}[/green]")
        if failed:
            console.print(f"  [red]Failed: {len(failed)}[/red]")
        console.print(f"  Duration: {format_duration(duration)}")
        
        if failed:
            console.print(f"\n[yellow]Some resources could not be updated.[/yellow]")


@batch_app.command("export")
def batch_export(
    collection_id: Optional[int] = typer.Option(
        None,
        "--collection",
        "-c",
        help="Collection ID to export (exports all resources in collection)",
    ),
    resource_ids: Optional[str] = typer.Option(
        None,
        "--ids",
        help="Comma-separated list of resource IDs to export (e.g., '1,2,3')",
    ),
    format: str = typer.Option(
        "json",
        "--format",
        "-f",
        help="Export format (json, csv, zip, markdown)",
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file or directory path (default: stdout for JSON/CSV, current dir for zip)",
    ),
    workers: int = typer.Option(
        4,
        "--workers",
        "-w",
        help="Number of parallel workers for fetching resources (1-10)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be exported without actually exporting",
    ),
    content_only: bool = typer.Option(
        False,
        "--content-only",
        help="Export only resource content, not metadata",
    ),
) -> None:
    """Export multiple resources to a file or ZIP archive.
    
    Examples:
        pharos batch export --collection 1
        pharos batch export --ids "1,2,3" --format zip
        pharos batch export --collection 1 --output ./exports/
        pharos batch export --ids "1,2,3" --dry-run
    """
    console = get_console()
    
    # Validate inputs
    if collection_id is None and resource_ids is None:
        console.print("[red]Error:[/red] Must specify --collection or --ids")
        raise typer.Exit(1)
    
    if collection_id is not None and resource_ids is not None:
        console.print("[red]Error:[/red] Cannot specify both --collection and --ids")
        raise typer.Exit(1)
    
    # Validate workers
    if workers < 1 or workers > 10:
        console.print("[red]Error:[/red] Workers must be between 1 and 10")
        raise typer.Exit(1)
    
    # Get resource IDs from collection or directly
    target_resource_ids: List[int] = []
    
    if collection_id is not None:
        try:
            client = get_collection_client()
            collection = client.get(collection_id=collection_id)
            collection_name = collection.name
            
            # Get all resources from collection
            contents = client.get_contents(collection_id=collection_id, limit=10000)
            target_resource_ids = [item.get("id") for item in contents.items if item.get("id")]
            
            if not target_resource_ids:
                console.print(f"[yellow]Collection '{collection_name}' has no resources to export.[/yellow]")
                raise typer.Exit(0)
            
            console.print(f"[dim]Collection: {collection_name} ({len(target_resource_ids)} resources)[/dim]")
            
        except CollectionNotFoundError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)
        except (APIError, NetworkError) as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)
    else:
        target_resource_ids = parse_ids(resource_ids)
        
        if not target_resource_ids:
            console.print("[red]Error:[/red] No valid resource IDs provided")
            raise typer.Exit(1)
    
    # Show what will be exported in dry-run mode
    if dry_run:
        console.print(Panel(
            f"[bold]Dry Run - Resources to Export:[/bold]\n\n"
            f"  Total: {len(target_resource_ids)}\n"
            f"  Format: {format}\n"
            f"  Content only: {'Yes' if content_only else 'No'}\n\n"
            f"[dim]No files will be created.[/dim]",
            title="Batch Export (Dry Run)",
            border_style="yellow",
        ))
        return
    
    # Fetch resources in parallel
    start_time = datetime.now()
    resources: List[Dict[str, Any]] = []
    errors: List[Dict] = []
    
    def fetch_single(resource_id: int) -> Dict[str, Any]:
        """Fetch a single resource."""
        try:
            client = get_resource_client()
            resource = client.get(resource_id=resource_id)
            return dict(resource)
        except Exception as e:
            return {"id": resource_id, "error": str(e)}
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        transient=True,
    ) as progress:
        task = progress.add_task(
            f"Fetching {len(target_resource_ids)} resources...",
            total=len(target_resource_ids)
        )
        
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(fetch_single, rid): rid
                for rid in target_resource_ids
            }
            
            for future in as_completed(futures):
                result = future.result()
                if "error" in result:
                    errors.append(result)
                else:
                    resources.append(result)
                progress.update(task, advance=1)
    
    # Export based on format
    duration = (datetime.now() - start_time).total_seconds()
    
    if format == "zip":
        _export_zip(resources, output, content_only, console, duration)
    elif format == "markdown":
        _export_markdown(resources, output, content_only, console, duration)
    elif format == "csv":
        _export_csv(resources, output, console, duration)
    else:
        _export_json(resources, output, console, duration)


def _export_json(
    resources: List[Dict[str, Any]],
    output: Optional[str],
    console: Console,
    duration: float,
) -> None:
    """Export resources as JSON."""
    export_data = {
        "exported_at": datetime.now().isoformat(),
        "total": len(resources),
        "resources": resources,
    }
    
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(export_data, f, indent=2, default=str)
        console.print(f"[green]Exported {len(resources)} resources to {output_path}[/green]")
    else:
        formatter = get_formatter("json")
        print(formatter.format(export_data))
    
    console.print(f"[dim]Duration: {format_duration(duration)}[/dim]")


def _export_csv(
    resources: List[Dict[str, Any]],
    output: Optional[str],
    console: Console,
    duration: float,
) -> None:
    """Export resources as CSV."""
    if not resources:
        console.print("[yellow]No resources to export.[/yellow]")
        return
    
    # Get all possible columns from first resource
    all_columns = set()
    for r in resources:
        all_columns.update(r.keys())
    all_columns = sorted(all_columns)
    
    # Build CSV content
    import io
    
    output_buffer = io.StringIO()
    writer = csv.DictWriter(output_buffer, fieldnames=all_columns)
    writer.writeheader()
    
    for r in resources:
        row = {col: str(r.get(col, "")) for col in all_columns}
        writer.writerow(row)
    
    csv_content = output_buffer.getvalue()
    
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(csv_content)
        console.print(f"[green]Exported {len(resources)} resources to {output_path}[/green]")
    else:
        print(csv_content)
    
    console.print(f"[dim]Duration: {format_duration(duration)}[/dim]")


def _export_markdown(
    resources: List[Dict[str, Any]],
    output: Optional[str],
    content_only: bool,
    console: Console,
    duration: float,
) -> None:
    """Export resources as Markdown files."""
    if not resources:
        console.print("[yellow]No resources to export.[/yellow]")
        return
    
    if output:
        output_dir = Path(output)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        for resource in resources:
            resource_id = resource.get("id", "unknown")
            title = resource.get("title", f"Resource {resource_id}")
            # Sanitize filename
            safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)[:50]
            filename = f"{resource_id}_{safe_title}.md"
            filepath = output_dir / filename
            
            content = _build_markdown(resource, content_only)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
        
        console.print(f"[green]Exported {len(resources)} resources to {output_dir}/[/green]")
    else:
        # Combine all into single markdown output
        combined = []
        for resource in resources:
            combined.append(_build_markdown(resource, content_only))
            combined.append("\n---\n\n")
        
        print("".join(combined))
    
    console.print(f"[dim]Duration: {format_duration(duration)}[/dim]")


def _build_markdown(resource: Dict[str, Any], content_only: bool) -> str:
    """Build markdown content for a resource."""
    lines = []
    
    if not content_only:
        lines.append(f"# {resource.get('title', 'Untitled')}")
        lines.append("")
        
        if resource.get("resource_type"):
            lines.append(f"**Type:** {resource['resource_type']}")
        if resource.get("language"):
            lines.append(f"**Language:** {resource['language']}")
        if resource.get("quality_score"):
            lines.append(f"**Quality Score:** {resource['quality_score']}")
        if resource.get("url"):
            lines.append(f"**URL:** {resource['url']}")
        if resource.get("created_at"):
            lines.append(f"**Created:** {resource['created_at']}")
        
        lines.append("")
        lines.append("## Content")
        lines.append("")
    
    if resource.get("content"):
        lines.append(resource["content"])
    else:
        lines.append("*No content available*")
    
    return "\n".join(lines)


def _export_zip(
    resources: List[Dict[str, Any]],
    output: Optional[str],
    content_only: bool,
    console: Console,
    duration: float,
) -> None:
    """Export resources as a ZIP archive."""
    if not resources:
        console.print("[yellow]No resources to export.[/yellow]")
        return
    
    import io
    
    output_path = Path(output) if output else Path(f"pharos_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip")
    
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for resource in resources:
            resource_id = resource.get("id", "unknown")
            title = resource.get("title", f"Resource {resource_id}")
            safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)[:50]
            
            if content_only:
                # Just the content
                content = resource.get("content", "")
                filename = f"{resource_id}_{safe_title}.txt"
                zf.writestr(filename, content)
            else:
                # Full JSON
                json_content = json.dumps(resource, indent=2, default=str)
                filename = f"{resource_id}_{safe_title}.json"
                zf.writestr(filename, json_content)
    
    console.print(f"[green]Exported {len(resources)} resources to {output_path}[/green]")
    console.print(f"[dim]Duration: {format_duration(duration)}[/dim]")


# Import csv module at module level
import csv