import os

import pytest

from .conftest import skip_without_drive

pytestmark = [pytest.mark.drive, skip_without_drive]

DRIVE_FOLDER_ID = "1ctbm16oYic5PlsuewbKCh1wFaVUQgya0"  # agents' "sheet music" folder


async def test_scan_drive_folder(drive_client):
    # Add the agents' Drive folder
    resp = await drive_client.post(
        "/folders",
        json={
            "backend_type": "gdrive",
            "backend_folder_id": DRIVE_FOLDER_ID,
            "folder_name": "sheet music",
        },
    )
    assert resp.status_code == 201
    folder_id = resp.json()["id"]

    # Scan it
    resp = await drive_client.post(f"/folders/{folder_id}/scan")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_count"] > 0


async def test_download_drive_pdf(drive_client):
    # Add and scan
    resp = await drive_client.post(
        "/folders",
        json={
            "backend_type": "gdrive",
            "backend_folder_id": DRIVE_FOLDER_ID,
            "folder_name": "sheet music",
        },
    )
    folder_id = resp.json()["id"]
    await drive_client.post(f"/folders/{folder_id}/scan")

    # Get first sheet
    sheets = await drive_client.get("/sheets")
    sheet_id = sheets.json()["sheets"][0]["id"]

    # Download PDF
    resp = await drive_client.get(f"/sheets/{sheet_id}/pdf")
    assert resp.status_code == 200
    assert resp.content.startswith(b"%PDF")
