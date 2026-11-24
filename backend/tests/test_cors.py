from fastapi.testclient import TestClient

from mnemonic.main import app

PREFLIGHT = {
    "Access-Control-Request-Method": "POST",
    "Access-Control-Request-Headers": "authorization,content-type",
}


def test_preflight_allows_the_spa_origin_and_our_headers():
    # No `with`: the lifespan (database) is not needed for a preflight.
    r = TestClient(app).options("/chat", headers={"Origin": "http://localhost:5173", **PREFLIGHT})
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"
    allowed = r.headers["access-control-allow-headers"].lower()
    assert "authorization" in allowed and "content-type" in allowed


def test_preflight_rejects_a_foreign_origin():
    r = TestClient(app).options("/chat", headers={"Origin": "https://evil.example", **PREFLIGHT})
    assert r.status_code == 400
    assert "access-control-allow-origin" not in r.headers


def test_retry_after_is_readable_by_the_browser():
    # Without expose_headers the SPA cannot read Retry-After from a cross-origin 429, so it could
    # not show the "try again in N seconds" countdown.
    r = TestClient(app).get("/health", headers={"Origin": "http://localhost:5173"})
    assert "retry-after" in r.headers["access-control-expose-headers"].lower()
