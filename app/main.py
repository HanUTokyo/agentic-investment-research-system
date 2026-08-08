from fastapi import FastAPI

from app.api import health_router
from app.config import get_settings
from app.observability import configure_logging, request_id_middleware

app = FastAPI(title="Agentic Investment Research System", version="0.1.0")
configure_logging(get_settings().log_level)
app.middleware("http")(request_id_middleware)
app.include_router(health_router)
