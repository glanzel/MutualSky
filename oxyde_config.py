"""Oxyde ORM configuration."""

from pathlib import Path

MODELS = ["app.models"]
DIALECT = "sqlite"
MIGRATIONS_DIR = "migrations"
DATABASES = {
    "default": f"sqlite://{Path(__file__).resolve().parent}/mutualsky.db",
}