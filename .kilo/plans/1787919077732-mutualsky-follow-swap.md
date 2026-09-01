# MutualSky – Plan: Bluesky Follow-Swap Webapp

## Ziel

Webapp, in der ein Nutzer („Anbieter", Alice) einen beliebigen Bluesky-Account („Ziel", Bob) auswählt (Suche/Handle) und ihm anbietet: **„Ich folge dir, wenn du mir folgst."** Alice und Bob sind beide per Bluesky-OAuth angemeldet.

Mechanik (bilateral, ereignisgetrieben, **kein Hintergrund-Worker**):
1. Alice wählt Bob, erstellt ein Angebot (Status `pending`).
2. App informiert Bob per Bluesky-DM mit Link zur Angebotsseite `<PUBLIC_BASE_URL>/o/<id>` + das Angebot erscheint in „Eingegangene Angebote" in Bobs Inbox, sobald er sich anmeldet.
3. Bob öffnet die Angebotsseite. Ist er nicht eingeloggt → Login-Prompt; nach Login sieht er den Confirm-Button.
4. Bob klickt „Follow-Swap bestätigen". Die App führt **beide Follows in einem Schritt** aus, im selben Request-Handler:
   - Bob → Alice über **Bobs** OAuth-Grant (`com.atproto.repo.createRecord` auf Bobs PDS)
   - Alice → Bob über **Alices** serverseitig gespeichertem OAuth-Grant (`com.atproto.repo.createRecord` auf Alices PDS)
5. Beide erfolgreich → `status=completed`, `completed_at` setzen. Teilfehler → siehe Fehlerbehandlung unten. Kein Auto-Unfollow.

Kein Polling: Verifikation ist konstruktionsbedingt erfüllt, weil die App beide Follows selbst ausführt. Zeitliche Fristen (Expiry) werden **lazy** geprüft (beim Seitenaufruf der Angebotsseite, beim Confirm-Klick und im Dashboard).

## Bestätigte Entscheidungen

| Entscheidung | Wert |
|---|---|
| Ausführung | Automatisch per OAuth im Namen des jeweiligen Nutzers; beide Follows beim Bestätigen, ein Schritt |
| Benachrichtigung | In-App (Inbox) + Bluesky-DM |
| Stack | Python: FastAPI + PyJSX (`.px`-Templates) + HTMX + Oxyde ORM |
| DB | SQLite (Oxyde), auch im Produktivbetrieb (wenige Nutzer erwartet) |
| Deployment | Produktiv unter **https://mutualsky.ecord.de** (Subdomain von ecord.de, DNS/TLS dort einzurichten); Domain-Wechsel später möglich (hat Konsequenzen, s. Risiken) |
| Follow-Modell | Bilateral + atomar-best-effort beim Confirm von Bob; Bob muss die App mit Bluesky-Account nutzen |
| UI-Sprache | Deutsch |
| Browsing | Öffentlich (ohne Login); Login zum Anbieten, Bestätigen und Verwalten |

## Tech-Stack & Abhängigkeiten

- Python >= 3.12, `uv` als Projekt-Manager
- `fastapi`, `uvicorn[standard]`
- `python-jsx` (= PyJSX, Import: `pyjsx`) für Server-gerenderte JSX-Templates
- `oxyde` (async Pydantic-ORM, Rust-Core; SQLite; CLI: `oxyde makemigrations`/`oxyde migrate`)
- HTMX über CDN (`<script src="https://unpkg.com/htmx.org">`)
- `PyJWT` + `cryptography` für Client-Assertion-JWT und DPoP-JWTs (ES256/P-256)
- `httpx` (async HTTP: Metadaten, PAR, Token, XRPC-Calls)
- `pydantic-settings` für `.env`-Konfiguration
- Session: `starlette.middleware.sessions.SessionMiddleware` (signierter Cookie, Inhalt nur `user_did`)
- Verschlüsselung Tokens-at-rest: `cryptography` Fernet mit `APP_SECRET`

## Projektstruktur

