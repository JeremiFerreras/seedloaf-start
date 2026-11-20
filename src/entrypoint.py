"""Choose a start backend; optional read-only Minecraft protocol preflight."""
import os
import sys


def preflight():
    address = (os.environ.get("MINECRAFT_ADDRESS") or "").strip()
    if not address:
        return False
    from mc_probe import minecraft_status_auto
    status = minecraft_status_auto(address, timeout=3)
    if status and status.get("responding") is True:
        print("MINECRAFT_RESPONDE: el servidor ya contesta status; "
              "se evita una autenticacion web innecesaria.", flush=True)
        return True
    print("MINECRAFT_NO_CONFIRMADO: se intenta el metodo seleccionado.",
          flush=True)
    return False


def postflight(address, *, probe=None, pause=None, attempts=5):
    """After Start, check whether Minecraft Java eventually answers.

    No further Start clicks, even if every network attempt fails.
    This does NOT claim the world is joinable if the host uses a proxy.
    """
    if not address:
        return "not_configured"
    from mc_probe import minecraft_status_auto, parse_mc_address
    from time import sleep
    parse_mc_address(address)
    probe = probe or minecraft_status_auto
    pause = pause or sleep
    for i in range(max(0, min(attempts, 10))):
        if i:
            pause(7)
        reply = probe(address, timeout=3)
        if reply and reply.get("responding") is True:
            return "responding"
    return "not_confirmed"


def main():
    provider = (os.environ.get("START_BACKEND") or "browser").strip().lower()
    if provider not in ("official_api", "browser", "browser_cdp", "public_start"):
        raise ValueError("START_BACKEND no permitido.")
    # This never sends commands to the Minecraft server.
    # A proxy can answer status while a world is still starting.
    if preflight():
        return 0
    if provider == "official_api":
        from official_start import main as official_main
        result = official_main()
    elif provider == "public_start":
        from public_start import main as public_main
        result = public_main()
    elif provider == "browser_cdp":
        from seedloaf_cdp import main as cdp_main
        result = cdp_main()
    else:
        from seedloaf_start import main as browser_main
        result = browser_main()
    # A completed browser/API request is NOT automatically Minecraft readiness.
    # Probe only after requested starts, not on read-only checks.
    if result == 0 and (os.environ.get("CHECK_ONLY") or "").lower() != "true":
        address = (os.environ.get("MINECRAFT_ADDRESS") or "").strip()
        if address:
            verdict = postflight(address)
            print("POSTFLIGHT_MINECRAFT estado=" + verdict, flush=True)
    return result


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print("CONFIG_ERROR: " + str(exc), flush=True)
        raise SystemExit(1)
