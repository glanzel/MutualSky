# MutualSky

Freundschaft auf dem Atmosphere / Bluesky – eine Webapp zum Tauschen von Bluesky-Follows.

Der Anbieter wählt einen Account aus und bietet einen „Follow-Swap" an: **Du bekommst einen Follow, wenn du zurückfolgst.** Sobald die angefragte Person den Tausch in der App bestätigt, werden **beide Follows in einem Schritt** per OAuth im Namen der jeweiligen Nutzer gesetzt.

## So funktioniert es

1. Anmelden mit dem eigenen Bluesky-Account (OAuth 2.1 + DPoP, confidential client).
2. Account suchen und „Follow-Swap anbieten". Die Person bekommt eine Bluesky-DM mit einem Link zur Angebotsseite.
3. Die Person öffnet den Link, meldet sich an und bestätigt den Tausch.
4. Die App führt beide Follows sofort aus: Ziel→Anbieter (Grant des Ziels) und Anbieter→Ziel (gespeicherter Grant des Anbieters).

Kein Hintergrund-Worker: alles ist ereignisgetrieben über den Bestätigungs-Klick. Angebote verfallen datenbasiert (`OFFER_TTL_DAYS`, lazy geprüft).

## Tech-Stack

- FastAPI + uvicorn (async)
- PyJSX (`.px`-Templates, JSX in Python) + HTMX + eigenes CSS
- Oxyde ORM (async, Pydantic, Rust-Core) + SQLite
- Offizielles Bluesky-Referenz-Cookbook `python-oauth-web-app` als OAuth-Basis (auf httpx portiert)

## Voraussetzungen

- Python >= 3.12 (verwaltet via `uv`)
- Öffentliche HTTPS-Domain (OAuth-Redirect + Client-Metadaten)

## Lokale Entwicklung

```bash
uv sync
cp .env.example .env        # Werte setzen, COOKIE_SECURE=false
uv run python scripts/generate_jwk.py   # -> OAUTH_CLIENT_SECRET_JWK
uv run oxyde migrate        # Datenbank anlegen
uv run uvicorn app.main:app --reload
```

Lokales Login funktioniert über den Loopback-OAuth-Client (kein Metadaten-Hosting nötig).

## Deployment

1. DNS: `mutualsky`-Record auf den Server (Subdomain von ecord.de) + HTTPS-Zertifikat (Caddy/nginx).
2. `.env` mit `PUBLIC_BASE_URL=https://mutualsky.ecord.de`, generierten Secrets, `OAUTH_CLIENT_SECRET_JWK`, `COOKIE_SECURE=true`, `DATABASE_URL` (Volume).
3. Migrationen anwenden: `uv run oxyde migrate` (oder im Container `migrate` vor App-Start).
4. Container starten (siehe `Dockerfile`):

```bash
docker build -t mutualsky .
docker run -d -p 8000:8000 -v mutualsky-data:/data --env-file .env mutualsky
```

5. **Vor Go-Live verifizieren:** `curl https://mutualsky.ecord.de/bsky-oauth-client.json` – der Wert `client_id` im Dokument muss exakt mit der Abruf-URL übereinstimmen. Danach einmal mit einem echten Account einloggen.

### Wichtig: Domain-Wechsel

`client_id` (URL der Client-Metadaten) und `redirect_uris` sind an die Domain gebunden; ebenso bindet der Authorization Server Refresh-Tokens an die `client_id`. **Ein Wechsel der Domain invalidiert alle bestehenden Logins** – alle Nutzer müssen sich neu autorisieren.

## Tests

```bash
uv run pytest        # 20 Tests (Swap-Orchestrierung + Routen, Provider gemockt)
uv run ruff check    # Lint
```

## Einschränkungen (MVP)

- **DM-Zustellung nicht garantierbar**: nur sendbar, wenn der Sender den `transition:chat.bsky`-Scope erteilt hat und der Empfänger DMs zulässt. Sonst bleibt das Angebot in der App sichtbar (Badge + „DM erneut senden").
- **OAuth-Tokens funktionieren nur gegen PDS-Endpoints** (Bluesky-Policy). Schreibaktionen (Follow, Chat) laufen daher über die jeweilige PDS; öffentliche Leseaufrufe über `public.api.bsky.app`.
- **Follow-Baiting / nachträgliches Unfollow** wird nicht überwacht (kein Auto-Unfollow, keine Mindesthaltedauer).
- **Logout** löscht nur die Browser-Session, nicht den serverseitigen Grant (damit laufende Angebote abgeschlossen werden können).
- Tokens liegen mit `APP_SECRET` (Fernet) verschlüsselt in SQLite.

## Routen

| Route | Zweck |
|---|---|
| `GET /` | Landing / Dashboard (meine + eingehende Angebote) |
| `GET /auth/login`, `POST /auth/start`, `GET /auth/callback`, `POST /auth/logout` | Bluesky-OAuth |
| `POST /profiles/search` | Suche (HTMX) |
| `GET /profile/{handle}` | Profil + Angebots-Button |
| `POST /offers` | Angebot erstellen + DM |
| `GET /o/{id}` | Öffentliche Angebotsseite |
| `POST /offers/{id}/confirm` | Tausch bestätigen (beide Follows) |
| `POST /offers/{id}/cancel`, `POST /offers/{id}/resend-dm` | Aufheben / DM erneut senden |
| `GET /bsky-oauth-client.json`, `GET /oauth/jwks.json` | OAuth-Client-Metadaten |