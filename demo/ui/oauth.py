"""OAuth 2.1 support for MCP servers with PKCE.

Implements the MCP authorization specification:
- Protected Resource Metadata discovery
- Authorization Server Metadata discovery
- Dynamic Client Registration (RFC 7591)
- OAuth 2.1 Authorization Code flow with PKCE
- Session-based token storage (no disk)
"""

import base64
import hashlib
import secrets
import time
from urllib.parse import urlencode, urlparse

import httpx


def _generate_code_verifier() -> str:
    """Generate a PKCE code verifier."""
    return secrets.token_urlsafe(32)


def _generate_code_challenge(verifier: str) -> str:
    """Generate S256 code challenge from verifier."""
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def _get_token_key(server_url: str) -> str:
    """Get session key for a server's token."""
    url_hash = hashlib.sha256(server_url.encode()).hexdigest()[:16]
    return f"oauth_token_{url_hash}"


def get_stored_token(server_url: str, session: dict) -> dict | None:
    """Get stored OAuth token for a server from session."""
    key = _get_token_key(server_url)
    token_data = session.get(key)
    if token_data:
        # Check expiration (with 60s buffer)
        if token_data.get("expires_at", float("inf")) > time.time() + 60:
            return token_data
    return None


def get_access_token(server_url: str, session: dict) -> str | None:
    """Get just the access token string for a server."""
    token_data = get_stored_token(server_url, session)
    if token_data:
        return token_data.get("access_token")
    return None


def store_token(server_url: str, token_data: dict, session: dict) -> None:
    """Store OAuth token for a server in session."""
    # Add expiration timestamp if we have expires_in
    if "expires_in" in token_data and "expires_at" not in token_data:
        token_data["expires_at"] = time.time() + token_data["expires_in"]

    token_data["server_url"] = server_url

    key = _get_token_key(server_url)
    session[key] = token_data


def clear_token(server_url: str, session: dict) -> None:
    """Clear stored token for a server."""
    key = _get_token_key(server_url)
    session.pop(key, None)


async def discover_oauth_metadata(server_url: str) -> dict | None:
    """Discover OAuth metadata for an MCP server.

    Returns dict with:
    - authorization_endpoint
    - token_endpoint
    - registration_endpoint (optional)
    - scopes_supported (optional)
    """
    parsed = urlparse(server_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Step 1: Try to get protected resource metadata
        resource_metadata_url = f"{base_url}/.well-known/oauth-protected-resource"
        try:
            resp = await client.get(resource_metadata_url)
            if resp.status_code == 200:
                resource_meta = resp.json()
                auth_server = resource_meta.get("authorization_servers", [None])[0]
                if auth_server:
                    # Step 2: Get authorization server metadata
                    as_metadata_url = f"{auth_server}/.well-known/oauth-authorization-server"
                    resp = await client.get(as_metadata_url)
                    if resp.status_code == 200:
                        return resp.json()
        except Exception:
            pass

        # Fallback: Try well-known endpoints directly on the server
        for endpoint in [
            f"{base_url}/.well-known/oauth-authorization-server",
            f"{base_url}/.well-known/openid-configuration",
        ]:
            try:
                resp = await client.get(endpoint)
                if resp.status_code == 200:
                    return resp.json()
            except Exception:
                continue

        return None


async def register_client(
    registration_endpoint: str,
    redirect_uri: str,
    client_name: str = "MCP Gateway Demo",
) -> dict | None:
    """Dynamically register an OAuth client (RFC 7591)."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                registration_endpoint,
                json={
                    "client_name": client_name,
                    "redirect_uris": [redirect_uri],
                    "grant_types": ["authorization_code", "refresh_token"],
                    "response_types": ["code"],
                    "token_endpoint_auth_method": "none",
                },
            )
            if resp.status_code in (200, 201):
                return resp.json()
        except Exception:
            pass
    return None


class OAuthFlow:
    """Manages an OAuth authorization flow."""

    def __init__(
        self,
        server_url: str,
        redirect_uri: str,
        client_id: str | None = None,
        authorization_endpoint: str | None = None,
        token_endpoint: str | None = None,
        scopes: list[str] | None = None,
    ):
        self.server_url = server_url
        self.redirect_uri = redirect_uri
        self.client_id = client_id
        self.authorization_endpoint = authorization_endpoint
        self.token_endpoint = token_endpoint
        self.scopes = scopes or []

        # PKCE
        self.code_verifier = _generate_code_verifier()
        self.code_challenge = _generate_code_challenge(self.code_verifier)

        # State for CSRF protection
        self.state = secrets.token_urlsafe(16)

    def get_authorization_url(self) -> str:
        """Get the URL to redirect the user to for authorization."""
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "code_challenge": self.code_challenge,
            "code_challenge_method": "S256",
            "state": self.state,
            "resource": self.server_url,  # RFC 8707
        }
        if self.scopes:
            params["scope"] = " ".join(self.scopes)

        return f"{self.authorization_endpoint}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> dict:
        """Exchange authorization code for tokens."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                self.token_endpoint,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self.redirect_uri,
                    "client_id": self.client_id,
                    "code_verifier": self.code_verifier,
                    "resource": self.server_url,
                },
            )
            resp.raise_for_status()
            return resp.json()


# In-memory storage for pending OAuth flows (state -> OAuthFlow)
_pending_flows: dict[str, OAuthFlow] = {}


def store_pending_flow(flow: OAuthFlow) -> None:
    """Store a pending OAuth flow by its state."""
    _pending_flows[flow.state] = flow


def get_pending_flow(state: str) -> OAuthFlow | None:
    """Get and remove a pending OAuth flow by state."""
    return _pending_flows.pop(state, None)


def get_oauth_status(server_urls: list[str]) -> dict[str, dict]:
    """Get OAuth status for multiple servers.

    Returns dict mapping server_url to status info:
    - authenticated: bool
    - expires_at: timestamp or None
    """
    result = {}
    for url in server_urls:
        token = get_stored_token(url)
        result[url] = {
            "authenticated": token is not None,
            "expires_at": token.get("expires_at") if token else None,
        }
    return result
