"""Graph commands for Pharos CLI."""

import json
from pathlib import Path
from typing import Optional

import typer
from rich import print
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree
from rich.json import JSON

from pharos_cli.client.graph_client import GraphClient
from pharos_cli.formatters import get_formatter
from pharos_cli.utils.console import get_console
from pharos_cli.utils.helpers import format_score, format_number

graph_app = typer.Typer(
    name="graph",
    help="Knowledge graph and citation commands",
    add_completion=False,
)


@graph_app.callback()
def graph_callback():
    """Knowledge graph and citation commands."""
    pass


def get_graph_client() -> GraphClient:
    """Get a graph client instance.

    Returns:
        GraphClient instance.
    """
    from pharos_cli.client import SyncAPIClient

    api_client = SyncAPIClient()
    return GraphClient(api_client)


def format_graph_output(
    graph_data: dict,
    output_format: str = "tree",
) -> str:
    """Format graph data for output.

    Args:
        graph_data: Graph data with nodes and edges.
        output_format: Output format (tree, json, table).

    Returns:
        Formatted string.
    """
    console = get_console()

    if output_format == "json":
        return JSON(json.dumps(graph_data, default=str)).text

    if output_format == "tree":
        tree = Tree("Knowledge Graph")

        # Add nodes
        nodes_tree = tree.add(f"Nodes ({len(graph_data.get('nodes', []))})")
        for node in graph_data.get("nodes", []):
            node_info = f"{node.get('title', node.get('id', 'Unknown'))}"
            if node.get("type"):
                node_info += f" [{node['type']}]"
            if node.get("quality_score"):
                node_info += f" (score: {format_score(node['quality_score'])})"
            nodes_tree.add(node_info)

        # Add edges
        edges_tree = tree.add(f"Edges ({len(graph_data.get('edges', []))})")
        for edge in graph_data.get("edges", []):
            edge_info = f"{edge.get('source', '?')} → {edge.get('target', '?')}"
            if edge.get("relationship_type"):
                edge_info += f" [{edge['relationship_type']}]"
            if edge.get("weight"):
                edge_info += f" (weight: {edge['weight']:.2f})"
            edges_tree.add(edge_info)

        # Render tree to string
        with console.capture() as capture:
            console.print(tree)
        return capture.get()

    # Table format
    formatter = get_formatter(output_format)
    return formatter.format_list(graph_data.get("nodes", []))


@graph_app.command()
def stats(
    output_format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (json, table)",
    ),
) -> None:
    """Show graph statistics.

    Examples:
        pharos graph stats
        pharos graph stats --format json
    """
    console = get_console()

    try:
        client = get_graph_client()
        stats_data = client.get_stats()

        if output_format == "json":
            print(JSON(json.dumps(stats_data, default=str)).text)
            return

        # Create stats table
        table = Table(title="Graph Statistics")
        table.add_column("Metric", style="bold")
        table.add_column("Value", justify="right")

        # Add stats
        stats_mapping = [
            ("Node Count", stats_data.get("node_count", 0)),
            ("Edge Count", stats_data.get("edge_count", 0)),
            ("Connected Components", stats_data.get("connected_components", 0)),
            ("Average Degree", stats_data.get("average_degree", 0)),
        ]

        for metric, value in stats_mapping:
            if isinstance(value, float):
                value = f"{value:.2f}"
            else:
                value = format_number(value)
            table.add_row(metric, value)

        console.print(table)

        # Show additional info if available
        if stats_data.get("entity_count"):
            console.print(f"\n[dim]Entity Count: {format_number(stats_data['entity_count'])}[/dim]")
        if stats_data.get("hypothesis_count"):
            console.print(f"[dim]Hypothesis Count: {format_number(stats_data['hypothesis_count'])}[/dim]")

    except Exception as e:
        console.print(f"[red]Error getting graph stats: {e}[/red]")
        raise typer.Exit(1)


