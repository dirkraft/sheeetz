"""Tests for the organize-files feature."""

import asyncio
from pathlib import Path

import pytest

from .conftest import wait_for_scan

FIXTURES_DIR = Path(__file__).parent / "fixtures"


async def _scan_fixtures(client) -> list[dict]:
    """Scan the seeded fixtures folder and return sheet list."""
    folders = await client.get("/folders")
    folder_id = folders.json()["folders"][0]["id"]
    await client.post(f"/folders/{folder_id}/scan")
    await wait_for_scan(client, folder_id)
    resp = await client.get("/sheets")
    return resp.json()["sheets"]


async def _wait_for_job(client, job_id: str, timeout: float = 5.0) -> dict:
    """Poll organize job until complete or error."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        resp = await client.get(f"/organize/jobs/{job_id}")
        data = resp.json()
        if data["status"] != "running":
            return data
        await asyncio.sleep(0.05)
    raise TimeoutError(f"Organize job {job_id} did not complete in {timeout}s")


async def test_organize_preview_basic(client, tmp_path):
    """Preview should resolve a simple template for sheets with composer/title."""
    sheets = await _scan_fixtures(client)
    sample = next(s for s in sheets if s["filename"] == "sample.pdf")

    resp = await client.post(
        "/organize/preview",
        json={
            "sheet_ids": [sample["id"]],
            "template": "$composer/$title.$ext",
        },
    )
    assert resp.status_code == 200
    previews = resp.json()["previews"]
    assert len(previews) == 1
    p = previews[0]
    assert p["can_move"] is True
    assert "Ludwig van Beethoven" in p["to_path"]
    assert "Sonata No. 14" in p["to_path"]


async def test_organize_preview_missing_metadata(client):
    """Preview should flag sheets where template cannot be resolved."""
    sheets = await _scan_fixtures(client)
    sample = next(s for s in sheets if s["filename"] == "sample.pdf")

    resp = await client.post(
        "/organize/preview",
        json={
            "sheet_ids": [sample["id"]],
            # $nonexistent key doesn't exist → can't move
            "template": "$nonexistent/$title.$ext",
        },
    )
    assert resp.status_code == 200
    previews = resp.json()["previews"]
    assert previews[0]["can_move"] is False
    assert previews[0]["warning"] is not None


async def test_organize_preview_fallback(client):
    """($composer or $nonexistent) should fall back to composer."""
    sheets = await _scan_fixtures(client)
    sample = next(s for s in sheets if s["filename"] == "sample.pdf")

    resp = await client.post(
        "/organize/preview",
        json={
            "sheet_ids": [sample["id"]],
            "template": "($composer or $nonexistent)/($title or $filename).$ext",
        },
    )
    assert resp.status_code == 200
    p = resp.json()["previews"][0]
    assert p["can_move"] is True
    assert "Ludwig van Beethoven" in p["to_path"]


async def test_organize_moves_file_local(client, tmp_path):
    """Organize should physically move a local file and update the DB."""
    import shutil
    # Copy fixtures to tmp dir so we don't destroy real fixtures
    tmp_fixtures = tmp_path / "fixtures"
    shutil.copytree(str(FIXTURES_DIR), str(tmp_fixtures))

    # Add a new library folder pointing at tmp_fixtures
    resp = await client.post(
        "/folders",
        json={
            "backend_type": "local",
            "backend_folder_id": str(tmp_fixtures),
            "folder_name": "tmp",
        },
    )
    assert resp.status_code == 201
    folder_id = resp.json()["id"]

    # Scan it
    await client.post(f"/folders/{folder_id}/scan")
    await wait_for_scan(client, folder_id)

    sheets = await client.get("/sheets", params={"folder_id": folder_id})
    all_sheets = sheets.json()["sheets"]
    sample = next(s for s in all_sheets if s["filename"] == "sample.pdf")

    # Organize: $composer/$filename.$ext
    resp = await client.post(
        "/organize",
        json={
            "sheet_ids": [sample["id"]],
            "template": "$composer/$filename.$ext",
        },
    )
    assert resp.status_code == 200
    job = await _wait_for_job(client, resp.json()["job_id"])
    assert job["status"] == "complete"
    assert job["moved_count"] == 1

    # File should now be in tmp_fixtures/Ludwig van Beethoven/sample.pdf
    new_path = tmp_fixtures / "Ludwig van Beethoven" / "sample.pdf"
    assert new_path.exists()

    # DB should be updated
    sheet_resp = await client.get(f"/sheets/{sample['id']}")
    updated = sheet_resp.json()
    assert updated["filename"] == "sample.pdf"
    assert "Ludwig van Beethoven" in updated["backend_file_id"]


async def test_organize_no_sheets(client):
    """Empty sheet_ids should return 400."""
    resp = await client.post(
        "/organize/preview",
        json={"sheet_ids": [], "template": "$filename.$ext"},
    )
    assert resp.status_code == 400


async def test_organize_missing_template(client):
    """Empty template should return 400."""
    sheets = await _scan_fixtures(client)
    resp = await client.post(
        "/organize/preview",
        json={"sheet_ids": [sheets[0]["id"]], "template": ""},
    )
    assert resp.status_code == 400
