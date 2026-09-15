import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_DETAILS_MEDIA_TYPE = "application/problem+json"

logger = logging.getLogger(__name__)


def _instance(request: Request) -> str:
    return request.url.path + (f"?{request.url.query}" if request.url.query else "")


def _title(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return "HTTP Error"


def _response(
    request: Request,
    *,
    status_code: int,
    title: str,
    detail: str,
    type_uri: str = "about:blank",
    headers: dict[str, str] | None = None,
    extensions: dict[str, Any] | None = None,
) -> JSONResponse:
    content: dict[str, Any] = {
        "type": type_uri,
        "title": title,
        "status": status_code,
        "detail": detail,
        "instance": _instance(request),
    }
    if extensions:
        content.update(extensions)

    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(content),
        headers=headers,
        media_type=PROBLEM_DETAILS_MEDIA_TYPE,
    )


def register_problem_details_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exception: StarletteHTTPException
    ) -> JSONResponse:
        detail = exception.detail
        extensions = None
        if not isinstance(detail, str):
            extensions = {"errors": detail}
            detail = _title(exception.status_code)

        return _response(
            request,
            status_code=exception.status_code,
            title=_title(exception.status_code),
            detail=detail,
            headers=exception.headers,
            extensions=extensions,
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_exception_handler(
        request: Request, exception: RequestValidationError
    ) -> JSONResponse:
        return _response(
            request,
            status_code=422,
            type_uri="urn:physiotrack:problem:request-validation",
            title="Request Validation Error",
            detail="The request contains invalid or missing data.",
            extensions={"errors": exception.errors()},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exception: Exception
    ) -> JSONResponse:
        logger.error(
            "Unhandled exception while processing %s",
            request.url.path,
            exc_info=(type(exception), exception, exception.__traceback__),
        )
        return _response(
            request,
            status_code=500,
            title="Internal Server Error",
            detail="An unexpected error occurred.",
        )
