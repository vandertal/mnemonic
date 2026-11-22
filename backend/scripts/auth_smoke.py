"""Smoke test of the auth endpoints against a running server.

Usage (from backend/):  uv run python scripts/auth_smoke.py http://127.0.0.1:8000
If the server sets REGISTRATION_CODE, pass it as the second argument.
Creates one account with a random email; prints PASS/FAIL per step. Exit code 1 on any FAIL.
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
    email = f"smoke-{secrets.token_hex(4)}@example.com"
    password = secrets.token_urlsafe(16)
    failed = False

    def step(name: str, ok: bool, detail: str = "") -> None:
        nonlocal failed
        failed |= not ok
        print(f"{'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail and not ok else ''}")

    with httpx.Client(base_url=base, timeout=30) as http:
        body = {"email": email, "password": password}
        if code:
            body["registration_code"] = code
        r = http.post("/auth/register", json=body)
        step("register -> 201", r.status_code == 201, f"got {r.status_code}")

        r = http.post("/auth/login", data={"username": email, "password": password})
        token = r.json().get("access_token") if r.status_code == 200 else None
        step("login -> 200 + token", token is not None, f"got {r.status_code}")

        r = http.post("/auth/login", data={"username": email, "password": password + "x"})
        step("wrong password -> 401", r.status_code == 401, f"got {r.status_code}")

        r = http.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        step(
            "me -> 200 + same email",
            r.status_code == 200 and r.json().get("email") == email,
            f"got {r.status_code}",
        )

        r = http.get("/auth/me")
        step("me without token -> 401", r.status_code == 401, f"got {r.status_code}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
