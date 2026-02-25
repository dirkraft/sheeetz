from .conftest import FIXTURES_DIR


async def test_browse_local_folders(client):
    resp = await client.get(
        "/folders/browse",
        params={"backend": "local", "parent_id": str(FIXTURES_DIR)},
    )
    assert resp.status_code == 200
    data = resp.json()
    names = [f["name"] for f in data["folders"]]
    assert "subfolder" in names


async def test_add_folder(client):
    resp = await client.post(
        "/folders",
        json={
            "backend_type": "local",
            "backend_folder_id": str(FIXTURES_DIR / "subfolder"),
            "folder_name": "subfolder",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["backend_type"] == "local"
    assert data["folder_name"] == "subfolder"
    return data["id"]


async def test_scan_folder(client):
    # The seeded_db fixture already has a folder pointing at FIXTURES_DIR
    folders = await client.get("/folders")
    folder_id = folders.json()["folders"][0]["id"]

    resp = await client.post(f"/folders/{folder_id}/scan")
    assert resp.status_code == 200
    data = resp.json()
    assert data["new_count"] == 2  # sample.pdf + subfolder/nested.pdf
    assert data["total_count"] == 2
    assert data["skipped_count"] == 0


async def test_rescan_skips_duplicates(client):
    folders = await client.get("/folders")
    folder_id = folders.json()["folders"][0]["id"]

    # First scan
    await client.post(f"/folders/{folder_id}/scan")

    # Second scan
    resp = await client.post(f"/folders/{folder_id}/scan")
    data = resp.json()
    assert data["new_count"] == 0
    assert data["skipped_count"] == 2


async def test_delete_folder_cascades_sheets(client):
    folders = await client.get("/folders")
    folder_id = folders.json()["folders"][0]["id"]

    # Scan to create sheets
    await client.post(f"/folders/{folder_id}/scan")
    sheets = await client.get("/sheets")
    assert sheets.json()["total"] > 0

    # Delete folder
    resp = await client.delete(f"/folders/{folder_id}")
    assert resp.status_code == 204

    # Sheets should be gone
    sheets = await client.get("/sheets")
    assert sheets.json()["total"] == 0
