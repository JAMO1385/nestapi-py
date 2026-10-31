from __future__ import annotations

import asyncio
import copy
import json
import pickle
from collections.abc import Coroutine
from typing import Any

import httpx
import pytest

from nestapi import (
    ApiError,
    AsyncNestApi,
    NestApi,
    RateLimitError,
    Response,
    ServerError,
    ServiceNotFoundError,
    TransportError,
    ValidationError,
)

OK = (
    '{"success":true,"data":{"bmi":22.86,"input":{"age":30,"note":null},'
    '"items":[{"id":7}]},"meta":{"page":2},"source":{"name":"NestAPI","version":"1.0.1"}}'
)


class Fake:
    """Injected httpx client answering every request with one canned response."""

    def __init__(self, body: str | bytes = OK, status: int = 200) -> None:
        self.requests: list[httpx.Request] = []
        self.body = body.encode() if isinstance(body, str) else body
        self.status = status
        self.client = httpx.Client(transport=httpx.MockTransport(self.handle))

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.status, content=self.body)

    def api(self, version: int = 1) -> NestApi:
        return NestApi(version=version, client=self.client)

    @property
    def url(self) -> str:
        return str(self.requests[-1].url)

    @property
    def query(self) -> str:
        return self.requests[-1].url.query.decode()


@pytest.fixture
def fake() -> Fake:
    return Fake()


def respond(body: str | bytes, status: int = 200) -> Response:
    return Fake(body, status).api().foo()


# Routing


@pytest.mark.parametrize(
    ("method", "route"),
    [
        ("ip_info", "ip-info"),
        ("search_shazam", "search-shazam"),
        ("chatAi", "chat-ai"),
        ("ChatAi", "chat-ai"),
        ("chatAI", "chat-a-i"),
        ("bmi", "bmi"),
        ("Bmi", "bmi"),
        ("num2words", "num2words"),
        ("soundcloudDownloadV2", "soundcloud-download-v2"),
        ("soundcloud_download_v2", "soundcloud-download-v2"),
        ("a__b", "a--b"),
    ],
)
def test_method_name_becomes_route(fake: Fake, method: str, route: str) -> None:
    getattr(fake.api(), method)()

    assert fake.url == f"https://open.nestapi.ir/apis-1/{route}"
    assert fake.requests[0].method == "GET"


@pytest.mark.parametrize("name", ["_x", "__x", "_", "__deepcopy__", "__wrapped__", "_repr_html_"])
def test_underscore_names_are_not_services(fake: Fake, name: str) -> None:
    with pytest.raises(AttributeError):
        getattr(fake.api(), name)

    assert not hasattr(fake.api(), name)


@pytest.mark.parametrize("client_class", [NestApi, AsyncNestApi])
def test_only_documented_public_names_exist(client_class: type[Any]) -> None:
    public = {name for name in dir(client_class) if not name.startswith("_")}

    assert public == {"call", "request", "version", "close"}


def test_instance_state_is_private(fake: Fake) -> None:
    assert all(name.startswith("_") for name in vars(fake.api()))


def test_helpers_do_not_shadow_services(fake: Fake) -> None:
    fake.api().build_url(a=1)
    assert fake.url == "https://open.nestapi.ir/apis-1/build-url?a=1"

    fake.api().parse()
    assert fake.url == "https://open.nestapi.ir/apis-1/parse"


# Parameters


def test_named_arguments(fake: Fake) -> None:
    fake.api().bmi(age=30, weight=70, height=175)

    assert fake.url == "https://open.nestapi.ir/apis-1/bmi?age=30&weight=70&height=175"


def test_dict_argument(fake: Fake) -> None:
    fake.api().bmi({"age": 30, "weight": 70, "height": 175})

    assert fake.url == "https://open.nestapi.ir/apis-1/bmi?age=30&weight=70&height=175"


def test_dict_argument_reaches_keyword_names(fake: Fake) -> None:
    fake.api().convert({"from": "USD", "in": "EUR"})

    assert fake.query == "from=USD&in=EUR"


