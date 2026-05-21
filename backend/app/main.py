import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from .api import audio as audio_api
from .api import auth as auth_api
from .api import teams as teams_api
from .config import get_settings
from .database import SessionLocal
from .logging_config import configure_logging
from .services.auth import ensure_admin_user

configure_logging()
log = logging.getLogger(__name__)

app = FastAPI(title="Private Audio Intelligence Tool", version="0.1.0")


@app.on_event("startup")
def _on_startup() -> None:
    log.info("Starting backend")
    db = SessionLocal()
    try:
        ensure_admin_user(db)
    finally:
        db.close()


@app.get("/healthz", tags=["health"])
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"detail": "internal server error"})


app.include_router(auth_api.router)
app.include_router(audio_api.router)
app.include_router(teams_api.router)


_ = get_settings()
