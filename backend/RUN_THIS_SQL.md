# ⚡ Run This SQL Command in NeonDB

## 🎯 Quick Fix (2 minutes)

### 1. Go to NeonDB Console
```
https://console.neon.tech
```

### 2. Open SQL Editor
- Find your database: **neondb**
- Click **SQL Editor** in left sidebar

### 3. Copy-Paste This Command
```sql
CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(64) NOT NULL PRIMARY KEY
);
```

### 4. Click "Run"

You should see: `CREATE TABLE` or `Table already exists`

### 5. Go Back to Render
```
https://dashboard.render.com
→ pharos-cloud-api
→ Manual Deploy
→ Deploy latest commit
```

### 6. Wait 2-3 Minutes

---

## ✅ Done!

Your Pharos API will be live after this fix.

---

**What this does**: Creates the `alembic_version` table with 64-character column size (instead of default 32).

**Why needed**: Migration name `20250911_add_ingestion_status_fields` is 37 characters, but Alembic's default column only allows 32.

**Time**: 1 minute to run SQL + 2-3 minutes redeploy = ~4 minutes total
