async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_config_returns_backends(client):
    resp = await client.get("/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "backends" in data
    assert "local" in data["backends"]
