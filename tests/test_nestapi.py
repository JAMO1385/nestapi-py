import asyncio
import pytest
import respx
import httpx
from NestApi import (
    NestApi,
    AsyncNestApi,
    NestApiRequest,
    Response,
    NestError,
    APIResponseError,
    ParamNotFoundError,
    AuthenticationError,
    PermissionDeniedError,
    NotFoundError,
    ValidationError,
    RateLimitError,
    URLtooLongError,
    InternalServerError,
    GatewayError,
    ServiceUnavailableError,
    CloudflareError,
    NetworkError,
)
from NestApi.Client.NestApi import _to_route, _format_query_params


# ==========================================
# 1. Tests for Routing & Query Formatting
# ==========================================

def test_to_route():
    assert _to_route("chat_ai") == "chat-ai"
    assert _to_route("search_shazam") == "search-shazam"
    assert _to_route("ip_info") == "ip-info"
    assert _to_route("bmi") == "bmi"
    assert _to_route("chatAi") == "chat-ai"


def test_format_query_params():
    params = {
        "name": "ali",
        "is_active": True,
        "is_admin": False,
        "empty": None,
        "age": 20,
    }
    formatted = _format_query_params(params)
    assert formatted["name"] == "ali"
    assert formatted["is_active"] == "true"
    assert formatted["is_admin"] == "false"
    assert formatted["age"] == 20
    assert "empty" not in formatted


# ==========================================
# 2. Tests for Response Model
# ==========================================

def test_response_from_dict():
    payload = {
        "data": {
            "user": {"name": "Ali", "age": 25},
            "tags": ["python", "api"],
            "score": 98.5,
        },
        "meta": {"page": 1, "total": 10},
        "source": {"name": "NestAPI", "version": "1.0"},
    }
    res = Response.from_dict(payload, status_code=200)

    assert res.status_code == 200
    assert res.data == payload["data"]
    assert res.meta == {"page": 1, "total": 10}
    assert res.source == {"name": "NestAPI", "version": "1.0"}
    assert res.raw == payload

    # Dot-path traversal
    assert res.get("user.name") == "Ali"
    assert res.get("user.age") == 25
    assert res.get("tags.0") == "python"
    assert res.get("tags.1") == "api"
    assert res.get("user.invalid", "default_val") == "default_val"
    assert res.get("tags.99", "missing") == "missing"

    # Indexing & membership
    assert res["user"]["name"] == "Ali"
    assert "user" in res
    assert "nonexistent" not in res
    assert "<Response status=200" in repr(res)


def test_response_list_data():
    res = Response(data=[10, 20, 30], status_code=200)
    assert res[0] == 10
    assert 1 in res
    assert 5 not in res
    assert res.get("1") == 20
    assert res.get("9") is None


# ==========================================
# 3. Tests for Sync NestApi Client
# ==========================================

@respx.mock
def test_sync_nestapi_dynamic_call():
    route = respx.get("https://open.nestapi.ir/apis-1/chat-ai").respond(
        status_code=200,
        json={"data": {"reply": "سلام"}, "meta": None, "source": {"name": "NestAPI"}},
    )

    with NestApi() as api:
        res = api.chat_ai(q="سلام", fast=True)
        assert res.status_code == 200
        assert res.data["reply"] == "سلام"
        assert res.get("reply") == "سلام"

    assert route.called
    assert route.calls.last.request.url.query.decode() == "q=%D8%B3%D9%84%D8%A7%D9%85&fast=true"


@respx.mock
def test_sync_nestapi_manual_request():
    route = respx.get("https://open.nestapi.ir/apis-1/ip-info").respond(
        status_code=200,
        json={"data": {"ip": "1.1.1.1", "country": "US"}},
    )

    api = NestApi()
    try:
        res = api.request("/apis-1/ip-info", ip="1.1.1.1")
        assert res.data["ip"] == "1.1.1.1"
    finally:
        api.close()

    assert route.called


