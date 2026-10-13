"""One place for how errors look on the wire.

Every failure the API can produce funnels through here so the frontend has a
single shape to parse: `{detail, error: {code, message, ...}}`. `detail` is kept
as the plain message because the fetch helper has always read it.
"""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("errors")

# so the frontend can branch on `error.code` instead of on HTTP numbers
_STATUS_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "unprocessable",
    429: "rate_limited",
    500: "internal_error",
}


class AppError(Exception):
    status_code = 400
    code = "app_error"

    def __init__(self, message: str, status_code: int | None = None, code: str | None = None):
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code


class NotFound(AppError):
    status_code = 404
    code = "not_found"


class BadRequest(AppError):
    status_code = 400
    code = "bad_request"


def _envelope(status_code: int, code: str, message: str, **extra) -> JSONResponse:
    error = {"code": code, "message": message}
    error.update(extra)
    return JSONResponse(status_code=status_code, content={"detail": message, "error": error})


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exc(request: Request, exc: StarletteHTTPException):
        return _envelope(
            exc.status_code,
            _STATUS_CODES.get(exc.status_code, "http_error"),
            exc.detail if isinstance(exc.detail, str) else "request failed",
            path=request.url.path,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exc(request: Request, exc: RequestValidationError):
        fields = [
            {"loc": ".".join(str(p) for p in e.get("loc", [])), "msg": e.get("msg")}
            for e in exc.errors()
        ]
        return _envelope(
            422,
            "validation_error",
            "request failed validation",
            fields=fields,
            path=request.url.path,
        )

    @app.exception_handler(AppError)
    async def app_exc(request: Request, exc: AppError):
        return _envelope(exc.status_code, exc.code, exc.message, path=request.url.path)

    @app.exception_handler(Exception)
    async def unhandled_exc(request: Request, exc: Exception):
        # never leak a stack trace to the client; full detail goes to the log
        log.exception("unhandled error on %s %s", request.method, request.url.path)
        return _envelope(
            500,
            "internal_error",
            "something went wrong on the server",
            path=request.url.path,
        )
