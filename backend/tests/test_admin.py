async def test_clear_index(client):
    # Scan to populate index
    folders = await client.get("/folders")
    folder_id = folders.json()["folders"][0]["id"]
    await client.post(f"/folders/{folder_id}/scan")

    sheets = await client.get("/sheets")
    assert sheets.json()["total"] > 0

    # Clear index
    resp = await client.post("/admin/clear-index")
    assert resp.status_code == 200
    assert resp.json()["deleted"] > 0

    # Verify empty
    sheets = await client.get("/sheets")
    assert sheets.json()["total"] == 0


async def test_clear_index_when_empty(client):
    resp = await client.post("/admin/clear-index")
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 0
