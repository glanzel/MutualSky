from datetime import UTC, datetime

from oxyde import Field, Model

STATUS_PENDING = "pending"
STATUS_PROCESSING = "processing"
STATUS_COMPLETED = "completed"
STATUS_CANCELLED = "cancelled"
STATUS_EXPIRED = "expired"

DM_NONE = "none"
DM_SENT = "sent"
DM_FAILED = "failed"


def utcnow() -> datetime:
    # Naive UTC: SQLite stores datetimes as TEXT and reads them back naive, so
    # we keep every timestamp naive-UTC to stay comparable in both directions.
    return datetime.now(UTC).replace(tzinfo=None)


class User(Model):
    id: int | None = Field(default=None, db_pk=True)
    did: str = Field(db_unique=True)
    handle: str = Field(db_index=True)
    display_name: str | None = Field(default=None)
    avatar_url: str | None = Field(default=None)
    pds_url: str = ""
    authserver_iss: str = ""
    client_id: str = ""
    scope: str = ""
    access_token: str | None = Field(default=None)
    refresh_token: str = ""
    dpop_authserver_nonce: str = ""
    dpop_pds_nonce: str = ""
    dpop_private_jwk: str = ""
    created_at: datetime | None = Field(default=None, db_default="CURRENT_TIMESTAMP")
    updated_at: datetime | None = Field(default=None, db_default="CURRENT_TIMESTAMP")

    class Meta:
        is_table = True
        table_name = "users"


class Offer(Model):
    id: int | None = Field(default=None, db_pk=True)
    offerer_did: str = Field(db_index=True)
    offerer_handle: str = ""
    target_did: str = Field(db_index=True)
    target_handle: str = ""
    status: str = Field(default=STATUS_PENDING)
    dm_status: str = Field(default=DM_NONE)
    dm_error: str | None = Field(default=None)
    follow_error: str | None = Field(default=None)
    expires_at: datetime | None = Field(default=None)
    created_at: datetime | None = Field(default=None, db_default="CURRENT_TIMESTAMP")
    completed_at: datetime | None = Field(default=None)
    cancelled_at: datetime | None = Field(default=None)

    class Meta:
        is_table = True
        table_name = "offers"