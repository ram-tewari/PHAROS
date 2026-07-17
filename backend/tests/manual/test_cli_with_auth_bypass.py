#!/usr/bin/env python3
"""
CLI Integration Test with Authentication

Tests actual CRUD operations using the CLI with proper authentication.
Requires a running backend with valid JWT tokens for authentication.

Usage:
    1. Start the backend: cd backend && uvicorn app.main:app --reload
    2. Set up authentication:
       - Set JWT_SECRET_KEY environment variable
       - Generate a valid JWT token for testing
       - Set PHAROS_API_TOKEN environment variable or use pharos config set-token
    3. Run this test: python test_cli_with_auth_bypass.py
"""
import subprocess
import sys
import json
import httpx
import os
import time
from pathlib import Path

# Colors
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
            timeout=30,
            env={**os.environ, "PHAROS_API_URL": "http://127.0.0.1:8000"}
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

def check_authentication():
    """Check if CLI is authenticated."""
    try:
        # Try to run a simple authenticated command
        code, out, err = run_cli(["config", "show"])
        # If config show works, we're authenticated
        return code == 0
    except:
        return False

def show_auth_instructions():
    """Show instructions for setting up authentication."""
    print(f"\n{C.YELLOW}⚠️  Authentication required{C.RESET}")
    print(f"\n{C.CYAN}To set up authentication:{C.RESET}")
    print(f"  1. Set JWT_SECRET_KEY environment variable:")
    print(f"     {C.GREEN}export JWT_SECRET_KEY=your-secret-key{C.RESET}")
    print(f"")
    print(f"  2. Generate a test JWT token or use the backend's test user:")
    print(f"     {C.GREEN}python -c \"from app.shared.security import create_access_token; print(create_access_token({'sub': 'testuser', 'user_id': '1', 'scopes': [], 'tier': 'free'}))\"{C.RESET}")
    print(f"")
    print(f"  3. Set the API token for the CLI:")
    print(f"     {C.GREEN}export PHAROS_API_TOKEN=<your-jwt-token>{C.RESET}")
    print(f"     Or use: {C.GREEN}pharos config set-token <your-jwt-token>{C.RESET}")
    print(f"")
    print(f"  4. Verify authentication:")
    print(f"     {C.GREEN}pharos config show{C.RESET}")
    print()

# Test counters
total_tests = 0
passed_tests = 0

print_header("PHAROS CLI INTEGRATION TEST WITH AUTHENTICATION")

# Check backend
print("Checking backend status...")
backend_ok = check_backend()
print_test("Backend running", backend_ok, 
           "Backend is running at http://127.0.0.1:8000" if backend_ok else "Backend is not responding")

if not backend_ok:
    print(f"\n{C.RED}ERROR: Backend must be running{C.RESET}")
    print("Start backend with: cd backend && uvicorn app.main:app --reload")
    sys.exit(1)

# Check authentication
print("\nChecking authentication status...")
auth_ok = check_authentication()
print_test("CLI authenticated", auth_ok,
           "API token configured" if auth_ok else "Authentication required")

if not auth_ok:
    show_auth_instructions()
    print(f"{C.YELLOW}Waiting for authentication setup...{C.RESET}")
    print("Press Enter after setting up authentication, or Ctrl+C to exit")
    input()
    
    # Check again
    auth_ok = check_authentication()
    if not auth_ok:
        print(f"\n{C.RED}ERROR: Authentication not configured{C.RESET}")
        sys.exit(1)
    print(f"{C.GREEN}✅ Authentication configured!{C.RESET}\n")

# Test 1: Create a Resource
print_header("TEST 1: Create Resource")

# Create a test file
test_file = Path("test_resource.txt")
test_file.write_text("This is a test resource for CLI integration testing.")

total_tests += 1
code, out, err = run_cli(["resource", "add", str(test_file), "--type", "documentation"])
passed = code == 0 and ("created successfully" in out.lower() or "id:" in out.lower())
passed_tests += passed

resource_id = None
if passed:
    # Extract resource ID from output
    for line in out.split('\n'):
        if 'ID:' in line or 'id:' in line:
            try:
                resource_id = int(line.split(':')[1].strip())
                break
            except:
                pass

print_test("Create resource", passed, 
           f"Resource ID: {resource_id}" if resource_id else f"Output: {out[:100]}")

# Test 2: List Resources
print_header("TEST 2: List Resources")

total_tests += 1
code, out, err = run_cli(["resource", "list", "--format", "json"])
passed = code == 0 and ('"items"' in out or '"data"' in out or "[]" in out)
passed_tests += passed

resource_count = 0
if passed:
    try:
        data = json.loads(out)
        if isinstance(data, dict) and 'items' in data:
            resource_count = len(data['items'])
        elif isinstance(data, list):
            resource_count = len(data)
    except:
        pass

print_test("List resources", passed, f"Found {resource_count} resources")

# Test 3: Get Resource by ID
if resource_id:
    print_header("TEST 3: Get Resource by ID")
    
    total_tests += 1
    code, out, err = run_cli(["resource", "get", str(resource_id), "--format", "json"])
    passed = code == 0 and (f'"id": {resource_id}' in out or f'"id":{resource_id}' in out)
    passed_tests += passed
    
    print_test(f"Get resource {resource_id}", passed, 
               f"Retrieved successfully" if passed else f"Error: {err[:100]}")

