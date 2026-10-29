"""Error handling that never leaks internals or echoes attacker input."""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.logging import get_logger

log = get_logger()


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        # FastAPI's default response echoes the rejected input; return only where/why.
        issues = [{"loc": [str(p) for p in e["loc"]], "msg": e["msg"]} for e in exc.errors()]
        return JSONResponse({"error": "validation_error", "issues": issues}, status_code=422)

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        rid = getattr(request.state, "request_id", "unknown")
        log.error("unhandled_exception", error_type=type(exc).__name__, path=request.url.path)
        return JSONResponse({"error": "internal_error", "request_id": rid}, status_code=500)