def test_named_arguments_may_match_internal_names(fake: Fake) -> None:
    fake.api().foo(
        self="a",
        name="b",
        service="c",
        params="d",
        named="e",
        route="f",
        version=3,
        key="g",
    )

    assert fake.query == "self=a&name=b&service=c&params=d&named=e&route=f&version=3&key=g"


@pytest.mark.parametrize(
    "arguments",
    [
        (30, 70),
        (30,),
        (None,),
        ("a",),
        ([30, 70],),
        ({"age": 30}, {"weight": 70}),
        ({"age": 30}, 70),
    ],
)
def test_unnamed_arguments_are_rejected(fake: Fake, arguments: tuple[Any, ...]) -> None:
    with pytest.raises(TypeError):
        fake.api().bmi(*arguments)

    assert fake.requests == []


@pytest.mark.parametrize("params", [{"age": 30}, {}])
def test_mixing_dict_and_named_arguments_is_rejected(fake: Fake, params: dict[str, Any]) -> None:
    with pytest.raises(TypeError):
        fake.api().bmi(params, weight=70)

    assert fake.requests == []


@pytest.mark.parametrize("params", [{1: "a"}, {None: "a"}, {"a": "b", 2: "c"}, {"x": {1: "a"}}])
def test_non_string_keys_are_rejected(fake: Fake, params: dict[Any, Any]) -> None:
    for send in (fake.api().bmi, lambda p: fake.api().call("bmi", p)):
        with pytest.raises(TypeError):
            send(params)

    assert fake.requests == []


def test_booleans_are_sent_as_words(fake: Fake) -> None:
    fake.api().foo(on=True, off=False)

    assert fake.query == "on=true&off=false"


def test_zero_and_empty_string_are_kept(fake: Fake) -> None:
    fake.api().foo(zero=0, one=1, empty="", real=1.5)

    assert fake.query == "zero=0&one=1&empty=&real=1.5"


def test_none_is_not_sent(fake: Fake) -> None:
    fake.api().foo(a=None, b=1, c=[None, 2], d={"e": None})

    assert fake.query == "b=1&c=2"


def test_only_none_sends_no_query(fake: Fake) -> None:
    fake.api().foo(a=None)

    assert fake.url == "https://open.nestapi.ir/apis-1/foo"


def test_lists_and_tuples_are_sent_as_repeated_keys(fake: Fake) -> None:
    fake.api().foo(ids=[1, 2], tags=("a", "b"), flags=[True, False], empty=[])

    assert fake.query == "ids=1&ids=2&tags=a&tags=b&flags=true&flags=false"


def test_nested_dicts_use_brackets_like_php(fake: Fake) -> None:
    fake.api().foo(x={"key": 1, "on": True, "deep": {"y": [1, 2]}}, z=[{"a": 1}])

    assert httpx.URL(fake.url).params.multi_items() == [
        ("x[key]", "1"),
        ("x[on]", "true"),
        ("x[deep][y]", "1"),
        ("x[deep][y]", "2"),
        ("z[0][a]", "1"),
    ]
    assert fake.query.startswith("x%5Bkey%5D=1&")


def test_values_are_percent_encoded(fake: Fake) -> None:
    fake.api().foo(q="a b&c=[0]=+", fa="سلام دنیا")

    assert fake.query == (
        "q=a%20b%26c%3D%5B0%5D%3D%2B"
        "&fa=%D8%B3%D9%84%D8%A7%D9%85%20%D8%AF%D9%86%DB%8C%D8%A7"
    )
    assert httpx.URL(fake.url).params["fa"] == "سلام دنیا"


def test_percent_sign_is_not_decoded_on_the_way(fake: Fake) -> None:
    fake.api().foo(q="100%25")

    assert fake.query == "q=100%2525"


# Public methods


def test_call_uses_exact_route(fake: Fake) -> None:
    fake.api().call("MobileSearch", {"q": "x"})
    assert fake.url == "https://open.nestapi.ir/apis-1/MobileSearch?q=x"

    fake.api().call("snake_case")
    assert fake.url == "https://open.nestapi.ir/apis-1/snake_case"


