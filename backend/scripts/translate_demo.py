#!/usr/bin/env python3
import json
import sys
import urllib.request


def _read_text(args: list[str]) -> str:
    if args:
        return " ".join(args).strip()
    data = sys.stdin.read().strip()
    return data


def main() -> int:
    # Usage:
    #   python backend/scripts/translate_demo.py "your text"
    #   echo "your text" | python backend/scripts/translate_demo.py
    text = _read_text(sys.argv[1:])
    if not text:
        print("ERROR: empty text", file=sys.stderr)
        return 2

    url = "http://127.0.0.1:9000/translate"
    payload = json.dumps({"english_text": text}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
    except Exception as exc:
        print(f"ERROR: request failed: {exc}", file=sys.stderr)
        return 1

    try:
        data = json.loads(body)
    except Exception:
        print(body)
        return 0

    print("english_text:", data.get("english_text", ""))
    print("chinese_text:", data.get("chinese_text", ""))
    print("status:", data.get("status", ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
