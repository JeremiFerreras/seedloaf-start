"""Early read-only Minecraft status check. Never logs the configured address.

Only writes a boolean to GITHUB_OUTPUT. This can skip expensive browser
installation if the Minecraft protocol already responds reliably.
"""
import os
import sys
import time

from mc_probe import ProbeError, minecraft_status_auto, parse_mc_address


def evaluate(address, *, probe=minecraft_status_auto, pause=time.sleep):
    if not address:
        return "not_configured"
    parse_mc_address(address)
    # Verify twice. A single transient answer is insufficient to claim online.
    first = probe(address, timeout=3)
    if not first or first.get("responding") is not True:
        return "not_confirmed"
    pause(0.7)
    second = probe(address, timeout=3)
    return "online" if second and second.get("responding") is True else "not_confirmed"


def main():
    address = (os.environ.get("MINECRAFT_ADDRESS") or "").strip()
    try:
        result = evaluate(address)
    except (ProbeError, ValueError):
        # Never reveal the hostname or IP from the private secret.
        print("PREFLIGHT_CONFIG_ERROR: formato invalido de MINECRAFT_ADDRESS; "
              "admite *.seedloaf.gg[:puerto] o IPv4 publica[:puerto].",
              flush=True)
        return 2
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as stream:
            stream.write("online=" + ("true" if result == "online" else "false") + "\n")
    print("PREFLIGHT resultado=" + result + " (sin direccion ni datos sensibles)",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
