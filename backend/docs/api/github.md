# GitHub Code Fetch API

On-demand source-code retrieval for remote code chunks stored on GitHub.

## Overview

The GitHub API provides direct access to the GitHubFetcher layer, allowing clients to fetch raw source code for specific line ranges from GitHub files. Results are cached in Redis for 1 hour.

**Base path**: `/api/github`  
**Authentication**: same JWT Bearer token as all other endpoints

## Endpoints

### POST /api/github/fetch

Fetch a single code chunk from a GitHub file.

**Request Body:**
```json
{
  "github_uri": "https://raw.githubusercontent.com/owner/repo/abc123def/src/main.py",
  "branch_reference": "abc123def456789",
  "start_line": 42,
  "end_line": 78
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `github_uri` | string | yes | Full `raw.githubusercontent.com` URL |
| `branch_reference` | string | no | Commit SHA or branch (default: `HEAD`) |
| `start_line` | integer | no | First line, 1-based inclusive (default: 1) |
| `end_line` | integer | no | Last line, 1-based inclusive (default: 9999) |

**Response:**
```json
{
  "code": "def main():\n    print('hello')\n",
  "cache_hit": false,
  "latency_ms": 142.3,
  "error": null
}
```

**Example:**
```bash
curl -X POST http://127.0.0.1:8000/api/github/fetch \
  -H "Content-Type: application/json" \
  -d '{
    "github_uri": "https://raw.githubusercontent.com/owner/repo/main/src/utils.py",
    "start_line": 10,
    "end_line": 30
  }'
```

---

### POST /api/github/fetch-batch

Fetch up to 50 code chunks in a single parallel request.

**Request Body:**
```json
{
  "chunks": [
    {
      "github_uri": "https://raw.githubusercontent.com/owner/repo/main/src/a.py",
      "start_line": 1,
      "end_line": 50
    },
    {
      "github_uri": "https://raw.githubusercontent.com/owner/repo/main/src/b.py",
      "start_line": 100,
      "end_line": 150
    }
  ]
}
```

**Response:**
```json
{
  "results": [
    {"code": "...", "cache_hit": true, "latency_ms": 3.1, "error": null},
    {"code": "...", "cache_hit": false, "latency_ms": 201.4, "error": null}
  ],
  "total": 2,
  "cache_hits": 1,
  "errors": 0,
  "total_latency_ms": 204.8
}
```

**Limits**: Maximum 50 chunks per request. Fetches run in parallel (bounded by `GITHUB_FETCH_CONCURRENCY`).

---

### GET /api/github/health

Health check for the GitHub module — verifies Redis connectivity and reports configuration.

**Response:**
```json
{
  "status": "healthy",
  "cache_available": true,
  "github_token_configured": true,
  "max_concurrency": 10
}
```

| Status | Meaning |
|--------|---------|
| `healthy` | Redis reachable, all systems nominal |
| `degraded` | Redis unavailable; fetches still work but are not cached |

---

## Security

- **SSRF protection**: only `raw.githubusercontent.com` and `api.github.com` URIs are accepted. Any other host raises HTTP 422.
- **HTTPS only**: HTTP URIs are rejected.

## Rate Limits

| Mode | Limit |
|------|-------|
| Unauthenticated | 60 req/hour per IP |
| Authenticated (`GITHUB_API_TOKEN` set) | 5,000 req/hour |

Set `GITHUB_API_TOKEN` in your environment to use the authenticated limit.

## Caching

Cache TTL is **1 hour**. Cache keys are deterministic based on the URI + commit SHA + line range, so force-pushed branches do not produce stale results when a commit SHA is used as `branch_reference`.

## Related Documentation

- [Search API](search.md) — `include_code` flag for inline code attachment
- [Code Ingestion Guide](../guides/code-ingestion.md) — ingesting GitHub repositories
- [Architecture: Modules](../architecture/modules.md) — GitHub module internals
