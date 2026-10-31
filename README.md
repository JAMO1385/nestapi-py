# NestAPI Python Client

[![Python Version](https://img.shields.io/badge/python-%3E%3D3.10-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A small, fully dynamic Python client for the [NestAPI](https://nestapi.ir/api-usage) web services.

The library contains no service names: any method you call becomes a route. New services work the moment they go live, and removed ones need no code change.

## Features

- **Dynamic routing:** `api.ip_info()` calls `ip-info` with no per-service classes or models
- **Keyword or dict parameters**, with validation left to the server
- **Immutable version switching** through `version()`
- **Read-only responses** with dot-path access and `res["key"]` lookups
- **Typed exceptions** mapped from the API's `error.code`
- **Fully typed**, and built on `httpx` with your own client as an option

## Requirements

- Python 3.10 or higher
- [httpx](https://www.python-httpx.org/), installed automatically

## Installation

From a checkout of this repository:

```bash
pip install .
```

## Quick start

```python
from nestapi import NestApi

with NestApi() as api:
    result = api.bmi(age=30, weight=70, height=175)

    print(result["bmi"])             # 22.86
    print(result.get("input.age"))   # 30
```

This client is synchronous only.

## Routing

The route is built from the method name. Every `_` becomes `-`, every uppercase letter except the first starts a new `-` segment, and the result is lowercase.

| Method | Route |
|---|---|
| `ip_info` | `ip-info` |
| `search_shazam` | `search-shazam` |
| `chatAi`, `ChatAi` | `chat-ai` |
| `chatAI` | `chat-a-i` |

Names starting with `_` are not services and raise `AttributeError`.

Pass parameters as keyword arguments or as a single dict. The dict form is needed for names that are Python keywords, such as `from` or `in`.

```python
api.bmi(age=30, weight=70, height=175)
api.bmi({"age": 30, "weight": 70, "height": 175})

api.convert({"from": "USD", "in": "EUR"})

api.bmi(30, 70)                  # TypeError: arguments must be named
api.bmi({"age": 30}, weight=70)  # TypeError: use one form, not both
api.bmi({1: "a"})                # TypeError: names must be strings
```

### Explicit calls

```python
# GET with the exact route name, no conversion
api.call("ip-info", {"ip": "8.8.8.8"})

# Any other HTTP method; parameters still go in the query string
api.request("POST", "some-service", {"a": 1})
```

> [!NOTE]
> Services named `call`, `request`, `version` or `close` collide with the client's own methods. Reach them through `call()`, for example `api.call("version")`.

### Parameter values

| Python value | Sent as | Notes |
|---|---|---|
| `True` / `False` | `x=true` / `x=false` | The server rejects `1`, `0`, `True` and `TRUE` |
| `None` | Not sent | Also skipped inside lists and dicts |
| `list` / `tuple` | `x=1&x=2` | Repeated keys. Not yet verified against the live API, as no documented service takes an array input |
| `dict` | `x[key]=1` | Same format as the PHP client |

Spaces are encoded as `%20`, and non-ASCII text is sent as UTF-8.

## Versions

The default version is `1`, and the `apis-` prefix is added for you. `version()` returns a copy and leaves the original instance unchanged. A version below `1` raises `ValueError`, and anything other than an `int`, including `bool`, raises `TypeError`.

```python
api = NestApi(version=2)

v3 = api.version(3)
```

There is no automatic "latest version" mode. The `source.version` field in responses is unrelated to the version in the URL.

## Responses

A successful call returns a read-only `nestapi.Response`.

```python
result = api.bmi(age=30, weight=70, height=175)

result.data                  # Dict, list, string or None
result.meta                  # Optional, service-defined
result.source                # {"name": "NestAPI", ...}

result.get("input.age")      # 30
result.get("input.nope", 0)  # 0
result.get("items.0.title")  # Paths can index into lists

result["bmi"]                # 22.86
"bmi" in result              # True
result["nope"]               # KeyError

result.data = {}             # AttributeError
result["bmi"] = 1            # TypeError
del result["bmi"]            # TypeError
```

A key that exists with a null value gives `None`, not the default. If `data` is not a dict or list, `get()` returns the default value.

## Error handling

Branch on `error_code`, not on the message, because message text can change.

| Exception | Raised for |
|---|---|
| `ServiceNotFoundError` | `NOT_FOUND`: unknown service or API version |
| `ValidationError` | `PARAM_NOT_FOUND`, `VALIDATION_ERROR` |
| `RateLimitError` | `RATE_LIMITED`, `RATE_LIMIT_EXCEEDED` |
| `ServerError` | Any other code with HTTP status 500 or above |
| `ApiError` | Base class of the above, and any other code such as `INVALID_IP` |
| `TransportError` | Network failure, non-JSON body, or a body outside the API format |

`TransportError` is separate from `ApiError`, so catch it as well if you want to handle every failure.

```python
from nestapi import ApiError, NestApi, TransportError, ValidationError

try:
    api.bmi(age=500, weight=70, height=175)
except ValidationError as e:
    e.error_code  # "VALIDATION_ERROR"
    e.status      # 422
    e.details     # {"query.age": "Must be less than or equal to 120"}
except ApiError as e:
    ...           # Any other error reported by the API
except TransportError as e:
    ...           # No usable response arrived; the cause is in e.__cause__
```

`details` is a list for `PARAM_NOT_FOUND` and a dict for `VALIDATION_ERROR`.

## Configuration

`NestApi()` works without any setup. Every option can be set through the constructor:

```python
import httpx

api = NestApi(
    version=1,
    base_url="https://open.nestapi.ir",
    timeout=30,                  # Seconds, default client only
    client=httpx.Client(),       # Optional
)
```

SSL verification is always on in the default client, and there is no option to turn it off.

### Closing connections

Call `close()` or use `with NestApi() as api:` to release the connection.

- A client you inject stays yours: `close()` leaves it open.
- Copies from `version()` share the client of the original. Closing a copy does nothing, so the original keeps working.
- Closing the original closes the shared client, and its copies then raise `TransportError`.

## Testing

```bash
pip install -e ".[dev]"
```

```bash
pytest
```

## License

Released under the [MIT License](LICENSE).
