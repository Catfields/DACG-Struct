#!/usr/bin/env python3
import json
import os
import sys
import urllib.request
import urllib.error


def _post_json(url: str, payload: dict) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8") if exc.fp else ""
        try:
            parsed = json.loads(body) if body else {}
        except Exception:
            parsed = {"raw": body}
        return exc.code, parsed


def main() -> int:
    base_url = os.getenv("BASE_URL", "http://127.0.0.1:8000")
    login_name = os.getenv("LOGIN_NAME", "").strip()
    password = os.getenv("PASSWORD", "").strip()
    role_name = os.getenv("ROLE_NAME", "").strip()

    if not login_name or not password or not role_name:
        print("Missing LOGIN_NAME, PASSWORD, or ROLE_NAME env vars.", file=sys.stderr)
        print("Example:", file=sys.stderr)
        print(
            "  BASE_URL=http://127.0.0.1:8000 LOGIN_NAME=RAD001 PASSWORD=pass@RAD001 ROLE_NAME=影像科医生 python backend/scripts/min_login_test.py",
            file=sys.stderr,
        )
        return 2

    login_url = f"{base_url}/auth/login"
    status, payload = _post_json(
        login_url,
        {"login_name": login_name, "password": password, "role_name": role_name},
    )
    print(f"POST {login_url} -> {status}")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    if status != 200:
        return 1

    access_token = payload.get("access_token", "")
    refresh_token = payload.get("refresh_token", "")
    user = payload.get("user", {})

    print("Access token length:", len(access_token))
    print("Refresh token length:", len(refresh_token))
    print("User role:", user.get("role_name"))

    refresh_url = f"{base_url}/auth/refresh"
    r_status, r_payload = _post_json(refresh_url, {"refresh_token": refresh_token})
    print(f"POST {refresh_url} -> {r_status}")
    print(json.dumps(r_payload, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
