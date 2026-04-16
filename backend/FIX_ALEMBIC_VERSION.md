# 🔧 Fix Alembic Version Column Size

## Current Error

```
value too long for type character varying(32)
[SQL: UPDATE alembic_version SET version_num='20250911_add_ingestion_status_fields']
```

## The Problem

The `alembic_version` table has a `version_num` column limited to 32 characters, but one of our migration names is 37 characters long:

```
20250911_add_ingestion_status_fields  ← 37 characters
```

## Solution: Increase Column Size

We need to increase the column from `VARCHAR(32)` to `VARCHAR(64)`.

---

## Option 1: NeonDB SQL Editor (Recommended - 2 minutes)

### Step 1: Open NeonDB Console

1. Go to: https://console.neon.tech
2. Sign in with your account
3. Find your project (should be the one with `ep-flat-meadow-ahvsmoyw`)
4. Click on your database: **neondb**

### Step 2: Open SQL Editor

1. Click **SQL Editor** in the left sidebar
2. You'll see a query editor

### Step 3: Run This SQL Command

Copy and paste this into the SQL Editor:

```sql
ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(64);
```

Click **Run** or press `Ctrl+Enter`

### Step 4: Verify the Change

Run this to confirm:

```sql
SELECT column_name, data_type, character_maximum_length 
FROM information_schema.columns 
WHERE table_name = 'alembic_version' AND column_name = 'version_num';
```

Expected result:
```
column_name  | data_type        | character_maximum_length
version_num  | character varying| 64
```

### Step 5: Redeploy on Render

1. Go to Render Dashboard: https://dashboard.render.com
2. Click **pharos-cloud-api**
3. Click **Manual Deploy** → **Deploy latest commit**
4. Wait 2-3 minutes

---

## Option 2: Using psql Command Line (Alternative)

If you have `psql` installed locally:

```bash
# Connect to NeonDB
psql "postgresql://neondb_owner:npg_2Lv8pxVJzgyd@ep-flat-meadow-ahvsmoyw-pooler.c-3.us-east-1.aws.neon.tech/neondb?sslmode=require"

# Run the fix
ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(64);

# Verify
\d alembic_version

# Exit
\q
```

Then redeploy on Render.

---

## Option 3: Drop and Recreate (Nuclear Option)

If the above doesn't work, you can drop the alembic_version table and let migrations recreate it:

```sql
-- WARNING: This will reset migration tracking
DROP TABLE IF EXISTS alembic_version;
```

Then redeploy on Render. Alembic will recreate the table with the correct size and run all migrations from scratch.

**Note**: This is safe for a fresh database with no data, but use with caution on production databases with existing data.

---

## Why This Happened

The `alembic_version` table is created by Alembic with a default `VARCHAR(32)` column size. Most migration names are short enough (e.g., `20250911_add_authority_tables` = 31 chars), but some longer names exceed this limit.

The migration name `20250911_add_ingestion_status_fields` is 37 characters, which exceeds the 32-character limit.

---

## Expected Result After Fix

Once you've increased the column size and redeployed:

```
✅ Database connection successful
✅ Running Alembic migrations...
✅ INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
✅ INFO  [alembic.runtime.migration] Will assume transactional DDL.
✅ INFO  [alembic.runtime.migration] Running upgrade 20250911_add_authority_tables -> 20250911_add_ingestion_status_fields
✅ INFO  [alembic.runtime.migration] Running upgrade 20250911_add_ingestion_status_fields -> 20250912_add_classification_codes
✅ INFO  [alembic.runtime.migration] Running upgrade ... (all migrations)
✅ Migrations completed successfully
✅ Starting Uvicorn server...
✅ Application startup complete
```

---

## Quick Summary

1. **Go to**: https://console.neon.tech
2. **Open**: SQL Editor for your `neondb` database
3. **Run**: `ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(64);`
4. **Redeploy**: Render → Manual Deploy
5. **Wait**: 2-3 minutes
6. **Success**: API is live!

---

**Recommended**: Use Option 1 (NeonDB SQL Editor) - it's the fastest and safest.

**Time**: 2 minutes to fix + 2-3 minutes redeploy = ~5 minutes total
