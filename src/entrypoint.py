"""Single selected start backend. No fallback between providers after errors."""
import os
import sys


def main():
    provider = os.environ.get("START_BACKEND", "browser").strip().lower()
    if provider == "official_api":
        from official_start import main as official_main
        return official_main()
    if provider == "browser":
        from seedloaf_start import main as browser_main
        return browser_main()
    raise ValueError("START_BACKEND no permitido: solo browser u official_api.")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print("CONFIG_ERROR: " + str(exc), flush=True)
        raise SystemExit(1)
