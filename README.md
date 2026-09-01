# MutualSky

Friendship on the Atmosphere / Bluesky – a web app for swapping Bluesky follows.

An offerer picks an account and proposes a "follow swap": **You get a follow if you follow back.** As soon as the requested person confirms the swap in the app, **both follows are set in a single step** via OAuth on behalf of the respective users.

## How it works

1. Sign in with your own Bluesky account (OAuth 2.1 + DPoP, confidential client).
2. Search for an account and offer a follow swap. The person receives a Bluesky DM with a link to the offer page.
3. The person opens the link, signs in, and confirms the swap.
4. The app executes both follows immediately: target→offerer (target's grant) and offerer→target (stored grant of the offerer).

No background worker: everything is event-driven via the confirmation click. Offers expire based on the database (`OFFER_TTL_DAYS`, checked lazily).

The UI is bilingual (German/English) with a language switch in the header, shows a **Beta** badge, and links to this repository (open source).

## Tech stack

- FastAPI + uvicorn (async)
- PyJSX (`.px` templates, JSX in Python) + HTMX + custom CSS
- Oxyde ORM (async, Pydantic, Rust core) + SQLite
- The official Bluesky reference cookbook `python-oauth-web-app` as OAuth base (ported to httpx)

## Prerequisites

- Python >= 3.12 (managed via `uv`)
- A public HTTPS domain (OAuth redirect + client metadata)

## Local development

```bash
uv sync
cp .env.example .env        # set values; COOKIE_SECURE=false
uv run python scripts/generate_jwk.py   # -> OAUTH_CLIENT_SECRET_JWK
uv run oxyde migrate        # create the database
uv run uvicorn app.main:app --reload
```

Local sign-in works through the loopback OAuth client (no metadata hosting needed). For the authenticated post search (Posts/Account tab) and DMs, use the app through a public domain such as an ngrok static domain (`PUBLIC_BASE_URL`).

## Deployment

1. DNS: point a record at the server (own domain) + HTTPS certificate (Caddy/nginx).
2. `.env` with `PUBLIC_BASE_URL=https://your.domain`, generated secrets, `OAUTH_CLIENT_SECRET_JWK`, `COOKIE_SECURE=true`, `DATABASE_URL` (volume).
3. Apply migrations: `uv run oxyde migrate` (or `migrate` in the container before app start).
4. Start the container (see `Dockerfile`):

```bash
docker build -t mutualsky .
docker run -d -p 8000:8000 -v mutualsky-data:/data --env-file .env mutualsky
```

### Docker Compose (Coolify)

A `docker-compose.yml` is provided. Environment and the SQLite database both live in the `data/` directory, which is mounted as a volume:

```bash
cp data/.env.example data/.env   # fill in real values
docker compose up -d --build
```

Before starting the app the first time, apply the migrations inside the container:

```bash
docker compose run --rm app /app/.venv/bin/oxyde migrate
```

5. **Verify before going live:** `curl https://your.domain/bsky-oauth-client.json` – the value of `client_id` in the document must exactly match the fetch URL. Then sign in once with a real account.

### Important: domain change

`client_id` (client metadata URL) and `redirect_uris` are bound to the domain; the authorization server also binds refresh tokens to the `client_id`. **Changing the domain invalidates all existing sign-ins** – every user must re-authorize.

## Tests

```bash
uv run pytest        # 20 tests (swap orchestration + routes, providers mocked)
uv run ruff check    # lint
```

## MVP limitations

- **DM delivery is not guaranteed**: only sendable when the sender granted the `transition:chat.bsky` scope and the recipient allows incoming DMs. The app pre-checks the recipient's DM policy and explains the reason; the offer still exists in the app (badge + "Resend DM"). If DMs are blocked, the offerer can optionally post a public reply to the recipient's latest post – this is an explicit action, is publicly visible, and can't be undone.
- **OAuth tokens only work against PDS endpoints** (Bluesky policy). Write actions (follow, chat) go through the respective PDS; public reads use `public.api.bsky.app`.
- **Follow baiting / unfollowing afterwards** is not monitored (no auto-unfollow, no minimum holding period).
- **Logout** only clears the browser session, not the server-side grant (so running offers can be completed).
- Tokens are stored encrypted in SQLite using `APP_SECRET` (Fernet).
- Offer URLs are capability links (`/o/{id}-{signature}`, HMAC-signed) – they are not enumerable; withdrawn offers are hidden from listings.

## Routes

| Route | Purpose |
|---|---|
| `GET /` | Landing / dashboard (my + incoming offers) |
| `GET /archiv` | Archive of completed/expired offers |
| `GET /auth/login`, `POST /auth/start`, `GET /auth/callback`, `POST /auth/logout` | Bluesky OAuth |
| `GET /lang/{de\|en}` | Language switch (preserves current page) |
| `POST /profiles/search` | Account search (HTMX) |
| `POST /profiles/search/more` | Account search pagination |
| `POST /posts/search`, `POST /posts/search/more` | Post/Account search (signed-in, via AppView proxy) |
| `GET /profile/{handle}` | Profile + offer button |
| `POST /offers` | Create offer + DM |
| `GET /o/{ref}` | Offer page (capability URL) |
| `POST /offers/{id}/confirm` | Confirm swap (both follows) |
| `POST /offers/{id}/cancel` | Withdraw offer (+ deletes public reply) |
| `POST /offers/{id}/resend-dm` | Resend the notification DM |
| `POST /offers/{id}/reply` | Post the offer publicly as a reply |
| `GET /bsky-oauth-client.json`, `GET /oauth/jwks.json` | OAuth client metadata |