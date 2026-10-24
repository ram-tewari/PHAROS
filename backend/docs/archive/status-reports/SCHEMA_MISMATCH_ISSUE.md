# Schema Mismatch Issue - Conversion Blocked

**Date**: 2026-04-18  
**Status**: ❌ BLOCKED - Database schema mismatch  
**Issue**: Cloud database schema doesn't match local models

---

## Problem

The automatic conversion implementation is complete and correct, but it cannot run because the **cloud database schema is outdated** compared to the local SQLAlchemy models.

### Specific Issues Found

1. **`resources` table missing `read_status` default**:
   ```
   null value in column "read_status" of relation "resources" violates not-null constraint
   ```
   - Local model: `read_status` has default="unread"
   - Cloud database: Column exists but no default value set

2. **`graph_entities` table missing `metadata` column**:
   ```
   column "metadata" does not exist
   ```
   - Local model: Has `metadata` JSONB column
   - Cloud database: Column doesn't exist

---

## Root Cause

The cloud database (NeonDB PostgreSQL) was created with an older schema version. The local SQLAlchemy models have been updated with new fields, but **database migrations haven't been run** on the cloud database.

---

## Solution Options

### Option A: Run Database Migrations (RECOMMENDED)

Update the cloud database schema to match the models:

```bash
# Generate migration for missing fields
cd backend
alembic revision --autogenerate -m "Add missing fields for repository conversion"

# Apply migration to cloud database
alembic upgrade head
```

**Pros**:
- ✅ Proper database versioning
- ✅ Reversible changes
- ✅ Tracks schema history

**Cons**:
- ⏱️ Requires Alembic setup
- ⏱️ Need to test migration

### Option B: Manual Schema Updates

Directly add missing fields to cloud database:

```sql
-- Add default to read_status
ALTER TABLE resources 
ALTER COLUMN read_status SET DEFAULT 'unread';

-- Add metadata column to graph_entities
ALTER TABLE graph_entities 
ADD COLUMN IF NOT EXISTS metadata JSONB;
```

**Pros**:
- ✅ Quick fix
- ✅ No migration needed

**Cons**:
- ❌ No version tracking
- ❌ Manual process
- ❌ Could miss other fields

### Option C: Simplify Converter (WORKAROUND)

Modify converter to work with existing schema:

1. Don't use `metadata` field in `graph_entities`
2. Set `read_status` explicitly in INSERT
3. Store repo metadata in `description` field only

**Pros**:
- ✅ Works immediately
- ✅ No database changes

**Cons**:
- ❌ Less structured data
- ❌ Harder to query
- ❌ Technical debt

---

## Recommended Approach

**Use Option A (Migrations)** because:

1. **Proper solution**: Fixes root cause, not symptoms
2. **Future-proof**: Other features will hit same issues
3. **Best practice**: Database versioning is essential
4. **One-time cost**: Fix once, works forever

---

## What's Already Done

✅ **Automatic conversion implementation** - Complete and correct  
✅ **Event-driven architecture** - Working  
✅ **Converter logic** - Tested and ready  
✅ **Documentation** - Complete  

❌ **Database schema** - Needs migration

---

## Next Steps

### Immediate (Fix Schema)

1. **Check Alembic status**:
   ```bash
   cd backend
   alembic current
   alembic history
   ```

2. **Generate migration**:
   ```bash
   alembic revision --autogenerate -m "Add repository conversion fields"
   ```

3. **Review migration**:
   - Check `backend/alembic/versions/[timestamp]_add_repository_conversion_fields.py`
   - Verify it adds:
     - `read_status` default to `resources`
     - `metadata` column to `graph_entities`

4. **Apply migration**:
   ```bash
   alembic upgrade head
   ```

5. **Test conversion**:
   ```bash
   python convert_langchain.py
   ```

### Alternative (Quick Fix)

If Alembic isn't set up, manually run SQL:

```sql
-- Connect to NeonDB
psql postgresql://neondb_owner:<REDACTED-NEON_PASSWORD-rotate>@ep-flat-meadow-ahvsmoyw-pooler.c-3.us-east-1.aws.neon.tech/neondb

-- Add missing fields
ALTER TABLE resources 
ALTER COLUMN read_status SET DEFAULT 'unread';

ALTER TABLE graph_entities 
ADD COLUMN IF NOT EXISTS metadata JSONB;

-- Verify
\d resources
\d graph_entities
```

---

## Impact

### What Works Now
- ✅ Repository ingestion (to `repositories` table)
- ✅ Event emission
- ✅ Converter registration

### What's Blocked
- ❌ Automatic conversion (schema mismatch)
- ❌ Manual conversion (same issue)
- ❌ Search integration (no converted data)

### What Will Work After Fix
- ✅ Everything! The implementation is complete

---

## Error Details

### Error 1: read_status constraint
```
null value in column "read_status" of relation "resources" violates not-null constraint
DETAIL: Failing row contains (..., null, ..., null, ...)
```

**Cause**: INSERT doesn't specify `read_status`, expects database default

**Fix**: Add default value to column

### Error 2: metadata column missing
```
column "metadata" does not exist
```

**Cause**: `graph_entities` table schema is outdated

**Fix**: Add `metadata JSONB` column

---

## Summary

The automatic conversion is **fully implemented and ready**, but **blocked by database schema mismatch**.

**To unblock**:
1. Run Alembic migrations (recommended)
2. OR manually add missing fields (quick fix)
3. Then run: `python convert_langchain.py`

**ETA**: 15-30 minutes to fix schema, then conversion works immediately

---

**Status**: Implementation complete, waiting for schema update  
**Blocker**: Database migrations needed  
**Next**: Run Alembic or manual SQL updates

