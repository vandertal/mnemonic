"""Smoke test of /search and /search/explain against a running server (not run by CI).

Usage (from backend/):
    uv run python scripts/search_smoke.py http://127.0.0.1:8000 [REGISTRATION_CODE]
Registers TWO accounts (A and B): /auth/* allows 5 requests per minute per IP, and this uses 4
(2 registers + 2 logins). Wait a minute between runs. Prints PASS/FAIL per step; exit 1 on a FAIL.
Needs the shared knowledge base to be loaded (the last step searches for `Depends`).
"""

import secrets
import sys

import httpx


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    base = sys.argv[1].rstrip("/")
    code = sys.argv[2] if len(sys.argv) > 2 else None
    token = "zq" + secrets.token_hex(6)  # unique: no other document can contain it
    failed = False

    def step(name: str, ok: bool, detail: str = "") -> None:
        nonlocal failed
        failed |= not ok
        print(f"{'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail and not ok else ''}")

    def sign_up(http: httpx.Client, label: str) -> dict | None:
        email, password = (
            f"smoke-{label}-{secrets.token_hex(4)}@example.com",
            secrets.token_urlsafe(16),
        )
        body = {"email": email, "password": password}
        if code:
            body["registration_code"] = code
        r = http.post("/auth/register", json=body)
        step(f"register {label} -> 201", r.status_code == 201, f"got {r.status_code}")
        r = http.post("/auth/login", data={"username": email, "password": password})
        ok = r.status_code == 200
        step(f"login {label} -> 200", ok, f"got {r.status_code}")
        return {"Authorization": f"Bearer {r.json()['access_token']}"} if ok else None

    with httpx.Client(base_url=base, timeout=60) as http:
        a, b = sign_up(http, "A"), sign_up(http, "B")
        if not a or not b:
            return 1

        md = f"# Smoke notes\n\nThe secret word is {token}. It appears in this tiny file.\n"
        r = http.post(
            "/documents", files={"file": ("smoke.md", md.encode(), "text/markdown")}, headers=a
        )
        step("A uploads a tiny markdown -> 201", r.status_code == 201, f"got {r.status_code}")
        doc_id = r.json().get("id") if r.status_code == 201 else None

        r = http.get("/search", params={"q": token}, headers=a)
        hits = r.json() if r.status_code == 200 else []
        step(
            "A finds the token via /search", len(hits) == 1, f"got {r.status_code} {len(hits)} hits"
        )
        chunk_id = hits[0]["chunk_id"] if hits else None
        if hits:
            snip = hits[0]["snippet"]
            marked = [snip["text"][s:e] for s, e in snip["highlights"]]
            step("snippet highlights are offsets into plain text", token in marked, str(marked))

        r = http.get("/search", params={"q": token}, headers=b)
        step(
            "B gets 0 hits for the token",
            r.status_code == 200 and r.json() == [],
            f"got {r.text[:80]}",
        )

        r = http.get("/search", params={"q": token})
        step("no token -> 401", r.status_code == 401, f"got {r.status_code}")

        if chunk_id is not None:
            explain = {"q": token, "chunk_id": chunk_id}
            r = http.get("/search/explain", params=explain, headers=a)
            body = r.json() if r.status_code == 200 else {}
            total = sum(t["contribution"] for t in body.get("terms", []))
            step(
                "explain for A's chunk -> 200, contributions sum to the score",
                r.status_code == 200 and abs(total - body["score"]) < 1e-6,
                f"got {r.status_code}",
            )
            r = http.get("/search/explain", params=explain, headers=b)
            step("explain for B on A's chunk -> 404", r.status_code == 404, f"got {r.status_code}")

        r = http.get("/search", params={"q": "Depends"}, headers=b)
        step(
            "`Depends` returns >= 1 shared hit",
            r.status_code == 200 and len(r.json()) >= 1,
            f"got {r.status_code}",
        )

        if doc_id is not None:  # clean up, and check that the delete reaches the index at once
            r = http.delete(f"/documents/{doc_id}", headers=a)
            step("A deletes the document -> 204", r.status_code == 204, f"got {r.status_code}")
            r = http.get("/search", params={"q": token}, headers=a)
            step("the token is gone from /search", r.status_code == 200 and r.json() == [])
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
