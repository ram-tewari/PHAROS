"""
Pharos — FastAPI application factory.

``create_app()`` wires:

* the code-intelligence API (``app.modules.code``: repositories, ingestion
  jobs, code search, context retrieval) and the legacy module routers;
* the native MCP server at ``/mcp`` (built per application instance);
* bearer-token authentication (``app.shared.auth``) on every path except
  health checks and API docs;
* SQLite table creation for local/test use (PostgreSQL schema is owned by
  Alembic: ``alembic -c config/alembic.ini upgrade head``).

The cloud API (``MODE=CLOUD``) never imports torch: query embeddings go to
the edge embed server over HTTP, or the configured CPU backend.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config.settings import get_settings
from .monitoring import setup_monitoring
from .shared import database as shared_db
from .shared.auth import allowed_for, is_public, parse_bearer, principal_for_token, token_problems
from .shared.database import Base, get_pool_usage_warning, init_database

if os.getenv("TESTING") != "true" and os.getenv("PYTEST_CURRENT_TEST") is None:
    from .database import models  # noqa: F401  (populate Base.metadata)

logger = logging.getLogger(__name__)

APP_TITLE = "Pharos"
APP_VERSION = "0.5.0"


def _is_test_mode() -> bool:
    return os.getenv("TESTING", "").lower() in ("true", "1", "yes")


def register_all_modules(app: FastAPI) -> None:
    """Import every module slice and register its routers and event handlers.

    Module failures are collected; in production any failure aborts startup
    (a missing module means silently-404ing endpoints). Elsewhere the app
    keeps booting so a partially broken tree is still explorable.
    """
    settings = get_settings()
    modules: list[tuple[str, str, list[str]]] = [
        ("code", "app.modules.code", ["code_router"]),
        ("resources", "app.modules.resources", ["resources_router", "chunking_router"]),
        ("search", "app.modules.search", ["search_router", "advanced_search_router"]),
        ("graph", "app.modules.graph", ["graph_router", "citations_router", "discovery_router"]),
        ("planning", "app.modules.planning", ["ai_planning_router"]),
        ("mcp", "app.modules.mcp", ["mcp_router"]),
        ("patterns", "app.modules.patterns", ["patterns_router"]),
        ("pdf_ingestion", "app.modules.pdf_ingestion", ["router"]),
        ("github", "app.modules.github", ["github_router"]),
        ("admin", "app.modules.admin", ["admin_router"]),
        ("monitoring", "app.modules.monitoring", ["monitoring_router"]),
    ]

    import importlib

    failed: list[str] = []
    # Legacy /api/v1/ingestion routes first: its /jobs/history must win over
    # the code router's /ingestion/jobs/{job_id}.
    try:
        from .routers.ingestion import router as ingestion_router

        app.include_router(ingestion_router)
    except Exception as exc:
        failed.append("ingestion")
        logger.error("Failed to register ingestion router: %s", exc, exc_info=True)

    for module_name, module_path, router_names in modules:
        try:
            module = importlib.import_module(module_path)
            for router_name in router_names:
                router = getattr(module, router_name, None)
                if router is None:
                    logger.warning("Module %s does not expose %s", module_name, router_name)
                    continue
                app.include_router(router)
            register: Callable[[], None] | None = getattr(module, "register_handlers", None)
            if register is not None:
                register()
        except Exception as exc:
            failed.append(module_name)
            logger.error("Failed to register module %s: %s", module_name, exc, exc_info=True)

    logger.info("Registered %d module(s), %d failed", len(modules) + 1 - len(failed), len(failed))
    if failed and settings.ENV == "prod":
        raise RuntimeError(
            f"Refusing to start: {len(failed)} module(s) failed to register in production: "
            f"{', '.join(failed)}. See the log for the underlying errors."
        )


def _validate_production(settings) -> None:
    if settings.ENV != "prod":
        return
    if _is_test_mode() or settings.TEST_MODE:
        raise RuntimeError("TESTING / TEST_MODE must not be enabled in production")
    if os.getenv("TEST_AUTH_BYPASS"):
        raise RuntimeError("TEST_AUTH_BYPASS must not be set in production")


def _build_lifespan(mcp_server, *, test_mode: bool):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not test_mode:
            settings = get_settings()
            _validate_production(settings)
            for problem in token_problems():
                logger.warning("Auth configuration: %s", problem)
            try:
                from .events.hooks import register_all_hooks

                register_all_hooks()
            except Exception as exc:
                logger.error("Failed to register event hooks: %s", exc, exc_info=True)
            logger.info("Pharos started (MODE=%s, ENV=%s)", settings.MODE, settings.ENV)
        # The mounted MCP app does not receive this lifespan; its session
        # manager must run for the app's whole lifetime.
        async with mcp_server.session_manager.run():
            yield
        logger.info("Pharos shutting down")

    return lifespan


def _install_auth_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def authentication_middleware(request: Request, call_next):
        path = request.url.path
        if request.method == "OPTIONS" or is_public(path):
            return await call_next(request)

        # Opt-in bypass for local tests only; refused in production at startup
        # and ignored here when ENV=prod. Never driven by a request header.
        if os.getenv("TEST_AUTH_BYPASS", "").lower() in ("true", "1", "yes") and get_settings().ENV != "prod":
            from .shared.auth import ADMIN

            request.state.principal = ADMIN
            request.state.user = ADMIN.as_state()
            return await call_next(request)

        token = parse_bearer(request.headers.get("Authorization"))
        if token is None:
            return JSONResponse(
                status_code=401,
                content={"detail": "Not authenticated"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        principal = principal_for_token(token)
        if principal is None:
            logger.info("Rejected invalid bearer token for %s %s", request.method, path)
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid authentication token"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not allowed_for(principal, request.method, path):
            return JSONResponse(status_code=403, content={"detail": "admin token required"})
        request.state.principal = principal
        request.state.user = principal.as_state()
        return await call_next(request)


def _install_pool_monitor(app: FastAPI) -> None:
    counter = {"n": 0}

    @app.middleware("http")
    async def monitor_connection_pool(request: Request, call_next):
        counter["n"] += 1
        if counter["n"] % 50 == 0:
            try:
                warning = get_pool_usage_warning()
                if warning:
                    logger.warning(
                        "Connection pool near capacity: %.1f%% (%s/%s in use)",
                        warning["pool_usage_percent"], warning["checked_out"], warning["total_capacity"],
                    )
            except Exception as exc:
                logger.debug("Pool monitoring failed: %s", exc)
        return await call_next(request)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    test_mode = _is_test_mode()
    settings = get_settings()
    if not test_mode:
        init_database(settings.get_database_url(), settings.ENV)

    from .modules.mcp.native_server import build_mcp_server

    mcp_server = build_mcp_server()
    app = FastAPI(
        title=APP_TITLE,
        version=APP_VERSION,
        description=(
            "Code-intelligence backend for AI coding assistants: AST-aware repository "
            "indexing, hybrid (keyword + vector + graph) retrieval and context assembly."
        ),
        lifespan=_build_lifespan(mcp_server, test_mode=test_mode),
    )
    app.state.mcp_server = mcp_server

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=False,  # bearer tokens only; no cookies
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Mcp-Session-Id"],
    )
    _install_pool_monitor(app)
    _install_auth_middleware(app)

    # Local / test convenience: SQLite gets tables directly. PostgreSQL
    # schema is managed exclusively by Alembic.
    engine = shared_db.sync_engine
    if engine is not None and engine.dialect.name == "sqlite":
        Base.metadata.create_all(bind=engine)

    @app.get("/health", tags=["meta"])
    async def root_health_check():
        """Liveness probe (no dependencies checked)."""
        return {"status": "healthy", "service": "pharos-api", "version": APP_VERSION}

    register_all_modules(app)

    app.mount("/mcp", mcp_server.streamable_http_app())

    if not test_mode:
        setup_monitoring(app)
    return app


# Never create the app at import time; use create_app() (see app/main.py).
app = None
