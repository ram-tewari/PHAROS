"""Code analysis commands for Pharos CLI."""

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional, List, Dict, Any

import typer
from rich import print
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from rich.tree import Tree
from rich.json import JSON
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn
from rich.console import Console

from pharos_cli.client.code_client import CodeClient
from pharos_cli.formatters import get_formatter
from pharos_cli.utils.console import get_console
from pharos_cli.utils.helpers import format_score, format_number, format_duration

code_app = typer.Typer(
    name="code",
    help="Code analysis and intelligence commands",
    add_completion=False,
)


@code_app.callback()
def code_callback():
    """Code analysis and intelligence commands."""
    pass


def get_code_client() -> CodeClient:
    """Get a code client instance.

    Returns:
        CodeClient instance.
    """
    from pharos_cli.client import SyncAPIClient
    from pharos_cli.config.settings import load_config, apply_env_overrides

    config = load_config()
    config = apply_env_overrides(config)
    profile = config.get_active_profile()

    api_client = SyncAPIClient(
        base_url=profile.api_url,
        api_key=profile.api_key,
    )
    return CodeClient(api_client)


@code_app.command("analyze")
def analyze_code(
    file: Path = typer.Argument(
        ...,
        help="Code file to analyze",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    output_format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (json, table, tree)",
    ),
    language: Optional[str] = typer.Option(
        None,
        "--language",
        "-l",
        help="Programming language (auto-detected if not specified)",
    ),
) -> None:
    """Analyze a code file for metrics and quality.

    Examples:
        pharos code analyze ./myfile.py
        pharos code analyze ./myfile.py --language python
        pharos code analyze ./myfile.py --format json
    """
    console = get_console()

    try:
        client = get_code_client()
        result = client.analyze_code(str(file), language=language)

        if output_format == "json":
            print(JSON(json.dumps(result, indent=2, default=str)).text)
            return

        # Create summary panel
        panel = Panel(
            f"[bold]File:[/bold] {result['file_name']}\n"
            f"[bold]Language:[/bold] {result['language']}\n\n"
            f"[bold]Metrics:[/bold]\n"
            f"  Total Lines: {result['metrics']['total_lines']}\n"
            f"  Code Lines: {result['metrics']['code_lines']}\n"
            f"  Comment Lines: {result['metrics']['comment_lines']}\n"
            f"  Blank Lines: {result['metrics']['blank_lines']}\n"
            f"  Code %: {result['metrics']['code_percentage']}%\n\n"
            f"[bold]Structure:[/bold]\n"
            f"  Functions: {result['structure']['function_count']}\n"
            f"  Classes: {result['structure']['class_count']}\n"
            f"  Imports: {result['structure']['import_count']}\n\n"
            f"[bold]Complexity Score:[/bold] {result['complexity_score']:.2f}\n"
            f"[bold]Estimated Quality:[/bold] {result['estimated_quality'].upper()}",
            title=f"Code Analysis: {file.name}",
            border_style="blue",
        )
        console.print(panel)

    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error analyzing code:[/red] {e}")
        raise typer.Exit(1)


@code_app.command("ast")
def show_ast(
    file: Path = typer.Argument(
        ...,
        help="Code file to extract AST from",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    format: str = typer.Option(
        "json",
        "--format",
        "-f",
        help="Output format (json, text)",
    ),
    output_file: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file path (default: print to stdout)",
    ),
) -> None:
    """Extract and display Abstract Syntax Tree from a code file.

    Examples:
        pharos code ast ./myfile.py
        pharos code ast ./myfile.py --format text
        pharos code ast ./myfile.py -o ast.json
    """
    console = get_console()

    try:
        client = get_code_client()
        result = client.get_ast(str(file), format=format)

        if output_file:
            if format == "json":
                output_file.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
            else:
                output_file.write_text(result.get("ast_text", ""), encoding="utf-8")
            console.print(f"[green]AST saved to {output_file}[/green]")
            return

        if format == "json":
            print(JSON(json.dumps(result, indent=2, default=str)).text)
        else:
            # Display as tree
            ast_data = result.get("ast", {})
            tree = Tree(f"AST: {file.name}")

            if "definitions" in ast_data:
                defs_tree = tree.add("Definitions")
                for defn in ast_data["definitions"]:
                    if defn["type"] == "class":
                        class_tree = defs_tree.add(f"[bold]Class:[/bold] {defn['name']}")
                        if defn.get("bases"):
                            class_tree.add(f"Bases: {', '.join(defn['bases'])}")
                    else:
                        func_tree = defs_tree.add(f"[bold]Function:[/bold] {defn['name']}")
                        if defn.get("parameters"):
                            func_tree.add(f"Params: {', '.join(defn['parameters'])}")

            with console.capture() as capture:
                console.print(tree)
            console.print(capture.get())

    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error extracting AST:[/red] {e}")
        raise typer.Exit(1)