```
mutualsky/
  pyproject.toml
  .env / .env.example
  app/
    __init__.py
    main.py            # FastAPI-App, Lifespan: db.init, Mounts, Routen
    config.py          # pydantic-settings (alle Env-Werte)
    models.py          # Oxyde-Modelle: User, Offer
    oauth_client_metadata.json.in   # Vorlage; ausgeliefert unter PUBLIC_BASE_URL/bsky-oauth-client.json
    oauth/
      __init__.py
      identity.py      # Handle/DID/PDS-Auflösung (aus offiziellen Cookbook übernommen, async)
      security.py      # URL-/HTTP-Härtung, Issuer-Verifizierung (aus Cookbook, async)
      util.py          # JWT/DPoP-Helfer (aus Cookbook, async)
      flow.py          # PAR-, PKCE-, Token-Exchange-, Refresh-Flow (aus Cookbook, async, httpx)
    bluesky/
      __init__.py
      client.py        # öffentliche Calls (searchActors/getProfile/resolveHandle)
      actions.py       # Follow erstellen (createRecord), DM senden (Chat-Proxy)
      dm.py            # DM-Nachrichtenbau + Zustellungsfehler-Behandlung
      swap.py          # Bestätigungs-Orchestrierung: beide Follows ausführen + Teilfehler-Handling
    routes/
      __init__.py
      auth.py          # GET /auth/start, GET /auth/callback, POST /auth/logout
      profiles.py      # POST /profiles/search, GET /profile/{handle}
      offers.py        # POST /offers, POST /offers/{id}/confirm, POST /offers/{id}/cancel,
                       # POST /offers/{id}/resend-dm, GET /o/{id}
      home.py          # GET / (Landing + Dashboard incl. Inbox)
    ui/
      __init__.py      # import pyjsx.auto_setup (VOR allem anderen .px-Import)
      layout.px        # <Layout> (Header, Nav, HTMX-Script)
      home.px          # Landing/Dashboard (Meine Angebote + Eingegangene)
      profile.px       # Profilseite + Angebots-Button/Status
      offer.px         # Angebotsseite (öffentlich); für Ziel mit Confirm/Login-Block, DM-Status,
                       # Erneut-senden-Button, Error-Banner bei Teilfehler
      partials.px      # HTMX-Fragmente (Suche-Ergebnisse, Angebots-Karte, Status-Badges)
  tests/
    test_swap.py       # Confirm-Logik: beide Follows, Teilfehler, Status-Guards, Expiry (gemockt)
    test_routes.py     # Smoke-Tests der Routen
```

## Datenmodell (Oxyde, SQLite)

`users`
- `did` (str, PK)
- `handle`, `display_name`, `avatar_url` (Snapshot für UI)
- `pds_url` (issuer/PDS-Base-URL)
- `refresh_token` (encrypted, Fernet)
- `dpop_private_key_jwk` (encrypted str, Fernet)
- `access_token` wird nicht persistiert (wird bei Bedarf per Refresh geholt)
- `created_at`, `updated_at`

`offers`
- `id` (int PK)
- `offerer_did`, `target_did`, `target_handle` (Snapshot zum Anzeigen)
- `status`: `pending | completed | cancelled | expired`
- `dm_status`: `none | sent | failed` + `dm_error` (string)
- `expires_at` (Standard: jetzt + OFFER_DAYS=14; wird lazy geprüft)
- `follow_error` (string|None): letzter Teilfehler beim Confirm (für Error-Banner + Retry)
- `created_at`, `completed_at`, `cancelled_at`
- Unique-Constraint: `(offerer_did, target_did)` auf aktive (`pending`) Angebote

`oauth_states`: PAR-Zwischenzustand pro Redirect als In-Memory-Dict (ein uvicorn-Worker, kurze Lebensdauer). Kein Table nötig.

Migrations: `oxyde init` (SQLite), Modelle als oben, `oxyde makemigrations && oxyde migrate`.

## OAuth-Integration (Kernstück)

**Basis:** Offizielle Referenz `python-oauth-web-app` aus `bluesky-social/cookbook` (enthält komplette manuelle OAuth-2.1-implementierung mit DPoP: `atproto_identity.py`, `atproto_oauth.py`, `atproto_security.py`, `atproto_util.py`). Aus dem Flask+sqlite-Kontext nach FastAPI+httpx+Oxyde portieren (async).

**Client-Typ:** Confidential Client, `token_endpoint_auth_method: private_key_jwt`, Signatur ES256 mit einmalig generiertem App-Key (Skript `generate_jwk.py` aus Cookbook adaptieren → `OAUTH_CLIENT_SECRET_JWK`).