@graph_app.command()
def citations(
    resource_id: int = typer.Argument(
        ...,
        help="Resource ID to get citations for",
    ),
    output_format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (json, table, tree)",
    ),
) -> None:
    """Show citations for a resource.

    Examples:
        pharos graph citations 1
        pharos graph citations 1 --format json
    """
    console = get_console()

    try:
        client = get_graph_client()
        citations_data = client.get_citations(resource_id)

        if output_format == "json":
            print(JSON(json.dumps(citations_data, default=str)).text)
            return

        citations_list = citations_data.get("citations", [])

        if not citations_list:
            console.print("[yellow]No citations found for this resource.[/yellow]")
            return

        if output_format == "tree":
            tree = Tree(f"Citations for Resource {resource_id}")
            for citation in citations_list:
                citation_tree = tree.add(f"Citation [{citation.get('marker', '?')}]")
                citation_tree.add(f"Context: ...{citation.get('context', 'N/A')}...")
                if citation.get("position"):
                    citation_tree.add(f"Position: {citation['position']}")
            print(tree)
            return

        # Table format
        formatter = get_formatter(output_format)
        display_items = []
        for cit in citations_list:
            display_item = dict(cit)
            # Truncate context
            if "context" in display_item and len(display_item["context"]) > 100:
                display_item["context"] = display_item["context"][:100] + "..."
            display_items.append(display_item)

        print(formatter.format_list(display_items))
        console.print(f"\n[dim]Total citations: {len(citations_list)}[/dim]")

    except Exception as e:
        console.print(f"[red]Error getting citations: {e}[/red]")
        raise typer.Exit(1)


@graph_app.command()
def related(
    resource_id: int = typer.Argument(
        ...,
        help="Resource ID to find related resources for",
    ),
    limit: int = typer.Option(
        10,
        "--limit",
        "-l",
        help="Maximum number of related resources (1-100)",
    ),
    output_format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (json, table, tree)",
    ),
) -> None:
    """Find related resources using graph embeddings.

    Examples:
        pharos graph related 1
        pharos graph related 1 --limit 20
        pharos graph related 1 --format json
    """
    console = get_console()

    if limit < 1 or limit > 100:
        console.print("[red]Error: --limit must be between 1 and 100[/red]")
        raise typer.Exit(1)

    try:
        client = get_graph_client()
        related_data = client.get_related(resource_id, limit=limit)

        if output_format == "json":
            print(JSON(json.dumps(related_data, default=str)).text)
            return

        similar_nodes = related_data.get("similar_nodes", [])

        if not similar_nodes:
            console.print("[yellow]No related resources found.[/yellow]")
            return

        if output_format == "tree":
            tree = Tree(f"Related Resources for {resource_id}")
            for node in similar_nodes:
                node_tree = tree.add(f"{node.get('title', node.get('node_id', 'Unknown'))}")
                node_tree.add(f"Similarity: {node.get('similarity', 0):.2%}")
                if node.get("type"):
                    node_tree.add(f"Type: {node['type']}")
            print(tree)
            return

        # Table format
        formatter = get_formatter(output_format)
        display_items = []
        for node in similar_nodes:
            display_item = dict(node)
            # Format similarity as percentage
            if "similarity" in display_item:
                display_item["similarity"] = f"{display_item['similarity']:.2%}"
            display_items.append(display_item)

        print(formatter.format_list(display_items))
        console.print(f"\n[dim]Found {len(similar_nodes)} related resources[/dim]")

    except Exception as e:
        console.print(f"[red]Error finding related resources: {e}[/red]")
        raise typer.Exit(1)


