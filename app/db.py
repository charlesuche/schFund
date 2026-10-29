"""Database connection helper."""

import os

import psycopg
from dotenv import load_dotenv

# Read .env once when this module is imported. Real environment variables win
# over .env, so a server or CI can set DATABASE_URL without a file.
load_dotenv()


def get_database_url(variable: str = "DATABASE_URL") -> str:
    url = os.environ.get(variable)
    if not url:
        raise RuntimeError(f"{variable} is not set. Copy .env.example to .env and fill it in.")
    return url


def get_connection(url: str | None = None) -> psycopg.Connection:
    """Open a new connection. Pass url to override DATABASE_URL (e.g. in tests)."""
    if url is None:
        url = get_database_url()
    return psycopg.connect(url)
