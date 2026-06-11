"""
Reference client for the OneTrust automation backend.

This is a DOCUMENTATION REFERENCE only — not required for normal skill consumption.
The skill is designed to be used from GitHub Copilot Chat, not by running this script.

Usage (if you want to call the APIs directly from Python):
    python python-client-reference.py https://www.example.com
"""

import json
import sys
import httpx

BASE_URL = "http://127.0.0.1:8000"


def check_health() -> bool:
    resp = httpx.get(f"{BASE_URL}/health", timeout=5)
    data = resp.json()
    print(f"Health: {data}")
    return resp.status_code == 200


def auth_login() -> dict:
    resp = httpx.post(f"{BASE_URL}/auth/login", json={}, timeout=120)
    return resp.json()


def add_app(url: str) -> dict:
    resp = httpx.post(f"{BASE_URL}/add_app", json={"url": url}, timeout=300)
    return resp.json()


def filter_code(url: str) -> dict:
    resp = httpx.post(f"{BASE_URL}/filter_code", json={"url": url}, timeout=300)
    return resp.json()


def run(url: str) -> None:
    print(f"\n--- OneTrust automation for {url} ---\n")

    if not check_health():
        print("Backend not running. Start uvicorn first.")
        return

    print("Step 1: Login...")
    login = auth_login()
    print(json.dumps(login, indent=2))
    if login.get("status") not in ("logged in",):
        print(f"Login issue: {login.get('status')} — {login.get('message')}")
        return

    print("\nStep 2: Add app...")
    add = add_app(url)
    print(json.dumps(add, indent=2))
    if add.get("status") != "website configuration confirmed":
        print(f"add_app failed at step: {add.get('failed_step') or 'unknown'}")
        return

    print("\nStep 3: Filter code...")
    fc = filter_code(url)
    print(json.dumps(fc, indent=2))
    if fc.get("status") == "data_domain_script extracted":
        print(f"\nSUCCESS: data-domain-script = {fc['data_domain_script']}")
    else:
        print(f"\nFAILED: {fc.get('status')} — {fc.get('message')}")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "https://www.example.com"
    run(target)