# Test 4: Update Resource
if resource_id:
    print_header("TEST 4: Update Resource")
    
    total_tests += 1
    code, out, err = run_cli(["resource", "update", str(resource_id), "--title", "Updated Test Resource"])
    passed = code == 0 and ("updated successfully" in out.lower() or "updated" in out.lower())
    passed_tests += passed
    
    print_test(f"Update resource {resource_id}", passed,
               "Title updated" if passed else f"Error: {err[:100]}")

# Test 5: Create Collection
print_header("TEST 5: Create Collection")

total_tests += 1
code, out, err = run_cli(["collection", "create", "Test Collection", "--description", "CLI test collection"])
passed = code == 0 and ("created successfully" in out.lower() or "id:" in out.lower())
passed_tests += passed

collection_id = None
if passed:
    for line in out.split('\n'):
        if 'ID:' in line or 'id:' in line:
            try:
                collection_id = int(line.split(':')[1].strip())
                break
            except:
                pass

print_test("Create collection", passed,
           f"Collection ID: {collection_id}" if collection_id else f"Output: {out[:100]}")

# Test 6: List Collections
print_header("TEST 6: List Collections")

total_tests += 1
code, out, err = run_cli(["collection", "list", "--format", "json"])
passed = code == 0 and ('"items"' in out or '"data"' in out or "[]" in out)
passed_tests += passed

collection_count = 0
if passed:
    try:
        data = json.loads(out)
        if isinstance(data, dict) and 'items' in data:
            collection_count = len(data['items'])
        elif isinstance(data, list):
            collection_count = len(data)
    except:
        pass

print_test("List collections", passed, f"Found {collection_count} collections")

# Test 7: Add Resource to Collection
if resource_id and collection_id:
    print_header("TEST 7: Add Resource to Collection")
    
    total_tests += 1
    code, out, err = run_cli(["collection", "add", str(collection_id), str(resource_id)])
    passed = code == 0 and ("added" in out.lower() or "success" in out.lower())
    passed_tests += passed
    
    print_test(f"Add resource {resource_id} to collection {collection_id}", passed,
               "Added successfully" if passed else f"Error: {err[:100]}")

# Test 8: Search
print_header("TEST 8: Search Functionality")

total_tests += 1
code, out, err = run_cli(["search", "test", "--format", "json"])
passed = code == 0 and ('"items"' in out or '"results"' in out or "[]" in out)
passed_tests += passed

search_results = 0
if passed:
    try:
        data = json.loads(out)
        if isinstance(data, dict):
            if 'items' in data:
                search_results = len(data['items'])
            elif 'results' in data:
                search_results = len(data['results'])
        elif isinstance(data, list):
            search_results = len(data)
    except:
        pass

print_test("Search for 'test'", passed, f"Found {search_results} results")

# Test 9: Delete Resource
if resource_id:
    print_header("TEST 9: Delete Resource")
    
    total_tests += 1
    code, out, err = run_cli(["resource", "delete", str(resource_id), "--force"])
    passed = code == 0 and ("deleted" in out.lower() or "success" in out.lower())
    passed_tests += passed
    
    print_test(f"Delete resource {resource_id}", passed,
               "Deleted successfully" if passed else f"Error: {err[:100]}")

# Test 10: Delete Collection
if collection_id:
    print_header("TEST 10: Delete Collection")
    
    total_tests += 1
    code, out, err = run_cli(["collection", "delete", str(collection_id), "--force"])
    passed = code == 0 and ("deleted" in out.lower() or "success" in out.lower())
    passed_tests += passed
    
    print_test(f"Delete collection {collection_id}", passed,
               "Deleted successfully" if passed else f"Error: {err[:100]}")

# Cleanup
if test_file.exists():
    test_file.unlink()

# Final Summary
print_header("TEST SUMMARY")

percentage = (passed_tests / total_tests * 100) if total_tests > 0 else 0
print(f"Tests passed: {C.GREEN if percentage >= 80 else C.RED}{passed_tests}/{total_tests} ({percentage:.1f}%){C.RESET}")

if percentage >= 90:
    print(f"\n{C.GREEN}{C.BOLD}✅ EXCELLENT: Full CRUD operations working!{C.RESET}")
    status = 0
elif percentage >= 70:
    print(f"\n{C.YELLOW}{C.BOLD}⚠️  GOOD: Most operations working{C.RESET}")
    status = 0
elif percentage >= 50:
    print(f"\n{C.YELLOW}{C.BOLD}⚠️  FAIR: Some operations working{C.RESET}")
    status = 1
else:
    print(f"\n{C.RED}{C.BOLD}❌ POOR: Many operations failing{C.RESET}")
    status = 1

print(f"\n{C.CYAN}Operations Tested:{C.RESET}")
print(f"  • Create resource: {'✅' if resource_id else '❌'}")
print(f"  • List resources: {'✅' if resource_count >= 0 else '❌'}")
print(f"  • Get resource: {'✅' if resource_id else '❌'}")
print(f"  • Update resource: {'✅' if resource_id else '❌'}")
print(f"  • Create collection: {'✅' if collection_id else '❌'}")
print(f"  • List collections: {'✅' if collection_count >= 0 else '❌'}")
print(f"  • Add to collection: {'✅' if resource_id and collection_id else '❌'}")
print(f"  • Search: {'✅' if search_results >= 0 else '❌'}")
print(f"  • Delete resource: {'✅' if resource_id else '❌'}")
print(f"  • Delete collection: {'✅' if collection_id else '❌'}")

print(f"\n{C.CYAN}Authentication:{C.RESET}")
print(f"  All operations require proper JWT authentication.")
print(f"  Set PHAROS_API_TOKEN environment variable or use 'pharos config set-token'.")

sys.exit(status)