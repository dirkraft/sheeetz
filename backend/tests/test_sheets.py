import json


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


async def test_scan_extracts_metadata(client):
    """Scanning should populate SheetMeta rows with mapped core fields."""
    data = await _scan_fixtures(client)
    sheets_by_name = {s["filename"]: s for s in data["sheets"]}

    sample = sheets_by_name["sample.pdf"]
    assert sample["metadata"]["composer"] == "Ludwig van Beethoven"
    assert sample["metadata"]["title"] == "Sonata No. 14"
    assert sample["metadata"]["genre"] == "Classical"
    assert sample["metadata"]["pages"] == "1"

    nested = sheets_by_name["nested.pdf"]
    assert nested["metadata"]["composer"] == "Johann Sebastian Bach"
    assert nested["metadata"]["genre"] == "Baroque"


async def test_meta_filters_composer(client):
    """meta_filters should filter by composer substring."""
    await _scan_fixtures(client)

    filters = json.dumps({"composer": "Bach"})
    resp = await client.get("/sheets", params={"meta_filters": filters})
    data = resp.json()
    assert data["total"] == 1
    assert data["sheets"][0]["filename"] == "nested.pdf"


async def test_meta_filters_multiple(client):
    """meta_filters with multiple keys uses AND semantics."""
    await _scan_fixtures(client)

    # Beethoven + Classical → should match sample.pdf
    filters = json.dumps({"composer": "Beethoven", "genre": "Classical"})
    resp = await client.get("/sheets", params={"meta_filters": filters})
    data = resp.json()
    assert data["total"] == 1
    assert data["sheets"][0]["filename"] == "sample.pdf"

    # Beethoven + Baroque → should match nothing
    filters = json.dumps({"composer": "Beethoven", "genre": "Baroque"})
    resp = await client.get("/sheets", params={"meta_filters": filters})
    data = resp.json()
    assert data["total"] == 0


async def test_meta_filters_no_match(client):
    """meta_filters with non-existent value returns empty."""
    await _scan_fixtures(client)

    filters = json.dumps({"composer": "Chopin"})
    resp = await client.get("/sheets", params={"meta_filters": filters})
    data = resp.json()
    assert data["total"] == 0


async def test_update_metadata_returns_501(client):
    """PATCH metadata is not yet implemented — should return 501."""
    data = await _scan_fixtures(client)
    sheet_id = data["sheets"][0]["id"]
    resp = await client.patch(f"/sheets/{sheet_id}/metadata", json={"title": "Test"})
    assert resp.status_code == 501
