"""Minimal German/English i18n for the UI.

The current locale is carried in a contextvar (set per-request by middleware).
``t()`` looks up a phrase (German source text as key), so templates stay
readable while the translations live in one dict.
"""

import contextvars

_LOCALE: contextvars.ContextVar[str] = contextvars.ContextVar("site_locale", default="de")

SUPPORTED = ("de", "en")


def set_locale(locale: str) -> None:
    _LOCALE.set(locale if locale in SUPPORTED else "de")


def get_locale() -> str:
    return _LOCALE.get()


STRINGS: dict[str, dict[str, str]] = {
    # nav / global
    "Abmelden": {"de": "Abmelden", "en": "Log out"},
    "Mit Bluesky anmelden": {"de": "Mit Bluesky anmelden", "en": "Sign in with Bluesky"},
    "Archiv": {"de": "Archiv", "en": "Archive"},
    "Freundschaft auf dem Atmosphere – MutualSky": {
        "de": "Freundschaft auf dem Atmosphere – MutualSky",
        "en": "Friendship on the Atmosphere – MutualSky",
    },
    "Open Source auf GitHub ansehen": {"de": "Open Source auf GitHub ansehen", "en": "View on GitHub – open source"},

    # landing
    "Freundschaft auf dem Atmosphere": {"de": "Freundschaft auf dem Atmosphere", "en": "Friendship on the Atmosphere"},
    "Folge gezielt neuen Accounts – und du bekommst einen Follow zurück, wenn du einem zurückfolgst. Tausche Follows mit Bluesky, fair und automatisch.": {
        "de": "Folge gezielt neuen Accounts – und du bekommst einen Follow zurück, wenn du einem zurückfolgst. Tausche Follows mit Bluesky, fair und automatisch.",
        "en": "Follow new accounts deliberately – and get a follow back when you follow them back. Swap follows on Bluesky, fair and automatic.",
    },
    "So funktioniert es": {"de": "So funktioniert es", "en": "How it works"},
    "Anmelden": {"de": "Anmelden", "en": "Sign in"},
    "Auswählen": {"de": "Auswählen", "en": "Pick"},
    "Anbieten": {"de": "Anbieten", "en": "Offer"},
    "Bestätigen": {"de": "Bestätigen", "en": "Confirm"},
    "mit deinem Bluesky-Account (OAuth, du behältst die Kontrolle).": {
        "de": "mit deinem Bluesky-Account (OAuth, du behältst die Kontrolle).",
        "en": "with your Bluesky account (OAuth, you stay in control).",
    },
    "suche einen Account, dem du folgen möchtest.": {
        "de": "suche einen Account, dem du folgen möchtest.",
        "en": "search for an account you want to follow.",
    },
    "sende ein Follow-Swap-Angebot. Die Person bekommt eine Nachricht.": {
        "de": "sende ein Follow-Swap-Angebot. Die Person bekommt eine Nachricht.",
        "en": "send a follow-swap offer. The person gets a message.",
    },
    "folgt sie dir zurück und bestätigt den Tausch, werden beide Follows sofort gesetzt.": {
        "de": "folgt sie dir zurück und bestätigt den Tausch, werden beide Follows sofort gesetzt.",
        "en": "if they follow you back and confirm, both follows are set immediately.",
    },

    # login page
    "Gib deinen Bluesky-Handle ein – du wirst zur Bluesky-Anmeldeseite weitergeleitet und bestimmst dort selbst, welche Rechte du erteilst.": {
        "de": "Gib deinen Bluesky-Handle ein – du wirst zur Bluesky-Anmeldeseite weitergeleitet und bestimmst dort selbst, welche Rechte du erteilst.",
        "en": "Enter your Bluesky handle – you'll be redirected to Bluesky's sign-in page and decide there what access to grant.",
    },
    "Weiter zu Bluesky": {"de": "Weiter zu Bluesky", "en": "Continue to Bluesky"},
    "z. B. anna.bsky.social": {"de": "z. B. anna.bsky.social", "en": "e.g. anna.bsky.social"},

    # dashboard
    "Hallo, @{handle}": {"de": "Hallo, @{handle}", "en": "Hi, @{handle}"},
    "Von mir angeboten": {"de": "Von mir angeboten", "en": "Offered by me"},
    "Eingegangene Angebote": {"de": "Eingegangene Angebote", "en": "Incoming offers"},
    "Noch keine Angebote – suche unten einen Account.": {
        "de": "Noch keine Angebote – suche unten einen Account.",
        "en": "No offers yet – search for an account below.",
    },
    "Noch keine Angebote an dich.": {"de": "Noch keine Angebote an dich.", "en": "No offers for you yet."},
    "Account suchen": {"de": "Account suchen", "en": "Search accounts"},

    # archive
    "Abgeschlossene Angebote von mir": {"de": "Abgeschlossene Angebote von mir", "en": "Completed offers by me"},
    "Abgeschlossene Angebote an mich": {"de": "Abgeschlossene Angebote an mich", "en": "Completed offers for me"},
    "Noch keine abgeschlossenen Angebote.": {"de": "Noch keine abgeschlossenen Angebote.", "en": "No completed offers yet."},

    # search tabs & forms
    "Accounts": {"de": "Accounts", "en": "Accounts"},
    "Post/Account": {"de": "Post/Account", "en": "Post/Account"},
    "Suche einen Bluesky-Account… (z. B. anna.bsky.social)": {
        "de": "Suche einen Bluesky-Account… (z. B. anna.bsky.social)",
        "en": "Search a Bluesky account… (e.g. anna.bsky.social)",
    },
    "max. Follower": {"de": "max. Follower", "en": "max. followers"},
    "Suchen": {"de": "Suchen", "en": "Search"},
    "Suche Posts… (z. B. Klima)": {"de": "Suche Posts… (z. B. Klima)", "en": "Search posts… (e.g. climate)"},
    "max. Follower-Autor": {"de": "max. Follower-Autor", "en": "max. author followers"},
    "Post/Account suchen": {"de": "Post/Account suchen", "en": "Search posts & accounts"},
    "Weitere Ergebnisse laden": {"de": "Weitere Ergebnisse laden", "en": "Load more results"},
    "Ende der Ergebnisse.": {"de": "Ende der Ergebnisse.", "en": "End of results."},
    "Keine weiteren Ergebnisse.": {"de": "Keine weiteren Ergebnisse.", "en": "No more results."},
    "Keine Ergebnisse.": {"de": "Keine Ergebnisse.", "en": "No results."},
    "Keine Accounts mit höchstens {max_followers} Followern gefunden.": {
        "de": "Keine Accounts mit höchstens {max_followers} Followern gefunden.",
        "en": "No accounts with at most {max_followers} followers found.",
    },
    "Keine Posts von Autoren mit höchstens {max_followers} Followern gefunden.": {
        "de": "Keine Posts von Autoren mit höchstens {max_followers} Followern gefunden.",
        "en": "No posts from authors with at most {max_followers} followers found.",
    },
    "Die Post-Suche braucht eine Anmeldung.": {
        "de": "Die Post-Suche braucht eine Anmeldung.",
        "en": "The post search requires signing in.",
    },

    # actor / post cards
    "Follower": {"de": "Follower", "en": "followers"},
    "folgt": {"de": "folgt", "en": "follows"},
    "Beiträge": {"de": "Beiträge", "en": "posts"},
    "zuletzt aktiv: {when}": {"de": "zuletzt aktiv: {when}", "en": "last active: {when}"},
    "Post vom {when}": {"de": "Post vom {when}", "en": "posted on {when}"},
    "Profil": {"de": "Profil", "en": "Profile"},

    # offer rows
    "Folge ich an:": {"de": "Folge ich an:", "en": "I follow:"},
    "Bietet mir an:": {"de": "Bietet mir an:", "en": "Offers to me:"},
    "Ansehen": {"de": "Ansehen", "en": "View"},

    # offer page
    "Angebot – MutualSky": {"de": "Angebot – MutualSky", "en": "Offer – MutualSky"},
    "DM konnte nicht zugestellt werden.": {
        "de": "DM konnte nicht zugestellt werden.",
        "en": "The notification DM could not be delivered.",
    },
    "Benachrichtigung per Bluesky-DM gesendet.": {
        "de": "Benachrichtigung per Bluesky-DM gesendet.",
        "en": "Notification sent via Bluesky DM.",
    },
    "{offerer} möchte {target} folgen, wenn {target} zurückfolgt.": {
        "de": "{offerer} möchte {target} folgen, wenn {target} zurückfolgt.",
        "en": "{offerer} wants to follow {target} if {target} follows back.",
    },
    "Nicht gefunden – MutualSky": {"de": "Nicht gefunden – MutualSky", "en": "Not found – MutualSky"},
    "Angebot nicht gefunden": {"de": "Angebot nicht gefunden", "en": "Offer not found"},
    "Angebot nicht gefunden.": {"de": "Angebot nicht gefunden.", "en": "Offer not found."},
    "Dieses Follow-Swap-Angebot existiert nicht (mehr).": {
        "de": "Dieses Follow-Swap-Angebot existiert nicht (mehr).",
        "en": "This follow-swap offer no longer exists.",
    },
    "Zur Startseite": {"de": "Zur Startseite", "en": "Back to home"},

    # profile page
    "Profil auf Bluesky ansehen": {"de": "Profil auf Bluesky ansehen", "en": "View profile on Bluesky"},
    "Account nicht gefunden": {"de": "Account nicht gefunden", "en": "Account not found"},
    "Zurück zur Suche": {"de": "Zurück zur Suche", "en": "Back to search"},
    "@{handle} konnte nicht aufgelöst werden.": {"de": "@{handle} konnte nicht aufgelöst werden.", "en": "@{handle} could not be resolved."},

    # offer panels / actions
    "Melde dich mit deinen Bluesky-Account an, um dieses Angebot zu bestätigen.": {
        "de": "Melde dich mit deinen Bluesky-Account an, um dieses Angebot zu bestätigen.",
        "en": "Sign in with your Bluesky account to confirm this offer.",
    },
    "Sobald du bestätigst, wirst du @{offerer} folgen – dein Follow wird im selben Schritt erwidert.": {
        "de": "Sobald du bestätigst, wirst du @{offerer} folgen – dein Follow wird im selben Schritt erwidert.",
        "en": "When you confirm, you'll follow @{offerer} – your follow is returned in the same step.",
    },
    "Follow-Swap bestätigen": {"de": "Follow-Swap bestätigen", "en": "Confirm follow swap"},
    "Zum Dashboard": {"de": "Zum Dashboard", "en": "Back to dashboard"},
    "Du wartest darauf, dass die Person das Angebot bestätigt.": {
        "de": "Du wartest darauf, dass die Person das Angebot bestätigt.",
        "en": "You're waiting for the other person to confirm the offer.",
    },
    "Angebot zurückziehen": {"de": "Angebot zurückziehen", "en": "Withdraw offer"},
    "DM erneut senden": {"de": "DM erneut senden", "en": "Resend DM"},
    "Öffentlich als Antwort posten": {"de": "Öffentlich als Antwort posten", "en": "Post publicly as a reply"},
    "Follow-Swap anbieten": {"de": "Follow-Swap anbieten", "en": "Offer follow swap"},
    "Die Person wird per Bluesky-DM benachrichtigt. Du folgst erst, wenn sie zustimmt – dann tauscht ihr sofort.": {
        "de": "Die Person wird per Bluesky-DM benachrichtigt. Du folgst erst, wenn sie zustimmt – dann tauscht ihr sofort.",
        "en": "The person is notified via Bluesky DM. You follow only after they agree – then you swap immediately.",
    },
    "Angebot erstellt und per DM gesendet.": {"de": "Angebot erstellt und per DM gesendet.", "en": "Offer created and DM sent."},
    "Angebot erstellt, aber die DM-Benachrichtigung fehlgeschlagen.": {
        "de": "Angebot erstellt, aber die DM-Benachrichtigung fehlgeschlagen.",
        "en": "Offer created, but the DM notification failed.",
    },
    "Angebot erstellt.": {"de": "Angebot erstellt.", "en": "Offer created."},
    "Angebot ansehen": {"de": "Angebot ansehen", "en": "View offer"},
    "Nur die angefragte Person kann diesen Tausch bestätigen.": {
        "de": "Nur die angefragte Person kann diesen Tausch bestätigen.",
        "en": "Only the requested person can confirm this swap.",
    },
    "Erfüllt – ihr folgt euch jetzt gegenseitig.": {"de": "Erfüllt – ihr folgt euch jetzt gegenseitig.", "en": "Done – you now follow each other."},
    "Dieses Angebot wurde zurückgezogen.": {"de": "Dieses Angebot wurde zurückgezogen.", "en": "This offer was withdrawn."},
    "Dieses Angebot ist abgelaufen.": {"de": "Dieses Angebot ist abgelaufen.", "en": "This offer has expired."},
    "Angebot zurückgezogen.": {"de": "Angebot zurückgezogen.", "en": "Offer withdrawn."},
    "Tausch erfüllt – ihr folgt euch jetzt gegenseitig.": {
        "de": "Tausch erfüllt – ihr folgt euch jetzt gegenseitig.",
        "en": "Swap fulfilled – you now follow each other.",
    },
    "Du bist nicht die angefragte Person.": {
        "de": "Du bist nicht die angefragte Person.",
        "en": "You are not the person this offer was meant for.",
    },
    "Angebot bereits erfüllt.": {"de": "Angebot bereits erfüllt.", "en": "Offer already fulfilled."},
    "Nur der Anbieter kann zurückziehen.": {"de": "Nur der Anbieter kann zurückziehen.", "en": "Only the offerer can withdraw the offer."},
    "Nur der Anbieter kann öffentlich antworten.": {
        "de": "Nur der Anbieter kann öffentlich antworten.",
        "en": "Only the offerer can post the public reply.",
    },
    "Nur der Anbieter kann eine Nachricht senden.": {
        "de": "Nur der Anbieter kann eine Nachricht senden.",
        "en": "Only the offerer can send a message.",
    },
    "Öffentliche Antwort auf den neuesten Post gepostet.": {
        "de": "Öffentliche Antwort auf den neuesten Post gepostet.",
        "en": "Public reply posted to their latest post.",
    },
    "Antwort fehlgeschlagen: {fehler}": {"de": "Antwort fehlgeschlagen: {fehler}", "en": "Reply failed: {fehler}"},
    "Tausch fehlgeschlagen – bitte erneut versuchen.": {
        "de": "Tausch fehlgeschlagen – bitte erneut versuchen.",
        "en": "Swap failed – please try again.",
    },
    "Dein Account ist bei uns nicht (mehr) angemeldet.": {
        "de": "Dein Account ist bei uns nicht (mehr) angemeldet.",
        "en": "Your account is no longer signed in here.",
    },
    "Der Anbieter hat seine Anmeldung entfernt – der Tausch kann nicht abgeschlossen werden.": {
        "de": "Der Anbieter hat seine Anmeldung entfernt – der Tausch kann nicht abgeschlossen werden.",
        "en": "The offerer removed their sign-in – the swap can't be completed.",
    },
    "Ungültiger Handle oder DID.": {"de": "Ungültiger Handle oder DID.", "en": "Invalid handle or DID."},
    "Account konnte nicht aufgelöst werden: {fehler}": {
        "de": "Account konnte nicht aufgelöst werden: {fehler}",
        "en": "Could not resolve account: {fehler}",
    },
    "Suche fehlgeschlagen: {fehler}": {"de": "Suche fehlgeschlagen: {fehler}", "en": "Search failed: {fehler}"},
    "Post-Suche fehlgeschlagen: {fehler}": {"de": "Post-Suche fehlgeschlagen: {fehler}", "en": "Post search failed: {fehler}"},
    "Such-Sitzung abgelaufen.": {"de": "Such-Sitzung abgelaufen.", "en": "Search session expired."},
    "Das ist dein eigenes Profil.": {"de": "Das ist dein eigenes Profil.", "en": "That's your own profile."},
    "Dein Angebot ist ausstehend – du folgst erst nach der Bestätigung.": {
        "de": "Dein Angebot ist ausstehend – du folgst erst nach der Bestätigung.",
        "en": "Your offer is pending – you follow only after confirmation.",
    },
    "Diese Person hat dir einen Follow-Swap angeboten.": {
        "de": "Diese Person hat dir einen Follow-Swap angeboten.",
        "en": "This person has offered you a follow swap.",
    },
    "Du folgst diesem Account bereits.": {"de": "Du folgst diesem Account bereits.", "en": "You already follow this account."},
    "Erneut anmelden": {"de": "Erneut anmelden", "en": "Sign in again"},
    "Identität konnte nicht aufgelöst werden: {fehler}": {
        "de": "Identität konnte nicht aufgelöst werden: {fehler}",
        "en": "Identity could not be resolved: {fehler}",
    },
    "Anmeldung fehlgeschlagen: {fehler}": {
        "de": "Anmeldung fehlgeschlagen: {fehler}",
        "en": "Sign-in failed: {fehler}",
    },
    "Angemeldeter Account entspricht nicht der Anfrage.": {
        "de": "Angemeldeter Account entspricht nicht der Anfrage.",
        "en": "The signed-in account doesn't match the request.",
    },
    "Erforderliche atproto-Berechtigung fehlt.": {
        "de": "Erforderliche atproto-Berechtigung fehlt.",
        "en": "Required atproto permission is missing.",
    },
}


def t(text: str, **fmt) -> str:
    """Translate ``text`` (German source) into the current locale's string."""
    entry = STRINGS.get(text)
    out = entry.get(get_locale()) if entry else None
    if out is None:
        out = text
    if fmt:
        try:
            out = out.format(**fmt)
        except (KeyError, IndexError):
            pass
    return out