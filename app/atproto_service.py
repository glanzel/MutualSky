"""Bridge between the Oxyde ``User`` model and the OAuth/DPoP flow functions.

The OAuth module works on a plain ``session`` dict; this module serializes
decrypted snapshots of the stored user and persists token rotations back.
"""

import json
from collections.abc import Callable

from authlib.jose import JsonWebKey

from . import crypto
from .models import User


def _secrets(settings) -> str:
    return settings.encryption_secret


def _enc(settings, value: str) -> str:
    return crypto.encrypt_str(value, _secrets(settings)) if value else ""


def _dec(settings, value: str | None) -> str:
    return crypto.decrypt_str(value, _secrets(settings)) if value else ""


def session_to_dict(user: User, settings) -> dict:
    """Materialize the decrypted session dict used by atproto_oauth functions."""
    return {
        "did": user.did,
        "handle": user.handle,
        "pds_url": user.pds_url,
        "authserver_iss": user.authserver_iss,
        "client_id": user.client_id,
        "scope": user.scope,
        "access_token": _dec(settings, user.access_token),
        "refresh_token": _dec(settings, user.refresh_token),
        "dpop_authserver_nonce": user.dpop_authserver_nonce or "",
        "dpop_pds_nonce": user.dpop_pds_nonce or "",
        "dpop_private_jwk": _dec(settings, user.dpop_private_jwk),
    }


def apply_token_updates(user: User, settings, updates: dict) -> None:
    """Persist rotated tokens/nonces back onto the user row.

    OAuth refresh-token rotation MUST be persisted immediately or the session
    is invalidated, so this is deliberately synchronous from the caller's
    point of view (the actual DB write happens on ``save``).
    """
    if "access_token" in updates and updates["access_token"] is not None:
        user.access_token = _enc(settings, updates["access_token"])
    if "refresh_token" in updates and updates["refresh_token"] is not None:
        user.refresh_token = _enc(settings, updates["refresh_token"])
    if "dpop_authserver_nonce" in updates:
        user.dpop_authserver_nonce = updates["dpop_authserver_nonce"] or ""
    if "dpop_pds_nonce" in updates:
        user.dpop_pds_nonce = updates["dpop_pds_nonce"] or ""


def make_persist_cb(user: User, settings) -> Callable[[dict], None]:
    def cb(updates: dict) -> None:
        apply_token_updates(user, settings, updates)

    return cb


def generate_dpop_key() -> str:
    key = JsonWebKey.generate_key("EC", "P-256", is_private=True)
    return key.as_json(is_private=True)


def get_client_key(settings) -> JsonWebKey:
    return JsonWebKey.import_key(json.loads(settings.oauth_client_secret_jwk))


def client_id_for_host(request, settings) -> str:
    """Dynamically compute the client_id (and redirect URI) for a request host.

    For localhost the special loopback client form is used (no metadata file
    needed); otherwise the deployed public base URL is used.
    """
    from urllib.parse import urlencode, urlparse

    parsed = urlparse(str(request.base_url))
    hostname = parsed.hostname or ""
    if hostname in ["localhost", "127.0.0.1", "0.0.0.0", "::1"]:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        redirect_uri = f"http://127.0.0.1:{port}/auth/callback"
        client_id = "http://localhost?" + urlencode({"redirect_uri": redirect_uri, "scope": settings.oauth_scope})
        return client_id, redirect_uri
    return settings.client_id_url, settings.redirect_uri