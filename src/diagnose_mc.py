"""Read-only Minecraft Java network diagnostic; never visits Seedloaf web.

Output categories only. Does not log the server address or DNS targets.
"""
import os
import sys

from mc_probe import lookup_mc_srv, minecraft_status, parse_mc_address


def diagnose(address, *, srv_lookup=lookup_mc_srv, probe=minecraft_status):
    host, port = parse_mc_address(address)
    direct = probe(address, timeout=3)
    result = {"configured": "responding" if direct else "no_response",
              "srv_record": "not_checked", "srv_probe": "not_checked"}
    if host.endswith(".seedloaf.gg"):
        record = srv_lookup(host)
        result["srv_record"] = "found" if record is not None else "absent_or_unavailable"
        if record is not None and (host, port) != record:
            # Keep the original host in the handshake for virtual hosting.
            reply = probe(host, timeout=3, connect_override=record)
            result["srv_probe"] = "responding" if reply else "no_response"
    return result


def main():
    address = (os.environ.get("MINECRAFT_ADDRESS") or "").strip()
    if not address:
        print("DIAG_MC config=missing", flush=True)
        return 2
    try:
        result = diagnose(address)
    except ValueError:
        print("DIAG_MC config=invalid", flush=True)
        return 2
    print("DIAG_MC " + " ".join(f"{k}={v}" for k, v in result.items()),
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