@code_app.command("deps")
def show_dependencies(
    file: Path = typer.Argument(
        ...,
        help="Code file to analyze dependencies for",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    output_format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (json, table, tree)",
    ),
    transitive: bool = typer.Option(
        False,
        "--transitive",
        "-t",
        help="Include transitive dependencies (if available)",
    ),
) -> None:
    """Show dependencies for a code file.

    Examples:
        pharos code deps ./myfile.py
        pharos code deps ./myfile.py --format json
        pharos code deps ./myfile.py --transitive
    """
    console = get_console()

    try:
        client = get_code_client()
        result = client.get_dependencies(str(file), include_transitive=transitive)

        if output_format == "json":
            print(JSON(json.dumps(result, indent=2, default=str)).text)
            return

        # Create dependency tree
        tree = Tree(f"Dependencies: {result['file_name']}")

        # Add imports
        imports_tree = tree.add(f"Imports ({len(result['imports'])})")
        for imp in result["imports"][:30]:  # Limit display
            if imp.get("item"):
                imports_tree.add(f"[cyan]{imp['module']}[/cyan] -> [yellow]{imp['item']}[/yellow]")
            else:
                imports_tree.add(f"[cyan]{imp['module']}[/cyan]")

        if len(result['imports']) > 30:
            imports_tree.add(f"... and {len(result['imports']) - 30} more")

        # Add package dependencies
        if result["package_dependencies"]:
            pkg_tree = tree.add(f"Package Dependencies ({len(result['package_dependencies'])})")
            for pkg in result["package_dependencies"]:
                pkg_tree.add(f"[green]{pkg['dependency']}[/green] ({pkg['file']})")

        with console.capture() as capture:
            console.print(tree)
        console.print(capture.get())

        # Summary
        console.print(f"\n[dim]Total dependencies: {result['dependency_count']}[/dim]")

    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error getting dependencies:[/red] {e}")
        raise typer.Exit(1)


