#!/usr/bin/env python
"""Test importing pharos CLI."""

try:
    import pharos_cli.cli
    print(f"Import successful! Groups: {len(pharos_cli.cli.app.registered_groups)}")
except Exception as e:
    print(f"Import failed: {e}")
    import traceback
    traceback.print_exc()