@pytest.mark.parametrize("service", ["call", "request", "version", "close"])
def test_colliding_services_are_reachable_through_call(fake: Fake, service: str) -> None:
    fake.api().call(service)

    assert fake.url == f"https://open.nestapi.ir/apis-1/{service}"


def test_service_name_cannot_change_the_url(fake: Fake) -> None:
    fake.api().call("a b?x=1#y", {"q": 1})

    assert fake.url == "https://open.nestapi.ir/apis-1/a%20b%3Fx%3D1%23y?q=1"


def test_slash_in_service_name_is_kept(fake: Fake) -> None:
    fake.api().call("group/sub")

    assert fake.url == "https://open.nestapi.ir/apis-1/group/sub"


def test_request_sends_method_and_keeps_params_in_query(fake: Fake) -> None:
    fake.api().request("post", "upload-file", {"a": 1})

    request = fake.requests[0]
    assert request.method == "POST"
    assert request.url.query == b"a=1"
    assert request.content == b""


@pytest.mark.parametrize("params", [[30, 70], [], "a=1", 5])
def test_call_and_request_reject_non_dict_params(fake: Fake, params: Any) -> None:
    with pytest.raises(TypeError):
        fake.api().call("bmi", params)

    with pytest.raises(TypeError):
        fake.api().request("GET", "bmi", params)

    assert fake.requests == []


def test_accepts_json(fake: Fake) -> None:
    fake.api().bmi()

    assert fake.requests[0].headers["accept"] == "application/json"


# Version


def test_default_version_is_one(fake: Fake) -> None:
    fake.api().bmi()

    assert "/apis-1/bmi" in fake.url


def test_constructor_version(fake: Fake) -> None:
    fake.api(version=2).bmi()

    assert "/apis-2/bmi" in fake.url


def test_version_returns_copy_and_leaves_original_unchanged(fake: Fake) -> None:
    api = fake.api()
    other = api.version(3)

    assert other is not api
    assert type(other) is NestApi

    other.bmi()
    assert "/apis-3/bmi" in fake.url

    api.bmi()
    assert "/apis-1/bmi" in fake.url


@pytest.mark.parametrize("version", [0, -1])
def test_version_below_one_is_rejected(fake: Fake, version: int) -> None:
    with pytest.raises(ValueError):
        NestApi(version=version)

    with pytest.raises(ValueError):
        fake.api().version(version)


@pytest.mark.parametrize("version", [True, False, 1.0, "1", "apis-1", None])
def test_non_int_version_is_rejected(fake: Fake, version: Any) -> None:
    with pytest.raises(TypeError):
        NestApi(version=version)

    with pytest.raises(TypeError):
        fake.api().version(version)


def test_source_version_does_not_affect_url() -> None:
    fake = Fake('{"success":true,"data":1,"source":{"version":"9.9.9"}}')
    api = fake.api()

    api.bmi()
    api.bmi()

    assert "/apis-1/bmi" in fake.url


# Configuration and connection


def test_base_url_is_configurable(fake: Fake) -> None:
    NestApi(base_url="https://example.test/proxy/", client=fake.client).bmi()

    assert fake.url == "https://example.test/proxy/apis-1/bmi"


def test_default_client_uses_thirty_second_timeout() -> None:
    with NestApi() as api:
        assert api._client.timeout == httpx.Timeout(30.0)


def test_timeout_is_configurable_on_default_client() -> None:
    with NestApi(timeout=5) as api:
        assert api._client.timeout == httpx.Timeout(5)


def test_timeout_leaves_injected_client_alone() -> None:
    client = httpx.Client(timeout=7)

    NestApi(timeout=5, client=client)

    assert client.timeout == httpx.Timeout(7)
    client.close()


def test_failed_constructor_does_not_recurse() -> None:
    api = NestApi.__new__(NestApi)

    with pytest.raises(AttributeError):
        api._client


def test_close_closes_default_client() -> None:
    api = NestApi()
    client = api._client

    api.close()

    assert client.is_closed


