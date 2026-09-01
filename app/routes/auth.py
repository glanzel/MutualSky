from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .. import i18n
from ..atproto_service import client_id_for_host, generate_dpop_key, get_client_key
from ..config import get_settings
from ..crypto import encrypt_str
from ..models import User
from ..oauth import atproto_oauth as oauth
from ..oauth.atproto_identity import is_valid_did, is_valid_handle, pds_endpoint, resolve_identity
from ..oauth.atproto_security import is_safe_url
from ..oauth.state_store import oauth_state_store
from ..security import is_safe_local_path, rate_limit
from ..ui import home as home_ui

router = APIRouter()


def _clean_handle(raw: str) -> str:
    cleaned = "".join(ch for ch in raw if ord(ch) >= 32).strip()
    cleaned = cleaned.removeprefix("@")
    return cleaned


def _error_redirect(message: str) -> RedirectResponse:
    return RedirectResponse("/auth/login?" + urlencode({"error": message}), status_code=303)


def _render_page(content, status_code: int = 200) -> HTMLResponse:
    return HTMLResponse(content=str(content), status_code=status_code)


@router.get("/auth/login")
async def login_page(request: Request, next: str = ""):
    error = request.query_params.get("error", "")
    next_url = next if is_safe_local_path(next) else ""
    page = home_ui.LoginPage(error=error, next_url=next_url)
    return _render_page(page)


@router.post("/auth/start", dependencies=[Depends(rate_limit(5, 60))])
async def auth_start(request: Request):
    form = await request.form()
    settings = get_settings()
    raw_handle = str(form.get("handle", ""))
    next_url = str(form.get("next", ""))
    if not is_safe_local_path(next_url):
        next_url = ""

    handle = _clean_handle(raw_handle)
    if not (is_valid_handle(handle) or is_valid_did(handle)):
        return _error_redirect(i18n.t("Ungültiger Handle oder DID."))

    try:
        did, handle, did_doc = await resolve_identity(handle)
        pds_url = pds_endpoint(did_doc)
        try:
            authserver_url = await oauth.resolve_pds_authserver(pds_url)
            authserver_meta = await oauth.fetch_authserver_meta(authserver_url)
        except Exception:
            # The account's PDS may be temporarily unreachable. Fall back to the
            # last verified auth server for this account (stored at login).
            stashed = await User.objects.get_or_none(did=did)
            authserver_url = stashed.authserver_iss if stashed else None
            if not authserver_url:
                raise
            authserver_meta = await oauth.fetch_authserver_meta(authserver_url)
    except Exception as exc:
        return _error_redirect(i18n.t("Identität konnte nicht aufgelöst werden: {fehler}", fehler=exc))

    client_id, redirect_uri = client_id_for_host(request, settings)
    dpop_private_jwk = generate_dpop_key()

    try:
        pkce_verifier, state, dpop_nonce, resp = await oauth.send_par_auth_request(
            authserver_url,
            authserver_meta,
            login_hint=handle,
            client_id=client_id,
            redirect_uri=redirect_uri,
            scope=settings.oauth_scope,
            client_secret_jwk=get_client_key(settings),
            dpop_private_jwk=oauth.load_dpop_key(dpop_private_jwk),
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"PAR HTTP {resp.status_code}: {resp.text[:300]}")
        par_request_uri = resp.json()["request_uri"]
    except Exception as exc:
        return _error_redirect(i18n.t("Anmeldung fehlgeschlagen: {fehler}", fehler=exc))

    oauth_state_store.put(
        state,
        {
            "authserver_iss": authserver_meta["issuer"],
            "did": did,
            "handle": handle,
            "pds_url": pds_url,
            "pkce_verifier": pkce_verifier,
            "scope": settings.oauth_scope,
            "dpop_authserver_nonce": dpop_nonce,
            "dpop_private_jwk": dpop_private_jwk,
            "redirect_uri": redirect_uri,
            "next": next_url,
        },
    )

    auth_url = authserver_meta["authorization_endpoint"]
    if not is_safe_url(auth_url):
        return RedirectResponse("/auth/login?error=Falscher Authorization-Endpoint.", status_code=303)
    qparam = urlencode({"client_id": client_id, "request_uri": par_request_uri})
    return RedirectResponse(f"{auth_url}?{qparam}", status_code=303)


@router.get("/auth/callback")
async def auth_callback(request: Request):
    settings = get_settings()
    error = request.query_params.get("error")
    if error:
        error_description = request.query_params.get("error_description", "")
        return RedirectResponse(
            "/auth/login?error=" + urlencode({"error": f"{error}: {error_description}"}), status_code=303
        )

    state = request.query_params.get("state")
    authserver_iss = request.query_params.get("iss")
    authorization_code = request.query_params.get("code")
    if not (state and authserver_iss and authorization_code):
        return RedirectResponse("/auth/login?error=" + urlencode({"error": "Unvollständige Antwort."}), status_code=303)

    auth_request = oauth_state_store.pop(state)
    if auth_request is None:
        return RedirectResponse("/auth/login?error=" + urlencode({"error": "Anmelde-Sitzung abgelaufen oder unbekannt."}), status_code=303)
    if auth_request["authserver_iss"] != authserver_iss:
        return RedirectResponse("/auth/login?error=" + urlencode({"error": "Authorization-Server-Mismatch."}), status_code=303)

    client_id, _ = client_id_for_host(request, settings)
    try:
        tokens, dpop_nonce = await oauth.initial_token_request(
            auth_request, authorization_code, client_id, get_client_key(settings)
        )
    except Exception as exc:
        return RedirectResponse(
            "/auth/login?error=" + urlencode({"error": f"Token-Austausch fehlgeschlagen: {exc}"}), status_code=303
        )

    # Identity verification: the "sub" must match the requested account.
    expected_did = auth_request["did"]
    if tokens.get("sub") != expected_did:
        return _error_redirect(i18n.t("Angemeldeter Account entspricht nicht der Anfrage."))

    granted_scope = tokens.get("scope", "")
    if "atproto" not in granted_scope:
        return _error_redirect(i18n.t("Erforderliche atproto-Berechtigung fehlt."))

    from ..atproto_service import apply_token_updates

    user = await User.objects.get_or_none(did=expected_did)
    if user is None:
        user = User(did=expected_did, handle=auth_request["handle"])
    user.handle = auth_request["handle"]
    user.pds_url = auth_request["pds_url"]
    user.authserver_iss = auth_request["authserver_iss"]
    user.client_id = client_id
    user.scope = granted_scope
    user.dpop_private_jwk = encrypt_str(auth_request["dpop_private_jwk"], settings.encryption_secret)
    apply_token_updates(
        user,
        settings,
        {
            "access_token": tokens.get("access_token", ""),
            "refresh_token": tokens.get("refresh_token", ""),
            "dpop_authserver_nonce": dpop_nonce,
            "dpop_pds_nonce": "",
        },
    )
    await user.save()

    request.session["user_did"] = user.did
    request.session["user_handle"] = user.handle

    next_url = auth_request.get("next") or "/"
    return RedirectResponse(next_url, status_code=303)


@router.post("/auth/logout")
async def auth_logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=303)