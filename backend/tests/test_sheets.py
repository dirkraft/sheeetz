import json

from .conftest import wait_for_scan


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
    await wait_for_scan(client, folder_id)
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
    assert sample["metadata"]["pages"] == "1"

    nested = sheets_by_name["nested.pdf"]
    assert nested["metadata"]["composer"] == "Johann Sebastian Bach"


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

    # Beethoven + Sonata title → should match sample.pdf
    filters = json.dumps({"composer": "Beethoven", "title": "Sonata"})
    resp = await client.get("/sheets", params={"meta_filters": filters})
    data = resp.json()
    assert data["total"] == 1
    assert data["sheets"][0]["filename"] == "sample.pdf"

    # Beethoven + wrong title → should match nothing
    filters = json.dumps({"composer": "Beethoven", "title": "Nocturne"})
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


async def test_distinct_metadata_values(client):
    """GET /sheets/metadata/distinct returns unique values for a given key."""
    await _scan_fixtures(client)

    resp = await client.get("/sheets/metadata/distinct", params={"key": "composer"})
    assert resp.status_code == 200
    values = resp.json()["values"]
    assert "Ludwig van Beethoven" in values
    assert "Johann Sebastian Bach" in values


async def test_distinct_metadata_values_with_query(client):
    """Substring filter narrows results (case-insensitive)."""
    await _scan_fixtures(client)

    resp = await client.get("/sheets/metadata/distinct", params={"key": "composer", "q": "bach"})
    assert resp.status_code == 200
    values = resp.json()["values"]
    assert values == ["Johann Sebastian Bach"]


async def test_distinct_metadata_values_no_match(client):
    """Non-matching query returns empty list."""
    await _scan_fixtures(client)

    resp = await client.get("/sheets/metadata/distinct", params={"key": "composer", "q": "chopin"})
    assert resp.status_code == 200
    assert resp.json()["values"] == []


async def test_distinct_metadata_values_empty_key(client):
    """Unknown key returns empty list."""
    await _scan_fixtures(client)

    resp = await client.get("/sheets/metadata/distinct", params={"key": "nonexistent"})
    assert resp.status_code == 200
    assert resp.json()["values"] == []


async def test_distinct_metadata_values_requires_key(client):
    """Missing key param returns 422."""
    resp = await client.get("/sheets/metadata/distinct")
    assert resp.status_code == 422


async def _get_sample_sheet_id(client):
    """Helper: scan fixtures and return sample.pdf's sheet ID."""
    data = await _scan_fixtures(client)
    for s in data["sheets"]:
        if s["filename"] == "sample.pdf":
            return s["id"]


