"""Read-only view of a successful API response."""

from __future__ import annotations

from typing import Any


class Response:
    """Read-only view of a successful API response.

    Item access reads top-level keys of ``data``; :meth:`get` follows dot paths.
    The attributes cannot be reassigned, but the objects they hold are plain
    decoded JSON.
    """

    __slots__ = ("_data", "_meta", "_source")

    # Without this, Python would fall back to iterating through __getitem__.
    __iter__ = None

    def __init__(self, data: Any, meta: Any, source: dict[str, Any]) -> None:
        self._data = data
        self._meta = meta
        self._source = source

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Response:
        """Build a Response from the decoded JSON of a successful response."""
        source = payload.get("source")

        return cls(
            payload.get("data"),
            payload.get("meta"),
            source if isinstance(source, dict) else {},
        )

    @property
    def data(self) -> Any:
        """Object, list, string or None."""
        return self._data

    @property
    def meta(self) -> Any:
        """Service-defined; None when absent."""
        return self._meta

    @property
    def source(self) -> dict[str, Any]:
        """Service identity. Unrelated to the version in the URL."""
        return self._source

    def get(self, path: str, default: Any = None) -> Any:
        """Read from ``data`` by dot path, e.g. ``input.age`` or ``items.0.title``.

        A key that exists with a null value returns None, not ``default``.
        """
        value = self._data

        for key in path.split("."):
            if isinstance(value, dict):
                if key not in value:
                    return default
                value = value[key]
            elif isinstance(value, list):
                if not (key.isascii() and key.isdigit()) or int(key) >= len(value):
                    return default
                value = value[int(key)]
            else:
                return default

        return value

    def __getitem__(self, key: Any) -> Any:
        if key not in self:
            raise KeyError(key)

        return self._data[key]

    def __contains__(self, key: Any) -> bool:
        if isinstance(self._data, dict):
            return key in self._data

        if isinstance(self._data, list):
            is_index = isinstance(key, int) and not isinstance(key, bool)
            return is_index and 0 <= key < len(self._data)

        return False
