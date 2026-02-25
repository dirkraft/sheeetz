async def test_list_sheets_empty(client):
    resp = await client.get("/sheets")
    assert resp.status_code == 200
    data = resp.json()
    assert data["sheets"] == []
    assert data["total"] == 0


async def _scan_fixtures(client):
    """Helper: scan the seeded fixtures folder and return sheet list."""
    folders = await client.get("/folders")
    folder_id = folders.json()["folders"][0]["id"]
    await client.post(f"/folders/{folder_id}/scan")
    resp = await client.get("/sheets")
    return resp.json()


async def test_list_sheets_after_scan(client):
    data = await _scan_fixtures(client)
    assert data["total"] == 2
    filenames = {s["filename"] for s in data["sheets"]}
    assert "sample.pdf" in filenames
    assert "nested.pdf" in filenames


async def test_filter_by_filename(client):
    await _scan_fixtures(client)
    resp = await client.get("/sheets", params={"filename": "sample"})
    data = resp.json()
    assert data["total"] == 1
    assert data["sheets"][0]["filename"] == "sample.pdf"


async def test_get_sheet_detail(client):
    await _scan_fixtures(client)
    sheets = await client.get("/sheets")
    sheet_id = sheets.json()["sheets"][0]["id"]

    resp = await client.get(f"/sheets/{sheet_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "filename" in data
    assert "backend_file_id" in data
    assert data["backend_type"] == "local"


async def test_download_pdf(client):
    await _scan_fixtures(client)
    sheets = await client.get("/sheets")
    sheet_id = sheets.json()["sheets"][0]["id"]

    resp = await client.get(f"/sheets/{sheet_id}/pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")


async def test_unauthenticated_returns_401(unauth_client):
    resp = await unauth_client.get("/sheets")
    assert resp.status_code == 401
