import random
import socket
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mc_probe import (
    ProbeError, minecraft_status, packet, parse_mc_address, read_varint, varint,
)


class FakeSocket:
    def __init__(self, response=b"", chunks=1, broken=False):
        self.payload = response
        self.chunks = chunks
        self.broken = broken
        self.requests = []
        self.timeout = None

    def settimeout(self, value):
        self.timeout = value

    def sendall(self, data):
        if self.broken:
            raise OSError("intentional network failure")
        self.requests.append(data)

    def recv(self, count):
        if self.broken:
            raise TimeoutError("intentional network timeout")
        amount = max(1, min(count, self.chunks))
        head, self.payload = self.payload[:amount], self.payload[amount:]
        return head

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def status_packet(obj):
    import json
    body = json.dumps(obj).encode("utf-8")
    return packet(varint(0) + varint(len(body)) + body)


VALID_RESPONSE = status_packet({
    "version": {"name": "NeoForge", "protocol": 767},
    "players": {"online": 0, "max": 6},
    "description": "Server ready",
})


class TestHostValidation(unittest.TestCase):
    def test_domain_default_port(self):
        self.assertEqual(parse_mc_address("myserver.seedloaf.gg"),
                         ("myserver.seedloaf.gg", 25565))

    def test_domain_custom_port(self):
        self.assertEqual(parse_mc_address("myserver.seedloaf.gg:27364"),
                         ("myserver.seedloaf.gg", 27364))

    def test_lowercase_and_trailing_dot(self):
        self.assertEqual(parse_mc_address("MyServer.SeedLoaf.GG."),
                         ("myserver.seedloaf.gg", 25565))

    def test_invalid_domains(self):
        for addr in ("", None, 12, "127.0.0.1", "localhost", "::1",
                     "https://x.seedloaf.gg", "x.seedloaf.gg.evil.com",
                     "seedloaf.gg", "evil.seedloaf.com", "user@x.seedloaf.gg",
                     "x.seedloaf.gg:0", "x.seedloaf.gg:65536",
                     "x.seedloaf.gg:abc", "x.seedloaf.gg/a",
                     "x.seedloaf.gg#foo", "x.seedloaf.gg?x=1",
                     "-bad.seedloaf.gg", "x.seedloaf.gg:80:99"):
            with self.subTest(address=repr(addr)):
                with self.assertRaises(ProbeError):
                    parse_mc_address(addr)


class TestProtocol(unittest.TestCase):
    def test_varint_roundtrip(self):
        for value in (0, 1, 127, 128, 255, 16384, 2147483647):
            payload = varint(value)
            s = FakeSocket(payload)
            self.assertEqual(read_varint(s), value)

    def test_varint_random_2000(self):
        rng = random.Random(2031)
        for _ in range(2000):
            n = rng.randint(0, 2147483647)
            self.assertEqual(read_varint(FakeSocket(varint(n), chunks=1)), n)

    def test_varint_malformed(self):
        for body in (b"", b"\x80", b"\x80" * 5, b"\xff" * 5, b"\xff" * 6):
            with self.subTest(body=body):
                with self.assertRaises(ProbeError):
                    read_varint(FakeSocket(body))

    def test_varint_out_of_range(self):
        for n in (-1, 0x80000000, "abc", None):
            with self.subTest(n=n):
                with self.assertRaises(ProbeError):
                    varint(n)


class TestStatusProbe(unittest.TestCase):
    def test_valid_response(self):
        sock = FakeSocket(VALID_RESPONSE, chunks=2)
        result = minecraft_status("myserver.seedloaf.gg",
                                  connect=lambda address, timeout: sock)
        self.assertEqual(result, {"responding": True})
        self.assertEqual(sock.timeout, 3)
        self.assertEqual(len(sock.requests), 1)

    def test_valid_response_read_one_byte_at_time(self):
        sock = FakeSocket(VALID_RESPONSE, chunks=1)
        self.assertEqual(minecraft_status(
            "test.seedloaf.gg", connect=lambda addr, timeout: sock),
            {"responding": True})

    def test_empty_reply(self):
        self.assertIsNone(minecraft_status(
            "test.seedloaf.gg",
            connect=lambda addr, timeout: FakeSocket(b"")))

    def test_broken_connection(self):
        self.assertIsNone(minecraft_status(
            "test.seedloaf.gg",
            connect=lambda addr, timeout: FakeSocket(broken=True)))

    def test_connection_timeout(self):
        def timeout(addr, timeout):
            raise socket.timeout("simulated")
        self.assertIsNone(minecraft_status("test.seedloaf.gg", connect=timeout))

    def test_http_html_rejected(self):
        self.assertIsNone(minecraft_status(
            "test.seedloaf.gg",
            connect=lambda addr, timeout: FakeSocket(b"HTTP/1.1 200 OK\r\n")))

    def test_missing_version_rejected(self):
        self.assertIsNone(minecraft_status(
            "test.seedloaf.gg",
            connect=lambda addr, timeout: FakeSocket(status_packet(
                {"players": {"online": 2}}))))

    def test_missing_players_rejected(self):
        self.assertIsNone(minecraft_status(
            "test.seedloaf.gg",
            connect=lambda addr, timeout: FakeSocket(status_packet(
                {"version": {"name": "NeoForge"}}))))

    def test_response_too_large(self):
        self.assertIsNone(minecraft_status(
            "test.seedloaf.gg",
            connect=lambda addr, timeout: FakeSocket(varint(65537))))

    def test_random_broken_replies_1000(self):
        rng = random.Random(30938)
        for _ in range(1000):
            blob = bytes(rng.randrange(256) for _ in range(rng.randrange(0, 24)))
            status = minecraft_status(
                "test.seedloaf.gg",
                connect=lambda addr, timeout, b=blob: FakeSocket(b))
            self.assertIsNone(status)


if __name__ == "__main__":
    unittest.main()
