"""FastAPI application serving REST API and compiled static Research Console."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from quantseal import __version__
from quantseal.api.routes import router as api_router
from quantseal.config import Settings, get_settings
from quantseal.runtime.scheduler import get_scheduler
from quantseal.runtime.shadow_service import ensure_demo_seeded
from quantseal.storage.db import configure_database, get_session_factory

logger = logging.getLogger("quantseal")


def _static_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "static"


def create_app(
    settings: Settings | None = None,
    *,
    start_scheduler: bool = True,
) -> FastAPI:
    cfg = settings or get_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        configure_database(cfg.resolved_database_url())
        factory = get_session_factory()
        with factory() as db:
            ensure_demo_seeded(db, cfg)
        if not cfg.admin_password.strip():
            logger.warning(
                "QUANTSEAL_ADMIN_PASSWORD is empty — dashboard auth is disabled. "
                "Set QUANTSEAL_ADMIN_PASSWORD before exposing on a public VPS."
            )
        sched = get_scheduler()
        if start_scheduler and cfg.scheduler_enabled:
            sched.start()
        try:
            yield
        finally:
            if start_scheduler:
                sched.stop()

    app = FastAPI(
        title="QuantSeal by berichlab",
        version=__version__,
        description="Self-hosted anti-overfitting autonomous quantitative research lab by berichlab.",
        lifespan=lifespan,
    )

    @app.get("/health", tags=["health"])
    def health() -> dict[str, Any]:
        return {"status": "ok", "version": __version__}

    app.include_router(api_router)

    static_root = _static_dir()
    assets_dir = static_root / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        index_file = static_root / "index.html"
        if index_file.exists():
            candidate = (static_root / full_path).resolve()
            if (
                full_path
                and candidate.is_file()
                and str(candidate).startswith(str(static_root.resolve()))
            ):
                return FileResponse(str(candidate))
            return FileResponse(str(index_file))
        return JSONResponse(
            {
                "service": "QuantSeal API",
                "version": __version__,
                "docs": "/docs",
                "message": "Frontend static bundle not built yet. Run `cd frontend && npm run build`.",
            }
        )

    return app


app = create_app()
