"""AT Protocol OAuth 2.1 + DPoP client flows.

Ported to async/httpx from the official bluesky-social/cookbook
`python-oauth-web-app` atproto_oauth.py.

All functions operate on a denormalized ``user_session`` dict with the keys:
did, handle, pds_url, authserver_iss, access_token, refresh_token,
dpop_authserver_nonce, dpop_pds_nonce, dpop_private_jwk (JSON), scope.
Persisting rotations back to storage is the caller's responsibility (a
``persist_cb`` accepting the raw token/nonce dict is provided where relevant).
"""

import json
import time
import urllib.request
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlparse

from authlib.common.security import generate_token
from authlib.jose import JsonWebKey, jwt
from authlib.oauth2.rfc7636 import create_s256_code_challenge

from .atproto_security import safe_get, safe_post

PersistCB = Callable[[dict], Awaitable[None] | None]


# --------------------------------------------------------------------------- #
# Auth server metadata
# --------------------------------------------------------------------------- #
def is_valid_authserver_meta(obj: dict, url: str) -> bool:
    fetch_url = urlparse(url)
    issuer_url = urlparse(obj["issuer"])
    assert issuer_url.hostname == fetch_url.hostname
    assert issuer_url.scheme == "https"
    assert issuer_url.port is None
    assert issuer_url.path in ["", "/"]
    assert issuer_url.params == ""
    assert issuer_url.fragment == ""

    assert "code" in obj["response_types_supported"]
    assert "authorization_code" in obj["grant_types_supported"]
    assert "refresh_token" in obj["grant_types_supported"]
    assert "S256" in obj["code_challenge_methods_supported"]
    assert "none" in obj["token_endpoint_auth_methods_supported"]
    assert "private_key_jwt" in obj["token_endpoint_auth_methods_supported"]
    assert "ES256" in obj["token_endpoint_auth_signing_alg_values_supported"]
    assert "atproto" in obj["scopes_supported"]
    assert obj["authorization_response_iss_parameter_supported"] is True
    assert obj["pushed_authorization_request_endpoint"] is not None
    assert obj["require_pushed_authorization_requests"] is True
    assert "ES256" in obj["dpop_signing_alg_values_supported"]
    if "require_request_uri_registration" in obj:
        assert obj["require_request_uri_registration"] is True
    assert obj["client_id_metadata_document_supported"] is True

    return True


async def resolve_pds_authserver(url: str) -> str:
    resp = await safe_get(f"{url}/.well-known/oauth-protected-resource")
    resp.raise_for_status()
    assert resp.status_code == 200
    return resp.json()["authorization_servers"][0]


async def fetch_authserver_meta(url: str) -> dict:
    resp = await safe_get(f"{url}/.well-known/oauth-authorization-server")
    resp.raise_for_status()
    authserver_meta = resp.json()
    assert is_valid_authserver_meta(authserver_meta, url)
    return authserver_meta


# --------------------------------------------------------------------------- #
# JWT / DPoP helpers
# --------------------------------------------------------------------------- #
def client_assertion_jwt(client_id: str, authserver_url: str, client_secret_jwk: JsonWebKey) -> str:
    return jwt.encode(
        {"alg": "ES256", "kid": client_secret_jwk["kid"]},
        {
            "iss": client_id,
            "sub": client_id,
            "aud": authserver_url,
            "jti": generate_token(),
            "iat": int(time.time()),
            "exp": int(time.time()) + 60,
        },
        client_secret_jwk,
    ).decode("utf-8")


def dpop_jwt(
    method: str,
    url: str,
    nonce: str,
    dpop_private_jwk: JsonWebKey,
    access_token: str | None = None,
) -> str:
    dpop_pub_jwk = json.loads(dpop_private_jwk.as_json(is_private=False))
    body = {
        "jti": generate_token(),
        "htm": method,
        "htu": url,
        "iat": int(time.time()),
        "exp": int(time.time()) + 30,
    }
    if nonce:
        body["nonce"] = nonce
    if access_token:
        # PKCE S256 hashing is the same as DPoP "ath" hashing
        body["ath"] = create_s256_code_challenge(access_token)
    return jwt.encode(
        {"typ": "dpop+jwt", "alg": "ES256", "jwk": dpop_pub_jwk},
        body,
        dpop_private_jwk,
    ).decode("utf-8")


def load_dpop_key(jwk_json: str) -> JsonWebKey:
    return JsonWebKey.import_key(json.loads(jwk_json))


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def parse_www_authenticate(data: str) -> tuple[str, dict]:
    scheme, _, params = data.partition(" ")
    items = urllib.request.parse_http_list(params)
    opts = urllib.request.parse_keqv_list(items)
    return scheme, opts


def is_use_dpop_nonce_error_response(resp) -> bool:
    if resp.status_code not in [400, 401]:
        return False
    www_authenticate = resp.headers.get("WWW-Authenticate")
    if www_authenticate:
        try:
            scheme, params = parse_www_authenticate(www_authenticate)
            if scheme.lower() == "dpop" and params.get("error") == "use_dpop_nonce":
                return True
        except Exception:
            pass
    try:
        json_body = resp.json()
    except Exception:
        return False
    json_data = json_body if isinstance(json_body, dict) else {}
    return json_data.get("error") == "use_dpop_nonce"