async def test_update_metadata_writes_to_pdf_and_index(client):
    """PATCH metadata should write to PDF (sheeetz namespace) and update the index."""
    sheet_id = await _get_sample_sheet_id(client)

    resp = await client.patch(
        f"/sheets/{sheet_id}/metadata",
        json={"composer": "Wolfgang Amadeus Mozart", "tags": "classical, piano"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["metadata"]["composer"] == "Wolfgang Amadeus Mozart"
    assert data["metadata"]["tags"] == "classical, piano"
    # Pages should still be present (auto-derived)
    assert data["metadata"]["pages"] == "1"

    # Verify the index is updated — filtering by new composer works
    filters = json.dumps({"composer": "Mozart"})
    resp2 = await client.get("/sheets", params={"meta_filters": filters})
    assert resp2.json()["total"] == 1

    # Old composer should no longer match
    filters_old = json.dumps({"composer": "Beethoven"})
    resp3 = await client.get("/sheets", params={"meta_filters": filters_old})
    assert resp3.json()["total"] == 0


async def test_update_metadata_blank_field_removes_from_pdf(client):
    """Setting a field to blank should remove it from the PDF and index."""
    sheet_id = await _get_sample_sheet_id(client)

    # First set key
    await client.patch(
        f"/sheets/{sheet_id}/metadata",
        json={"key": "D Minor"},
    )
    resp = await client.get(f"/sheets/{sheet_id}")
    assert resp.json()["metadata"]["key"] == "D Minor"

    # Now blank it out
    resp2 = await client.patch(
        f"/sheets/{sheet_id}/metadata",
        json={"key": ""},
    )
    assert "key" not in resp2.json()["metadata"]

    # Verify via sheet detail too
    resp3 = await client.get(f"/sheets/{sheet_id}")
    assert "key" not in resp3.json()["metadata"]


async def test_update_metadata_preserves_original_pdf_metadata(client):
    """Editing via sheeetz namespace should not destroy original dc: metadata."""
    sheet_id = await _get_sample_sheet_id(client)

    # Edit composer via our endpoint
    await client.patch(
        f"/sheets/{sheet_id}/metadata",
        json={"composer": "Edited Composer"},
    )

    # Raw PDF metadata should still have the original Author/dc:creator
    resp = await client.get(f"/sheets/{sheet_id}/pdf-metadata")
    raw = resp.json()["metadata"]
    # Original docinfo Author should still be present
    assert raw.get("Author") == "Ludwig van Beethoven"
    # Our sheeetz namespace value should also be present
    assert raw.get("{http://sheeetz.app/meta/1.0/}composer") == "Edited Composer"


async def test_update_metadata_pages_cannot_be_overwritten(client):
    """'pages' is auto-derived and should not be overwritable."""
    sheet_id = await _get_sample_sheet_id(client)

    resp = await client.patch(
        f"/sheets/{sheet_id}/metadata",
        json={"pages": "999"},
    )
    assert resp.status_code == 200
    # Pages should stay at actual value, not 999
    assert resp.json()["metadata"]["pages"] == "1"


async def test_edit_title_survives_reload(client):
    """Edit title (pre-filled from raw PDF), save, reload page → edited value sticks.

    This reproduces the exact user flow: title is auto-populated from dc:title
    during scan, user edits it, saves, reloads the viewer, expects to see their edit.
    """
    sheet_id = await _get_sample_sheet_id(client)

    # Verify original title from scan
    resp = await client.get(f"/sheets/{sheet_id}")
    assert resp.json()["metadata"]["title"] == "Sonata No. 14"

    # Simulate the frontend form: user edits title, other fields sent as-is
    await client.patch(
        f"/sheets/{sheet_id}/metadata",
        json={
            "title": "My Custom Title",
            "composer": "Ludwig van Beethoven",
            "tags": "piano, sonata, moonlight",
        },
    )

    # "Reload" — fresh GET, simulating what the viewer does on mount
    resp2 = await client.get(f"/sheets/{sheet_id}")
    assert resp2.json()["metadata"]["title"] == "My Custom Title"

    # Also verify via raw PDF metadata endpoint (what the Info panel fetches)
    resp3 = await client.get(f"/sheets/{sheet_id}/pdf-metadata")
    raw = resp3.json()["metadata"]
    assert raw["{http://sheeetz.app/meta/1.0/}title"] == "My Custom Title"
    # Original dc:title should still be there
    assert raw["{http://purl.org/dc/elements/1.1/}title"] == "Sonata No. 14"


async def test_arbitrary_key_persists(client):
    """PATCH with an arbitrary key like 'arranger' should persist in index and PDF."""
    sheet_id = await _get_sample_sheet_id(client)

    resp = await client.patch(
        f"/sheets/{sheet_id}/metadata",
        json={"arranger": "John Doe"},
    )
    assert resp.status_code == 200
    assert resp.json()["metadata"]["arranger"] == "John Doe"

    # Verify it survives a reload
    resp2 = await client.get(f"/sheets/{sheet_id}")
    assert resp2.json()["metadata"]["arranger"] == "John Doe"

    # Verify it's in the raw PDF metadata under sheeetz namespace
    resp3 = await client.get(f"/sheets/{sheet_id}/pdf-metadata")
    raw = resp3.json()["metadata"]
    assert raw["{http://sheeetz.app/meta/1.0/}arranger"] == "John Doe"


async def test_arbitrary_key_blank_removes(client):
    """Setting an arbitrary key to blank should remove it."""
    sheet_id = await _get_sample_sheet_id(client)

    # First set it
    await client.patch(
        f"/sheets/{sheet_id}/metadata",
        json={"transcriber": "Jane Smith"},
    )
    resp = await client.get(f"/sheets/{sheet_id}")
    assert resp.json()["metadata"]["transcriber"] == "Jane Smith"

    # Now blank it out
    resp2 = await client.patch(
        f"/sheets/{sheet_id}/metadata",
        json={"transcriber": ""},
    )
    assert "transcriber" not in resp2.json()["metadata"]


async def test_distinct_keys_endpoint(client):
    """GET /sheets/metadata/keys returns distinct key names."""
    sheet_id = await _get_sample_sheet_id(client)

    # Add a custom field
    await client.patch(
        f"/sheets/{sheet_id}/metadata",
        json={"arranger": "Someone"},
    )

    resp = await client.get("/sheets/metadata/keys")
    assert resp.status_code == 200
    keys = resp.json()["keys"]
    assert "arranger" in keys
    assert "composer" in keys
    # pages should be excluded
    assert "pages" not in keys


async def test_distinct_keys_with_query_filter(client):
    """Substring filter narrows key results."""
    sheet_id = await _get_sample_sheet_id(client)

    await client.patch(
        f"/sheets/{sheet_id}/metadata",
        json={"arranger": "Someone"},
    )

    resp = await client.get("/sheets/metadata/keys", params={"q": "arr"})
    assert resp.status_code == 200
    keys = resp.json()["keys"]
    assert "arranger" in keys
    assert "composer" not in keys