@code_app.command("chunk")
def chunk_code(
    file: Path = typer.Argument(
        ...,
        help="Code file to chunk",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    strategy: str = typer.Option(
        "semantic",
        "--strategy",
        "-s",
        help="Chunking strategy (semantic, fixed)",
    ),
    chunk_size: int = typer.Option(
        500,
        "--chunk-size",
        "-c",
        help="Target chunk size",
    ),
    overlap: int = typer.Option(
        50,
        "--overlap",
        "-o",
        help="Overlap between chunks",
    ),
    output_format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (json, table, tree)",
    ),
    output_file: Optional[Path] = typer.Option(
        None,
        "--output",
        "-w",
        help="Write chunks to file (one per line with --- separator)",
    ),
) -> None:
    """Chunk a code file for indexing.

    Examples:
        pharos code chunk ./myfile.py
        pharos code chunk ./myfile.py --strategy semantic --chunk-size 1000
        pharos code chunk ./myfile.py -o chunks.txt
    """
    console = get_console()

    # Validate parameters
    if chunk_size < 50 or chunk_size > 5000:
        console.print("[red]Error: --chunk-size must be between 50 and 5000[/red]")
        raise typer.Exit(1)

    if overlap < 0 or overlap >= chunk_size:
        console.print("[red]Error: --overlap must be non-negative and less than chunk-size[/red]")
        raise typer.Exit(1)

    if strategy not in ["semantic", "fixed"]:
        console.print("[red]Error: --strategy must be 'semantic' or 'fixed'[/red]")
        raise typer.Exit(1)

    try:
        client = get_code_client()
        result = client.chunk_code(
            str(file),
            strategy=strategy,
            chunk_size=chunk_size,
            overlap=overlap,
        )

        if output_file:
            # Write chunks to file
            chunks_text = f"---\n".join(result["chunks"][i]["content"] for i in range(len(result["chunks"])))
            output_file.write_text(chunks_text, encoding="utf-8")
            console.print(f"[green]Wrote {result['total_chunks']} chunks to {output_file}[/green]")
            return

        if output_format == "json":
            print(JSON(json.dumps(result, indent=2, default=str)).text)
            return

        # Create chunk summary
        console.print(f"[bold]Chunking Results for {file.name}[/bold]\n")
        console.print(f"Strategy: {result['strategy']}")
        console.print(f"Language: {result['language']}")
        console.print(f"Total Chunks: {result['total_chunks']}\n")

        if output_format == "tree":
            tree = Tree(f"Chunks ({result['total_chunks']})")
            for chunk in result["chunks"][:20]:  # Limit display
                chunk_tree = tree.add(f"Chunk {chunk['chunk_index']} (lines {chunk['start_line']}-{chunk['end_line']})")
                # Show first few lines
                content_preview = chunk["content"][:100].replace("\n", " ")
                if len(chunk["content"]) > 100:
                    content_preview += "..."
                chunk_tree.add(f"[dim]{content_preview}[/dim]")

            if len(result["chunks"]) > 20:
                tree.add(f"... and {len(result['chunks']) - 20} more chunks")

            with console.capture() as capture:
                console.print(tree)
            console.print(capture.get())
        else:
            # Table format
            table = Table(title="Code Chunks")
            table.add_column("Index", justify="right", style="bold")
            table.add_column("Lines", style="dim")
            table.add_column("Content Preview", style="dim")

            for chunk in result["chunks"][:50]:
                content_preview = chunk["content"][:60].replace("\n", " ")
                if len(chunk["content"]) > 60:
                    content_preview += "..."
                table.add_row(
                    str(chunk["chunk_index"]),
                    f"{chunk['start_line']}-{chunk['end_line']}",
                    content_preview,
                )

            if len(result["chunks"]) > 50:
                console.print(f"[dim]... and {len(result['chunks']) - 50} more chunks[/dim]")

            console.print(table)

    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error chunking code:[/red] {e}")
        raise typer.Exit(1)


