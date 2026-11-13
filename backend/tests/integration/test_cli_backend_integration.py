#!/usr/bin/env python3
"""
Integration test for Pharos CLI + Backend
Tests that CLI commands successfully communicate with backend and receive valid responses.
"""
import subprocess
import json
import sys
import os
import time
from typing import Dict, List, Tuple
import httpx

# Configuration
BACKEND_URL = "http://127.0.0.1:8000"
CLI_PATH = "pharos-cli"
TIMEOUT = 30

class Colors:
    """ANSI color codes for terminal output."""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_header(text: str):
    """Print a formatted header."""
    print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*80}{Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}{text}{Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}{'='*80}{Colors.RESET}\n")

def print_test(name: str, status: str, message: str = ""):
    """Print a test result."""
    if "PASS" in status or "SUCCESS" in status:
        color = Colors.GREEN
        symbol = "✅"
    elif "AUTH" in status:
        color = Colors.YELLOW
        symbol = "🔒"
    elif "FAIL" in status or "ERROR" in status:
        color = Colors.RED
        symbol = "❌"
    else:
        color = Colors.BLUE
        symbol = "ℹ️"
    
    print(f"{symbol} {name}: {color}{status}{Colors.RESET}")
    if message:
        print(f"   {Colors.RESET}{message}{Colors.RESET}")

def check_backend_health() -> bool:
    """Check if backend is running and responding."""
    try:
        response = httpx.get(f"{BACKEND_URL}/docs", timeout=5)
        return response.status_code == 200
    except Exception as e:
        return False

