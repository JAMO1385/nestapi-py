"""NestAPI clients with dynamic service routing."""

from __future__ import annotations

import asyncio
import copy
from typing import Any, Callable, Dict, Optional, Union
from urllib.parse import quote
import httpx

from .Exceptions import (
    NestError,
    APIResponseError,
    AuthenticationError,
    ServiceUnavailableError,
    InternalServerError,
    GatewayError,
    NetworkError,
    NotFoundError,
    ParamNotFoundError,
    PermissionDeniedError,
    URLtooLongError,
    UrlTooLongError,
    ValidationError,
    RateLimitError,
    CloudflareError,
)
from .Response import Response


def _to_route(name: str) -> str:
    """Convert camelCase or snake_case method names to kebab-case route strings."""
    dashed = "".join(
        f"-{char}" if idx and char.isupper() else char
        for idx, char in enumerate(name)
    )
    return dashed.replace("_", "-").lower()


def _format_query_params(params: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize query parameters. Convert booleans to 'true'/'false' and omit None."""
    cleaned = {}
    for k, v in params.items():
        if v is None:
            continue
        if isinstance(v, bool):
            cleaned[k] = "true" if v else "false"
        else:
            cleaned[k] = v
    return cleaned


class NestApiRequest:
    """NestAPI dynamic client with automatic Sync/Async dispatch and route mapping.

    Supports dynamic service calls:
        api.chat_ai(q="سلام")
        api.ip_info(ip="8.8.8.8")

    And direct path requests:
        api.request("chat-ai", q="سلام")
    """

    def __init__(
        self,
        base_url: str = "https://open.nestapi.ir",
        version: int = 1,
        timeout: Optional[Union[float, httpx.Timeout]] = None,
        headers: Optional[Dict[str, str]] = None,
    ):
        self.Base_URL = base_url.rstrip("/")
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise ValueError("version must be a positive integer")
        self.Version = version
        self.Headers = {"User-Agent": "NestApi-Python/1.0", "Accept": "application/json"}
        if headers:
            self.Headers.update(headers)

        if isinstance(timeout, httpx.Timeout):
            self.Timeout = timeout
        elif isinstance(timeout, (int, float)):
            self.Timeout = httpx.Timeout(timeout)
        else:
            self.Timeout = httpx.Timeout(connect=5.0, read=40.0, write=10.0, pool=10.0)

    def version(self, version: int) -> NestApiRequest:
        """Return a copy of the client configured for a specific API version."""
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise ValueError("version must be a positive integer")
        clone = copy.copy(self)
        clone.Version = version
        return clone

    def _build_url(self, endpoint: str) -> str:
        endpoint = endpoint.lstrip("/")
        if endpoint.startswith("apis-") or endpoint.startswith("http://") or endpoint.startswith("https://"):
            if endpoint.startswith("http://") or endpoint.startswith("https://"):
                return endpoint
            return f"{self.Base_URL}/{endpoint}"
        return f"{self.Base_URL}/apis-{self.Version}/{quote(endpoint, safe='/')}"

    @staticmethod
    def _parse_error_payload(response: httpx.Response) -> tuple[str, Optional[str], Any]:
        """Extract message, machine-readable code and details from an error body."""
        msg = response.text or f"HTTP {response.status_code} error"
        code = None
        details = None
        try:
            payload = response.json()
            if isinstance(payload, dict):
                err = payload.get("error")
                if isinstance(err, dict):
                    code = err.get("code")
                    msg = err.get("message") or msg
                    details = err.get("details")
                elif isinstance(err, str):
                    msg = err
                code = code or payload.get("error_code") or payload.get("code")
        except (ValueError, TypeError):
            pass
        return msg, code, details

    def _handle_response(self, response: httpx.Response) -> Response:
        status = response.status_code
        if 200 <= status < 300:
            try:
                results = response.json()
                if not (isinstance(results, dict) and results.get("success") is False):
                    return Response.from_dict(results if isinstance(results, dict) else {"data": results}, status_code=status)
            except (ValueError, TypeError):
                return Response(data=response.text, status_code=status)

        msg, error_code, details = self._parse_error_payload(response)
        kwargs = {"Status_Code": status, "Error_Code": error_code, "details": details, "response": response}
        by_code = {
            "PARAM_NOT_FOUND": ParamNotFoundError,
            "UNAUTHORIZED": AuthenticationError,
            "FORBIDDEN": PermissionDeniedError,
            "NOT_FOUND": NotFoundError,
            "VALIDATION_ERROR": ValidationError,
            "RATE_LIMITED": RateLimitError,
            "RATE_LIMIT_EXCEEDED": RateLimitError,
            "INTERNAL_ERROR": InternalServerError,
            "SERVICE_UNAVAILABLE": ServiceUnavailableError,
        }
        error_class = by_code.get(error_code)
        if error_class is not None:
            raise error_class(msg, **kwargs)

        if status == 400:
            raise ParamNotFoundError(f"Bad Request: {msg}", **kwargs)
        elif status == 401:
            raise AuthenticationError(f"Unauthorized: {msg}", **kwargs)
        elif status == 403:
            raise PermissionDeniedError(f"Forbidden: {msg}", **kwargs)
        elif status == 404:
            raise NotFoundError(f"Not Found: {msg}", **kwargs)
        elif status == 422:
            raise ValidationError(f"Unprocessable Entity: {msg}", **kwargs)
        elif status == 429:
            raise RateLimitError(f"Too Many Requests: {msg}", **kwargs)
        elif status == 431:
            raise URLtooLongError(f"Request URI Too Large: {msg}", **kwargs)
        elif status == 500:
            raise InternalServerError(f"Internal Server Error: {msg}", **kwargs)
        elif status in (502, 504):
            desc = "Bad Gateway" if status == 502 else "Gateway Timeout"
            raise GatewayError(f"{desc}: {msg}", **kwargs)
        elif status == 503:
            raise ServiceUnavailableError(f"Service Unavailable: {msg}", **kwargs)
        elif status == 520:
            raise CloudflareError(f"Cloudflare Error: {msg}", **kwargs)
        else:
            raise APIResponseError(f"HTTP {status} Error: {msg}", **kwargs)

    def _request_sync(self, endpoint: str, **params) -> Response:
        url = self._build_url(endpoint)
        query = _format_query_params(params)
        try:
            with httpx.Client(timeout=self.Timeout, headers=self.Headers) as client:
                res = client.get(url, params=query)
        except (httpx.NetworkError, httpx.TimeoutException) as e:
            raise NetworkError(f"Network error occurred: {e}") from e

        return self._handle_response(res)

    async def _request_async(self, endpoint: str, **params) -> Response:
        url = self._build_url(endpoint)
        query = _format_query_params(params)
        try:
            async with httpx.AsyncClient(timeout=self.Timeout, headers=self.Headers) as client:
                res = await client.get(url, params=query)
        except (httpx.NetworkError, httpx.TimeoutException) as e:
            raise NetworkError(f"Network error occurred: {e}") from e

        return self._handle_response(res)

    def request(self, endpoint: str, **params) -> Union[Response, Any]:
        """Dispatch request synchronously or asynchronously based on current event loop."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            return self._request_async(endpoint, **params)
        return self._request_sync(endpoint, **params)

    def __getattr__(self, name: str) -> Callable[..., Any]:
        """Dynamically map method access to API service routes.

        Example:
            api.chat_ai(q="Hello") -> GET /apis-1/chat-ai?q=Hello
        """
        if name.startswith("_"):
            raise AttributeError(f"{type(self).__name__!r} object has no attribute {name!r}")

        route = _to_route(name)

        def caller(*args, **kwargs):
            if args:
                if len(args) == 1 and isinstance(args[0], dict):
                    kwargs = {**args[0], **kwargs}
                else:
                    raise TypeError("Positional arguments not supported; use key=value pairs.")
            return self.request(route, **kwargs)

        return caller


class NestApi(NestApiRequest):
    """Explicit Synchronous NestAPI client with connection pooling and context manager support."""

    def __init__(
        self,
        base_url: str = "https://open.nestapi.ir",
        version: int = 1,
        timeout: Optional[Union[float, httpx.Timeout]] = None,
        headers: Optional[Dict[str, str]] = None,
    ):
        super().__init__(base_url=base_url, version=version, timeout=timeout, headers=headers)
        self._client = httpx.Client(timeout=self.Timeout, headers=self.Headers)

    def request(self, endpoint: str, **params) -> Response:
        url = self._build_url(endpoint)
        query = _format_query_params(params)
        try:
            res = self._client.get(url, params=query)
        except (httpx.NetworkError, httpx.TimeoutException) as e:
            raise NetworkError(f"Network error occurred: {e}") from e
        return self._handle_response(res)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> NestApi:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


class AsyncNestApi(NestApiRequest):
    """Explicit Asynchronous NestAPI client with connection pooling and async context manager."""

    def __init__(
        self,
        base_url: str = "https://open.nestapi.ir",
        version: int = 1,
        timeout: Optional[Union[float, httpx.Timeout]] = None,
        headers: Optional[Dict[str, str]] = None,
    ):
        super().__init__(base_url=base_url, version=version, timeout=timeout, headers=headers)
        self._client = httpx.AsyncClient(timeout=self.Timeout, headers=self.Headers)

    async def request(self, endpoint: str, **params) -> Response:
        url = self._build_url(endpoint)
        query = _format_query_params(params)
        try:
            res = await self._client.get(url, params=query)
        except (httpx.NetworkError, httpx.TimeoutException) as e:
            raise NetworkError(f"Network error occurred: {e}") from e
        return self._handle_response(res)

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> AsyncNestApi:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()
