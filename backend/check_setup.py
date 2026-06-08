import sys


def main() -> int:
    print(f"Python executable: {sys.executable}")
    imports = [
        "fastapi",
        "pydantic",
        "pydantic_settings",
        "playwright.async_api",
        "app.main",
    ]
    for module_name in imports:
        try:
            __import__(module_name)
        except Exception as exc:  # noqa: BLE001
            print(f"SETUP FAILED: could not import {module_name}: {exc}")
            return 1
    print("SETUP OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