def test_context_manager_closes_default_client() -> None:
    with NestApi() as api:
        client = api._client

    assert client.is_closed


def test_close_leaves_injected_client_open(fake: Fake) -> None:
    with fake.api() as api:
        api.bmi()

    api.close()

    assert not fake.client.is_closed
    api.bmi()


def test_closing_a_copy_keeps_the_original_working() -> None:
    api = NestApi()
    other = api.version(2)

    assert other._client is api._client

    other.close()
    with other:
        pass
    assert not api._client.is_closed

    api.close()
    assert api._client.is_closed


def test_closing_a_shallow_copy_keeps_the_original_working() -> None:
    api = NestApi()

    copy.copy(api).close()

    assert not api._client.is_closed
    api.close()


def test_closed_client_raises_transport_error() -> None:
    api = NestApi()
    other = api.version(2)

    api.close()

    with pytest.raises(TransportError):
        other.bmi()


def test_copying_injected_client_shares_it(fake: Fake) -> None:
    other = copy.copy(fake.api(version=2))

    other.bmi()

    assert other._client is fake.client
    assert "/apis-2/bmi" in fake.url


@pytest.mark.parametrize("clone", [copy.deepcopy, lambda a: pickle.loads(pickle.dumps(a))])
def test_deep_clone_gets_its_own_client(clone: Any) -> None:
    api = NestApi(version=4, base_url="https://example.test", timeout=9)
    other = clone(api.version(5))

    assert other._client is not api._client
    assert other._client.timeout == httpx.Timeout(9)
    assert other._build_url("bmi", {}) == "https://example.test/apis-5/bmi"

    other.close()
    assert other._client.is_closed
    assert not api._client.is_closed
    api.close()


# Response


def test_response_attributes(fake: Fake) -> None:
    response = fake.api().bmi()

    assert isinstance(response, Response)
    assert response.data["bmi"] == 22.86
    assert response.meta == {"page": 2}
    assert response.source["name"] == "NestAPI"


@pytest.mark.parametrize("name", ["data", "meta", "source", "other"])
def test_response_attributes_are_read_only(fake: Fake, name: str) -> None:
    response = fake.api().bmi()

    with pytest.raises(AttributeError):
        setattr(response, name, "x")

    assert not hasattr(response, "other")


@pytest.mark.parametrize("name", ["data", "meta", "source"])
def test_response_attributes_cannot_be_deleted(fake: Fake, name: str) -> None:
    with pytest.raises(AttributeError):
        delattr(fake.api().bmi(), name)


def test_from_dict_handles_missing_fields() -> None:
    response = Response.from_dict({"success": True})

    assert response.data is None
    assert response.meta is None
    assert response.source == {}


def test_from_dict_ignores_non_object_source() -> None:
    assert Response.from_dict({"source": "x"}).source == {}


def test_get_reads_dot_paths(fake: Fake) -> None:
    response = fake.api().bmi()

    assert response.get("bmi") == 22.86
    assert response.get("input.age") == 30
    assert response.get("items.0.id") == 7
    assert response.get("input.missing", "d") == "d"
    assert response.get("bmi.deeper", "d") == "d"
    assert response.get("items.1.id", "d") == "d"
    assert response.get("items.x", "d") == "d"
    assert response.get("items.-1", "d") == "d"
    assert response.get("items.²", "d") == "d"
    assert response.get("missing") is None


def test_get_returns_existing_null_rather_than_default(fake: Fake) -> None:
    assert fake.api().bmi().get("input.note", "d") is None


@pytest.mark.parametrize("value", ['"hello"', "null", "5", "true"])
def test_non_container_data(value: str) -> None:
    response = respond(f'{{"success":true,"data":{value},"source":{{}}}}')

    assert response.data == json.loads(value)
    assert response.get("a", "d") == "d"
    assert "a" not in response
    assert "hel" not in response

    with pytest.raises(KeyError):
        response["a"]

    with pytest.raises(KeyError):
        response[0]