def run_cli_command(command: str) -> Tuple[int, str, str]:
    """
    Run a CLI command and return exit code, stdout, stderr.
    
    Returns:
        Tuple of (exit_code, stdout, stderr)
    """
    try:
        # Use sys.executable to get the current Python interpreter
        full_command = [sys.executable, "-m", "pharos_cli"] + command.split()
        
        result = subprocess.run(
            full_command,
            cwd=CLI_PATH,
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            env={"PHAROS_API_URL": BACKEND_URL, "PATH": os.environ.get("PATH", "")}
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except Exception as e:
        return -1, "", str(e)

def test_cli_local_commands():
    """Test commands that don't require backend."""
    print_header("Testing Local Commands (No Backend Required)")
    
    tests = [
        ("version", "version command"),
        ("info", "info command"),
        ("--help", "help command"),
    ]
    
    passed = 0
    for cmd, name in tests:
        exit_code, stdout, stderr = run_cli_command(cmd)
        
        if exit_code == 0 and stdout:
            print_test(name, "PASS", f"Output: {stdout[:80]}...")
            passed += 1
        else:
            print_test(name, "FAIL", f"Exit code: {exit_code}, Error: {stderr[:100]}")
    
    return passed, len(tests)

def test_cli_backend_communication():
    """Test that CLI can communicate with backend."""
    print_header("Testing CLI → Backend Communication")
    
    # Test commands that should hit the backend
    tests = [
        {
            "name": "List resources (should require auth)",
            "command": "resource list",
            "expect_auth": True,
        },
        {
            "name": "List collections (should require auth)",
            "command": "collection list",
            "expect_auth": True,
        },
        {
            "name": "Search (should require auth)",
            "command": "search test",
            "expect_auth": True,
        },
    ]
    
    passed = 0
    for test in tests:
        exit_code, stdout, stderr = run_cli_command(test["command"])
        output = stdout + stderr
        
        # Check if we got a response from backend
        if "Not authenticated" in output or "401" in output or "Unauthorized" in output:
            # Backend responded with auth requirement - this is SUCCESS
            print_test(
                test["name"],
                "PASS (Backend responding)",
                "Backend correctly requires authentication"
            )
            passed += 1
        elif "Connection" in output and "refused" in output:
            # Cannot connect to backend - this is FAIL
            print_test(
                test["name"],
                "FAIL (Backend not responding)",
                "Cannot connect to backend"
            )
        elif exit_code == 0:
            # Command succeeded - check if we got data
            print_test(
                test["name"],
                "PASS (Got response)",
                f"Command succeeded, output: {output[:80]}..."
            )
            passed += 1
        else:
            # Some other error
            print_test(
                test["name"],
                "FAIL",
                f"Exit code: {exit_code}, Output: {output[:100]}"
            )
    
    return passed, len(tests)

def test_backend_endpoints_directly():
    """Test backend endpoints directly to verify they're working."""
    print_header("Testing Backend Endpoints Directly")
    
    endpoints = [
        ("/docs", "Swagger UI"),
        ("/openapi.json", "OpenAPI Schema"),
        ("/api/monitoring/health", "Health endpoint (may require auth)"),
    ]
    
    passed = 0
    for path, name in endpoints:
        try:
            response = httpx.get(f"{BACKEND_URL}{path}", timeout=5)
            
            if response.status_code == 200:
                print_test(name, "PASS", f"Status: {response.status_code}")
                passed += 1
            elif response.status_code == 401:
                print_test(name, "PASS (Auth required)", f"Status: {response.status_code}")
                passed += 1
            else:
                print_test(name, "FAIL", f"Status: {response.status_code}")
        except Exception as e:
            print_test(name, "FAIL", f"Error: {str(e)[:100]}")
    
    return passed, len(endpoints)

def test_cli_help_commands():
    """Test that all command groups have working help."""
    print_header("Testing CLI Help Commands")
    
    command_groups = [
        "auth", "config", "resource", "collection", "search",
        "graph", "batch", "chat", "annotate",
        "quality", "code", "ask", "system", "backup"
    ]
    
    passed = 0
    for group in command_groups:
        exit_code, stdout, stderr = run_cli_command(f"{group} --help")
        
        if exit_code == 0 and ("Usage:" in stdout or "Commands:" in stdout):
            print_test(f"{group} --help", "PASS", "Help displayed correctly")
            passed += 1
        else:
            print_test(f"{group} --help", "FAIL", f"Exit code: {exit_code}")
    
    return passed, len(command_groups)

def main():
    """Run all integration tests."""
    print_header("PHAROS CLI + BACKEND INTEGRATION TEST")
    print(f"Backend URL: {BACKEND_URL}")
    print(f"CLI Path: {CLI_PATH}")
    
    # Check backend health first
    print("\nChecking backend health...")
    if check_backend_health():
        print_test("Backend health check", "PASS", "Backend is running and responding")
    else:
        print_test("Backend health check", "FAIL", "Backend is not responding")
        print(f"\n{Colors.RED}ERROR: Backend is not running. Please start the backend first.{Colors.RESET}")
        print(f"Run: cd backend && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000")
        return 1
    
    # Run test suites
    results = []
    
    # Test 1: Local commands
    passed, total = test_cli_local_commands()
    results.append(("Local Commands", passed, total))
    
    # Test 2: CLI help commands
    passed, total = test_cli_help_commands()
    results.append(("Help Commands", passed, total))
    
    # Test 3: Backend endpoints
    passed, total = test_backend_endpoints_directly()
    results.append(("Backend Endpoints", passed, total))
    
    # Test 4: CLI-Backend communication
    passed, total = test_cli_backend_communication()
    results.append(("CLI-Backend Communication", passed, total))
    
    # Print summary
    print_header("TEST SUMMARY")
    
    total_passed = 0
    total_tests = 0
    
    for name, passed, total in results:
        total_passed += passed
        total_tests += total
        percentage = (passed / total * 100) if total > 0 else 0
        status = f"{passed}/{total} ({percentage:.1f}%)"
        
        if passed == total:
            print_test(name, f"✅ {status}", "All tests passed")
        elif passed > 0:
            print_test(name, f"⚠️ {status}", "Some tests failed")
        else:
            print_test(name, f"❌ {status}", "All tests failed")
    
    print(f"\n{Colors.BOLD}Overall: {total_passed}/{total_tests} tests passed ({total_passed/total_tests*100:.1f}%){Colors.RESET}")
    
    # Interpretation
    print_header("INTERPRETATION")
    
    if total_passed == total_tests:
        print(f"{Colors.GREEN}✅ EXCELLENT: All tests passed!{Colors.RESET}")
        print("The CLI and backend are fully integrated and working correctly.")
        return 0
    elif total_passed >= total_tests * 0.8:
        print(f"{Colors.YELLOW}⚠️ GOOD: Most tests passed.{Colors.RESET}")
        print("The CLI and backend are mostly working. Some issues need attention.")
        return 0
    else:
        print(f"{Colors.RED}❌ POOR: Many tests failed.{Colors.RESET}")
        print("There are significant issues with CLI-backend integration.")
        return 1

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Test interrupted by user{Colors.RESET}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Colors.RED}Unexpected error: {e}{Colors.RESET}")
        sys.exit(1)
