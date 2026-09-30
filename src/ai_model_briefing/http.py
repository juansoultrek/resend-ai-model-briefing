from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Sequence
from types import TracebackType
from urllib.parse import urljoin, urlsplit

import httpx

MAX_RESPONSE_BYTES = 1_500_000
MAX_REDIRECTS = 3
REQUEST_TIMEOUT_SECONDS = 15.0
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
ALLOWED_CONTENT_TYPES = frozenset(
    {
        "application/atom+xml",
        "application/rss+xml",
        "application/xhtml+xml",
        "application/xml",
        "text/html",
        "text/plain",
        "text/xml",
    }
)

Resolver = Callable[[str, int], Sequence[str]]


class SourceFetchError(RuntimeError):
    """Raised when a remote source violates a network or response boundary."""


def resolve_host(host: str, port: int) -> tuple[str, ...]:
    try:
        addresses = {
            str(result[4][0]) for result in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        }
    except OSError as error:
        raise SourceFetchError(f"could not resolve host: {host}") from error
    return tuple(sorted(addresses))


class SafeHttpClient:
    def __init__(
        self,
        *,
        allowed_hosts: frozenset[str],
        resolver: Resolver = resolve_host,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not allowed_hosts:
            raise ValueError("at least one allowed host is required")
        self._allowed_hosts = allowed_hosts
        self._resolver = resolver
        self._client = httpx.Client(
            follow_redirects=False,
            timeout=REQUEST_TIMEOUT_SECONDS,
            trust_env=False,
            transport=transport,
            headers={"User-Agent": "resend-ai-model-briefing/0.1"},
        )

    def __enter__(self) -> SafeHttpClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def get_text(self, url: str) -> str:
        current_url = url
        for redirect_count in range(MAX_REDIRECTS + 1):
            self._validate_destination(current_url)
            try:
                with self._client.stream("GET", current_url) as response:
                    if response.status_code in REDIRECT_STATUSES:
                        if redirect_count == MAX_REDIRECTS:
                            raise SourceFetchError("source exceeded the redirect limit")
                        location = response.headers.get("location")
                        if not location:
                            raise SourceFetchError("source returned a redirect without a location")
                        current_url = urljoin(current_url, location)
                        continue

                    response.raise_for_status()
                    self._validate_content_type(response)
                    return self._read_limited_body(response)
            except SourceFetchError:
                raise
            except httpx.HTTPError as error:
                raise SourceFetchError(f"source request failed: {error}") from error

        raise SourceFetchError("source exceeded the redirect limit")

    def _validate_destination(self, url: str) -> None:
        parsed = urlsplit(url)
        if parsed.scheme != "https":
            raise SourceFetchError("source requests must use HTTPS")
        if parsed.username or parsed.password:
            raise SourceFetchError("source requests must not contain credentials")
        if parsed.port not in (None, 443):
            raise SourceFetchError("source requests must use the default HTTPS port")
        host = parsed.hostname or ""
        if host not in self._allowed_hosts:
            raise SourceFetchError(f"source host is not allowed: {host or '<missing>'}")

        addresses = self._resolver(host, 443)
        if not addresses:
            raise SourceFetchError(f"source host did not resolve: {host}")
        for address in addresses:
            try:
                parsed_address = ipaddress.ip_address(address)
            except ValueError as error:
                raise SourceFetchError(f"source resolved to an invalid address: {host}") from error
            if not parsed_address.is_global:
                raise SourceFetchError(f"source resolved to a non-public address: {host}")

    @staticmethod
    def _validate_content_type(response: httpx.Response) -> None:
        content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
        if content_type not in ALLOWED_CONTENT_TYPES:
            raise SourceFetchError(f"source returned an unsupported content type: {content_type}")

    @staticmethod
    def _read_limited_body(response: httpx.Response) -> str:
        content_length = response.headers.get("content-length")
        if content_length:
            try:
                declared_size = int(content_length)
            except ValueError as error:
                raise SourceFetchError("source returned an invalid content length") from error
            if declared_size > MAX_RESPONSE_BYTES:
                raise SourceFetchError("source response exceeds the size limit")

        body = bytearray()
        for chunk in response.iter_bytes():
            body.extend(chunk)
            if len(body) > MAX_RESPONSE_BYTES:
                raise SourceFetchError("source response exceeds the size limit")

        encoding = response.encoding or "utf-8"
        return bytes(body).decode(encoding, errors="replace")
