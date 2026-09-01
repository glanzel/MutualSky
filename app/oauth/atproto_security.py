"""SSRF-hardened HTTP helpers on top of httpx (ported from the official
bluesky-social/cookbook `python-oauth-web-app` atproto_security.py).
"""

import ipaddress
import socket
from urllib.parse import urlparse

import httpx

USER_AGENT = "MutualSky/0.1 (+https://mutualsky.ecord.de)"


def is_safe_url(url: str) -> bool:
    """Crude/partial filter for HTTPS URLs used in server-side requests.

    The underlying HTTP client additionally enforces timeouts and redirects are
    disabled, and hosts must resolve to public IPs (see ``check_public_host``).
    """
    parts = urlparse(url)
    if not (
        parts.scheme == "https"
        and parts.hostname is not None
        and parts.hostname == parts.netloc
        and parts.username is None
        and parts.password is None
        and parts.port is None
    ):
        return False

    segments = parts.hostname.split(".")
    if len(segments) < 2 or segments[-1] in ["local", "arpa", "internal", "localhost"]:
        return False

    return not segments[-1].isdigit()


def check_public_host(url: str) -> None:
    """Resolve the URL hostname and reject private/loopback/search-zone IPs."""
    hostname = urlparse(url).hostname
    if hostname is None:
        raise ValueError("URL has no hostname")
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ValueError(f"Could not resolve host {hostname!r}") from exc
    if not infos:
        raise ValueError(f"Could not resolve host {hostname!r}")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise ValueError(f"Refusing non-public host {hostname} ({ip})")


def check_safe_request(url: str) -> httpx.AsyncClient:
    if not is_safe_url(url):
        raise ValueError(f"Unsafe URL: {url}")
    check_public_host(url)
    return httpx.AsyncClient(
        timeout=httpx.Timeout(10.0, connect=2.0),
        follow_redirects=False,
        headers={"User-Agent": USER_AGENT},
    )


async def safe_get(url: str, **kwargs) -> httpx.Response:
    async with check_safe_request(url) as client:
        return await client.get(url, **kwargs)


async def safe_post(url: str, **kwargs) -> httpx.Response:
    async with check_safe_request(url) as client:
        return await client.post(url, **kwargs)