# Running CLI Integration Tests with Auth Bypass

## Overview

This guide shows how to run comprehensive CLI integration tests that perform actual CRUD operations by enabling the backend's TEST_MODE, which bypasses authentication.

## Prerequisites

- Backend code in `backend/` directory
- CLI installed: `pip install -e pharos-cli`
- Python 3.8+ installed

## Quick Start

### Option 1: Automated Script (Windows)

```cmd
# Run the batch file to restart backend with TEST_MODE
restart_backend_test_mode.bat
```

Then in another terminal:
```cmd
# Run the integration tests
python test_cli_with_auth_bypass.py
```

### Option 2: Manual Setup

#### Step 1: Stop Current Backend

If backend is running, stop it (Ctrl+C in the terminal where it's running).

#### Step 2: Start Backend with TEST_MODE

**Windows (CMD)**:
```cmd
cd backend
set TESTING=true
python -m uvicorn app.main:app --reload
```

**Windows (PowerShell)**:
```powershell
cd backend
$env:TESTING = "true"
python -m uvicorn app.main:app --reload
```

**Linux/Mac**:
```bash
cd backend
TESTING=true python -m uvicorn app.main:app --reload
```

#### Step 3: Verify TEST_MODE is Enabled

In another terminal:
```bash
python -c "import httpx; r = httpx.get('http://127.0.0.1:8000/api/v1/resources/', timeout=5); print('TEST_MODE:', 'ENABLED' if r.status_code == 200 else 'DISABLED')"
```

You should see: `TEST_MODE: ENABLED`

#### Step 4: Run Integration Tests

```bash
python test_cli_with_auth_bypass.py
```

## What the Tests Do

The integration test performs a complete CRUD workflow:

1. ✅ **Create Resource** - Adds a test file as a resource
2. ✅ **List Resources** - Retrieves all resources
3. ✅ **Get Resource** - Fetches specific resource by ID
4. ✅ **Update Resource** - Modifies resource title
5. ✅ **Create Collection** - Creates a new collection
6. ✅ **List Collections** - Retrieves all collections
7. ✅ **Add to Collection** - Adds resource to collection
8. ✅ **Search** - Searches for resources
9. ✅ **Delete Resource** - Removes the test resource
10. ✅ **Delete Collection** - Removes the test collection

## Expected Output

```
======================================================================
PHAROS CLI INTEGRATION TEST WITH AUTH BYPASS
======================================================================

Checking backend status...
✅ Backend running: PASS
   Backend is running at http://127.0.0.1:8000

Checking TEST_MODE status...
✅ TEST_MODE enabled: PASS
   Authentication bypassed

======================================================================
TEST 1: Create Resource
======================================================================

✅ Create resource: PASS
   Resource ID: 1

======================================================================
TEST 2: List Resources
======================================================================

✅ List resources: PASS
   Found 1 resources

... (more tests)

======================================================================
TEST SUMMARY
======================================================================

Tests passed: 10/10 (100.0%)

✅ EXCELLENT: Full CRUD operations working!

Operations Tested:
  • Create resource: ✅
  • List resources: ✅
  • Get resource: ✅
  • Update resource: ✅
  • Create collection: ✅
  • List collections: ✅
  • Add to collection: ✅
  • Search: ✅
  • Delete resource: ✅
  • Delete collection: ✅
```

## Troubleshooting

### Backend Not Running
```
ERROR: Backend must be running
```

**Solution**: Start the backend with TEST_MODE as shown in Step 2.

### TEST_MODE Not Enabled
```
⚠️  Backend needs to be restarted with TEST_MODE enabled
```

**Solution**: Make sure you set `TESTING=true` before starting uvicorn.

### Connection Refused
```
Backend is not responding
```

**Solution**: 
1. Check if backend is running: `curl http://127.0.0.1:8000/docs`
2. Check if port 8000 is in use by another process
3. Try restarting the backend

### Import Errors
```
ModuleNotFoundError: No module named 'pharos_cli'
```

**Solution**: Install the CLI in editable mode:
```bash
pip install -e pharos-cli
```

## Security Note

⚠️ **IMPORTANT**: TEST_MODE bypasses all authentication and should **NEVER** be used in production!

TEST_MODE is only for:
- Local development testing
- Integration test suites
- CI/CD pipelines

In production, always use proper authentication with JWT tokens.

## Files

- `test_cli_with_auth_bypass.py` - Main integration test script
- `restart_backend_test_mode.bat` - Windows batch file to restart backend
- `restart_backend_test_mode.ps1` - PowerShell script to restart backend
- `RUN_INTEGRATION_TESTS.md` - This guide

## Next Steps

After running these tests successfully:

1. ✅ Verify all CRUD operations work
2. ✅ Test with actual authentication (without TEST_MODE)
3. ✅ Test error handling
4. ✅ Test edge cases
5. ✅ Run cross-platform tests

## Additional Tests

### Test Individual Commands

```bash
# Test resource commands
python -m pharos_cli.cli resource list
python -m pharos_cli.cli resource add test.txt
python -m pharos_cli.cli resource get 1

# Test collection commands
python -m pharos_cli.cli collection list
python -m pharos_cli.cli collection create "My Collection"

# Test search
python -m pharos_cli.cli search "test query"
```

### Test with Different Formats

```bash
# JSON output
python -m pharos_cli.cli resource list --format json

# Table output (default)
python -m pharos_cli.cli resource list --format table

# CSV output
python -m pharos_cli.cli resource list --format csv
```

## Support

If you encounter issues:

1. Check backend logs for errors
2. Verify TEST_MODE is enabled
3. Check CLI installation: `pip show pharos-cli`
4. Review test output for specific error messages
5. Check backend database: `backend/backend.db`

---

**Last Updated**: February 17, 2026  
**Status**: Ready for testing  
**Backend Version**: Phase 19  
**CLI Version**: 0.1.0