@graph_app.command()
def neighbors(
    resource_id: int = typer.Argument(
        ...,
        help="Resource ID to get neighbors for",
    ),
    limit: int = typer.Option(
        10,
        "--limit",
        "-l",
        help="Maximum number of neighbors (1-20)",
    ),
    output_format: str = typer.Option(
        "tree",
        "--format",
        "-f",
        help="Output format (json, table, tree)",
    ),
) -> None:
    """Get hybrid neighbors for mind-map visualization.

    Examples:
        pharos graph neighbors 1
        pharos graph neighbors 1 --limit 15
        pharos graph neighbors 1 --format json
    """
    console = get_console()

    if limit < 1 or limit > 20:
        console.print("[red]Error: --limit must be between 1 and 20[/red]")
        raise typer.Exit(1)

    try:
        client = get_graph_client()
        graph_data = client.get_neighbors(resource_id, limit=limit)

        if not graph_data.get("nodes"):
            console.print("[yellow]No neighbors found for this resource.[/yellow]")
            return

        output_str = format_graph_output(graph_data, output_format)
        if output_str.strip():
            console.print(output_str)

    except Exception as e:
        console.print(f"[red]Error getting neighbors: {e}[/red]")
        raise typer.Exit(1)


@graph_app.command()
def overview(
    limit: int = typer.Option(
        50,
        "--limit",
        "-l",
        help="Maximum edges to return (1-100)",
    ),
    threshold: float = typer.Option(
        0.7,
        "--threshold",
        "-t",
        help="Minimum vector similarity (0.0-1.0)",
    ),
    output_format: str = typer.Option(
        "tree",
        "--format",
        "-f",
        help="Output format (json, table, tree)",
    ),
) -> None:
    """Show global overview of strongest connections.

    Examples:
        pharos graph overview
        pharos graph overview --limit 100 --threshold 0.8
    """
    console = get_console()

    if limit < 1 or limit > 100:
        console.print("[red]Error: --limit must be between 1 and 100[/red]")
        raise typer.Exit(1)

    if threshold < 0.0 or threshold > 1.0:
        console.print("[red]Error: --threshold must be between 0.0 and 1.0[/red]")
        raise typer.Exit(1)

    try:
        client = get_graph_client()
        graph_data = client.get_overview(limit=limit, vector_threshold=threshold)

        if not graph_data.get("nodes"):
            console.print("[yellow]No connections found in the graph.[/yellow]")
            return

        output_str = format_graph_output(graph_data, output_format)
        if output_str.strip():
            console.print(output_str)

    except Exception as e:
        console.print(f"[red]Error getting graph overview: {e}[/red]")
        raise typer.Exit(1)


@graph_app.command()
def export(
    format: str = typer.Option(
        "graphml",
        "--format",
        "-f",
        help="Export format (graphml, json, csv)",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file path",
    ),
) -> None:
    """Export graph data.

    Examples:
        pharos graph export --format graphml -o graph.graphml
        pharos graph export --format json
    """
    console = get_console()

    valid_formats = ["graphml", "json", "csv"]
    if format not in valid_formats:
        console.print(f"[red]Error: Invalid format. Must be one of: {', '.join(valid_formats)}[/red]")
        raise typer.Exit(1)

    try:
        client = get_graph_client()
        export_data = client.export_graph(format=format)

        if output:
            if format == "json":
                content = json.dumps(export_data, indent=2, default=str)
            elif format == "csv":
                # Simple CSV export for nodes
                nodes = export_data.get("nodes", [])
                if nodes:
                    headers = nodes[0].keys()
                    lines = [",".join(headers)]
                    for node in nodes:
                        lines.append(",".join(str(node.get(h, "")) for h in headers))
                    content = "\n".join(lines)
                else:
                    content = ""
            else:
                # GraphML format - return as is
                content = str(export_data)

            output.write_text(content)
            console.print(f"[green]Graph exported to {output}[/green]")
        else:
            # Print to console
            if format == "json":
                print(JSON(json.dumps(export_data, indent=2, default=str)).text)
            else:
                print(export_data)

    except Exception as e:
        console.print(f"[red]Error exporting graph: {e}[/red]")
        raise typer.Exit(1)