def test_list_data() -> None:
    response = respond('{"success":true,"data":[{"id":1}],"source":{}}')

    assert response.get("0.id") == 1
    assert response[0] == {"id": 1}
    assert 0 in response
    assert 1 not in response
    assert {"id": 1} not in response
    assert True not in response

    for key in (1, -1, "a", "0", True):
        with pytest.raises(KeyError):
            response[key]


def test_item_access_reads(fake: Fake) -> None:
    response = fake.api().bmi()

    assert response["bmi"] == 22.86
    assert "bmi" in response
    assert "missing" not in response

    with pytest.raises(KeyError):
        response["missing"]


def test_item_access_returns_null_values() -> None:
    response = respond('{"success":true,"data":{"a":null},"source":{}}')

    assert response["a"] is None
    assert "a" in response


def test_item_write_is_rejected(fake: Fake) -> None:
    response = fake.api().bmi()

    with pytest.raises(TypeError):
        response["bmi"] = 1

    assert response["bmi"] == 22.86


def test_item_delete_is_rejected(fake: Fake) -> None:
    response = fake.api().bmi()

    with pytest.raises(TypeError):
        del response["bmi"]

    assert "bmi" in response


def test_response_is_not_iterable(fake: Fake) -> None:
    with pytest.raises(TypeError):
        iter(fake.api().bmi())


def test_response_survives_pickle(fake: Fake) -> None:
    response = pickle.loads(pickle.dumps(fake.api().bmi()))

    assert response["bmi"] == 22.86


# Errors


@pytest.mark.parametrize(
    ("code", "status", "error_class"),
    [
        ("NOT_FOUND", 404, ServiceNotFoundError),
        ("PARAM_NOT_FOUND", 400, ValidationError),
        ("VALIDATION_ERROR", 422, ValidationError),
        ("RATE_LIMITED", 429, RateLimitError),
        ("RATE_LIMIT_EXCEEDED", 429, RateLimitError),
        ("NOT_FOUND", 500, ServiceNotFoundError),
        ("VALIDATION_ERROR", 502, ValidationError),
        ("RATE_LIMITED", 503, RateLimitError),
        ("DATABASE_ERROR", 500, ServerError),
        ("SERVICE_UNAVAILABLE", 503, ServerError),
        ("VOICES_FETCH_FAILED", 502, ServerError),
        ("INVALID_IP", 400, ApiError),
        ("FORBIDDEN", 403, ApiError),
        ("SOMETHING", 499, ApiError),
    ],
)
def test_error_mapping(code: str, status: int, error_class: type[ApiError]) -> None:
    body = json.dumps({"success": False, "error": {"code": code, "message": "m", "details": ["x"]}})

    with pytest.raises(ApiError) as caught:
        respond(body, status)

    assert type(caught.value) is error_class
    assert caught.value.error_code == code
    assert caught.value.status == status
    assert caught.value.details == ["x"]
    assert str(caught.value) == "m"


@pytest.mark.parametrize(
    "error_class", [ServiceNotFoundError, ValidationError, RateLimitError, ServerError]
)
def test_specific_errors_derive_from_api_error(error_class: type[ApiError]) -> None:
    assert issubclass(error_class, ApiError)


def test_error_depends_on_code_not_message() -> None:
    with pytest.raises(ValidationError):
        respond('{"success":false,"error":{"code":"VALIDATION_ERROR","message":"Route not found"}}', 400)


def test_error_on_http_200_is_still_an_error() -> None:
    with pytest.raises(ValidationError):
        respond('{"success":false,"error":{"code":"VALIDATION_ERROR","message":"m"}}')


def test_validation_details_object() -> None:
    body = '{"success":false,"error":{"code":"VALIDATION_ERROR","message":"m","details":{"query.age":"too big"}}}'

    with pytest.raises(ValidationError) as caught:
        respond(body, 422)

    assert caught.value.details == {"query.age": "too big"}


def test_details_are_optional() -> None:
    with pytest.raises(ServiceNotFoundError) as caught:
        respond('{"success":false,"error":{"code":"NOT_FOUND","message":"m"}}', 404)

    assert caught.value.details is None


