"""Deterministic Minecraft Java DNS SRV tests. No external DNS/network."""
import random
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mc_probe import lookup_mc_srv, minecraft_status, minecraft_status_auto


HOST = "serverdejfxdchess.seedloaf.gg"
BARE = HOST
EXPLICIT = HOST + ":50690"


def record(target, port, priority=0, weight=0):
    return SimpleNamespace(target=target, port=port,
                           priority=priority, weight=weight)


class TestSRVRecords(unittest.TestCase):
    def test_correct_minecraft_srv_question(self):
        q = []
        def resolve(name):
            q.append(name)
            return [record("node1.seedloaf.gg.", 50690)]
        self.assertEqual(lookup_mc_srv(HOST, resolve),
                         ("node1.seedloaf.gg", 50690))
        self.assertEqual(q, ["_minecraft._tcp." + HOST])

    def test_dns_error_means_fallback(self):
        def fail(name):
            raise TimeoutError("DNS timeout injected")
        self.assertIsNone(lookup_mc_srv(HOST, fail))

    def test_no_srv_means_fallback(self):
        self.assertIsNone(lookup_mc_srv(HOST, lambda _: []))

    def test_lower_priority_number_wins(self):
        answers = [record("high.seedloaf.gg.", 53000, 15),
                   record("low.seedloaf.gg.", 50690, 0)]
        self.assertEqual(lookup_mc_srv(HOST, lambda _: answers),
                         ("low.seedloaf.gg", 50690))

    def test_weight_preference_on_same_priority(self):
        answers = [record("one.seedloaf.gg.", 53000, 0, 5),
                   record("two.seedloaf.gg.", 50690, 0, 15)]
        self.assertEqual(lookup_mc_srv(HOST, lambda _: answers),
                         ("two.seedloaf.gg", 50690))

    def test_bad_port_is_ignored(self):
        answers = [record("bad.seedloaf.gg.", 0),
                   record("good.seedloaf.gg.", 50690)]
        self.assertEqual(lookup_mc_srv(HOST, lambda _: answers),
                         ("good.seedloaf.gg", 50690))

    def test_overflow_port_is_ignored(self):
        self.assertIsNone(lookup_mc_srv(
            HOST, lambda _: [record("node.seedloaf.gg.", 65536)]))

    def test_localhost_target_rejected(self):
        self.assertIsNone(lookup_mc_srv(
            HOST, lambda _: [record("myhost.local.", 50690)]))

    def test_invalid_target_rejected(self):
        bad = ["node", "node..seedloaf.gg", "bad target.com",
               "_hidden.seedloaf.gg", "", "localhost",
               "a" * 64 + ".seedloaf.gg"]
        for target in bad:
            with self.subTest(target=target):
                self.assertIsNone(lookup_mc_srv(
                    HOST, lambda _: [record(target, 50690)]))

    def test_malformed_record_rejected(self):
        self.assertIsNone(lookup_mc_srv(
            HOST, lambda _: [object()]))

    def test_srv_changes_connect_target_but_preserves_virtual_host(self):
        class FakeSocket:
            def __init__(self):
                self.sent = b""
                self.answer = b""
            def settimeout(self, value):
                pass
            def sendall(self, data):
                self.sent += data
            def recv(self, n):
                return b""
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
        sock = FakeSocket()
        destinations = []
        def connect(dest, timeout):
            destinations.append(dest)
            return sock
        self.assertIsNone(minecraft_status(
            BARE, connect=connect, connect_override=("node.seedloaf.gg", 50690)))
        self.assertEqual(destinations, [("node.seedloaf.gg", 50690)])
        self.assertIn(HOST.encode("ascii"), sock.sent)

    def test_explicit_port_must_skip_dns(self):
        calls = []
        def dns(name):
            raise AssertionError("Explicit port should never perform SRV lookup")
        def probe(addr, **kw):
            calls.append((addr, kw))
            return {"responding": True}
        self.assertEqual(minecraft_status_auto(EXPLICIT, srv_lookup=dns,
                                               probe=probe),
                         {"responding": True})
        self.assertEqual(calls, [(EXPLICIT, {"timeout": 3})])

    def test_public_ipv4_skips_srv(self):
        def dns(name):
            raise AssertionError("IPv4 should never perform SRV lookup")
        seen = []
        def probe(addr, **kwargs):
            seen.append(addr)
            return {"responding": True}
        minecraft_status_auto("8.8.8.8:50690", srv_lookup=dns, probe=probe)
        self.assertEqual(seen, ["8.8.8.8:50690"])

    def test_bare_domain_uses_valid_srv(self):
        seen = []
        def probe(addr, **kwargs):
            seen.append((addr, kwargs.get("connect_override")))
            return {"responding": True}
        result = minecraft_status_auto(BARE,
            srv_lookup=lambda _: ("node.seedloaf.gg", 50690), probe=probe)
        self.assertEqual(result, {"responding": True})
        self.assertEqual(seen, [(BARE, ("node.seedloaf.gg", 50690))])

    def test_bare_domain_falls_back_without_srv(self):
        seen = []
        def probe(addr, **kwargs):
            seen.append((addr, kwargs.get("timeout")))
            return {"responding": True}
        minecraft_status_auto(BARE, srv_lookup=lambda _: None, probe=probe)
        self.assertEqual(seen, [(BARE, 3)])

    def test_srv_target_validation_never_crashes_on_fuzz(self):
        rng = random.Random(20261120)
        alphabet = "abcdefghijklmnopqrstuvwxyz0123456789.:@/?_ #"
        for _ in range(3000):
            text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 50)))
            result = lookup_mc_srv(HOST,
                lambda _, text=text: [record(text, 50690)])
            if result is not None:
                self.assertEqual(result[1], 50690)
                self.assertNotIn(" ", result[0])


if __name__ == "__main__":
    unittest.main()
