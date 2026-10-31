"""Exceptions raised by the NestAPI client."""

from __future__ import annotations

from typing import Any


class ApiError(Exception):
    """The server answered with ``success: false``.

    Branch on ``error_code``, not on the message, which may change.
    Unrecognized codes land here directly.

    Attributes:
        error_code: Value of ``error.code``; empty if the server sent none.
        status: HTTP status code.
        details: Value of ``error.details``: a list for ``PARAM_NOT_FOUND``,
            a dict with keys like ``query.age`` for ``VALIDATION_ERROR``.
    """

    # The defaults let pickle rebuild the exception from its message alone;
    # the attributes are then restored from the instance dict.
    def __init__(
        self,
        message: str = "",
        error_code: str = "",
        status: int = 0,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.status = status
        self.details = details


class ServiceNotFoundError(ApiError):
    """NOT_FOUND: the service or the API version does not exist."""


class ValidationError(ApiError):
    """PARAM_NOT_FOUND or VALIDATION_ERROR: the server rejected the parameters."""


class RateLimitError(ApiError):
    """RATE_LIMITED or RATE_LIMIT_EXCEEDED."""


class ServerError(ApiError):
    """Any other error code with an HTTP status of 500 or above."""


class TransportError(Exception):
    """No usable API answer arrived.

    Raised for a network failure, a non-JSON body, or a body that does not
    follow the API format. Deliberately not an :class:`ApiError`.
    """