**Client-Metadaten** werden von der App selbst ausgeliefert:
`https://mutualsky.ecord.de/bsky-oauth-client.json`:
```json
{
  "client_id": "https://mutualsky.ecord.de/bsky-oauth-client.json",
  "application_type": "web",
  "client_name": "MutualSky",
  "grant_types": ["authorization_code", "refresh_token"],
  "response_types": ["code"],
  "redirect_uris": ["https://mutualsky.ecord.de/auth/callback"],
  "scope": "atproto transition:generic transition:chat.bsky",
  "dpop_bound_access_tokens": true,
  "token_endpoint_auth_method": "private_key_jwt",
  "token_endpoint_auth_signing_alg": "ES256",
  "jwks": {"keys": [...]}
}
```
`client_id` im Dokument MUSS exakt die ausgelieferte URL sein.
Konfiguration: `PUBLIC_BASE_URL=https://mutualsky.ecord.de` als einzige Domänen-Quelle im Code; alle OAuth-URLs und DM-Links werden daraus abgeleitet (kein Hardcoding an anderen Stellen).

**Flow:**
1. `POST /auth/start` mit Handle → Handle zu DID auflösen → PDS/AS-Discovery (`/.well-known/oauth-protected-resource`, `/.well-known/oauth-authorization-server`) → neues ES256-DPoP-Keypair für die Sitzung → PAR mit PKCE(S256) + Client-Assertion (`private_key_jwt`) → Redirect auf Authorization-Endpoint mit `request_uri`.
2. `GET /auth/callback` (Params `code`, `state`, `iss`) → Code gegen Token-Endpoint tauschen (DPoP mit Nonce-Retry) → **Pflicht:** `sub` (DID) gegen `iss` + ursprüngliche DID verifizieren; `atproto`-Scope im Token prüfen → User anlegen/aktualisieren, Refresh-Token + DPoP-Privkey verschlüsselt speichern → Session-Cookie (`user_did`) → Redirect auf Ziel-URL (bei Angebots-Kontext: `/o/<id>`), sonst `/`.
3. Danach pro Account: DPoP-gebundene Requests mit automatischem Refresh (auf 401 → Refresh → Retry), Nonce-Rotation beidseitig (AS + PDS). Serverseitig arbeitet jede plattform-übergreifende Aktion (Confirm) mit den **gespeicherten Grants beider Nutzer**, nicht mit der Session des aufrufenden Browsers.

**Domain-Wechsel:** `client_id` + `redirect_uris` sind an die Domain gebunden, ebenso die ausgestellten Refresh-Tokens. Nutzer müssen nach Domain-Wechsel neu autorisieren (Hinweis in Message beim Login + README dokumentieren).

## Bluesky-Calls

Öffentlich (kein Auth, AppView bsky.social):
- `com.atproto.identity.resolveHandle` (Handle → DID)
- `app.bsky.actor.searchActors` (Suche)
- `app.bsky.actor.getProfile` (Profil-Daten)

Authentifiziert (über DPoP-Access-Token des jeweiligen Users, Request an dessen PDS-Base-URL):
- Follow setzen: `com.atproto.repo.createRecord`, Body `{repo: <DID>, collection: "app.bsky.graph.follow", record: {"$type":"app.bsky.graph.follow","subject": <Ziel-DID>, "createdAt": <iso>}}`
- DM senden (Chat wird über den PDS proxy-t):
  - `POST <PDS>/xrpc/chat.bsky.convo.getConvoForMembers` mit Header `atproto-proxy: did:web:api.bsky.chat#bsky_chat`, Body `{members:[Bob-DID]}`
  - `POST <PDS>/xrpc/chat.bsky.convo.sendMessage` mit `{convoId, message:{text}}`
  - DM-Text: „@Alice bietet einen Follow-Swap an: Du bekommst einen Follow von @Alice, wenn du zurückfolgst. Bestätigen: <PUBLIC_BASE_URL>/o/<offer_id>" (Facets/URL-Link optional über `app.bsky.richtext.facet`).

