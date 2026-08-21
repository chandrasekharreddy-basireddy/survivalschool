from __future__ import annotations

import os
import re
import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://survivalschool:survivalschool@localhost:5432/survivalschool_test")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql+psycopg2://survivalschool:survivalschool@localhost:5432/survivalschool_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ.setdefault("JWT_SECRET", "test-secret-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
os.environ.setdefault("EMAIL_BACKEND", "console")
os.environ.setdefault("AI_PROVIDER", "mock")
# The suite legitimately calls these endpoints far more often, from the same
# "IP", than any real client would inside one window — raise the ceiling
# rather than disable enforcement, so a real regression in the limiter would
# still fail test_rate_limiting.py.
os.environ.setdefault("RATE_LIMIT_REGISTER_PER_HOUR", "1000")
os.environ.setdefault("RATE_LIMIT_LOGIN_PER_5MIN", "1000")
os.environ.setdefault("RATE_LIMIT_RESEND_VERIFY_PER_HOUR", "1000")
os.environ.setdefault("RATE_LIMIT_FORGOT_PASSWORD_PER_HOUR", "1000")

import app.models  # noqa: E402, F401
import app.services.email_service as email_service  # noqa: E402
from app.core.logging import configure_logging  # noqa: E402
from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed_rbac  # noqa: E402

# The test client's ASGITransport never fires app.main's lifespan, so
# configure_logging() (JSON structlog output) never runs and structlog falls
# back to its default dev ConsoleRenderer — which crashes on this
# rich/Python combination the instant a genuinely unhandled exception needs
# to be logged, masking the real traceback behind a rich internals crash
# instead of the actual bug. Configure it explicitly so a real bug during
# tests fails loudly and readably instead of double-faulting.
configure_logging()

VALID_PASSWORD = "Sup3r$ecretPass1"

#: captured (to, subject, template, context) tuples for every "sent" email —
#: lets tests grab a verification/reset token without ever touching the DB
#: hash directly, exactly like a real user reading their inbox would.
_sent_emails: list[dict] = []


async def _capturing_send_email(to, subject, template, **context):
    _sent_emails.append({"to": to, "subject": subject, "template": template, "context": context})
    return True


email_service.send_email = _capturing_send_email
# Also patch the reference imported into modules that did `from ... import send_email`.
import app.api.v1.auth as _auth_mod  # noqa: E402

_auth_mod.send_email = _capturing_send_email


def unique_email() -> str:
    return f"test_{uuid.uuid4().hex[:10]}@example.com"


def unique_username() -> str:
    return f"test_{uuid.uuid4().hex[:12]}"


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _setup_database():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await seed_rbac()

    # Rate limiting is real (Redis-backed) and must stay real in tests — a
    # dedicated test suite is exactly where you want to catch a regression in
    # the limiter itself. We just make sure each test session starts from a
    # clean counter state rather than disabling enforcement.
    from app.redis_client import get_redis
    await get_redis().flushdb()

    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as ac:
        yield ac


def _last_token_for(email: str, template: str) -> str:
    for entry in reversed(_sent_emails):
        if entry["to"] == email and entry["template"] == template:
            url = entry["context"].get("verify_url") or entry["context"].get("reset_url")
            match = re.search(r"token=([^&\s]+)", url)
            assert match, f"no token found in {url}"
            return match.group(1)
    raise AssertionError(f"no {template} email captured for {email}")


async def register_and_verify(
    client, email: str | None = None, password: str = VALID_PASSWORD, full_name: str = "Test User",
    username: str | None = None,
) -> str:
    email = email or unique_email()
    username = username or unique_username()
    resp = await client.post("/auth/register", json={"email": email, "password": password, "full_name": full_name, "username": username})
    assert resp.status_code == 201, resp.text

    token = _last_token_for(email, "verify_email")
    verify_resp = await client.post("/auth/verify-email", json={"token": token})
    assert verify_resp.status_code == 200, verify_resp.text
    return email


async def login(client, email: str, password: str = VALID_PASSWORD) -> dict:
    resp = await client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def auth_headers(client, email: str | None = None, password: str = VALID_PASSWORD) -> tuple[str, dict]:
    email = await register_and_verify(client, email, password)
    tokens = await login(client, email, password)
    return email, {"Authorization": f"Bearer {tokens['access_token']}"}


async def grant_role(email: str, role_name: str) -> None:
    """Test-only helper: promote a user directly via the DB (equivalent to an
    admin calling POST /users/{id}/roles/{role}, but without needing an admin
    session bootstrapped in every test)."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.database import AsyncSessionLocal
    from app.models.user import Role, User

    async with AsyncSessionLocal() as db:
        user = (await db.execute(
            select(User).where(User.email == email.lower()).options(selectinload(User.roles))
        )).scalar_one()
        role = (await db.execute(select(Role).where(Role.name == role_name))).scalar_one()
        if role not in user.roles:
            user.roles.append(role)
        await db.commit()
