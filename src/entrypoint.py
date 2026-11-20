"""Choose a start backend; optional read-only Minecraft protocol preflight."""
import os
import sys


def preflight():
    address = (os.environ.get("MINECRAFT_ADDRESS") or "").strip()
    if not address:
        return False
    from mc_probe import minecraft_status
    status = minecraft_status(address, timeout=3)
    if status and status.get("responding") is True:
        print("MINECRAFT_RESPONDE: el servidor ya contesta status; "
              "se evita una autenticacion web innecesaria.", flush=True)
        return True
    print("MINECRAFT_NO_CONFIRMADO: se intenta el metodo seleccionado.",
          flush=True)
    return False


def main():
    provider = (os.environ.get("START_BACKEND") or "browser").strip().lower()
    if provider not in ("official_api", "browser"):
        raise ValueError("START_BACKEND no permitido.")
    # This never sends commands to the Minecraft server.
    # A proxy can answer status while a world is still starting.
    if preflight():
        return 0
    if provider == "official_api":
        from official_start import main as official_main
        return official_main()
    from seedloaf_start import main as browser_main
    return browser_main()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print("CONFIG_ERROR: " + str(exc), flush=True)
        raise SystemExit(1)
