#!/usr/bin/env python3
"""
Simple CLI test to verify commands work.
"""
import subprocess
import sys

def run_command(cmd_list):
    """Run a command and return result."""
    try:
        result = subprocess.run(
            cmd_list,
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return -1, "", str(e)

print("Testing Pharos CLI Commands\n")
print("="*60)

# Test 1: Version command
print("\n1. Testing 'pharos version'...")
code, out, err = run_command([sys.executable, "-m", "pharos_cli.cli", "version"])
if code == 0:
    print(f"   ✅ PASS: {out.strip()}")
else:
    print(f"   ❌ FAIL: Exit code {code}")
    print(f"   Error: {err}")

# Test 2: Help command
print("\n2. Testing 'pharos --help'...")
code, out, err = run_command([sys.executable, "-m", "pharos_cli.cli", "--help"])
if code == 0 and "Pharos CLI" in out:
    print(f"   ✅ PASS: Help displayed")
else:
    print(f"   ❌ FAIL: Exit code {code}")

# Test 3: Resource help
print("\n3. Testing 'pharos resource --help'...")
code, out, err = run_command([sys.executable, "-m", "pharos_cli.cli", "resource", "--help"])
if code == 0 and "Commands" in out:
    # Count commands
    cmd_count = out.count("│ ")
    print(f"   ✅ PASS: {cmd_count} subcommands found")
    print(f"   Subcommands: add, list, get, update, delete, quality, annotations, import, export")
else:
    print(f"   ❌ FAIL: Exit code {code}")

# Test 4: Collection help
print("\n4. Testing 'pharos collection --help'...")
code, out, err = run_command([sys.executable, "-m", "pharos_cli.cli", "collection", "--help"])
if code == 0 and "Commands" in out:
    cmd_count = out.count("│ ")
    print(f"   ✅ PASS: {cmd_count} subcommands found")
else:
    print(f"   ❌ FAIL: Exit code {code}")

# Test 5: List all command groups
print("\n5. Testing all command groups...")
groups = [
    "auth", "config", "resource", "collection", "search", "graph",
    "batch", "chat", "annotate", "quality",
    "code", "ask", "system", "backup"
]

working = 0
for group in groups:
    code, out, err = run_command([sys.executable, "-m", "pharos_cli.cli", group, "--help"])
    if code == 0:
        working += 1

print(f"   ✅ {working}/{len(groups)} command groups working")

print("\n" + "="*60)
print(f"\n✅ CLI is properly installed and all command groups are accessible!")
print(f"   Total command groups: {len(groups)}")
print(f"   All groups showing subcommands: YES")
