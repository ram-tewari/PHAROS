"""Machine-to-machine authentication.

Pharos is single-tenant: its clients are the owner's own tools (Ronin, an
MCP client such as Claude Code, the CLI, the edge worker). Authentication is
therefore two static bearer tokens rather than user accounts:

``PHAROS_ADMIN_TOKEN``  full access: ingestion, deletion, admin endpoints.
``PHAROS_READ_TOKEN``   optional, read-only: GET requests plus the read-only
                        POST endpoints listed in ``READ_ONLY_POST_PREFIXES``
                        (search, context retrieval, MCP). Give assistants
                        this token so a prompt-injected agent cannot trigger
                        clones of arbitrary repositories or delete data.

Threat model and rotation are documented in ``SECURITY.md``. Properties:

* fail closed — if no token is configured, every protected request is 401;
* constant-time comparison (``hmac.compare_digest``);
* tokens are never logged; failures log only the path;
* public paths are matched exactly (no prefix tricks like ``/healthz``).
"""

from __future__ import annotations

import hmac
import logging
import os
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)

PUBLIC_PATHS = frozenset(
    {
        "/health",
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc",
        "/openapi.json",
        "/api/v1/ingestion/health",
        "/api/search/search/health",
        "/api/github/health",
        "/api/monitoring/health",
    }
)

#: POST endpoints that only read data and are therefore allowed for the read token.
READ_ONLY_POST_PREFIXES = (
    "/api/v1/search/",
    "/api/v1/context/",
)
READ_ONLY_POST_PATHS = frozenset(
    {
        "/mcp",  # native MCP server: every registered tool is read-only
        "/mcp/",
        "/api/v1/mcp/context/retrieve",
        "/api/search/search",
        "/api/search/search/advanced",
        "/api/search/search/evaluate",
        "/api/search/advanced",
    }
)

MIN_TOKEN_LENGTH = 32


@dataclass(frozen=True)
class Principal:
    name: str
    scopes: frozenset[str]

    @property
    def is_admin(self) -> bool:
        return "admin" in self.scopes

    def as_state(self) -> dict:
        # Shape kept for existing code that reads request.state.user.
        return {"user_id": self.name, "username": self.name, "scopes": sorted(self.scopes), "tier": self.name}


ADMIN = Principal("admin", frozenset({"admin", "read"}))
READER = Principal("reader", frozenset({"read"}))


def _configured(name: str) -> str | None:
    value = os.getenv(name)
    return value if value else None


def principal_for_token(token: str) -> Principal | None:
    admin = _configured("PHAROS_ADMIN_TOKEN")
    reader = _configured("PHAROS_READ_TOKEN")
    encoded = token.encode()
    if admin and hmac.compare_digest(encoded, admin.encode()):
        return ADMIN
    if reader and hmac.compare_digest(encoded, reader.encode()):
        return READER
    return None


def parse_bearer(header: str | None) -> str | None:
    if not header:
        return None
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()


def is_public(path: str) -> bool:
    return path in PUBLIC_PATHS


def allowed_for(principal: Principal, method: str, path: str) -> bool:
    if principal.is_admin:
        return True
    if method in ("GET", "HEAD", "OPTIONS"):
        return True
    if method != "POST":
        return False
    return path in READ_ONLY_POST_PATHS or path.startswith(READ_ONLY_POST_PREFIXES)


def require_admin(request: Request) -> Principal:
    """FastAPI dependency for endpoints that change state."""
    principal = getattr(request.state, "principal", None)
    if principal is None or not principal.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin token required")
    return principal


def token_problems() -> list[str]:
    """Configuration warnings surfaced at startup (never the token values)."""
    problems = []
    admin = _configured("PHAROS_ADMIN_TOKEN")
    if not admin:
        problems.append("PHAROS_ADMIN_TOKEN is not set: every protected endpoint will return 401")
    elif len(admin) < MIN_TOKEN_LENGTH:
        problems.append(f"PHAROS_ADMIN_TOKEN is shorter than {MIN_TOKEN_LENGTH} characters")
    reader = _configured("PHAROS_READ_TOKEN")
    if reader and len(reader) < MIN_TOKEN_LENGTH:
        problems.append(f"PHAROS_READ_TOKEN is shorter than {MIN_TOKEN_LENGTH} characters")
    if admin and reader and hmac.compare_digest(admin.encode(), reader.encode()):
        problems.append("PHAROS_READ_TOKEN equals PHAROS_ADMIN_TOKEN, so the read-only scope has no effect")
    return problems
