from fastapi.testclient import TestClient

from mnemonic.main import app

PREFLIGHT = {
    "Access-Control-Request-Method": "POST",
    "Access-Control-Request-Headers": "x-api-key,content-type",
}


def test_preflight_allows_the_spa_origin_and_our_headers():
    # No `with`: the lifespan (database) is not needed for a preflight.
    r = TestClient(app).options("/chat", headers={"Origin": "http://localhost:5173", **PREFLIGHT})
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"
    allowed = r.headers["access-control-allow-headers"].lower()
    assert "x-api-key" in allowed and "content-type" in allowed


def test_preflight_rejects_a_foreign_origin():
    r = TestClient(app).options("/chat", headers={"Origin": "https://evil.example", **PREFLIGHT})
    assert r.status_code == 400
    assert "access-control-allow-origin" not in r.headers