@pytest.mark.parametrize(
    ("body", "status", "error_class"),
    [
        ('{"success":false}', 400, ApiError),
        ('{"success":false,"error":"boom"}', 400, ApiError),
        ('{"success":false,"error":{"message":"m"}}', 400, ApiError),
        ('{"success":false,"error":{"code":5}}', 400, ApiError),
        ('{"success":false,"error":{"code":["NOT_FOUND"]}}', 404, ApiError),
        ('{"success":false,"error":null}', 499, ApiError),
        ('{"success":false}', 500, ServerError),
        ('{"success":false,"error":{"message":"m"}}', 503, ServerError),
    ],
)
def test_failure_without_error_code(body: str, status: int, error_class: type[ApiError]) -> None:
    with pytest.raises(ApiError) as caught:
        respond(body, status)

    assert type(caught.value) is error_class
    assert caught.value.error_code == ""
    assert caught.value.status == status
    assert str(caught.value)


@pytest.mark.parametrize("copier", [copy.copy, lambda e: pickle.loads(pickle.dumps(e))])
def test_errors_survive_copy_and_pickle(copier: Any) -> None:
    error = copier(ValidationError("m", "VALIDATION_ERROR", 422, {"query.age": "x"}))

    assert type(error) is ValidationError
    assert str(error) == "m"
    assert error.error_code == "VALIDATION_ERROR"
    assert error.status == 422
    assert error.details == {"query.age": "x"}


# Transport


@pytest.mark.parametrize(
    ("body", "status"),
    [
        ("<html>502 Bad Gateway</html>", 502),
        ("", 200),
        ('{"success":tr', 200),
        ('{"data":1}', 200),
        ("{}", 200),
        ("[1,2]", 200),
        ('"ok"', 200),
        ("null", 200),
        ("5", 200),
        ('{"success":null}', 200),
        ('{"success":"true","data":1}', 200),
        ('{"success":1,"data":1}', 200),
        ('{"success":true,"data":NaN}', 200),
        (b'{"success":true,"data":"\xff"}', 200),
        (b"\xff\xfe\xfa", 200),
        ("[" * 200000, 200),
    ],
)
def test_malformed_body_raises_transport_error(body: str | bytes, status: int) -> None:
    with pytest.raises(TransportError):
        respond(body, status)


def test_invalid_json_keeps_the_original_error() -> None:
    with pytest.raises(TransportError) as caught:
        respond("<html>")

    assert isinstance(caught.value.__cause__, ValueError)


def test_network_failure_raises_transport_error() -> None:
    failure = httpx.ConnectError("Connection refused")

    def fail(request: httpx.Request) -> httpx.Response:
        raise failure

    api = NestApi(client=httpx.Client(transport=httpx.MockTransport(fail)))

    with pytest.raises(TransportError) as caught:
        api.bmi()

    assert caught.value.__cause__ is failure


def test_timeout_raises_transport_error() -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    with pytest.raises(TransportError):
        NestApi(client=httpx.Client(transport=httpx.MockTransport(fail))).bmi()


def test_oversized_url_raises_transport_error(fake: Fake) -> None:
    with pytest.raises(TransportError) as caught:
        fake.api().bmi(q="a" * 70000)

    assert isinstance(caught.value.__cause__, httpx.InvalidURL)


def test_transport_error_is_not_api_error() -> None:
    assert not issubclass(TransportError, ApiError)
    assert not issubclass(ApiError, TransportError)


# Async client


class AsyncFake(Fake):
    """Injected httpx async client answering every request with one canned response."""

    def __init__(self, body: str | bytes = OK, status: int = 200) -> None:
        super().__init__(body, status)
        self.client = httpx.AsyncClient(transport=httpx.MockTransport(self.handle))  # type: ignore[assignment]

    def api(self, version: int = 1) -> AsyncNestApi:  # type: ignore[override]
        return AsyncNestApi(version=version, client=self.client)  # type: ignore[arg-type]


def run(coroutine: Coroutine[Any, Any, Any]) -> Any:
    return asyncio.run(coroutine)


@pytest.fixture
def async_fake() -> AsyncFake:
    return AsyncFake()


