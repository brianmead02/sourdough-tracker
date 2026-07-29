"""FastAPI application factory."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.config import get_settings
from app.db import dispose_engine
from app.queue import dispose_arq_pool

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    logger.info("%s starting (environment=%s)", settings.app_name, settings.environment)
    yield
    await dispose_arq_pool()
    await dispose_engine()
    logger.info("shutdown complete")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.is_dev else None,
        redoc_url=None,
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)
    _mount_pwa(app)
    return app


def _mount_pwa(app: FastAPI) -> None:
    """Serve the PWA from the API when a `web/` directory is present.

    In production Caddy serves these files directly and never reaches the API.
    Mounting here means a bare `docker compose up` gives a working app instead
    of only an API — and it is registered *after* the routers, so it can never
    shadow `/api` or `/docs`.

    The service worker is served with `no-cache` deliberately: browsers honour
    that for `sw.js`, and a cached-forever service worker is how a PWA gets
    permanently stuck on an old release.
    """
    web_root = Path(__file__).resolve().parent.parent / "web"
    if not (web_root / "index.html").exists():
        logger.info("no web/ directory found; serving API only")
        return

    @app.get("/sw.js", include_in_schema=False)
    async def service_worker() -> FileResponse:
        return FileResponse(
            web_root / "sw.js",
            media_type="application/javascript",
            headers={"Cache-Control": "no-cache"},
        )

    app.mount("/", StaticFiles(directory=web_root, html=True), name="pwa")
    logger.info("serving PWA from %s", web_root)


app = create_app()