# --------------------------------------------------------------------------- #
# Auth server interactions
# --------------------------------------------------------------------------- #
async def auth_server_post(
    authserver_url: str,
    client_id: str,
    client_secret_jwk: JsonWebKey,
    dpop_private_jwk: JsonWebKey,
    dpop_authserver_nonce: str,
    post_url: str,
    post_data: dict,
    persist_cb: PersistCB | None = None,
) -> tuple[str, Any]:
    client_assertion = client_assertion_jwt(client_id, authserver_url, client_secret_jwk)
    post_data |= {
        "client_id": client_id,
        "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
        "client_assertion": client_assertion,
    }

    dpop_proof = dpop_jwt("POST", post_url, dpop_authserver_nonce, dpop_private_jwk)
    resp = await safe_post(post_url, data=post_data, headers={"DPoP": dpop_proof})

    # retry once with the server-provided nonce
    if is_use_dpop_nonce_error_response(resp):
        dpop_authserver_nonce = resp.headers["DPoP-Nonce"]
        if persist_cb:
            persist_cb({"dpop_authserver_nonce": dpop_authserver_nonce})
        dpop_proof = dpop_jwt("POST", post_url, dpop_authserver_nonce, dpop_private_jwk)
        resp = await safe_post(post_url, data=post_data, headers={"DPoP": dpop_proof})

    return dpop_authserver_nonce, resp


async def send_par_auth_request(
    authserver_url: str,
    authserver_meta: dict,
    login_hint: str | None,
    client_id: str,
    redirect_uri: str,
    scope: str,
    client_secret_jwk: JsonWebKey,
    dpop_private_jwk: JsonWebKey,
) -> tuple[str, str, str, Any]:
    par_url = authserver_meta["pushed_authorization_request_endpoint"]
    state = generate_token()
    pkce_verifier = generate_token(48)

    code_challenge = create_s256_code_challenge(pkce_verifier)

    par_body = {
        "response_type": "code",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
        "redirect_uri": redirect_uri,
        "scope": scope,
    }
    if login_hint:
        par_body["login_hint"] = login_hint

    dpop_authserver_nonce, resp = await auth_server_post(
        authserver_url=authserver_url,
        client_id=client_id,
        client_secret_jwk=client_secret_jwk,
        dpop_private_jwk=dpop_private_jwk,
        dpop_authserver_nonce="",
        post_url=par_url,
        post_data=par_body,
    )

    return pkce_verifier, state, dpop_authserver_nonce, resp


async def initial_token_request(
    auth_request: dict,
    code: str,
    client_id: str,
    client_secret_jwk: JsonWebKey,
) -> tuple[dict, str]:
    authserver_url = auth_request["authserver_iss"]
    authserver_meta = await fetch_authserver_meta(authserver_url)

    params = {
        "redirect_uri": auth_request["redirect_uri"],
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": auth_request["pkce_verifier"],
    }

    token_url = authserver_meta["token_endpoint"]
    dpop_private_jwk = load_dpop_key(auth_request["dpop_private_jwk"])

    dpop_authserver_nonce, resp = await auth_server_post(
        authserver_url=authserver_url,
        client_id=client_id,
        client_secret_jwk=client_secret_jwk,
        dpop_private_jwk=dpop_private_jwk,
        dpop_authserver_nonce=auth_request["dpop_authserver_nonce"],
        post_url=token_url,
        post_data=params,
    )

    resp.raise_for_status()
    return resp.json(), dpop_authserver_nonce


async def refresh_token_request(
    user: dict,
    client_id: str,
    client_secret_jwk: JsonWebKey,
) -> tuple[dict, str]:
    authserver_url = user["authserver_iss"]
    authserver_meta = await fetch_authserver_meta(authserver_url)

    params = {
        "grant_type": "refresh_token",
        "refresh_token": user["refresh_token"],
    }

    token_url = authserver_meta["token_endpoint"]
    dpop_private_jwk = load_dpop_key(user["dpop_private_jwk"])

    dpop_authserver_nonce, resp = await auth_server_post(
        authserver_url=authserver_url,
        client_id=client_id,
        client_secret_jwk=client_secret_jwk,
        dpop_private_jwk=dpop_private_jwk,
        dpop_authserver_nonce=user["dpop_authserver_nonce"],
        post_url=token_url,
        post_data=params,
    )

    resp.raise_for_status()
    return resp.json(), dpop_authserver_nonce


# --------------------------------------------------------------------------- #
# PDS (resource server) requests
# --------------------------------------------------------------------------- #
async def pds_authed_req(
    url: str,
    user: dict,
    body: dict | None = None,
    headers: dict | None = None,
    persist_cb: PersistCB | None = None,
) -> Any:
    """POST to the user's PDS using DPoP + access token (with nonce retry).

    ``persist_cb`` is invoked when the PDS rotates the DPoP nonce so the caller
    can persist it immediately.
    """
    dpop_private_jwk = load_dpop_key(user["dpop_private_jwk"])
    dpop_pds_nonce = user["dpop_pds_nonce"]
    access_token = user["access_token"]

    for _ in range(2):
        dpop_jwt_header = dpop_jwt(
            "POST",
            url,
            access_token=access_token,
            nonce=dpop_pds_nonce,
            dpop_private_jwk=dpop_private_jwk,
        )
        final_headers = {
            "Authorization": f"DPoP {access_token}",
            "DPoP": dpop_jwt_header,
        }
        if headers:
            final_headers |= headers
        resp = await safe_post(url, json=body, headers=final_headers)

        if is_use_dpop_nonce_error_response(resp):
            new_nonce = resp.headers.get("DPoP-Nonce")
            if not new_nonce:
                raise RuntimeError("PDS requested a new DPoP nonce but provided none")
            dpop_pds_nonce = new_nonce
            if persist_cb:
                persist_cb({"dpop_pds_nonce": new_nonce})
            continue
        break

    return resp