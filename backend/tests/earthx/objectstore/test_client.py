"""The client: one way in (F2), no proxy (§3.2), no response text in errors (§9.2).

adr/0015 §12 points 6 and 7.
"""

from __future__ import annotations

import ast
import http.server
import inspect
import socket
import threading
from collections.abc import Iterator
from pathlib import Path

import botocore.session
import pytest
from botocore.config import Config
from botocore.exceptions import ClientError, EndpointConnectionError, ReadTimeoutError

from earthx.objectstore import client, config, errors, results
from earthx.objectstore.client import S3, build_clients
from earthx.objectstore.config import StoreConfig
from earthx.objectstore.errors import ResultNotFound, StoreDenied, StoreUnavailable
from earthx.objectstore.results import Store, lifecycle_ok

from .conftest import ACCESS_KEY, SECRET_KEY

PACKAGE = Path(client.__file__).parent
MODULES = (client, config, errors, results)
# A parameter with one of these in its name could steer the client somewhere else.
STEERING = ("endpoint", "host", "bucket", "url", "region")
# Taken at import, before the autouse `no_network` fixture replaces it.
_real_getaddrinfo = socket.getaddrinfo


# --- Auflage F2: the only way to the client is the environment --------------------


def _public_callables() -> Iterator[tuple[str, object]]:
    for module in MODULES:
        for name, member in vars(module).items():
            if name.startswith("_") or getattr(member, "__module__", None) != module.__name__:
                continue
            if inspect.isclass(member):
                for method_name in vars(member):
                    method = getattr(member, method_name)
                    if not method_name.startswith("_") and callable(method):
                        yield f"{module.__name__}.{name}.{method_name}", method
            elif inspect.isfunction(member):
                yield f"{module.__name__}.{name}", member


def test_the_check_sees_the_public_functions() -> None:
    names = {name for name, _ in _public_callables()}
    assert {"earthx.objectstore.results.upload_result", "earthx.objectstore.results.signed_download"} <= names
    assert "earthx.objectstore.client.S3.presign_get" in names


@pytest.mark.parametrize("name,function", list(_public_callables()), ids=lambda value: str(value))
def test_no_public_function_takes_an_endpoint_host_bucket_or_url(name: str, function: object) -> None:
    parameters = inspect.signature(function).parameters  # type: ignore[arg-type]
    assert not [p for p in parameters if any(word in p.lower() for word in STEERING)], name


def _calls_to(name: str) -> list[tuple[str, str]]:
    """(file, enclosing function) of every call to `name` in the package."""
    found = []
    for path in sorted(PACKAGE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for function in ast.walk(tree):
            if not isinstance(function, ast.FunctionDef):
                continue
            for node in ast.walk(function):
                if isinstance(node, ast.Call):
                    callee = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", None)
                    if callee == name:
                        found.append((path.name, function.name))
    return found


def test_clients_are_built_only_from_a_config_read_from_the_environment() -> None:
    assert _calls_to("build_clients") == [("results.py", "from_environ")]
    assert _calls_to("_create") == [("client.py", "build_clients"), ("client.py", "build_clients")]
    assert _calls_to("StoreConfig") == []
    assert _calls_to("S3") == [("client.py", "build_clients")]
    assert ("results.py", "from_environ") in _calls_to("from_environ")


def test_the_origin_check_would_notice_a_second_way() -> None:
    source = "def elsewhere(cfg):\n    return build_clients(cfg)\n"
    calls = [n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Call)]
    assert calls and calls[0].func.id == "build_clients"


def test_both_clients_carry_the_configured_settings(store_env: dict[str, str]) -> None:
    s3 = build_clients(StoreConfig.from_environ(store_env))
    assert s3._internal.meta.endpoint_url == "http://objectstore:3900"
    assert s3._signer.meta.endpoint_url == "http://localhost:3900"
    for botocore_client in (s3._internal, s3._signer):
        settings = botocore_client.meta.config
        assert botocore_client.meta.region_name == "garage"
        assert settings.proxies == {}
        assert (settings.connect_timeout, settings.read_timeout) == (5, 60)
        assert settings.retries == {"mode": "standard", "total_max_attempts": 3}
        assert settings.s3["addressing_style"] == "path"
        assert settings.request_checksum_calculation == "when_required"


