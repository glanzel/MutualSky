from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

router = APIRouter()


@router.get("/lang/{locale}")
async def set_lang(request: Request, locale: str, next: str = "/"):
    if locale not in ("de", "en"):
        locale = "de"
    request.session["locale"] = locale
    if not next.startswith("/") or next.startswith("//"):
        next = "/"
    return RedirectResponse(next, status_code=303)