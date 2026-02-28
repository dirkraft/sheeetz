import pytest


@pytest.mark.anyio
async def test_get_settings_returns_defaults(client):
    resp = await client.get("/auth/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert data["columns"] == ["filename", "composer", "folder", "source"]


@pytest.mark.anyio
async def test_patch_settings_saves_columns(client):
    resp = await client.patch(
        "/auth/settings",
        json={"columns": ["filename", "title", "genre"]},
    )
    assert resp.status_code == 200
    assert resp.json()["columns"] == ["filename", "title", "genre"]

    # Verify it persists on GET
    resp = await client.get("/auth/settings")
    assert resp.json()["columns"] == ["filename", "title", "genre"]


@pytest.mark.anyio
async def test_patch_settings_merges_keys(client):
    await client.patch("/auth/settings", json={"columns": ["filename"]})
    await client.patch("/auth/settings", json={"other_key": "value"})

    resp = await client.get("/auth/settings")
    data = resp.json()
    assert data["columns"] == ["filename"]
    assert data["other_key"] == "value"


@pytest.mark.anyio
async def test_settings_requires_auth(unauth_client):
    resp = await unauth_client.get("/auth/settings")
    assert resp.status_code == 401

    resp = await unauth_client.patch(
        "/auth/settings", json={"columns": ["filename"]}
    )
    assert resp.status_code == 401
