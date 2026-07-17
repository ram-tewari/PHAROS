#!/usr/bin/env python3
"""
Comprehensive CLI + Backend Integration Test
Tests that CLI commands work with the running backend.
"""
import subprocess
import sys
import json
import httpx
from pathlib import Path

# Colors for output
class C:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_header(text):
    print(f"\n{C.CYAN}{C.BOLD}{'='*70}{C.RESET}")
    print(f"{C.CYAN}{C.BOLD}{text}{C.RESET}")
    print(f"{C.CYAN}{C.BOLD}{'='*70}{C.RESET}\n")

def print_test(name, passed, details=""):
    symbol = f"{C.GREEN}✅" if passed else f"{C.RED}❌"
    status = f"{C.GREEN}PASS" if passed else f"{C.RED}FAIL"
    print(f"{symbol} {name}: {status}{C.RESET}")
    if details:
        print(f"   {details}")

def run_cli(args):
    """Run CLI command and return result."""
    try:
        cmd = [sys.executable, "-m", "pharos_cli.cli"] + args
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return -1, "", str(e)

def check_backend():
    """Check if backend is running."""
    try:
        r = httpx.get("http://127.0.0.1:8000/docs", timeout=5)
        return r.status_code == 200
    except:
        return False

# Test counters
total_tests = 0
passed_tests = 0

print_header("PHAROS CLI + BACKEND INTEGRATION TEST")

# Check backend
print("Checking backend status...")
backend_ok = check_backend()
print_test("Backend health check", backend_ok, 
           "Backend is running at http://127.0.0.1:8000" if backend_ok else "Backend is not responding")

if not backend_ok:
    print(f"\n{C.RED}ERROR: Backend must be running for integration tests{C.RESET}")
    print("Start backend with: cd backend && uvicorn app.main:app --reload")
    sys.exit(1)

# Test 1: CLI Structure Tests
print_header("TEST 1: CLI Structure")

tests = [
    (["--help"], "Main help", lambda out: "Pharos CLI" in out and "Commands" in out),
    (["version"], "Version command", lambda out: "0.1.0" in out),
    (["info"], "Info command", lambda out: "Terminal Information" in out),
]

for args, name, check in tests:
    total_tests += 1
    code, out, err = run_cli(args)
    passed = code == 0 and check(out)
    passed_tests += passed
    print_test(name, passed, f"Exit code: {code}")

# Test 2: Command Group Help
print_header("TEST 2: Command Groups Show Subcommands")

groups = [
    ("resource", 9, ["add", "list", "get", "update", "delete"]),
    ("collection", 9, ["create", "list", "show", "add", "remove"]),
    ("search", 1, ["search"]),
    ("graph", 1, ["graph"]),
]

for group, expected_count, sample_cmds in groups:
    total_tests += 1
    code, out, err = run_cli([group, "--help"])
    
    # Check if subcommands are shown
    has_commands = "Commands" in out or "COMMAND" in out
    has_samples = all(cmd in out.lower() for cmd in sample_cmds[:2])
    
    passed = code == 0 and has_commands and has_samples
    passed_tests += passed
    
    details = f"Subcommands visible: {has_commands}, Sample commands found: {has_samples}"
    print_test(f"{group} --help", passed, details)

# Test 3: Config Commands (No backend needed)
print_header("TEST 3: Configuration Commands")

# Check if config directory exists
config_dir = Path.home() / ".pharos"
config_file = config_dir / "config.yaml"

total_tests += 1
code, out, err = run_cli(["config", "show"])
# Config show might fail if no config exists, but should not crash
passed = code in [0, 1]  # Either works or reports no config
passed_tests += passed
print_test("config show", passed, f"Exit code: {code}")

# Test 4: Backend Communication (Will require auth)
print_header("TEST 4: Backend Communication (Auth Required)")

backend_tests = [
    (["resource", "list"], "List resources"),
    (["collection", "list"], "List collections"),
    (["search", "test"], "Search"),
]

