import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from oxyde import db
from starlette.middleware.sessions import SessionMiddleware

from .atproto_service import get_client_key
from .config import get_settings
from .routes import auth, home, offers, profiles

PROJECT_ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent
settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await db.init(default=settings.database_url)
    try:
        yield
    finally:
        await db.close()


app = FastAPI(title="MutualSky", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    same_site="lax",
    https_only=settings.cookie_secure,
)
app.mount("/static", StaticFiles(directory=PROJECT_ROOT / "app" / "static"), name="static")

app.include_router(home.router)
app.include_router(auth.router)
app.include_router(profiles.router)
app.include_router(offers.router)


def _public_jwk() -> dict:
    key = get_client_key(settings)
    pub = json.loads(key.as_json(is_private=False))
    assert "d" not in pub
    return pub


@app.get("/bsky-oauth-client.json")
async def oauth_client_metadata(request: Request):
    base = str(request.base_url).rstrip("/")
    https_base = base.replace("http://", "https://")
    return JSONResponse(
        {
            "client_id": f"{https_base}/bsky-oauth-client.json",
            "dpop_bound_access_tokens": True,
            "application_type": "web",
            "redirect_uris": [f"{https_base}/auth/callback"],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "scope": settings.oauth_scope,
            "token_endpoint_auth_method": "private_key_jwt",
            "token_endpoint_auth_signing_alg": "ES256",
            "jwks": {"keys": [_public_jwk()]},
            "client_name": "MutualSky",
            "client_uri": https_base,
        }
    )


@app.get("/oauth/jwks.json")
async def oauth_jwks():
    return JSONResponse({"keys": [_public_jwk()]})