def test_nestapi_version_switch():
    api = NestApi(version=1)
    v2 = api.version(2)
    assert v2.Version == 2
    assert v2._build_url("bmi") == "https://open.nestapi.ir/apis-2/bmi"


# ==========================================
# 4. Tests for Async NestApi Client
# ==========================================

@pytest.mark.asyncio
@respx.mock
async def test_async_nestapi_dynamic_call():
    route = respx.get("https://open.nestapi.ir/apis-1/search-shazam").respond(
        status_code=200,
        json={"data": {"title": "Song Title", "artist": "Artist"}},
    )

    async with AsyncNestApi() as api:
        res = await api.search_shazam(url="https://example.com/audio.mp3")
        assert res.status_code == 200
        assert res.get("title") == "Song Title"

    assert route.called


# ==========================================
# 5. Tests for Dual-Mode NestApiRequest
# ==========================================

@respx.mock
def test_nestapi_request_auto_sync():
    respx.get("https://open.nestapi.ir/apis-1/bmi").respond(
        status_code=200,
        json={"data": {"bmi": 22.5}},
    )

    client = NestApiRequest()
    res = client.bmi(height=180, weight=75)
    assert res.get("bmi") == 22.5


@pytest.mark.asyncio
@respx.mock
async def test_nestapi_request_auto_async():
    respx.get("https://open.nestapi.ir/apis-1/bmi").respond(
        status_code=200,
        json={"data": {"bmi": 22.5}},
    )

    client = NestApiRequest()
    res = await client.bmi(height=180, weight=75)
    assert res.get("bmi") == 22.5


# ==========================================
# 6. Tests for HTTP Error & Exception Mapping
# ==========================================

@pytest.mark.parametrize(
    "status,exc_class",
    [
        (400, ParamNotFoundError),
        (401, AuthenticationError),
        (403, PermissionDeniedError),
        (404, NotFoundError),
        (422, ValidationError),
        (429, RateLimitError),
        (431, URLtooLongError),
        (500, InternalServerError),
        (502, GatewayError),
        (503, ServiceUnavailableError),
        (504, GatewayError),
        (520, CloudflareError),
        (418, APIResponseError),
    ],
)
@respx.mock
def test_exceptions_mapping(status, exc_class):
    respx.get("https://open.nestapi.ir/apis-1/error-test").respond(
        status_code=status,
        json={"error": {"code": "TEST_ERR", "message": "Failed"}},
    )

    api = NestApi()
    try:
        with pytest.raises(exc_class) as exc_info:
            api.error_test()
        
        assert exc_info.value.status_code == status
        assert exc_info.value.error_code == "TEST_ERR"
        assert "Failed" in str(exc_info.value)
    finally:
        api.close()


def test_response_keyerror():
    res = Response(data={"a": 1})
    with pytest.raises(KeyError):
        _ = res["b"]


def test_exception_string_representation():
    err1 = ParamNotFoundError("Missing param", Status_Code=400, Error_Code="PARAM_NOT_FOUND")
    assert str(err1) == "[400 : PARAM_NOT_FOUND] Missing param"

    err2 = InternalServerError("Crash", Status_Code=500)
    assert str(err2) == "[500] Crash"


@respx.mock
def test_response_non_json_fallback():
    respx.get("https://open.nestapi.ir/apis-1/plain").respond(
        status_code=200,
        text="plain text response",
    )
    with NestApi() as api:
        res = api.plain()
        assert res.data == "plain text response"
        assert res.status_code == 200


@respx.mock
def test_network_error_wrapping():
    respx.get("https://open.nestapi.ir/apis-1/network-fail").mock(
        side_effect=httpx.ConnectError("Connection refused")
    )

    api = NestApi()
    try:
        with pytest.raises(NetworkError) as exc_info:
            api.network_fail()
        assert "Network error occurred" in str(exc_info.value)
    finally:
        api.close()