@graph_app.command()
def contradictions() -> None:
    """Show detected contradictions in the knowledge graph.

    Examples:
        pharos graph contradictions
    """
    console = get_console()

    try:
        client = get_graph_client()
        contradictions_data = client.get_contradictions()

        contradictions_list = contradictions_data.get("contradictions", [])

        if not contradictions_list:
            console.print("[green]No contradictions found in the knowledge graph.[/green]")
            return

        console.print(f"[yellow]Found {len(contradictions_list)} contradiction(s):[/yellow]\n")

        for i, contr in enumerate(contradictions_list, 1):
            panel = Panel(
                f"[bold]Contradiction {i}[/bold]\n\n"
                f"Entity: {contr.get('entity', 'Unknown')}\n"
                f"Type: {contr.get('type', 'Unknown')}\n\n"
                f"[bold]Supporting Evidence:[/bold]\n"
                f"{contr.get('supporting_evidence', 'N/A')}\n\n"
                f"[bold]Contradicting Evidence:[/bold]\n"
                f"{contr.get('contradicting_evidence', 'N/A')}",
                title="Contradiction Detected",
                border_style="red",
            )
            console.print(panel)
            console.print()

    except Exception as e:
        console.print(f"[red]Error getting contradictions: {e}[/red]")
        raise typer.Exit(1)


@graph_app.command()
def discover(
    concept_a: str = typer.Argument(
        ...,
        help="Starting concept (A)",
    ),
    concept_c: str = typer.Argument(
        ...,
        help="Target concept (C)",
    ),
    limit: int = typer.Option(
        50,
        "--limit",
        "-l",
        help="Maximum hypotheses (1-100)",
    ),
    start_date: Optional[str] = typer.Option(
        None,
        "--start-date",
        help="Start date for time-slicing (YYYY-MM-DD)",
    ),
    end_date: Optional[str] = typer.Option(
        None,
        "--end-date",
        help="End date for time-slicing (YYYY-MM-DD)",
    ),
    output_format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (json, table)",
    ),
) -> None:
    """Discover hypotheses using ABC pattern (Literature-Based Discovery).

    Finds bridging concepts that connect concept A to concept C.

    Examples:
        pharos graph discover "machine learning" "drug discovery"
        pharos graph discover "AI" "healthcare" --limit 20
        pharos graph discover "neural networks" "biology" --start-date 2020-01-01
    """
    console = get_console()

    if limit < 1 or limit > 100:
        console.print("[red]Error: --limit must be between 1 and 100[/red]")
        raise typer.Exit(1)

    try:
        client = get_graph_client()
        result = client.discover_hypotheses(
            concept_a=concept_a,
            concept_c=concept_c,
            limit=limit,
            start_date=start_date,
            end_date=end_date,
        )

        hypotheses = result.get("hypotheses", [])

        if not hypotheses:
            console.print("[yellow]No hypotheses discovered.[/yellow]")
            return

        console.print(
            f"[bold]Hypotheses connecting '[cyan]{concept_a}[/cyan]' to '[cyan]{concept_c}[/cyan]':[/bold]\n"
        )

        if output_format == "json":
            print(JSON(json.dumps(result, indent=2, default=str)).text)
            return

        # Table format
        table = Table(title="Discovered Hypotheses")
        table.add_column("Bridging Concept", style="bold")
        table.add_column("Support", justify="right")
        table.add_column("Novelty", justify="right")
        table.add_column("Evidence", justify="right")

        for hyp in hypotheses:
            table.add_row(
                hyp.get("bridging_concept", "Unknown"),
                f"{hyp.get('support_strength', 0):.2%}",
                f"{hyp.get('novelty_score', 0):.2%}",
                str(hyp.get("evidence_count", 0)),
            )

        console.print(table)

        # Show execution time
        if result.get("execution_time"):
            console.print(f"\n[dim]Execution time: {result['execution_time']:.2f}s[/dim]")

    except Exception as e:
        console.print(f"[red]Error discovering hypotheses: {e}[/red]")
        raise typer.Exit(1)


