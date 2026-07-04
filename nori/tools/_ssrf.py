"""SSRF guard for URL-fetching tools.

Blocks requests to non-public addresses (loopback, private, link-local,
cloud-metadata) so a prompt-injected agent can't turn WebClient/BrowserClient
into a probe of internal services or credential endpoints like
http://169.254.169.254/.

This is a guardrail, not airtight: it resolves the host and checks the IPs, but
DNS can rebind between this check and the actual request (TOCTOU). Redirects are
handled by re-checking each hop in the caller. See docs/security.md.
"""
import asyncio
import ipaddress
from urllib.parse import urlparse


def _ip_is_blocked(ip: ipaddress._BaseAddress) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


async def check_url(url: str) -> str | None:
    """Return a '[blocked] ...' string if the URL is unsafe to fetch, else None."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return f"[blocked] unsupported URL scheme '{parsed.scheme or '(none)'}'. Only http/https are allowed."
    host = parsed.hostname
    if not host:
        return "[blocked] URL has no host."

    try:
        ip = ipaddress.ip_address(host)
        addrs = [ip]
    except ValueError:
        loop = asyncio.get_running_loop()
        try:
            infos = await loop.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
        except OSError:
            return None  # unresolvable — let the real request surface a network error
        addrs = [ipaddress.ip_address(info[4][0]) for info in infos]

    for ip in addrs:
        if _ip_is_blocked(ip):
            return (
                f"[blocked] '{host}' resolves to a non-public address ({ip}). "
                "Refusing to fetch internal or cloud-metadata endpoints."
            )
    return None
