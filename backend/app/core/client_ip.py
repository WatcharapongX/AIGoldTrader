"""Resolve client identity only across an explicitly configured proxy boundary."""

from ipaddress import ip_address, ip_network

from starlette.requests import Request

from app.core.config import get_settings


def resolve_client_ip(request: Request) -> str:
    # Uvicorn must run with --no-proxy-headers so this is the transport peer.
    try:
        peer = ip_address(request.client.host if request.client else "")
    except ValueError:
        return "unknown"
    settings = get_settings()
    if not settings.trust_proxy:
        return str(peer)
    networks = [
        ip_network(value.strip(), strict=False) for value in settings.trusted_proxy_cidrs.split(",") if value.strip()
    ]
    if not any(peer in network for network in networks):
        return str(peer)
    forwarded = request.headers.getlist("x-forwarded-for")
    # A single bounded chain; ambiguous/malformed headers fall back to the peer.
    if len(forwarded) != 1 or len(forwarded[0]) > 2048:
        return str(peer)
    hops = forwarded[0].split(",")
    if len(hops) > 16:
        return str(peer)
    try:
        addresses = [ip_address(value.strip()) for value in hops]
    except ValueError:
        return str(peer)
    client = peer
    for address in reversed(addresses):
        if not any(client in network for network in networks):
            break
        client = address
    return str(client)