@graph_app.command()
def centrality(
    top_n: Optional[int] = typer.Option(
        None,
        "--top",
        "-t",
        help="Show only top N nodes by centrality",
    ),
    output_format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (json, table)",
    ),
) -> None:
    """Show centrality scores for nodes in the graph.

    Examples:
        pharos graph centrality
        pharos graph centrality --top 20
        pharos graph centrality --format json
    """
    console = get_console()

    try:
        client = get_graph_client()
        centrality_data = client.get_centrality(top_n=top_n)

        if output_format == "json":
            print(JSON(json.dumps(centrality_data, indent=2, default=str)).text)
            return

        scores = centrality_data.get("scores", [])

        if not scores:
            console.print("[yellow]No centrality data available.[/yellow]")
            return

        # Table format
        table = Table(title="Centrality Scores")
        table.add_column("Node", style="bold")
        table.add_column("Type", justify="center")
        table.add_column("Degree", justify="right")
        table.add_column("Betweenness", justify="right")
        table.add_column("PageRank", justify="right")

        for score in scores:
            table.add_row(
                score.get("node", score.get("id", "Unknown")),
                score.get("type", "-"),
                f"{score.get('degree', 0)}",
                f"{score.get('betweenness', 0):.4f}",
                f"{score.get('pagerank', 0):.4f}",
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error getting centrality: {e}[/red]")
        raise typer.Exit(1)


@graph_app.command()
def entities(
    entity_type: Optional[str] = typer.Option(
        None,
        "--type",
        "-t",
        help="Filter by entity type (Concept, Person, Organization, Method)",
    ),
    name: Optional[str] = typer.Option(
        None,
        "--name",
        "-n",
        help="Filter by name (partial match)",
    ),
    limit: int = typer.Option(
        50,
        "--limit",
        "-l",
        help="Number of results (1-100)",
    ),
    output_format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (json, table)",
    ),
) -> None:
    """List entities in the knowledge graph.

    Examples:
        pharos graph entities
        pharos graph entities --type Concept
        pharos graph entities --name "gradient" --limit 20
    """
    console = get_console()

    if limit < 1 or limit > 100:
        console.print("[red]Error: --limit must be between 1 and 100[/red]")
        raise typer.Exit(1)

    try:
        client = get_graph_client()
        result = client.get_entities(
            entity_type=entity_type,
            name_contains=name,
            limit=limit,
        )

        if output_format == "json":
            print(JSON(json.dumps({
                "entities": result.items,
                "total": result.total,
                "has_more": result.has_more,
            }, indent=2, default=str)).text)
            return

        if not result.items:
            console.print("[yellow]No entities found.[/yellow]")
            return

        formatter = get_formatter(output_format)
        print(formatter.format_list(result.items))

        console.print(f"\n[dim]Showing {len(result.items)} of {result.total} entities[/dim]")
        if result.has_more:
            console.print(f"[dim]Use --limit to see more[/dim]")

    except Exception as e:
        console.print(f"[red]Error getting entities: {e}[/red]")
        raise typer.Exit(1)


