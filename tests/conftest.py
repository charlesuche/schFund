"""Shared test setup."""

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# scripts/ is not a package; put it (and the repo root, for app/) on the path
# so tests can import validate and load_records the same way the scripts do.
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(scope="session")
def test_db_url() -> str:
    """URL of the separate test database. Tests using it drop and recreate tables."""
    from app import db  # noqa: F401  (importing app.db reads .env)

    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set")
    if url == os.environ.get("DATABASE_URL"):
        pytest.fail("TEST_DATABASE_URL must not be the same as DATABASE_URL")
    return url


@pytest.fixture(scope="module")
def loaded_db(test_db_url: str) -> str:
    """Test database freshly loaded with data/records/. Returns its URL."""
    import load_records
    from app.db import get_connection

    with get_connection(test_db_url) as conn:
        load_records.load_records(conn, reset=True)
    return test_db_url
