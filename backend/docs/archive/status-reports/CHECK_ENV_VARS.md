# 🔍 Check Your Environment Variables

Based on the error, the system is trying to connect to `neondb_owner` as the hostname, which means the variables might still be in the wrong order in Render's system.

## The Error

```
could not translate host name "neondb_owner" to address
```

This means the system is trying to use `neondb_owner` as the SERVER (hostname), which is wrong.

## Double-Check These 3 Variables

Go to Render Dashboard → Environment tab and verify:

### 1. POSTGRES_SERVER
```
Should be: ep-flat-meadow-ahvsmoyw-pooler.c-3.us-east-1.aws.neon.tech
NOT: neondb_owner
```

### 2. POSTGRES_USER  
```
Should be: neondb_owner
NOT: <REDACTED-NEON_PASSWORD-rotate>
NOT: ep-flat-meadow-ahvsmoyw-pooler.c-3.us-east-1.aws.neon.tech
```

### 3. POSTGRES_PASSWORD
```
Should be: <REDACTED-NEON_PASSWORD-rotate>
NOT: neondb_owner
NOT: ep-flat-meadow-ahvsmoyw-pooler.c-3.us-east-1.aws.neon.tech
```

## How to Verify

In Render Dashboard:
1. Click on **pharos-cloud-api**
2. Click **Environment** tab
3. Look at each variable
4. Click **"Show"** to reveal the actual values
5. Verify they match the correct values above

## If They're Wrong

Click **Edit** on each wrong variable and fix it:

```
POSTGRES_SERVER = ep-flat-meadow-ahvsmoyw-pooler.c-3.us-east-1.aws.neon.tech
POSTGRES_USER = neondb_owner
POSTGRES_PASSWORD = <REDACTED-NEON_PASSWORD-rotate>
```

Then click **Save Changes** and wait for redeploy.

## Why This Matters

The code uses `get_database_url()` which reconstructs the connection string:

```python
f"postgresql+asyncpg://{POSTGRES_USER}:<REDACTED-rotate>@{POSTGRES_SERVER}:{POSTGRES_PORT}/{POSTGRES_DB}"
```

If `POSTGRES_SERVER = neondb_owner` (wrong), it tries to connect to:
```
postgresql+asyncpg://???:???@neondb_owner:5432/???
                                └─────┬─────┘
                                  This is a username, not a server!
```

## Correct Connection String

Should be:
```
postgresql+asyncpg://neondb_owner:<REDACTED-NEON_PASSWORD-rotate>@ep-flat-meadow-ahvsmoyw-pooler.c-3.us-east-1.aws.neon.tech:5432/neondb
                     └────┬─────┘ └─────┬──────┘ └──────────────────────┬──────────────────────┘      └─┬──┘
                        USER        PASSWORD                          SERVER                           DB
```

---

**Action**: Go verify those 3 variables in Render Dashboard right now!
