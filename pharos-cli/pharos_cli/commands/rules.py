"""Rules triage commands for Pharos CLI (Phase 6 Feedback Loop)."""

from typing import Optional

import typer
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.json import JSON as RichJSON

from pharos_cli.client.rules_client import RulesClient
from pharos_cli.utils.console import get_console

rules_app = typer.Typer(
    name="rules",
    help="Manage auto-extracted coding rules (feedback loop)",
    add_completion=False,
)


@rules_app.callback()
def rules_callback():
    """Manage auto-extracted coding rules."""
    pass


def _get_rules_client() -> RulesClient:
    from pharos_cli.client import SyncAPIClient

    api_client = SyncAPIClient()
    return RulesClient(api_client)


# ============================================================================
# pharos rules list
# ============================================================================


@rules_app.command("list")
def list_rules(
    status: Optional[str] = typer.Option(
        None,
        "--status",
        "-s",
        help="Filter by status: PENDING_REVIEW, ACTIVE, REJECTED",
    ),
    limit: int = typer.Option(50, "--limit", "-n", help="Max rules to fetch"),
) -> None:
    """List proposed rules with optional status filter."""
    console = get_console()
    client = _get_rules_client()

    try:
        rules = client.list_rules(status=status, limit=limit)
    except Exception as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)

    if not rules:
        console.print("[dim]No rules found.[/dim]")
        return

    table = Table(title="Proposed Rules", show_lines=True)
    table.add_column("ID", style="dim", max_width=12)
    table.add_column("Name", style="bold")
    table.add_column("Repo")
    table.add_column("File")
    table.add_column("Confidence", justify="right")
    table.add_column("Status")

    status_colors = {
        "PENDING_REVIEW": "yellow",
        "ACTIVE": "green",
        "REJECTED": "red",
    }

    for r in rules:
        color = status_colors.get(r.get("status", ""), "white")
        table.add_row(
            str(r["id"])[:8] + "...",
            r["rule_name"],
            r["repository"],
            r["file_path"],
            f"{r['confidence']:.0%}",
            f"[{color}]{r['status']}[/{color}]",
        )

    console.print(table)


# ============================================================================
# pharos rules review
# ============================================================================


@rules_app.command("review")
def review_rules() -> None:
    """
    Interactive triage of pending rules.

    Fetches all PENDING_REVIEW rules, displays each one with its diff
    and extracted schema, and prompts to Accept (Y) or Reject (N).
    """
    console = get_console()
    client = _get_rules_client()

    try:
        rules = client.list_rules(status="PENDING_REVIEW")
    except Exception as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)

    if not rules:
        console.print("[green]No pending rules to review.[/green]")
        return

    console.print(f"\n[bold]Found {len(rules)} pending rule(s) to review.[/bold]\n")

    accepted = 0
    rejected = 0
    skipped = 0

    for i, rule in enumerate(rules, 1):
        rule_id = rule["id"]

        # Header
        console.print(
            Panel(
                f"[bold cyan]{rule['rule_name']}[/bold cyan]\n"
                f"[dim]{rule['rule_description']}[/dim]",
                title=f"Rule {i}/{len(rules)}",
                subtitle=f"Confidence: {rule['confidence']:.0%} | "
                f"{rule['repository']} | {rule['file_path']}",
            )
        )

        # Show the diff
        console.print("[bold]Diff:[/bold]")
        console.print(
            Syntax(
                rule["diff_payload"],
                "diff",
                theme="monokai",
                line_numbers=False,
            )
        )

        # Show the extracted schema
        console.print("\n[bold]Extracted Schema:[/bold]")
        import json

        console.print(
            Syntax(
                json.dumps(rule["rule_schema"], indent=2),
                "json",
                theme="monokai",
            )
        )

        # Prompt
        console.print()
        choice = typer.prompt(
            "Accept (Y), Reject (N), or Skip (S)?",
            default="S",
            show_default=True,
        ).strip().upper()

        if choice == "Y":
            try:
                client.accept_rule(rule_id)
                console.print(f"  [green]Accepted[/green] — rule is now ACTIVE\n")
                accepted += 1
            except Exception as exc:
                console.print(f"  [red]Failed to accept:[/red] {exc}\n")
                skipped += 1
        elif choice == "N":
            try:
                client.reject_rule(rule_id)
                console.print(f"  [red]Rejected[/red]\n")
                rejected += 1
            except Exception as exc:
                console.print(f"  [red]Failed to reject:[/red] {exc}\n")
                skipped += 1
        else:
            console.print(f"  [dim]Skipped[/dim]\n")
            skipped += 1

    console.print(
        f"\n[bold]Review complete:[/bold] "
        f"[green]{accepted} accepted[/green], "
        f"[red]{rejected} rejected[/red], "
        f"[dim]{skipped} skipped[/dim]"
    )