def test_an_aws_endpoint_in_the_environment_does_not_move_the_client(
    store_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AWS_ENDPOINT_URL", "https://elsewhere.example")
    monkeypatch.setenv("AWS_ENDPOINT_URL_S3", "https://elsewhere.example")
    s3 = build_clients(StoreConfig.from_environ(store_env))
    assert s3._internal.meta.endpoint_url == "http://objectstore:3900"


# --- §12 point 6: HTTP_PROXY does not divert the client ---------------------------


class _S3Stub(http.server.BaseHTTPRequestHandler):
    """Answers every request like a bucket without lifecycle configuration."""

    def do_GET(self) -> None:  # noqa: N802
        self.server.requests.append(self.path)  # type: ignore[attr-defined]
        body = b"<Error><Code>NoSuchLifecycleConfiguration</Code></Error>"
        self.send_response(404)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture
def loopback(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[str, list[str], list[int]]]:
    """A stub S3 on one loopback port and a 'proxy' on another that only counts connections.

    `no_network` forbids every name lookup; urllib3 looks up even an address, so this
    lets exactly 127.0.0.1 through.
    """

    def loopback_only(host: object, *args: object, **kwargs: object) -> object:
        if host != "127.0.0.1":
            raise RuntimeError(f"lookup of {host!r} in a loopback test")
        return _real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", loopback_only)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _S3Stub)
    server.requests = []  # type: ignore[attr-defined]
    proxy = socket.socket()
    proxy.bind(("127.0.0.1", 0))
    proxy.listen()
    proxy.settimeout(0.2)
    proxy_hits: list[int] = []

    def count_proxy() -> None:
        while not stop.is_set():
            try:
                connection, _ = proxy.accept()
            except OSError:
                continue
            proxy_hits.append(1)
            connection.close()

    stop = threading.Event()
    threads = [threading.Thread(target=server.serve_forever), threading.Thread(target=count_proxy)]
    for thread in threads:
        thread.start()
    proxy_url = f"http://127.0.0.1:{proxy.getsockname()[1]}"
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        monkeypatch.setenv(name, proxy_url)
    for name in ("NO_PROXY", "no_proxy"):
        monkeypatch.delenv(name, raising=False)
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", server.requests, proxy_hits  # type: ignore[attr-defined]
    finally:
        stop.set()
        server.shutdown()
        for thread in threads:
            thread.join()
        server.server_close()
        proxy.close()


def test_a_proxy_in_the_environment_does_not_divert_the_client(
    store_env: dict[str, str], loopback: tuple[str, list[str], list[int]]
) -> None:
    endpoint, requests, proxy_hits = loopback
    store = Store.from_environ(store_env | {"S3_ENDPOINT": endpoint})
    assert lifecycle_ok(store) is False
    assert requests and requests[0].startswith("/earthx?lifecycle")
    assert proxy_hits == []


def test_without_the_setting_the_same_request_would_go_to_the_proxy(
    loopback: tuple[str, list[str], list[int]],
) -> None:
    """The counter-check: the test above would notice a client that reads the proxy."""
    endpoint, requests, proxy_hits = loopback
    reads_environment = botocore.session.Session().create_client(
        "s3",
        endpoint_url=endpoint,
        region_name="garage",
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
        config=Config(connect_timeout=1, read_timeout=1, retries={"max_attempts": 1}),
    )
    with pytest.raises(Exception):  # noqa: B017, PT011 - the counting proxy just hangs up
        reads_environment.get_bucket_lifecycle_configuration(Bucket="earthx")
    assert proxy_hits
    assert requests == []


# --- §9.2: errors carry no response text, key or endpoint -------------------------


class _Raising:
    """Stands in for a botocore client and raises what it is given."""

    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    def __getattr__(self, name: str):  # noqa: ANN204
        def raise_(*args: object, **kwargs: object) -> None:
            raise self.exc

        return raise_


def _s3_raising(store_env: dict[str, str], exc: Exception) -> S3:
    return S3(StoreConfig.from_environ(store_env), _Raising(exc), _Raising(exc))


def _client_error(code: str, status: int, message: str) -> ClientError:
    return ClientError(
        {"Error": {"Code": code, "Message": message}, "ResponseMetadata": {"HTTPStatusCode": status}},
        "PutObject",
    )


@pytest.mark.parametrize(
    ("code", "status", "expected"),
    [
        ("AccessDenied", 403, StoreDenied),
        ("InvalidAccessKeyId", 403, StoreDenied),
        ("SignatureDoesNotMatch", 403, StoreDenied),
        ("NoSuchKey", 404, ResultNotFound),
        ("InternalError", 500, StoreUnavailable),
        ("SlowDown", 503, StoreUnavailable),
    ],
)
def test_a_store_error_is_translated_without_its_text(
    store_env: dict[str, str], code: str, status: int, expected: type[Exception]
) -> None:
    # Garage names the key id in AccessDenied (adr/0015 §3.2).
    leak = f"Forbidden: No such key: {ACCESS_KEY} secret {SECRET_KEY} at http://objectstore:3900/earthx"
    s3 = _s3_raising(store_env, _client_error(code, status, leak))
    with pytest.raises(expected) as caught:
        s3.put_object("results/x/result.tif", None, "image/tiff")  # type: ignore[arg-type]
    message = str(caught.value)
    assert message == f"object store PutObject failed ({code}, HTTP {status})"
    assert caught.value.__cause__ is None and caught.value.__suppress_context__
    for secret in (ACCESS_KEY, SECRET_KEY, "objectstore", "No such key"):
        assert secret not in message


def test_an_error_code_carrying_the_key_is_redacted(store_env: dict[str, str]) -> None:
    s3 = _s3_raising(store_env, _client_error(ACCESS_KEY, 400, ""))
    with pytest.raises(StoreUnavailable) as caught:
        s3.list_multipart_uploads("results/")
    assert ACCESS_KEY not in str(caught.value)
    assert "<redacted>" in str(caught.value)


@pytest.mark.parametrize(
    "exc",
    [
        EndpointConnectionError(endpoint_url="http://objectstore:3900/earthx"),
        ReadTimeoutError(endpoint_url="http://objectstore:3900/earthx"),
    ],
)
def test_an_unreachable_store_is_named_without_the_endpoint(store_env: dict[str, str], exc: Exception) -> None:
    s3 = _s3_raising(store_env, exc)
    with pytest.raises(StoreUnavailable) as caught:
        s3.lifecycle_rules()
    assert str(caught.value) == f"object store GetBucketLifecycleConfiguration failed ({type(exc).__name__})"


def test_a_missing_lifecycle_configuration_is_an_empty_list(store_env: dict[str, str]) -> None:
    s3 = _s3_raising(store_env, _client_error("NoSuchLifecycleConfiguration", 404, ""))
    assert s3.lifecycle_rules() == []


def test_partial_failures_of_a_batch_delete_are_reported(store_env: dict[str, str]) -> None:
    class Answers:
        def delete_objects(self, **kwargs: object) -> dict:
            return {"Errors": [{"Key": "results/x/a", "Code": "AccessDenied", "Message": ACCESS_KEY}]}

    s3 = S3(StoreConfig.from_environ(store_env), Answers(), Answers())
    with pytest.raises(StoreUnavailable) as caught:
        s3.delete_objects(["results/x/a"])
    assert str(caught.value) == "object store DeleteObjects failed for 1 keys (AccessDenied)"
