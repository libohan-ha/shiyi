"""Host header allow-list.

Replaces Starlette's TrustedHostMiddleware so that host names compare
case-insensitively (DNS names are case-insensitive) and bracketed IPv6
hosts such as ``[fd7a:115c:a1e0::1]:8765`` are understood. Hosts that are
not on the list are still rejected with ``400 Invalid host header``.
"""

from starlette.datastructures import Headers
from starlette.responses import PlainTextResponse


def parse_hosts(value: str) -> list[str]:
    hosts = []
    for raw in value.split(","):
        host = raw.strip().lower()
        if host.startswith("[") and host.endswith("]"):
            host = host[1:-1]
        if host and host not in hosts:
            hosts.append(host)
    return hosts


def host_name(header: str) -> str:
    header = header.strip().lower()
    if header.startswith("["):
        end = header.find("]")
        return header[1:end] if end > 0 else ""
    return header.split(":", 1)[0]


def host_allowed(host: str, allowed: list[str]) -> bool:
    if not host:
        return False
    for pattern in allowed:
        if pattern == "*" or host == pattern:
            return True
        if pattern.startswith("*.") and host.endswith(pattern[1:]):
            return True
    return False


class TrustedHosts:
    def __init__(self, app, allowed_hosts: list[str]):
        self.app = app
        self.allowed = allowed_hosts

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        host = host_name(Headers(scope=scope).get("host", ""))
        if host_allowed(host, self.allowed):
            await self.app(scope, receive, send)
            return
        await PlainTextResponse("Invalid host header", status_code=400)(scope, receive, send)