@code_app.command("scan")
def scan_directory(
    directory: Path = typer.Argument(
        ...,
        help="Directory to scan for code files",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
    ),
    recursive: bool = typer.Option(
        True,
        "--recursive/--no-recursive",
        help="Scan subdirectories recursively",
    ),
    pattern: Optional[str] = typer.Option(
        None,
        "--pattern",
        "-p",
        help="File pattern to match (glob format, e.g., '*.py')",
    ),
    file_limit: int = typer.Option(
        1000,
        "--limit",
        "-l",
        help="Maximum number of files to process",
    ),
    workers: int = typer.Option(
        4,
        "--workers",
        "-w",
        help="Number of parallel workers (1-10)",
    ),
    output_format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (json, table, summary)",
    ),
) -> None:
    """Scan a directory for code files and analyze them.

    Examples:
        pharos code scan ./myproject/
        pharos code scan ./myproject/ --no-recursive
        pharos code scan ./myproject/ --pattern "*.py" --limit 100
        pharos code scan ./myproject/ --format json
    """
    console = get_console()

    # Validate workers
    if workers < 1 or workers > 10:
        console.print("[red]Error: --workers must be between 1 and 10[/red]")
        raise typer.Exit(1)

    # Validate file limit
    if file_limit < 1 or file_limit > 10000:
        console.print("[red]Error: --limit must be between 1 and 10000[/red]")
        raise typer.Exit(1)

    try:
        client = get_code_client()

        # Use progress bar for large scans
        start_time = time.time()

        if workers == 1:
            # Sequential scan
            result = client.scan_directory(
                str(directory),
                recursive=recursive,
                pattern=pattern,
                file_limit=file_limit,
            )
        else:
            # For parallel processing, we need to handle this differently
            # since scan_directory is already optimized
            result = client.scan_directory(
                str(directory),
                recursive=recursive,
                pattern=pattern,
                file_limit=file_limit,
            )

        elapsed_time = time.time() - start_time

        if output_format == "json":
            # Remove full file list from JSON output for brevity
            summary = {
                "directory": result["directory"],
                "recursive": result["recursive"],
                "total_files_scanned": result["total_files_scanned"],
                "total_lines_of_code": result["total_lines_of_code"],
                "language_distribution": result["language_distribution"],
                "scan_summary": result["scan_summary"],
                "files_analyzed": len([f for f in result["files"] if "error" not in f]),
                "files_with_errors": len([f for f in result["files"] if "error" in f]),
            }
            print(JSON(json.dumps(summary, indent=2, default=str)).text)
            return

        # Display summary
        console.print(f"[bold]Scan Results for {directory}[/bold]\n")
        console.print(f"Total Files Scanned: {result['total_files_scanned']}")
        console.print(f"Total Lines of Code: {format_number(result['total_lines_of_code'])}")
        console.print(f"Scan Time: {format_duration(elapsed_time)}")

        # Language distribution
        if result["language_distribution"]:
            console.print(f"\n[bold]Language Distribution:[/bold]")
            lang_table = Table(show_header=False, box=None)
            lang_table.add_column("Language", style="cyan")
            lang_table.add_column("Count", justify="right", style="green")
            for lang, count in sorted(result["language_distribution"].items(), key=lambda x: -x[1]):
                lang_table.add_row(lang, str(count))
            console.print(lang_table)

        # Scan summary
        if result["scan_summary"]:
            console.print(f"\n[bold]Scan Summary:[/bold]")
            summary = result["scan_summary"]
            if summary.get("largest_file"):
                console.print(f"  Largest File: {summary['largest_file']['file']} ({summary['largest_file']['lines']} lines)")
            if summary.get("most_common_language"):
                console.print(f"  Most Common Language: {summary['most_common_language']}")
            if summary.get("average_complexity"):
                console.print(f"  Average Complexity: {summary['average_complexity']:.2f}")

        # File list
        if output_format == "table":
            console.print(f"\n[bold]Files:[/bold]")
            table = Table()
            table.add_column("File", style="cyan")
            table.add_column("Language", style="blue")
            table.add_column("Lines", justify="right", style="green")
            table.add_column("Complexity", justify="right", style="yellow")

            files_with_data = [f for f in result["files"] if "error" not in f]
            for f in files_with_data[:100]:
                table.add_row(
                    f["file"][-50:] if len(f["file"]) > 50 else f["file"],
                    f.get("language", "-"),
                    str(f.get("lines", 0)),
                    f"{f.get('complexity', 0):.2f}",
                )

            if len(files_with_data) > 100:
                console.print(f"[dim]... and {len(files_with_data) - 100} more files[/dim]")

            console.print(table)

        # Errors
        errors = [f for f in result["files"] if "error" in f]
        if errors:
            console.print(f"\n[yellow]Errors ({len(errors)}):[/yellow]")
            for f in errors[:10]:
                console.print(f"  {f['file']}: {f['error']}")
            if len(errors) > 10:
                console.print(f"  ... and {len(errors) - 10} more")

    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except NotADirectoryError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error scanning directory:[/red] {e}")
        raise typer.Exit(1)