Wichtige Einschränkung (Bsky-Policy): OAuth-Tokens funktionieren nur gegen PDS-Endpoints, NICHT gegen AppView-endpoints (`app.bsky.*` lehnt OAuth-Tokens ab). Daher: Schreib-Calls (`createRecord` Follow, Chat via Proxy) laufen gegen die jeweilige PDS – OK. Alle Lesecalls sind öffentlich – OK. Kein AppView-Auth-Call nötig.

## Confirm-Orchestrierung (`bluesky/swap.py`)

Handler `POST /offers/{id}/confirm` (nur eingeloggt, nur wenn Session-DID == `target_did`):
1. **Lazy Expiry**: ist `expires_at` überschritten → `status=expired`, Antwort „abgelaufen", kein Follow, kein Follow.
2. **Status-Guard atomar**: `UPDATE offers SET status='completed' WHERE id=? AND status='pending'` als Prä-Sperre (verhindert Doppel-Confirm bei parallelen Requests). War kein Row betroffen → bereits erledigt/storniert → Information.
3. **Reihenfolge**: 1. Bob→Alice (Bobs Grant), 2. Alice→Bob (Alices Grant). Warum in dieser Reihenfolge: Bobs Zustimmung ist das Commit; fällt Schritt 2 aus, existiert bereits ein echter Follow von Bob, Empfänger-seitig sichtbar.
4. Teilfehler: 
   - Schritt 1 (Bob→Alice) fehlgeschlagen → `status` zurück auf `pending` (Guard-Status zurücksetzen), `follow_error` setzen, User sieht Error-Banner mit „Erneut versuchen"-Button. Der „Erneut versuchen"-Button wiederholt den ganzen Pair-Step.
   - Schritt 2 (Alice→Bob) fehlgeschlagen → Status bleibt `pending` (nicht completed!), `follow_error` setzen, Error-Banner: „Bob folgt dir bereits; dein Follow konnte nicht gesetzt werden – erneut versuchen." Bobs Follow wird beim Retry **nicht dupliziert**: vor dem setzen prüfen wir per `getRelationships`, ob der Follow bereits existiert (gleiche Funktion wie Schritt 1 Schutz) – besser: einfach `getRelationships(actor=Bob, subject=Alice)` → schon `following` → Schritt 1 als erledigt überspringen.
5. Erfolg → `follow_error` leeren; Danach kann optional ein „Erfolg"-Status in der App und – falls DM-Möglichkeit – eine kurze Erfolgs-DM an Bob („Follow-Swap mit @Alice ist jetzt aktiv") gesendet werden (Best-Effort, nicht blockierend, kein Retry nötig).

Concurrency-/Idempotenz-Regel gilt symmetrisch: vor jedem `createRecord`-Follow prüfen, ob der Follow schon besteht.

## UI (PyJSX + HTMX)

`app/ui/__init__.py`: `import pyjsx.auto_setup` MUSS als Erstes importiert werden (Codec), danach `.px`-Module.
Rendering: Komponenten sind Funktionen, die JSX zurückgeben; FastAPI gibt `HTMLResponse(str(Component(...)))` zurück. HTMX-Fragmente ebenso (Partial-Rendering ohne Layout).

Seiten:
- `/` – Landing (dunkles Bsky-Flair): Erklärung, „Mit Bluesky anmelden"-Button; nach Login Dashboard mit **zwei Bereichen**: „Von mir angeboten" (eigene, inkl. Angebots-Gesamtstatus) und „Eingegangene Angebote" (wo ich Ziel bin, mit Pending-DM-Status) + Suchfeld.
- `/profile/{handle}` – Profilkarte (Avatar, Name), Status: „Du folgst bereits" / „Du hast ein Angebot (Status-Badge)" / „Follow-Swap anbieten"-Button (HTMX `hx-post="/offers"`). Nicht eingeloggt: Button → Login-Prompt (Redirect inkl. `next=`).
- `/o/{offer_id}` – **Zentrale Angebotsseite**: Anbieter, Ziel, Status-Badge (`Ausstehend`/`Erfüllt`/`Abgebrochen`/`Abgelaufen`), Datum, DM-Status-Badge. Für das Ziel (eingeloggt): großer „Follow-Swap bestätigen"-Button; nicht eingeloggt: „Anmelden, um zu bestätigen". Bei Teilfehler: Error-Banner + „Erneut versuchen". Für den Anbieter: „Angebot zurückziehen". DM-Zustellung fehlgeschlagen: Badge + „DM erneut senden"-Button (nur Anbieter).
- Suche: `POST /profiles/search` (HTMX) → Liste der Treffer mit Profilkarten und Angebots-Status.

