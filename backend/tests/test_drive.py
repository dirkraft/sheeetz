"""Drive integration tests.

Uses respx to mock Google OAuth and Drive API responses so tests run
without real credentials.
"""

from pathlib import Path

import respx
from httpx import Response

from sheeetz.storage.drive_api import DRIVE_API, GOOGLE_TOKEN_URL

FIXTURES_DIR = Path(__file__).parent / "fixtures"
FAKE_FOLDER_ID = "fake-folder-123"
FAKE_FILE_ID = "fake-file-456"
FAKE_SUBFOLDER_ID = "fake-subfolder-789"
FAKE_NESTED_FILE_ID = "fake-file-nested-001"


def _fixture_pdf_bytes() -> bytes:
    return (FIXTURES_DIR / "sample.pdf").read_bytes()


def _setup_mocks(mock: respx.MockRouter) -> None:
    """Set up common mocks for token refresh and folder path resolution."""
    # Token refresh — may be called multiple times
    mock.post(GOOGLE_TOKEN_URL).mock(
        return_value=Response(200, json={
            "access_token": "fake-access-token",
            "expires_in": 3600,
            "token_type": "Bearer",
        })
    )

    # build_folder_path walks parents: folder -> root (no parents = stop)
    mock.get(
        f"{DRIVE_API}/files/{FAKE_FOLDER_ID}",
        params={"fields": "id,name,parents"},
    ).mock(
        return_value=Response(200, json={
            "id": FAKE_FOLDER_ID,
            "name": "sheet music",
            "parents": ["root-id"],
        })
    )
    mock.get(
        f"{DRIVE_API}/files/root-id",
        params={"fields": "id,name,parents"},
    ).mock(
        return_value=Response(200, json={
            "id": "root-id",
            "name": "My Drive",
        })
    )


def _mock_list_pdfs(mock: respx.MockRouter, folder_id: str, files: list[dict]) -> None:
    mock.get(
        url=f"{DRIVE_API}/files",
    ).mock(side_effect=_make_list_side_effect(folder_id, "application/pdf", files))


def _make_list_side_effect(folder_id: str, mime_type: str, files: list[dict]):
    """Create a side effect that matches the query param for folder listings."""
    expected_q_fragment = f"'{folder_id}' in parents and mimeType = '{mime_type}'"

    def side_effect(request):
        q = str(request.url.params.get("q", ""))
        if expected_q_fragment in q:
            return Response(200, json={"files": files})
        return None  # Let other handlers try
    return side_effect


@respx.mock
async def test_scan_drive_folder(client):
    """Test scanning a Drive folder with mocked API responses."""
    _setup_mocks(respx)

    pdf_bytes = _fixture_pdf_bytes()

    # Use a single route handler for all /files listing requests
    files_route = respx.get(f"{DRIVE_API}/files")

    # Track calls to return appropriate responses based on query params
    call_responses = []

    def files_side_effect(request):
        q = str(request.url.params.get("q", ""))
        if f"'{FAKE_FOLDER_ID}' in parents" in q and "application/pdf" in q:
            return Response(200, json={"files": [
                {"id": FAKE_FILE_ID, "name": "Moonlight Sonata.pdf"},
            ]})
        if f"'{FAKE_FOLDER_ID}' in parents" in q and "folder" in q:
            return Response(200, json={"files": [
                {"id": FAKE_SUBFOLDER_ID, "name": "Bach"},
            ]})
        if f"'{FAKE_SUBFOLDER_ID}' in parents" in q and "application/pdf" in q:
            return Response(200, json={"files": [
                {"id": FAKE_NESTED_FILE_ID, "name": "Prelude in C.pdf"},
            ]})
        if f"'{FAKE_SUBFOLDER_ID}' in parents" in q and "folder" in q:
            return Response(200, json={"files": []})
        return Response(200, json={"files": []})

    files_route.mock(side_effect=files_side_effect)

    # Mock PDF downloads
    respx.get(
        f"{DRIVE_API}/files/{FAKE_FILE_ID}",
    ).mock(return_value=Response(200, content=pdf_bytes))
    respx.get(
        f"{DRIVE_API}/files/{FAKE_NESTED_FILE_ID}",
    ).mock(return_value=Response(200, content=pdf_bytes))

    # Add folder
    resp = await client.post(
        "/folders",
        json={
            "backend_type": "gdrive",
            "backend_folder_id": FAKE_FOLDER_ID,
            "folder_name": "sheet music",
        },
    )
    assert resp.status_code == 201
    folder_id = resp.json()["id"]

    # Scan it
    resp = await client.post(f"/folders/{folder_id}/scan")
    assert resp.status_code == 200
    data = resp.json()
    assert data["new_count"] == 2
    assert data["total_count"] == 2


