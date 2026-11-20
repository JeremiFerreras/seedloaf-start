"""Offline tests for Minecraft diagnostic; no DNS or TCP connections."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from diagnose_mc import diagnose

ADDRESS = "serverdejfxdchess.seedloaf.gg:50690"
HOST = "serverdejfxdchess.seedloaf.gg"


class TestConnectionDiagnostics(unittest.TestCase):
    def test_direct_replies_without_srv(self):
        calls = []
        def probe(addr, **kwargs):
            calls.append((addr, kwargs))
            return {"responding": True}
        report = diagnose(ADDRESS, srv_lookup=lambda _: None, probe=probe)
        self.assertEqual(report["configured"], "responding")
        self.assertEqual(report["srv_record"], "absent_or_unavailable")
        self.assertEqual(report["srv_probe"], "not_checked")
        self.assertEqual(len(calls), 1)

    def test_no_reply_reports_false_without_start(self):
        def probe(*a, **kw):
            return None
        report = diagnose(ADDRESS, srv_lookup=lambda _: None, probe=probe)
        self.assertEqual(report["configured"], "no_response")

    def test_srv_port_different_checks_second_destination(self):
        calls = []
        def probe(addr, **kwargs):
            calls.append((addr, kwargs.get("connect_override")))
            return {"responding": True} if kwargs.get("connect_override") else None
        report = diagnose(ADDRESS,
                          srv_lookup=lambda _: ("node.seedloaf.gg", 55001),
                          probe=probe)
        self.assertEqual(report["configured"], "no_response")
        self.assertEqual(report["srv_record"], "found")
        self.assertEqual(report["srv_probe"], "responding")
        self.assertEqual(calls, [(ADDRESS, None),
                                 (HOST, ("node.seedloaf.gg", 55001))])

    def test_srv_same_origin_skips_duplicate_probe(self):
        calls = []
        def probe(addr, **kwargs):
            calls.append(addr)
            return {"responding": True}
        report = diagnose(ADDRESS,
            srv_lookup=lambda _: (HOST, 50690), probe=probe)
        self.assertEqual(report["srv_probe"], "not_checked")
        self.assertEqual(len(calls), 1)

    def test_ipv4_never_looks_up_srv(self):
        def error(host):
            raise AssertionError("IPv4 must not trigger SRV")
        report = diagnose("8.8.8.8:50690", srv_lookup=error,
                          probe=lambda *a, **kw: None)
        self.assertEqual(report["srv_record"], "not_checked")

    def test_invalid_address_never_probed(self):
        def error(*a, **k):
            raise AssertionError("Invalid address must never be contacted")
        with self.assertRaises(ValueError):
            diagnose("http://localhost", srv_lookup=error, probe=error)


if __name__ == "__main__":
    unittest.main()
