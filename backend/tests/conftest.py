import json
import os
from pathlib import Path

import pikepdf
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


def _generate_fixture_pdf(path: Path, title: str = "", author: str = "", subject: str = "", keywords: str = "") -> None:
    """Generate a minimal valid PDF with metadata using pikepdf."""
    pdf = pikepdf.Pdf.new()
    pdf.add_blank_page(page_size=(612, 792))  # Letter size
    with pdf.open_metadata(set_pikepdf_as_editor=False) as xmp:
        if title:
            xmp["dc:title"] = title
        if author:
            xmp["dc:creator"] = author
        if subject:
            xmp["dc:subject"] = subject
        if keywords:
            xmp["pdf:Keywords"] = keywords
    pdf.save(path)


@pytest.fixture(scope="session", autouse=True)
def generate_fixtures():
    """Generate proper fixture PDFs with metadata before any tests run."""
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    subfolder = FIXTURES_DIR / "subfolder"
    subfolder.mkdir(parents=True, exist_ok=True)

    _generate_fixture_pdf(
        FIXTURES_DIR / "sample.pdf",
        title="Sonata No. 14",
        author="Ludwig van Beethoven",
        subject="Classical",
        keywords="piano, sonata, moonlight",
    )
    _generate_fixture_pdf(
        subfolder / "nested.pdf",
        title="Prelude in C Major",
        author="Johann Sebastian Bach",
        subject="Baroque",
        keywords="keyboard, prelude",
    )


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
