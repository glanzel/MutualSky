from fastapi import Request

from .models import User


async def current_user(request: Request) -> User | None:
    did = request.session.get("user_did")
    if not did:
        return None
    return await User.objects.get_or_none(did=did)