@code_app.command("languages")
def list_languages() -> None:
    """List supported programming languages.

    Examples:
        pharos code languages
    """
    console = get_console()

    languages = [
        ("python", "Python", "*.py"),
        ("javascript", "JavaScript", "*.js"),
        ("typescript", "TypeScript", "*.ts"),
        ("java", "Java", "*.java"),
        ("csharp", "C#", "*.cs"),
        ("cpp", "C++", "*.cpp, *.cc, *.cxx, *.hpp"),
        ("c", "C", "*.c, *.h"),
        ("go", "Go", "*.go"),
        ("rust", "Rust", "*.rs"),
        ("ruby", "Ruby", "*.rb"),
        ("php", "PHP", "*.php"),
        ("swift", "Swift", "*.swift"),
        ("kotlin", "Kotlin", "*.kt"),
        ("scala", "Scala", "*.scala"),
        ("r", "R", "*.r"),
        ("julia", "Julia", "*.jl"),
        ("shell", "Shell", "*.sh, *.bash, *.zsh"),
        ("html", "HTML", "*.html, *.htm"),
        ("css", "CSS", "*.css, *.scss"),
        ("sql", "SQL", "*.sql"),
        ("markdown", "Markdown", "*.md"),
        ("json", "JSON", "*.json"),
        ("yaml", "YAML", "*.yaml, *.yml"),
        ("xml", "XML", "*.xml"),
    ]

    table = Table(title="Supported Languages")
    table.add_column("Language", style="bold cyan")
    table.add_column("Display Name", style="blue")
    table.add_column("Extensions", style="yellow")

    for lang, display, ext in languages:
        table.add_row(lang, display, ext)

    console.print(table)


@code_app.command("stats")
def code_stats(
    file: Optional[Path] = typer.Argument(
        None,
        help="Code file to get stats for (default: all code files in current directory)",
        exists=False,
        file_okay=True,
        dir_okay=True,
        readable=True,
    ),
    recursive: bool = typer.Option(
        True,
        "--recursive/--no-recursive",
        help="Scan subdirectories recursively",
    ),
) -> None:
    """Show code statistics for a file or directory.

    Examples:
        pharos code stats ./myproject/
        pharos code stats ./myfile.py
    """
    console = get_console()

    try:
        client = get_code_client()

        if file and file.exists() and file.is_file():
            # Single file
            result = client.analyze_code(str(file))
            console.print(f"[bold]Code Statistics for {file.name}[/bold]\n")
            console.print(f"Language: {result['language']}")
            console.print(f"Total Lines: {result['metrics']['total_lines']}")
            console.print(f"Code Lines: {result['metrics']['code_lines']}")
            console.print(f"Comment Lines: {result['metrics']['comment_lines']}")
            console.print(f"Code Percentage: {result['metrics']['code_percentage']}%")
            console.print(f"Functions: {result['structure']['function_count']}")
            console.print(f"Classes: {result['structure']['class_count']}")
            console.print(f"Complexity Score: {result['complexity_score']}")
            console.print(f"Quality: {result['estimated_quality'].upper()}")
        else:
            # Directory
            target = str(file) if file else "."
            result = client.scan_directory(
                target,
                recursive=recursive,
                file_limit=10000,
            )

            console.print(f"[bold]Code Statistics for {result['directory']}[/bold]\n")
            console.print(f"Total Files: {result['total_files_scanned']}")
            console.print(f"Total Lines: {format_number(result['total_lines_of_code'])}")

            if result["language_distribution"]:
                console.print(f"\n[bold]By Language:[/bold]")
                for lang, count in sorted(result["language_distribution"].items(), key=lambda x: -x[1]):
                    console.print(f"  {lang}: {count} files")

            if result["scan_summary"]:
                console.print(f"\n[bold]Summary:[/bold]")
                summary = result["scan_summary"]
                if summary.get("largest_file"):
                    console.print(f"  Largest: {summary['largest_file']['file']} ({summary['largest_file']['lines']} lines)")
                if summary.get("average_complexity"):
                    console.print(f"  Avg Complexity: {summary['average_complexity']:.2f}")

    except (FileNotFoundError, NotADirectoryError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error getting stats:[/red] {e}")
        raise typer.Exit(1)