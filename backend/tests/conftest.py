import json
import os
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from itsdangerous import URLSafeTimedSerializer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Override settings before importing the app
os.environ["SECRET_KEY"] = "test-secret"
os.environ["ENABLE_LOCAL_BACKEND"] = "true"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"

from sheeetz.main import app  # noqa: E402
from sheeetz.models import Base, LibraryFolder, User  # noqa: E402
from sheeetz.db import get_db  # noqa: E402

FIXTURES_DIR = Path(__file__).parent / "fixtures"
TEST_SECRET = "test-secret"
TEST_EMAIL = "dirkraft.agents@gmail.com"


@pytest.fixture(scope="session", autouse=True)
def generate_fixtures():
    """Generate proper fixture PDFs with metadata before any tests run."""
    from .generate_fixtures import generate
    generate(FIXTURES_DIR)


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def seeded_db(db: AsyncSession):
    """DB with test user and a local library folder pointing at fixtures."""
    user = User(
        id=2,
        google_id="test-google-id",
        email=TEST_EMAIL,
        name="Test Agent",
    )
    db.add(user)

    folder = LibraryFolder(
        user_id=2,
        backend_type="local",
        backend_folder_id=str(FIXTURES_DIR),
        folder_name="fixtures",
        folder_path=str(FIXTURES_DIR),
    )
    db.add(folder)
    await db.commit()
    await db.refresh(folder)
    return db


def _auth_cookies() -> dict:
    serializer = URLSafeTimedSerializer(TEST_SECRET)
    token = serializer.dumps({"uid": 2})
    return {"session_token": token}


@pytest_asyncio.fixture
async def client(seeded_db: AsyncSession):
    """HTTP client with test DB injected and auth cookies set."""
    async def override_get_db():
        yield seeded_db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", cookies=_auth_cookies()
    ) as c:
        yield c
    app.dependency_overrides.clear()


def has_drive_secrets() -> bool:
    return bool(
        os.environ.get("GOOGLE_CLIENT_ID")
        and os.environ.get("GOOGLE_CLIENT_SECRET")
        and os.environ.get("TEST_DRIVE_TOKEN_JSON")
    )


skip_without_drive = pytest.mark.skipif(
    not has_drive_secrets(),
    reason="Drive secrets not available",
)


@pytest_asyncio.fixture
async def unauth_client(seeded_db: AsyncSession):
    """HTTP client without auth cookies."""
    async def override_get_db():
        yield seeded_db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def drive_db(db: AsyncSession):
    """DB with test user seeded with real Drive tokens."""
    token_json = os.environ.get("TEST_DRIVE_TOKEN_JSON", "{}")
    user = User(
        id=2,
        google_id="test-google-id",
        email=TEST_EMAIL,
        name="Test Agent",
        drive_token_json=token_json,
    )
    db.add(user)
    await db.commit()
    return db


@pytest_asyncio.fixture
async def drive_client(drive_db: AsyncSession):
    """HTTP client with Drive-capable test user."""
    async def override_get_db():
        yield drive_db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", cookies=_auth_cookies()
    ) as c:
        yield c
    app.dependency_overrides.clear()
