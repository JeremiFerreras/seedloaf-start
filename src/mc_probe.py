"""Optional Minecraft Java status probe.

Only enabled for a user-configured *.seedloaf.gg hostname.
A successful STATUS reply is evidence that Minecraft speaks its protocol,
but a proxy might answer without the underlying world fully loaded.
No start/stop command is transmitted by this module.
"""
import ipaddress
import json
import re
import socket


class ProbeError(ValueError):
    pass


def parse_mc_address(raw):
    if not isinstance(raw, str) or not raw or len(raw) > 250:
        raise ProbeError("MINECRAFT_ADDRESS no valida.")
    if "://" in raw or "/" in raw or "@" in raw or "#" in raw or "?" in raw:
        raise ProbeError("Usa subdominio.seedloaf.gg[:puerto] sin URL.")
    parts = raw.rsplit(":", 1)
    if len(parts) == 2:
        host, port_text = parts
        if not port_text.isdecimal():
            raise ProbeError("Puerto Minecraft invalido.")
        port = int(port_text)
    else:
        host, port = raw, 25565
    host = host.rstrip(".").lower()
    seedloaf_host = bool(re.fullmatch(
        r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9-]+)*\.seedloaf\.gg",
        host
    ))
    if not seedloaf_host:
        # Numerical Java IPs are supported only if globally routable:
        # never probe loopback, LAN, link-local, broadcast or reserved ranges.
        try:
            ip = ipaddress.IPv4Address(host)
            if not ip.is_global or ip.is_multicast or ip.is_reserved:
                raise ProbeError("La IP no es publica.")
        except ipaddress.AddressValueError as exc:
            raise ProbeError(
                "Solo *.seedloaf.gg o una direccion IPv4 publica."
            ) from exc
    if port < 1 or port > 65535:
        raise ProbeError("Puerto Minecraft fuera de rango.")
    return host, port


def varint(value):
    if not isinstance(value, int) or value < 0 or value > 0x7FFFFFFF:
        raise ProbeError("Numero VarInt no valido.")
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        out.append(byte | 0x80 if value else byte)
        if not value:
            return bytes(out)


def receive_exact(sock, n):
    if n < 0 or n > 65536:
        raise ProbeError("Longitud de paquete invalida.")
    parts = []
    while n:
        data = sock.recv(n)
        if not data:
            raise ProbeError("Paquete incompleto.")
        parts.append(data)
        n -= len(data)
    return b"".join(parts)


def read_varint(sock):
    value = 0
    for shift in range(0, 35, 7):
        byte = receive_exact(sock, 1)[0]
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            if value > 0x7FFFFFFF:
                raise ProbeError("VarInt demasiado grande.")
            return value
    raise ProbeError("VarInt no termino.")


def packet(payload):
    return varint(len(payload)) + payload


def minecraft_status(address, timeout=3, connect=socket.create_connection,
                     connect_override=None):
    """Returns protocol confirmation, not full world readiness."""
    host, port = parse_mc_address(address)
    destination = connect_override or (host, port)
    # One isolated status query; no login / commands / packets that start a world.
    h = host.encode("ascii")
    handshake = (
        varint(0) + varint(0) + varint(len(h)) + h +
        port.to_bytes(2, "big") + varint(1)
    )
    try:
        with connect(destination, timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(packet(handshake) + packet(varint(0)))
            frame_size = read_varint(sock)
            if frame_size < 2 or frame_size > 65536:
                return None
            response = receive_exact(sock, frame_size)
    except (OSError, TimeoutError, ProbeError, ValueError):
        return None
    try:
        class Buffer:
            def __init__(self, data):
                self.data, self.pos = data, 0
            def recv(self, n):
                part = self.data[self.pos:self.pos + n]
                self.pos += len(part)
                return part
        reader = Buffer(response)
        if read_varint(reader) != 0:
            return None
        body_len = read_varint(reader)
        if body_len <= 0 or body_len > 65536:
            return None
        body = receive_exact(reader, body_len)
        if reader.pos != len(response):
            return None
        info = json.loads(body.decode("utf-8"))
        if not isinstance(info, dict):
            return None
        if not isinstance(info.get("version"), dict):
            return None
        if not isinstance(info.get("players"), dict):
            return None
        return {"responding": True}
    except (ValueError, UnicodeError, ProbeError, TypeError):
        return None



def lookup_mc_srv(host, resolver=None):
    """Resolve the standard Minecraft Java SRV record, without logging addresses.

    DNS data is not authentication. Invalid/missing records fall back to :25565.
    A custom (explicit) port always wins over the SRV record.
    """
    if resolver is None:
        try:
            import dns.resolver
        except ImportError:
            return None
        def resolver(qname):
            return dns.resolver.resolve(qname, "SRV", lifetime=2.5)

    try:
        answers = resolver("_minecraft._tcp." + host)
        valid = []
        for a in answers:
            target = str(a.target).rstrip(".").lower()
            port = int(a.port)
            priority = int(a.priority)
            weight = int(a.weight)
            if not (1 <= port <= 65535 and 0 <= priority <= 65535
                    and 0 <= weight <= 65535):
                continue
            if (len(target) > 253 or not re.fullmatch(
                    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9-]+)+",
                    target)):
                continue
            if target.endswith((".local", ".localhost", ".internal", ".test")):
                continue
            valid.append((priority, -weight, target, port))
        if not valid:
            return None
        best = min(valid)
        return best[2], best[3]
    except Exception:
        return None


def minecraft_status_auto(address, timeout=3, *, srv_lookup=lookup_mc_srv,
                          probe=minecraft_status):
    """Java-compatible SRV discovery for bare Seedloaf domains.

    Explicit ports such as server.seedloaf.gg:50690 never trigger SRV.
    The original hostname is preserved in the Minecraft handshake.
    """
    host, port = parse_mc_address(address)
    if ":" in address or re.fullmatch(r"\d+\.\d+\.\d+\.\d+", host):
        return probe(address, timeout=timeout)
    destination = srv_lookup(host)
    if destination is None:
        return probe(address, timeout=timeout)
    return probe(address, timeout=timeout, connect_override=destination)