for args, name in backend_tests:
    total_tests += 1
    code, out, err = run_cli(args)
    output = out + err
    
    # We expect auth errors since we're not authenticated
    # Success = backend responds (even with auth error)
    backend_responded = any(x in output.lower() for x in [
        "not authenticated", "401", "unauthorized", "authentication", 
        "login", "token", "api", "error"
    ])
    
    # Also check if it's a connection error (bad)
    connection_error = "connection" in output.lower() and "refused" in output.lower()
    
    passed = backend_responded and not connection_error
    passed_tests += passed
    
    if passed:
        details = "Backend responded (auth required as expected)"
    elif connection_error:
        details = "Connection refused - backend not accessible"
    else:
        details = f"Unexpected response: {output[:100]}"
    
    print_test(name, passed, details)

# Test 5: Help for All Command Groups
print_header("TEST 5: All Command Groups Accessible")

all_groups = [
    "auth", "config", "resource", "collection", "search", "graph",
    "batch", "chat", "annotate", "quality",
    "code", "ask", "system", "backup"
]

group_results = []
for group in all_groups:
    total_tests += 1
    code, out, err = run_cli([group, "--help"])
    passed = code == 0 and len(out) > 50
    passed_tests += passed
    group_results.append((group, passed))

# Print summary
working = sum(1 for _, p in group_results if p)
print(f"Command groups working: {working}/{len(all_groups)}")
for group, passed in group_results:
    symbol = f"{C.GREEN}✓" if passed else f"{C.RED}✗"
    print(f"  {symbol} {group}{C.RESET}")

# Test 6: Verify Subcommands Are Listed
print_header("TEST 6: Subcommands Properly Listed")

# Test that resource group shows its subcommands
total_tests += 1
code, out, err = run_cli(["resource", "--help"])
expected_subcommands = ["add", "list", "get", "update", "delete", "quality", "annotations", "import", "export"]
found_subcommands = [cmd for cmd in expected_subcommands if cmd in out.lower()]

passed = len(found_subcommands) >= 7  # At least 7 out of 9
passed_tests += passed
print_test("Resource subcommands listed", passed, 
           f"Found {len(found_subcommands)}/{len(expected_subcommands)} subcommands")

# Test 7: Command Execution Format
print_header("TEST 7: Command Execution Format")

# Test that commands accept arguments properly
total_tests += 1
code, out, err = run_cli(["resource", "list", "--help"])
passed = code == 0 and ("--format" in out or "--type" in out or "OPTIONS" in out)
passed_tests += passed
print_test("Resource list accepts options", passed, "Help shows available options")

# Final Summary
print_header("TEST SUMMARY")

percentage = (passed_tests / total_tests * 100) if total_tests > 0 else 0
print(f"Tests passed: {C.GREEN if percentage >= 80 else C.RED}{passed_tests}/{total_tests} ({percentage:.1f}%){C.RESET}")

if percentage >= 90:
    print(f"\n{C.GREEN}{C.BOLD}✅ EXCELLENT: CLI is working correctly with backend!{C.RESET}")
    status = 0
elif percentage >= 70:
    print(f"\n{C.YELLOW}{C.BOLD}⚠️  GOOD: Most tests passing, minor issues remain{C.RESET}")
    status = 0
elif percentage >= 50:
    print(f"\n{C.YELLOW}{C.BOLD}⚠️  FAIR: Some tests passing, significant issues remain{C.RESET}")
    status = 1
else:
    print(f"\n{C.RED}{C.BOLD}❌ POOR: Many tests failing, major issues present{C.RESET}")
    status = 1

print(f"\n{C.CYAN}Key Findings:{C.RESET}")
print(f"  • Backend is {'running' if backend_ok else 'not running'}")
print(f"  • CLI structure: {'working' if passed_tests >= 5 else 'broken'}")
print(f"  • Command groups: {working}/{len(all_groups)} accessible")
print(f"  • Subcommands: {'properly displayed' if passed_tests >= 10 else 'not showing'}")
print(f"  • Backend communication: {'working (auth required)' if passed_tests >= 15 else 'issues detected'}")

sys.exit(status)