@pytest.mark.parametrize(
    ("method", "route"),
    [
        ("ip_info", "ip-info"),
        ("chatAi", "chat-ai"),
        ("ChatAi", "chat-ai"),
        ("chatAI", "chat-a-i"),
    ],
)
def test_async_method_name_becomes_route(async_fake: AsyncFake, method: str, route: str) -> None:
    run(getattr(async_fake.api(), method)())

    assert async_fake.url == f"https://open.nestapi.ir/apis-1/{route}"
    assert async_fake.requests[0].method == "GET"


def test_async_underscore_names_are_not_services(async_fake: AsyncFake) -> None:
    with pytest.raises(AttributeError):
        async_fake.api()._x

    assert not hasattr(async_fake.api(), "__wrapped__")


def test_async_parameters_are_encoded_like_sync(async_fake: AsyncFake) -> None:
    fake = Fake()
    params = {"on": True, "off": False, "none": None, "ids": [1, 2], "x": {"k": 1}, "q": "a b سلام"}

    run(async_fake.api().foo(params))
    fake.api().foo(params)

    assert async_fake.url == fake.url


def test_async_named_arguments_may_match_internal_names(async_fake: AsyncFake) -> None:
    run(async_fake.api().foo(self="a", name="b", params="c", version=3))

    assert async_fake.query == "self=a&name=b&params=c&version=3"


@pytest.mark.parametrize("arguments", [(30, 70), (30,), (None,), ([30],)])
def test_async_unnamed_arguments_are_rejected(async_fake: AsyncFake, arguments: tuple[Any, ...]) -> None:
    with pytest.raises(TypeError):
        async_fake.api().bmi(*arguments)

    assert async_fake.requests == []


def test_async_mixing_dict_and_named_arguments_is_rejected(async_fake: AsyncFake) -> None:
    with pytest.raises(TypeError):
        async_fake.api().bmi({"age": 30}, weight=70)


def test_async_non_string_keys_are_rejected(async_fake: AsyncFake) -> None:
    with pytest.raises(TypeError):
        run(async_fake.api().bmi({1: "a"}))

    assert async_fake.requests == []


def test_async_call_uses_exact_route(async_fake: AsyncFake) -> None:
    run(async_fake.api().call("version", {"q": "x"}))

    assert async_fake.url == "https://open.nestapi.ir/apis-1/version?q=x"


def test_async_service_name_cannot_change_the_url(async_fake: AsyncFake) -> None:
    run(async_fake.api().call("a b?x=1#y"))

    assert async_fake.url == "https://open.nestapi.ir/apis-1/a%20b%3Fx%3D1%23y"


def test_async_request_sends_method_and_keeps_params_in_query(async_fake: AsyncFake) -> None:
    run(async_fake.api().request("post", "upload-file", {"a": 1}))

    request = async_fake.requests[0]
    assert request.method == "POST"
    assert request.url.query == b"a=1"
    assert request.content == b""
    assert request.headers["accept"] == "application/json"


def test_async_version_returns_copy_and_leaves_original_unchanged(async_fake: AsyncFake) -> None:
    api = async_fake.api()
    other = api.version(3)

    assert other is not api
    assert type(other) is AsyncNestApi

    run(other.bmi())
    assert "/apis-3/bmi" in async_fake.url

    run(api.bmi())
    assert "/apis-1/bmi" in async_fake.url


@pytest.mark.parametrize(("version", "error"), [(0, ValueError), (True, TypeError), ("1", TypeError)])
def test_async_invalid_version_is_rejected(version: Any, error: type[Exception]) -> None:
    with pytest.raises(error):
        AsyncNestApi(version=version)


def test_async_response(async_fake: AsyncFake) -> None:
    response = run(async_fake.api().bmi())

    assert isinstance(response, Response)
    assert response["bmi"] == 22.86
    assert response.get("items.0.id") == 7
    assert response.meta == {"page": 2}