Layout: zentraler `<Layout>` mit Header (Logo „MutualSky", Navigation, Login-Status), HTMX-Script-Tag, minimalem CSS (eigene kleine `static/style.css`, kein Framework nötig).

## Sicherheit & Missbrauchs-Härtung

- Tokens (Refresh + DPoP-JWK) verschlüsselt in DB (Fernet, Schlüssel = `APP_SECRET`), niemals loggen; DB-Datei-Rechte 600.
- Session-Cookie: signiert, `HttpOnly`, `SameSite=Lax`.
- Confirm nur mit Session-DID == `target_did` und atomarem Status-Guard; Cancel nur mit Session-DID == `offerer_did`.
- Offer-Spam: max. 10 aktive Angebote pro Nutzer, Cooldown 30 s zwischen neuen Angeboten, max. 1 DM pro Ziel.
- Rate-Limiting auf `/auth/*`, `/offers`, `/offers/*/confirm` (einfache In-Memory-Token-Bucket pro IP).
- OAuth-Klassen aus Cookbook übernehmen inkl. SSRF-Härtung (URL-Validierung, Redirect-Limits) und Issuer-Reverifizierung nach Token-Exchange.
- Idempotenz: vor jedem Follow-`createRecord` prüfen, ob dieser Follow bereits existiert (verhindert Duplikate bei Retry).

## Risiken & Fallbacks

- **PyJSX ist jung/„not production ready"** (Autor-Einschätzung 2025). Fallback, falls Codec-Probleme auftreten: Jinja2, Layout/Struktur bleibt gleich.
- **DM-Zustellung nicht garantierbar**: Empfänger kann DMs einschränken (Declaration/`allow incoming`) oder Chat deaktiviert haben → `getConvoForMembers`/`sendMessage` schlagen fehl. App degradiert graceful (Angebot bleibt in der Inbox, Badge „DM fehlgeschlagen", Erneut-senden-Button).
- **OAuth-Refresh-Token-Rotation**: neu ausgestelltes Refresh-Token MUSS sofort gespeichert werden, sonst werden Sitzungen invalid. Im Client-Code als harter Punkt behandeln.
- **Domain-Wechsel ⇒ Re-Auth aller Nutzer** (OAuth-Constraint). Empfehlung: stabile (Sub-)Domain wählen.
- **Oxyde ist jung**: bei Migrations-/Runtime-Problemen Fallback auf `SQLAlchemy`+`aiosqlite`-Adapter hinter gleichem Model-Interface (Risiko klein, Modelle trivial).
- **Scope-Ablehnung**: Nutzer kann in der Bsky-Autorisierungsseite Scopes reduzieren (`transition:chat.bsky` abwählen). App prüft `scope` im Tokens-Response; fehlt `transition:chat.bsky` → DM nicht senden, stattdessen Badge „nur In-App". Der Follow-Swap selbst braucht nur `atproto`-Scope.
- **Follow-Baiting / nachträgliches Unfollow**: nicht im MVP adressiert; kein Auto-Unfollow, keine Mindesthaltedauer. Dokumentieren.
- **Atomarität über zwei PDS**: bestenfalls best-effort (Sequenz + Retry über Status-Guard), nicht transaktional über beide Systeme hinweg – durch Teilfehler-Handling und Idempotenz abgedeckt.

## Implementierungs-Schritte (Reihenfolge)

1. Projekt-Skeleton: `uv init`, `pyproject.toml`, `.env.example`, `config.py`, `main.py` mit Healthroute + Static-Mount; `import pyjsx.auto_setup`-Verifikation mit Mini-`.px`-Komponente → Smoke-Test.
2. Oxyde-Setup: `oxyde init` (sqlite:///mutualsky.db), `models.py` (User, Offer), Migrations anlegen/anwenden; kurzer CRUD-Smoke-Test.
3. OAuth-Modul: Cookbook-Code (identity/security/util/flow) nach `app/oauth/` portieren (async/httpx), Einheit für Token-Refresh + DPoP-Bound-Calls mit Nonce-Retry; Client-Metadaten-Datei + `generate_jwk.py` adaptiert.
4. Auth-Routen: `/auth/start`, `/auth/callback` (mit `next=`-Redirect z.B. auf `/o/<id>`), `/auth/logout`; Session-Cookie; User-Persistenz (verschlüsselte Tokens); Fehlerbehandlung (Scope-Check, Issuer-Verify).
5. Bluesky-Layer: `bluesky/client.py` (öffentliche Calls), `bluesky/actions.py` (Follow setzen mit Idempotenz-Check via `getRelationships`, Chat-Proxy-DM), `dm.py` (Message-Bau + Fehlerklassen).
6. `bluesky/swap.py`: Confirm-Orchestrierung (Lazy-Expiry, atomarer Guard, Sequenz Bob→Alice dann Alice→Bob, Teilfehler, Retry mit Idempotenz) – als reine, von HTTP entkoppelte async-Funktion für Tests.
7. UI-Grundgerüst: `layout.px`, `home.px` (Landing + Dashboard mit beiden Bereichen + Inbox), `static/style.css`, HTMX-Einbindung.
8. Profil- & Angebots-Flow: Suche (`searchActors`), Profilseite, `POST /offers` (Erzeugen + DM), öffentliche Angebotsseite `/o/{id}` mit Confirm-/Login-/Typ-/DM-Nacherreichen-Block, Cancel-Route; HTMX-Fragmente.
9. Härtung: Rate-Limits, max. aktive Angebote, Fernet-Verschlüsselung, Session-Cookie-Attribute, DB-Rechte.
10. Tests: `tests/test_swap.py` (gemockte getRelationships/createRecord: Erfolg, beide Teilfehler-Fälle, Doppel-Confirm-Guard, Expiry-Pfad, IDempotenz bei Retry), `tests/test_routes.py` (Smoke: Login-Redirect, Angebot erstellen, bestätigen, abbrechen, öffentliche Angebotsseite).
11. Deployment vorbereiten: DNS-Record `mutualsky` → Server (bei ecord.de), Dockerfile (uv, uvicorn 1 Workers, SQLite-Volume), `.env`-Vorlage (`PUBLIC_BASE_URL=https://mutualsky.ecord.de`), Caddy/nginx-TLS mit Auto-Zertifikat, `README` mit OAuth-Setup-Anleitung; **vor Go-Live** Client-Metadaten-URL mit `curl https://mutualsky.ecord.de/bsky-oauth-client.json` verifizieren (exakter Abgleich mit `client_id`), danach ersten echten OAuth-Login testen.

## Validierung

- Lokal: cookbook-kompatibler `localhost`-OAuth-Client automagisch nutzen (App erkennt `localhost` → Loopback-Client-ID, kein Metadaten-Hosting nötig) → End-to-End mit **zwei Test-Accounts**: Anna und Bob einloggen → Anna erstellt Angebot für Bob → DM-Ausgabe (dev: loggen) → Bob öffnet `/o/<id>`, bestätigt → **sofort** beide Follows auf bsky.social verifizieren (Ann a → Bob und Bob → Anna existieren). Teilfehler-Test: Bobs Confirm ohne aktives Alices-Grant simulieren → Error-Banner + Retry nach Alices Re-Login.
- Prod: `curl https://mutualsky.ecord.de/bsky-oauth-client.json` stimmt exakt mit `client_id` überein; OAuth-Login mit echtem Account (Redirect läuft auf `https://mutualsky.ecord.de/auth/callback`); Follow-Erstellung auf bsky.social sichtbar; Laufzeit-Logs frei von Tokens.
- `uv run pytest` grün; `uv run ruff check`.

## Out of Scope (MVP)

- Board/Feed „offen für Follow-Swap" mit Will-mitmachen-Status-Deklaration
- Auto-Unfollow/Verhaltenspolicing (Follow-Baiting, Mindesthaltedauer)
- Erkennung von Direkt-Follows außerhalb der App (Bob folgt Alice in der Bsky-App ohne /o/-Bestätigung → kein Tausch, gewollt)
- PWA/Notfall, i18n, Admin-Panel, PostgreSQL-CLI.