@graph_app.command()
def traverse(
    entity_id: str = typer.Argument(
        ...,
        help="Starting entity ID",
    ),
    relation_types: Optional[str] = typer.Option(
        None,
        "--relations",
        "-r",
        help="Comma-separated relation types to follow",
    ),
    max_hops: int = typer.Option(
        2,
        "--hops",
        "-h",
        help="Maximum traversal depth (1-5)",
    ),
    output_format: str = typer.Option(
        "tree",
        "--format",
        "-f",
        help="Output format (json, tree)",
    ),
) -> None:
    """Traverse the knowledge graph from an entity.

    Examples:
        pharos graph traverse entity-uuid-1
        pharos graph traverse entity-uuid-1 --relations EXTENDS,SUPPORTS --hops 3
    """
    console = get_console()

    if max_hops < 1 or max_hops > 5:
        console.print("[red]Error: --hops must be between 1 and 5[/red]")
        raise typer.Exit(1)

    try:
        client = get_graph_client()

        rel_list = None
        if relation_types:
            rel_list = [r.strip() for r in relation_types.split(",") if r.strip()]

        result = client.traverse_graph(
            start_entity_id=entity_id,
            relation_types=rel_list,
            max_hops=max_hops,
        )

        if output_format == "json":
            print(JSON(json.dumps(result, indent=2, default=str)).text)
            return

        # Tree format
        start_entity = result.get("start_entity", {})
        tree = Tree(f"Traversal from [bold]{start_entity.get('name', entity_id)}[/bold]")

        entities_by_hop = result.get("traversal_info", {}).get("entities_by_hop", {})

        for hop in range(max_hops):
            hop_key = str(hop)
            if hop_key in entities_by_hop:
                hop_entities = entities_by_hop[hop_key]
                hop_tree = tree.add(f"Hop {hop}")
                for entity in hop_entities:
                    entity_tree = hop_tree.add(f"{entity.get('name', entity.get('id', 'Unknown'))}")
                    if entity.get("type"):
                        entity_tree.add(f"Type: {entity['type']}")
                    if entity.get("description"):
                        desc = entity["description"]
                        if len(desc) > 50:
                            desc = desc[:50] + "..."
                        entity_tree.add(f"Description: {desc}")

        print(tree)

        # Show summary
        traversal_info = result.get("traversal_info", {})
        console.print(
            f"\n[dim]Total entities: {traversal_info.get('total_entities', 'N/A')}, "
            f"relationships: {traversal_info.get('total_relationships', 'N/A')}[/dim]"
        )

    except Exception as e:
        console.print(f"[red]Error traversing graph: {e}[/red]")
        raise typer.Exit(1)


@graph_app.command()
def embeddings(
    algorithm: str = typer.Option(
        "node2vec",
        "--algorithm",
        "-a",
        help="Algorithm (node2vec, deepwalk)",
    ),
    dimensions: int = typer.Option(
        128,
        "--dimensions",
        "-d",
        help="Embedding dimensionality (32-512)",
    ),
    walk_length: int = typer.Option(
        80,
        "--walk-length",
        help="Length of random walks (10-200)",
    ),
    num_walks: int = typer.Option(
        10,
        "--num-walks",
        help="Number of walks per node (1-100)",
    ),
) -> None:
    """Generate graph embeddings.

    Examples:
        pharos graph embeddings
        pharos graph embeddings --algorithm deepwalk --dimensions 256
    """
    console = get_console()

    if dimensions < 32 or dimensions > 512:
        console.print("[red]Error: --dimensions must be between 32 and 512[/red]")
        raise typer.Exit(1)

    if walk_length < 10 or walk_length > 200:
        console.print("[red]Error: --walk-length must be between 10 and 200[/red]")
        raise typer.Exit(1)

    if num_walks < 1 or num_walks > 100:
        console.print("[red]Error: --num-walks must be between 1 and 100[/red]")
        raise typer.Exit(1)

    valid_algorithms = ["node2vec", "deepwalk"]
    if algorithm not in valid_algorithms:
        console.print(f"[red]Error: Invalid algorithm. Must be one of: {', '.join(valid_algorithms)}[/red]")
        raise typer.Exit(1)

    try:
        client = get_graph_client()
        result = client.generate_embeddings(
            algorithm=algorithm,
            dimensions=dimensions,
            walk_length=walk_length,
            num_walks=num_walks,
        )

        console.print("[green]Graph embeddings generated successfully![/green]\n")

        table = Table()
        table.add_column("Metric", style="bold")
        table.add_column("Value", justify="right")

        table.add_row("Embeddings Computed", str(result.get("embeddings_computed", "N/A")))
        table.add_row("Dimensions", str(result.get("dimensions", dimensions)))
        table.add_row("Execution Time", f"{result.get('execution_time', 0):.2f}s")

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error generating embeddings: {e}[/red]")
        raise typer.Exit(1)