from collections.abc import Sequence

import httpx
import pytest

from ai_model_briefing.http import MAX_RESPONSE_BYTES, SafeHttpClient, SourceFetchError

PUBLIC_ADDRESS = "93.184.216.34"


def public_resolver(host: str, port: int) -> Sequence[str]:
    assert port == 443
    return [PUBLIC_ADDRESS]


def make_client(handler: httpx.MockTransport) -> SafeHttpClient:
    return SafeHttpClient(
        allowed_hosts=frozenset({"example.com"}),
        resolver=public_resolver,
        transport=handler,
    )


def test_fetches_allowed_text_response() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "application/rss+xml"},
            text="<rss />",
            request=request,
        )
    )

    with make_client(transport) as client:
        assert client.get_text("https://example.com/feed.xml") == "<rss />"


def test_follows_only_allowed_redirects() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/old":
            return httpx.Response(302, headers={"location": "/new"}, request=request)
        return httpx.Response(
            200,
            headers={"content-type": "text/plain"},
            text="ok",
            request=request,
        )

    with make_client(httpx.MockTransport(handler)) as client:
        assert client.get_text("https://example.com/old") == "ok"


def test_rejects_redirect_to_unlisted_host() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            302,
            headers={"location": "https://attacker.example/feed"},
            request=request,
        )
    )

    with make_client(transport) as client, pytest.raises(SourceFetchError, match="not allowed"):
        client.get_text("https://example.com/feed")


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/feed",
        "https://user:password@example.com/feed",
        "https://example.com:8443/feed",
        "https://attacker.example/feed",
    ],
)
def test_rejects_unsafe_destinations(url: str) -> None:
    with (
        make_client(
            httpx.MockTransport(lambda request: httpx.Response(200, request=request))
        ) as client,
        pytest.raises(SourceFetchError),
    ):
        client.get_text(url)


def test_rejects_private_resolution() -> None:
    client = SafeHttpClient(
        allowed_hosts=frozenset({"example.com"}),
        resolver=lambda host, port: ["127.0.0.1"],
        transport=httpx.MockTransport(lambda request: httpx.Response(200, request=request)),
    )

    with client, pytest.raises(SourceFetchError, match="non-public"):
        client.get_text("https://example.com/feed")


def test_rejects_oversized_response() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "text/plain"},
            content=b"x" * (MAX_RESPONSE_BYTES + 1),
            request=request,
        )
    )

    with make_client(transport) as client, pytest.raises(SourceFetchError, match="size limit"):
        client.get_text("https://example.com/large")
