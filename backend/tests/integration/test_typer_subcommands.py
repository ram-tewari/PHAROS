#!/usr/bin/env python
"""Test Typer subcommand registration."""

import typer

# Create main app
main_app = typer.Typer(name="main", help="Main app")

# Create sub-app
sub_app = typer.Typer(name="sub", help="Sub commands")

@sub_app.command("test")
def test_command():
    """Test command."""
    print("Test command executed!")

# Add sub-app to main app
main_app.add_typer(sub_app)

if __name__ == "__main__":
    main_app()
