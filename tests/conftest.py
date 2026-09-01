import asyncio
import os
import tempfile
from pathlib import Path

import pytest

# Configure the environment BEFORE importing the application.
_TMP = Path(tempfile.mkdtemp(prefix="mutualsky-test-"))
_TEST_KEY = __import__("authlib.jose", fromlist=["JsonWebKey"]).JsonWebKey.generate_key(
    "EC", "P-256", is_private=True
)
os.environ["DATABASE_URL"] = f"sqlite://{_TMP}/test.db"
os.environ["SESSION_SECRET"] = "test-session-secret"
os.environ["APP_SECRET"] = "test-app-secret"
os.environ["COOKIE_SECURE"] = "false"
os.environ["PUBLIC_BASE_URL"] = "https://mutualsky.test"
os.environ.setdefault("DM_ENABLED", "true")
os.environ["OAUTH_CLIENT_SECRET_JWK"] = _TEST_KEY.as_json(is_private=True)


def _run(coro):
    return asyncio.run(coro)


async def _init_db() -> None:
    from oxyde import db

    from app.config import get_settings

    await db.init(default=get_settings().database_url)
    from oxyde.db.registry import get_connection
    from oxyde.db.schema import create_tables

    await create_tables(await get_connection())


async def _close_db() -> None:
    from oxyde.db import disconnect_all

    await disconnect_all()


@pytest.fixture(scope="session", autouse=True)
def _database():
    _run(_init_db())
    yield
    _run(_close_db())


@pytest.fixture()
def settings():
    from app.config import get_settings

    return get_settings()


@pytest.fixture()
def client(_database):
    from fastapi.testclient import TestClient

    from app.main import app

    # Note: TestClient intentionally NOT used as a context manager, so the app
    # lifespan (db.init) does not run again; the fixture set the pool up.
    return TestClient(app)


@pytest.fixture()
def make_user(_database):
    async def create(did: str, handle: str, **kwargs) -> None:
        from app.models import User

        existing = await User.objects.get_or_none(did=did)
        if existing is not None:
            for key, value in kwargs.items():
                setattr(existing, key, value)
            await existing.save()
            return existing
        user = User(did=did, handle=handle, pds_url="https://test.pds", authserver_iss="https://test.pds", **kwargs)
        if not user.scope:
            user.scope = "atproto transition:generic transition:chat.bsky"
        await user.save()
        return user

    return create