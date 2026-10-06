import uuid
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.api.routes import router
from app.core.config import get_settings
from app.core.logging import configure_logging, current_request_id, get_logger

settings = get_settings()
logger = configure_logging()

app = FastAPI(title=settings.app_name, version="0.1.0")


class RequestCorrelationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        req_id = request.headers.get("X-Request-Id") or f"req_{uuid.uuid4().hex[:8]}"
        token = current_request_id.set(req_id)
        try:
            response: Response = await call_next(request)
            response.headers["X-Request-Id"] = req_id
            return response
        finally:
            current_request_id.reset(token)


app.add_middleware(RequestCorrelationMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.get("/")
async def root() -> dict:
    return {"name": "BhoomiLens", "status": "ok"}
