from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    public_base_url: str = "https://mutualsky.ecord.de"
    database_url: str = f"sqlite://{PROJECT_ROOT}/mutualsky.db"
    session_secret: str = "dev-session-secret-change-me"
    app_secret: str = ""

    oauth_client_secret_jwk: str = ""
    oauth_scope: str = "atproto transition:generic transition:chat.bsky"

    offer_ttl_days: int = 14
    max_active_offers: int = 10
    offer_cooldown_seconds: int = 30
    dm_enabled: bool = True

    cookie_secure: bool = True

    @property
    def encryption_secret(self) -> str:
        return self.app_secret or self.session_secret

    @property
    def client_metadata_path(self) -> str:
        return "bsky-oauth-client.json"

    @property
    def client_id_url(self) -> str:
        return f"{self.public_base_url}/{self.client_metadata_path}"

    @property
    def redirect_uri(self) -> str:
        return f"{self.public_base_url}/auth/callback"


@lru_cache
def get_settings() -> Settings:
    return Settings()