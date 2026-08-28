"""Handle/DID/PDS resolution with bi-directional handle verification.

Ported to async/httpx from the official bluesky-social/cookbook
`python-oauth-web-app` atproto_identity.py.
"""

import re

import dns.resolver

from .atproto_security import safe_get

HANDLE_REGEX = r"^([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$"
DID_REGEX = r"^did:[a-z]+:[a-zA-Z0-9._:%-]*[a-zA-Z0-9._-]$"


def is_valid_handle(handle: str) -> bool:
    return re.match(HANDLE_REGEX, handle) is not None


def is_valid_did(did: str) -> bool:
    return re.match(DID_REGEX, did) is not None


def handle_from_doc(doc: dict) -> str | None:
    for aka in doc.get("alsoKnownAs", []):
        if aka.startswith("at://"):
            handle = aka[5:]
            if is_valid_handle(handle):
                return handle
    return None


async def resolve_handle(handle: str) -> str | None:
    # 1) DNS TXT record
    try:
        answers = dns.resolver.resolve(f"_atproto.{handle}", "TXT")
        for record in answers:
            val = record.to_text().replace('"', "")
            if val.startswith("did="):
                val = val[4:]
                if is_valid_did(val):
                    return val
    except Exception:
        pass

    # 2) HTTP well-known (SSRF-mitigated)
    try:
        resp = await safe_get(f"https://{handle}/.well-known/atproto-did")
    except Exception:
        return None
    if resp.status_code != 200:
        return None
    did = resp.text.split()[0]
    return did if is_valid_did(did) else None


async def resolve_did(did: str) -> dict | None:
    if did.startswith("did:plc:"):
        try:
            resp = await safe_get(f"https://plc.directory/{did}")
        except Exception:
            return None
        if resp.status_code != 200:
            return None
        return resp.json()

    if did.startswith("did:web:"):
        domain = did[8:]
        assert is_valid_handle(domain), "invalid did:web domain"
        try:
            resp = await safe_get(f"https://{domain}/.well-known/did.json")
        except Exception:
            return None
        if resp.status_code != 200:
            return None
        return resp.json()

    raise ValueError("unsupported DID type")


async def resolve_identity(atid: str) -> tuple[str, str, dict]:
    if is_valid_handle(atid):
        handle = atid
        did = await resolve_handle(handle)
        if not did:
            raise RuntimeError(f"Failed to resolve handle: {handle}")
        doc = await resolve_did(did)
        if not doc:
            raise RuntimeError(f"Failed to resolve DID: {did}")
        doc_handle = handle_from_doc(doc)
        if not doc_handle or doc_handle != handle:
            raise RuntimeError(f"Handle did not match DID: {handle}")
        return did, handle, doc

    if is_valid_did(atid):
        did = atid
        doc = await resolve_did(did)
        if not doc:
            raise RuntimeError(f"Failed to resolve DID: {did}")
        handle = handle_from_doc(doc)
        if not handle:
            raise RuntimeError(f"Handle did not match DID: {handle}")
        if await resolve_handle(handle) != did:
            raise RuntimeError(f"Handle did not match DID: {handle}")
        return did, handle, doc

    raise RuntimeError(f"identifier not a handle or DID: {atid}")


def pds_endpoint(doc: dict) -> str:
    for svc in doc.get("service", []):
        if svc.get("id") == "#atproto_pds":
            return svc["serviceEndpoint"]
    raise RuntimeError("PDS endpoint not found in DID document")