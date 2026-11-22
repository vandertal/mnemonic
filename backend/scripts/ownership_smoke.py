"""Smoke test of ownership against a RUNNING server with the real database (Alice vs Bob).

Usage (from backend/):  uv run python scripts/ownership_smoke.py http://127.0.0.1:8000
If the server sets REGISTRATION_CODE, export it first:  $env:REGISTRATION_CODE = "..."
Creates two accounts with random emails and deletes them at the end (DELETE /auth/me).
Uses 4 auth calls (2 register + 2 login): the auth limit is 5 per minute per IP.
Prints PASS/FAIL per step. Exit code 1 on any FAIL.
"""

import os
import secrets
import sys

import httpx

DOCUMENT = b"# Smoke\n\nOwnership smoke test: this note belongs to Alice only.\n"


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    base = sys.argv[1].rstrip("/")
    code = os.environ.get("REGISTRATION_CODE") or None
    failed = False

    def step(name: str, ok: bool, detail: str = "") -> bool:
        nonlocal failed
        failed |= not ok
        print(f"{'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail and not ok else ''}")
        return ok

    def account(http: httpx.Client, who: str) -> dict | None:
        email = f"smoke-{who}-{secrets.token_hex(4)}@example.com"
        password = secrets.token_urlsafe(16)
        body = {"email": email, "password": password}
        if code:
            body["registration_code"] = code
        r = http.post("/auth/register", json=body)
        if not step(f"register {who} -> 201", r.status_code == 201, f"got {r.status_code}"):
            return None
        r = http.post("/auth/login", data={"username": email, "password": password})
        token = r.json().get("access_token") if r.status_code == 200 else None
        if not step(f"login {who} -> token", token is not None, f"got {r.status_code}"):
            return None
        return {"Authorization": f"Bearer {token}"}

    with httpx.Client(base_url=base, timeout=60) as http:
        alice = account(http, "alice")
        bob = account(http, "bob")
        try:
            if alice is None or bob is None:
                return 1

            r = http.get("/sessions")
            step("no token -> 401", r.status_code == 401, f"got {r.status_code}")

            r = http.post("/sessions", json={"title": "Alice's chat"}, headers=alice)
            session_id = r.json().get("id") if r.status_code == 201 else None
            if not step(
                "alice creates a session -> 201", session_id is not None, f"{r.status_code}"
            ):
                return 1

            r = http.post(
                "/documents", files={"file": ("smoke.md", DOCUMENT, "text/markdown")}, headers=alice
            )
            doc_id = r.json().get("id") if r.status_code == 201 else None
            step("alice uploads a document -> 201", doc_id is not None, f"got {r.status_code}")

            r = http.get(f"/sessions/{session_id}", headers=bob)
            step("bob GET alice's session -> 404", r.status_code == 404, f"got {r.status_code}")
            r = http.get(f"/sessions/{session_id}/messages", headers=bob)
            step("bob GET its messages -> 404", r.status_code == 404, f"got {r.status_code}")
            r = http.delete(f"/documents/{doc_id}", headers=bob)
            step("bob DELETE alice's document -> 404", r.status_code == 404, f"got {r.status_code}")

            r = http.get("/sessions", headers=alice)
            ids = [s["id"] for s in r.json()["items"]] if r.status_code == 200 else []
            step("alice lists her session", ids == [session_id], f"got {ids}")
            r = http.get("/sessions", headers=bob)
            step("bob's session list is empty", r.status_code == 200 and r.json()["total"] == 0)
            r = http.get("/documents", headers=alice)
            step("alice lists her document", r.status_code == 200 and len(r.json()) == 1)
            r = http.get("/documents", headers=bob)
            step("bob's document list is empty", r.status_code == 200 and r.json() == [])

            r = http.delete(f"/documents/{doc_id}", headers=alice)
            step("alice DELETE her document -> 204", r.status_code == 204, f"got {r.status_code}")
        finally:
            # Always clean up, even after a failed step: otherwise test accounts pile up.
            for who, headers in (("alice", alice), ("bob", bob)):
                if headers is None:
                    continue
                r = http.delete("/auth/me", headers=headers)
                step(f"delete account {who} -> 204", r.status_code == 204, f"got {r.status_code}")
                r = http.get("/auth/me", headers=headers)
                step(f"{who}'s old token -> 401", r.status_code == 401, f"got {r.status_code}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
