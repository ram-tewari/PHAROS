#!/usr/bin/env python
"""Test direct import."""
import sys
sys.path.insert(0, 'pharos-cli')

print("About to import...")
import pharos_cli.cli
print(f"Import done. Groups: {len(pharos_cli.cli.app.registered_groups)}")
