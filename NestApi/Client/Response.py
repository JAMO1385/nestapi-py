from __future__ import annotations

from typing import Any, Dict, Optional


class Response:
    """Read-only view of a successful NestAPI response.

    Supports dot-notation path traversal via ``get()`` and key/index access via ``[]``.
    """

    __slots__ = ("_data", "_meta", "_source", "_status_code", "_raw")

    def __init__(
        self,
        data: Any,
        meta: Any = None,
        source: Optional[Dict[str, Any]] = None,
        status_code: int = 200,
        raw: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._data = data
        self._meta = meta
        self._source = source or {}
        self._status_code = status_code
        self._raw = raw or {}

    @classmethod
    def from_dict(cls, payload: Dict[str, Any], status_code: int = 200) -> Response:
        """Create Response instance from decoded JSON payload."""
        return cls(
            data=payload.get("data"),
            meta=payload.get("meta"),
            source=payload.get("source") if isinstance(payload.get("source"), dict) else {},
            status_code=status_code,
            raw=payload,
        )

    @property
    def data(self) -> Any:
        """Core data payload returned by the endpoint."""
        return self._data

    @property
    def meta(self) -> Any:
        """Metadata provided by the endpoint (or None)."""
        return self._meta

    @property
    def source(self) -> Dict[str, Any]:
        """API provider and version metadata."""
        return self._source

    @property
    def status_code(self) -> int:
        """HTTP status code of the response."""
        return self._status_code

    @property
    def raw(self) -> Dict[str, Any]:
        """Full raw JSON response payload."""
        return self._raw

    def get(self, path: str, default: Any = None) -> Any:
        """Retrieve nested value from ``data`` using dot-separated keys.

        Example:
            response.get("user.profile.name")
            response.get("items.0.title")
        """
        value = self._data
        for part in path.split("."):
            if isinstance(value, dict):
                if part not in value:
                    return default
                value = value[part]
            elif isinstance(value, (list, tuple)):
                if not (part.isascii() and part.isdigit()) or int(part) >= len(value):
                    return default
                value = value[int(part)]
            else:
                return default
        return value

    def __getitem__(self, key: Any) -> Any:
        if isinstance(self._data, dict):
            return self._data[key]
        if isinstance(self._data, (list, tuple)) and isinstance(key, int):
            return self._data[key]
        raise KeyError(key)

    def __contains__(self, key: Any) -> bool:
        if isinstance(self._data, dict):
            return key in self._data
        if isinstance(self._data, (list, tuple)) and isinstance(key, int):
            return 0 <= key < len(self._data)
        return False

    def __repr__(self) -> str:
        return f"<Response status={self._status_code} data={self._data!r}>"
