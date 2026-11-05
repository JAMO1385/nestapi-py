# NestAPI Python

A Python SDK for the [NestAPI](https://nestapi.ir) web services, featuring dynamic routing, synchronous and asynchronous clients, and structured error handling.

## Features

- **Dynamic routing:** Method names are automatically converted to API routes (for example, `api.chat_ai()` maps to `/apis-1/chat-ai`).
- **Sync and async clients:** Use `NestApi` for synchronous requests, `AsyncNestApi` for asynchronous requests, or `NestApiRequest` for automatic dispatch.
- **Connection pooling:** Efficiently manages HTTP sessions and connections with `httpx`.
- **Convenient response object:** Supports dictionary and list access, as well as dot-path lookup such as `res.get("user.profile.name")`.
- **Typed exceptions:** Categorizes API and network errors using API error codes and HTTP status codes.

## What makes this version better

Compared with [`devh3n/nestapi-py`](https://github.com/devh3n/nestapi-py), this version retains the dynamic-routing approach and adds:

- Compatibility with the original `NestApi` exception names and attributes.
- Machine-readable `error.code` and `error.details` preserved on exceptions.
- Safer handling of empty, HTML, and malformed error responses.
- Support for all successful 2xx responses, not only HTTP 200.
- Validation of API versions and URL quoting for dynamic routes.
- A ready-to-use development extra and pytest configuration.

## Requirements and installation

Install the project and its dependencies from the project root:

```bash
pip install .
```

For editable installation with development and testing tools:

```bash
pip install -e ".[dev]"
```

## Usage

### 1. Synchronous client (recommended for synchronous code)

```python
from NestApi import NestApi

# The context manager closes connections automatically.
with NestApi() as api:
    response = api.chat_ai(q="Hello, how are you?")
    print("Status:", response.status_code)
    print("AI response:", response.data)
    print("Nested value:", response.get("ai.reply", "Not found"))
```

### 2. Asynchronous client (recommended for async applications)

```python
import asyncio
from NestApi import AsyncNestApi

async def main():
    async with AsyncNestApi() as api:
        response = await api.bmi(age=25, weight=70, height=175)
        print("BMI:", response.get("bmi"))

asyncio.run(main())
```

### 3. Automatic sync/async dispatch

```python
from NestApi import NestApiRequest

client = NestApiRequest()

# In synchronous code, this runs synchronously.
sync_response = client.ip_info(ip="8.8.8.8")
print(sync_response.data)

# In async code, it returns a coroutine that can be awaited.
async def async_call():
    async_response = await client.ip_info(ip="8.8.8.8")
    print(async_response.data)
```

### 4. Switching API versions

```python
api = NestApi(version=1)
v2_api = api.version(2)  # Routes requests through /apis-2/.
```

## Working with the response object

Requests return a convenient `Response` object:

```python
response = api.chat_ai(q="test")

response.status_code  # HTTP status code, e.g. 200
response.data         # Main payload: dict, list, string, or None
response.meta         # Response metadata
response.source       # NestAPI service information
response.raw          # Complete raw JSON response

# Dot-path lookup:
response.get("user.name")
response.get("items.0.title")
response.get("unknown.field", default="Not found")

# Dictionary-style access:
response["reply"]
"reply" in response
```

## Exception handling

Exceptions are selected based on the API error code and HTTP status code:

```python
from NestApi import (
    NestApi,
    ParamNotFoundError,
    NotFoundError,
    RateLimitError,
    NetworkError,
    APIResponseError,
)

with NestApi() as api:
    try:
        response = api.chat_ai(q="")
    except ParamNotFoundError as exc:
        print(f"Invalid parameter: [{exc.status_code}: {exc.error_code}] {exc.message}")
    except NotFoundError:
        print("The requested endpoint or resource was not found.")
    except RateLimitError:
        print("The request limit has been exceeded.")
    except NetworkError as exc:
        print(f"Network or connectivity error: {exc}")
    except APIResponseError as exc:
        print(f"API request failed: {exc}")
```

### Exception classes

| Exception | HTTP status / cause |
|---|---|
| `ParamNotFoundError` | 400 — Required or valid query parameters are missing or invalid. |
| `AuthenticationError` | 401 — Authentication is required or invalid. |
| `PermissionDeniedError` | 403 — Access is denied. |
| `NotFoundError` | 404 — The endpoint or resource was not found. |
| `ValidationError` | 422 — The submitted data is invalid. |
| `RateLimitError` | 429 — The request rate limit was exceeded. |
| `URLtooLongError` | 431 — The request URL is too long. |
| `InternalServerError` | 500 — An internal NestAPI server error occurred. |
| `GatewayError` | 502 / 504 — A gateway error occurred. |
| `ServiceUnavailableError` | 503 — The service is temporarily unavailable. |
| `CloudflareError` | 520 — An unknown Cloudflare edge error occurred. |
| `NetworkError` | Connection failure, timeout, or DNS error. |

## Testing

The project includes unit tests using `pytest` and `respx` to mock HTTP requests, so the tests do not need to call the live API.

### Install test dependencies

```bash
pip install -e ".[dev]"
```

If the development extra is not configured, install the test packages directly:

```bash
pip install pytest pytest-asyncio respx
```

### Run the tests

```bash
# Run the full test suite
pytest

# Show each test name and its result
pytest -v

# Also display output captured from the tests
pytest -v -s
```

### Test coverage

`tests/test_nestapi.py` covers dynamic route conversion (`_to_route`), query serialization, `Response` behavior, synchronous and asynchronous clients, automatic dispatch through `NestApiRequest`, API error-code mapping, and simulated network failures.

## License

See the `LICENSE` file in the repository for license terms.