@respx.mock
async def test_download_drive_pdf(client):
    """Test downloading a Drive PDF with mocked API responses."""
    _setup_mocks(respx)

    pdf_bytes = _fixture_pdf_bytes()

    files_route = respx.get(f"{DRIVE_API}/files")

    def files_side_effect(request):
        q = str(request.url.params.get("q", ""))
        if f"'{FAKE_FOLDER_ID}' in parents" in q and "application/pdf" in q:
            return Response(200, json={"files": [
                {"id": FAKE_FILE_ID, "name": "Moonlight Sonata.pdf"},
            ]})
        if f"'{FAKE_FOLDER_ID}' in parents" in q and "folder" in q:
            return Response(200, json={"files": []})
        return Response(200, json={"files": []})

    files_route.mock(side_effect=files_side_effect)

    # Download mock — used by both scan (metadata extraction) and direct download
    respx.get(f"{DRIVE_API}/files/{FAKE_FILE_ID}").mock(
        return_value=Response(200, content=pdf_bytes)
    )

    # Add and scan
    resp = await client.post(
        "/folders",
        json={
            "backend_type": "gdrive",
            "backend_folder_id": FAKE_FOLDER_ID,
            "folder_name": "sheet music",
        },
    )
    folder_id = resp.json()["id"]
    await client.post(f"/folders/{folder_id}/scan")

    # Get first sheet
    sheets = await client.get("/sheets")
    sheet_id = sheets.json()["sheets"][0]["id"]

    # Download PDF
    resp = await client.get(f"/sheets/{sheet_id}/pdf")
    assert resp.status_code == 200
    assert resp.content.startswith(b"%PDF")


@respx.mock
async def test_rescan_skips_existing(client):
    """Test that rescanning doesn't duplicate sheets."""
    _setup_mocks(respx)

    pdf_bytes = _fixture_pdf_bytes()

    respx.get(f"{DRIVE_API}/files").mock(side_effect=lambda request: (
        Response(200, json={"files": [{"id": FAKE_FILE_ID, "name": "Moonlight Sonata.pdf"}]})
        if "application/pdf" in str(request.url.params.get("q", ""))
        else Response(200, json={"files": []})
    ))
    respx.get(f"{DRIVE_API}/files/{FAKE_FILE_ID}").mock(
        return_value=Response(200, content=pdf_bytes)
    )

    resp = await client.post(
        "/folders",
        json={
            "backend_type": "gdrive",
            "backend_folder_id": FAKE_FOLDER_ID,
            "folder_name": "sheet music",
        },
    )
    folder_id = resp.json()["id"]

    resp = await client.post(f"/folders/{folder_id}/scan")
    assert resp.json()["new_count"] == 1

    # Rescan — should skip
    resp = await client.post(f"/folders/{folder_id}/scan")
    assert resp.json()["new_count"] == 0
    assert resp.json()["skipped_count"] == 1


@respx.mock
async def test_drive_metadata_extracted(client):
    """Test that metadata is extracted from scanned Drive PDFs."""
    _setup_mocks(respx)

    pdf_bytes = _fixture_pdf_bytes()

    respx.get(f"{DRIVE_API}/files").mock(side_effect=lambda request: (
        Response(200, json={"files": [{"id": FAKE_FILE_ID, "name": "sample.pdf"}]})
        if "application/pdf" in str(request.url.params.get("q", ""))
        else Response(200, json={"files": []})
    ))
    respx.get(f"{DRIVE_API}/files/{FAKE_FILE_ID}").mock(
        return_value=Response(200, content=pdf_bytes)
    )

    resp = await client.post(
        "/folders",
        json={
            "backend_type": "gdrive",
            "backend_folder_id": FAKE_FOLDER_ID,
            "folder_name": "sheet music",
        },
    )
    folder_id = resp.json()["id"]
    await client.post(f"/folders/{folder_id}/scan")

    sheets = await client.get("/sheets")
    sheet = sheets.json()["sheets"][0]
    assert sheet["metadata"].get("title") == "Sonata No. 14"
    assert sheet["metadata"].get("composer") == "Ludwig van Beethoven"