def test_async_calls_run_concurrently() -> None:
    active = 0
    peak = 0

    async def handle(request: httpx.Request) -> httpx.Response:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0)
        active -= 1
        return httpx.Response(200, content=OK.encode())

    async def main() -> list[Response]:
        client = httpx.AsyncClient(transport=httpx.MockTransport(handle))

        async with AsyncNestApi(client=client) as api:
            return await asyncio.gather(*(api.bmi(age=i) for i in range(5)))

    assert len(run(main())) == 5
    assert peak == 5


@pytest.mark.parametrize(
    ("code", "status", "error_class"),
    [
        ("NOT_FOUND", 404, ServiceNotFoundError),
        ("PARAM_NOT_FOUND", 400, ValidationError),
        ("VALIDATION_ERROR", 422, ValidationError),
        ("RATE_LIMITED", 429, RateLimitError),
        ("RATE_LIMIT_EXCEEDED", 429, RateLimitError),
        ("RATE_LIMITED", 503, RateLimitError),
        ("DATABASE_ERROR", 500, ServerError),
        ("INVALID_IP", 400, ApiError),
    ],
)
def test_async_error_mapping(code: str, status: int, error_class: type[ApiError]) -> None:
    body = json.dumps({"success": False, "error": {"code": code, "message": "m", "details": ["x"]}})

    with pytest.raises(ApiError) as caught:
        run(AsyncFake(body, status).api().foo())

    assert type(caught.value) is error_class
    assert caught.value.error_code == code
    assert caught.value.status == status
    assert caught.value.details == ["x"]


@pytest.mark.parametrize("body", ["<html>", "", "[1,2]", "{}", '{"success":"true"}'])
def test_async_malformed_body_raises_transport_error(body: str) -> None:
    with pytest.raises(TransportError):
        run(AsyncFake(body).api().foo())


def test_async_network_failure_raises_transport_error() -> None:
    failure = httpx.ConnectError("Connection refused")

    def fail(request: httpx.Request) -> httpx.Response:
        raise failure

    api = AsyncNestApi(client=httpx.AsyncClient(transport=httpx.MockTransport(fail)))

    with pytest.raises(TransportError) as caught:
        run(api.bmi())

    assert caught.value.__cause__ is failure


def test_async_default_client_settings() -> None:
    api = AsyncNestApi()
    assert api._client.timeout == httpx.Timeout(30.0)
    run(api.close())

    api = AsyncNestApi(timeout=5)
    assert api._client.timeout == httpx.Timeout(5)
    run(api.close())


def test_async_context_manager_closes_default_client() -> None:
    async def main() -> httpx.AsyncClient:
        async with AsyncNestApi() as api:
            return api._client

    assert run(main()).is_closed


def test_async_close_leaves_injected_client_open(async_fake: AsyncFake) -> None:
    async def main() -> None:
        async with async_fake.api() as api:
            await api.bmi()

        await api.close()
        await api.bmi()

    run(main())

    assert not async_fake.client.is_closed


def test_async_closing_a_copy_keeps_the_original_working() -> None:
    async def main() -> None:
        api = AsyncNestApi()
        other = api.version(2)

        assert other._client is api._client

        await other.close()
        async with other:
            pass
        await copy.copy(api).close()
        assert not api._client.is_closed

        await api.close()
        assert api._client.is_closed

        with pytest.raises(TransportError):
            await other.bmi()

    run(main())


@pytest.mark.parametrize("clone", [copy.deepcopy, lambda a: pickle.loads(pickle.dumps(a))])
def test_async_deep_clone_gets_its_own_client(clone: Any) -> None:
    api = AsyncNestApi(version=4, timeout=9)
    other = clone(api)

    assert type(other) is AsyncNestApi
    assert other._client is not api._client
    assert isinstance(other._client, httpx.AsyncClient)
    assert other._client.timeout == httpx.Timeout(9)

    run(other.close())
    assert not api._client.is_closed
    run(api.close())


def test_sync_and_async_clients_work_side_by_side() -> None:
    fake = Fake()
    async_fake = AsyncFake()

    fake.api().bmi(age=30)
    run(async_fake.api().bmi(age=30))

    assert fake.url == async_fake.url
