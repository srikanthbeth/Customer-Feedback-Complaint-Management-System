
import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException


logger = logging.getLogger(__name__)


def error_response(
    status_code: int,
    message: str,
    details: Any = None,
) -> JSONResponse:
    content = {
        "success": False,
        "error": {
            "code": status_code,
            "message": message,
        },
    }

    if details is not None:
        content["error"]["details"] = details

    return JSONResponse(
        status_code=status_code,
        content=content,
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ):
        errors = [
            {
                "field": ".".join(
                    str(part) for part in error.get("loc", ())
                ),
                "message": error.get("msg", "Invalid value"),
                "type": error.get("type", "value_error"),
            }
            for error in exc.errors()
        ]

        return error_response(
            422,
            "Request validation failed",
            errors,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request,
        exc: StarletteHTTPException,
    ):
        message = (
            exc.detail
            if isinstance(exc.detail, str)
            else "The request could not be completed"
        )

        return error_response(exc.status_code, message)

    @app.exception_handler(IntegrityError)
    async def integrity_exception_handler(
        request: Request,
        exc: IntegrityError,
    ):
        logger.warning(
            "Database integrity constraint failed for %s %s",
            request.method,
            request.url.path,
        )

        # Do not expose SQL statements, constraint names, or database details.
        return error_response(
            409,
            "The operation conflicts with existing data or a database constraint",
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_exception_handler(
        request: Request,
        exc: SQLAlchemyError,
    ):
        logger.exception(
            "Database operation failed for %s %s",
            request.method,
            request.url.path,
        )

        return error_response(
            500,
            "A database error occurred while processing the request",
        )

    @app.exception_handler(Exception)
    async def unexpected_exception_handler(
        request: Request,
        exc: Exception,
    ):
        logger.exception(
            "Unexpected error for %s %s",
            request.method,
            request.url.path,
        )

        return error_response(
            500,
            "An unexpected server error occurred",
        )
