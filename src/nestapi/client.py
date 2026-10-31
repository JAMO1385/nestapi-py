"""Dynamic client for the NestAPI web services."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable, Iterator
from types import TracebackType
from typing import Any, TypeVar
from urllib.parse import quote

import httpx

from .exceptions import (
    ApiError,
    RateLimitError,
    ServerError,
    ServiceNotFoundError,
    TransportError,
    ValidationError,
)
from .response import Response

_DEFAULT_BASE_URL = "https://open.nestapi.ir"

_ERROR_CLASSES: dict[str, type[ApiError]] = {
    "NOT_FOUND": ServiceNotFoundError,
    "PARAM_NOT_FOUND": ValidationError,
    "VALIDATION_ERROR": ValidationError,
    "RATE_LIMITED": RateLimitError,
    "RATE_LIMIT_EXCEEDED": RateLimitError,
}

_MISSING: Any = object()

_Self = TypeVar("_Self", bound="NestApi")


class NestApi:
    """Dynamic NestAPI client.

    Any attribute is a service: its name is turned into a route, so services
    can come and go without changes here. Attributes starting with ``_`` are
    never services and raise AttributeError.

        api.ip_info(ip="8.8.8.8")        # GET /apis-1/ip-info?ip=8.8.8.8
        api.bmi({"age": 30})             # GET /apis-1/bmi?age=30

    Services named ``call``, ``request``, ``version`` or ``close`` collide with
    the public methods below and must be reached through :meth:`call`, e.g.
    ``api.call("version")``.

    Args:
        version: API version; the ``apis-`` prefix is added automatically.
        base_url: Root of the API.
        timeout: Seconds; applies to the default client only. An injected
            client brings its own timeout.
        client: Optional httpx client. It stays yours, so :meth:`close` leaves
            it open.
    """

    def __init__(
        self,
        version: int = 1,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._version = _check_version(version)
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._injected = client is not None
        self._is_copy = False
        self._client = client if client is not None else _default_client(timeout)

    def __getattr__(self, name: str) -> Callable[..., Response]:
        if name.startswith("_"):
            raise AttributeError(f"{type(self).__name__!r} object has no attribute {name!r}")

        route = _to_route(name)

        # Positional-only, so that parameters called `params`, `self` or `name` go through.
        def invoke(params: Any = _MISSING, /, **named: Any) -> Response:
            if params is _MISSING:
                return self.call(route, named)

            if not isinstance(params, dict):
                raise TypeError("Parameters must be named: use name=value or a single dict.")

            if named:
                raise TypeError("Pass either a dict or named arguments, not both.")

            return self.call(route, params)

        return invoke

    def call(self, service: str, params: dict[str, Any] | None = None) -> Response:
        """GET a service by its exact route name, without any conversion."""
        return self.request("GET", service, params)

    def request(
        self,
        method: str,
        service: str,
        params: dict[str, Any] | None = None,
    ) -> Response:
        """Send any HTTP method. Parameters still go in the query string."""
        url = self._build_url(service, {} if params is None else params)

        if self._client.is_closed:
            raise TransportError("Request failed: the HTTP client is closed.")

        try:
            response = self._client.request(
                method.upper(),
                url,
                headers={"Accept": "application/json"},
            )
        except (httpx.HTTPError, httpx.InvalidURL) as e:
            raise TransportError(f"Request failed: {e}") from e

        return _parse(response.content, response.status_code)

    def version(self: _Self, version: int) -> _Self:
        """Return a copy bound to another API version; this instance is unchanged."""
        clone = copy.copy(self)
        clone._version = _check_version(version)

        return clone

    def close(self) -> None:
        """Close the HTTP connection.

        Only the instance that created the default client closes it: on a copy
        or with an injected client this does nothing. Closing the original also
        ends the copies that share its client.
        """
        if not self._injected and not self._is_copy:
            self._client.close()

    def __enter__(self: _Self) -> _Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def __copy__(self: _Self) -> _Self:
        clone = object.__new__(type(self))
        clone.__dict__.update(self.__dict__)
        clone._is_copy = True

        return clone

    # httpx clients cannot be pickled, so a default client is rebuilt on load.
    def __getstate__(self) -> dict[str, Any]:
        state = self.__dict__.copy()

        if not self._injected:
            del state["_client"]
            state["_is_copy"] = False

        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.__dict__.update(state)

        if not self._injected:
            self._client = _default_client(self._timeout)

    def _build_url(self, service: str, params: dict[str, Any]) -> str:
        url = f"{self._base_url}/apis-{self._version}/{quote(service, safe='/')}"
        query = _build_query(params)

        return f"{url}?{query}" if query else url


def _default_client(timeout: float) -> httpx.Client:
    return httpx.Client(timeout=timeout, verify=True)


def _check_version(version: int) -> int:
    if isinstance(version, bool) or not isinstance(version, int):
        raise TypeError(f"API version must be an int, got {type(version).__name__}.")

    if version < 1:
        raise ValueError(f"API version must be a positive integer, got {version}.")

    return version


def _to_route(name: str) -> str:
    dashed = "".join(
        f"-{char}" if index and char.isupper() else char
        for index, char in enumerate(name)
    )

    return dashed.replace("_", "-").lower()


def _build_query(params: dict[str, Any]) -> str:
    """Encode parameters the same way as the PHP client.

    Booleans become ``true``/``false``, the only form the server accepts. Lists
    become repeated keys (``a=1&a=2``), nested dicts become ``a[b]=1``, and None
    values are left out. Spaces are sent as ``%20``.
    """
    if not isinstance(params, dict):
        raise TypeError("Parameters must be a dict.")

    return "&".join(
        f"{quote(key, safe='')}={quote(value, safe='')}"
        for name, item in params.items()
        for key, value in _flatten(_check_name(name), item)
    )


def _flatten(key: str, value: Any) -> Iterator[tuple[str, str]]:
    # bool comes first because it is a subclass of int.
    if value is None:
        return
    elif isinstance(value, bool):
        yield key, "true" if value else "false"
    elif isinstance(value, dict):
        for name, item in value.items():
            yield from _flatten(f"{key}[{_check_name(name)}]", item)
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            nested = isinstance(item, (dict, list, tuple))
            yield from _flatten(f"{key}[{index}]" if nested else key, item)
    else:
        yield key, str(value)


def _check_name(name: Any) -> str:
    if not isinstance(name, str):
        raise TypeError(f"Parameter names must be strings, got {name!r}.")

    return name


def _parse(body: bytes, status: int) -> Response:
    try:
        payload = json.loads(body, parse_constant=_reject_constant)
    except (ValueError, RecursionError) as e:
        raise TransportError(f"Response is not valid JSON (HTTP {status}).") from e

    if not isinstance(payload, dict) or not isinstance(payload.get("success"), bool):
        raise TransportError(f'Response has no "success" field (HTTP {status}).')

    if payload["success"]:
        return Response.from_dict(payload)

    raise _to_error(payload.get("error"), status)


def _reject_constant(name: str) -> None:
    # Python would otherwise accept NaN and Infinity, which are not JSON.
    raise ValueError(f"Invalid JSON constant: {name}")


def _to_error(error: Any, status: int) -> ApiError:
    fields = error if isinstance(error, dict) else {}
    code = fields.get("code")
    message = fields.get("message")

    if not isinstance(code, str):
        code = ""

    if not isinstance(message, str):
        message = f"API error (HTTP {status})."

    fallback = ServerError if status >= 500 else ApiError
    error_class = _ERROR_CLASSES.get(code, fallback)

    return error_class(message, code, status, fields.get("details"))
