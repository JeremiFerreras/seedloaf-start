"""Stress tests for the early Minecraft probe; entirely offline."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fastcheck import evaluate, main

ADDR = "friend.seedloaf.gg:55021"


class TestEarlyProbe(unittest.TestCase):
    def test_empty_address(self):
        def unexpected(*a, **k):
            raise AssertionError("unexpected network call")
        self.assertEqual(evaluate("", probe=unexpected), "not_configured")

    def test_public_ipv4_address(self):
        calls = []
        def fake(address, timeout):
            calls.append((address, timeout))
            return {"responding": True}
        self.assertEqual(evaluate("8.8.8.8:25565", probe=fake,
                                  pause=lambda _: None), "online")
        self.assertEqual(len(calls), 2)

    def test_two_valid_responses(self):
        calls = []
        def fake(address, timeout):
            calls.append((address, timeout))
            return {"responding": True}
        self.assertEqual(evaluate(ADDR, probe=fake, pause=lambda _: None), "online")
        self.assertEqual(calls, [(ADDR, 3), (ADDR, 3)])

    def test_unconfirmed_no_second_query(self):
        calls = []
        def fake(address, timeout):
            calls.append(address)
            return None
        self.assertEqual(evaluate(ADDR, probe=fake,
                                  pause=lambda _: None), "not_confirmed")
        self.assertEqual(len(calls), 1)

    def test_transient_first_answer_not_enough(self):
        responses = iter([{"responding": True}, None])
        self.assertEqual(evaluate(ADDR, probe=lambda *a, **k: next(responses),
                                  pause=lambda _: None), "not_confirmed")

    def test_false_flag_fails_closed(self):
        responses = iter([{"responding": True}, {"responding": False}])
        self.assertEqual(evaluate(ADDR, probe=lambda *a, **k: next(responses),
                                  pause=lambda _: None), "not_confirmed")

    def test_private_ipv4_rejected(self):
        for raw in ("127.0.0.1", "10.0.0.1", "192.168.1.1",
                    "169.254.1.1", "172.20.0.1", "0.0.0.0"):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    evaluate(raw, probe=lambda *a, **k: {"responding": True})

    def test_custom_bad_domain(self):
        for raw in ("evil.example", "x.seedloaf.gg.evil.example",
                    "http://name.seedloaf.gg", "name.seedloaf.gg:99999"):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    evaluate(raw)

    def test_no_output_file_leaves_no_artifact(self):
        with patch.dict(os.environ, {"MINECRAFT_ADDRESS": ""}, clear=True):
            self.assertEqual(main(), 0)

    def test_output_false_when_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            output = os.path.join(directory, "out.txt")
            with patch.dict(os.environ,
                            {"GITHUB_OUTPUT": output, "MINECRAFT_ADDRESS": ""}):
                self.assertEqual(main(), 0)
            self.assertEqual(Path(output).read_text(), "online=false\n")

    def test_output_error_does_not_include_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            output = os.path.join(directory, "out.txt")
            with patch.dict(os.environ,
                            {"GITHUB_OUTPUT": output,
                             "MINECRAFT_ADDRESS": "127.0.0.1"}):
                self.assertEqual(main(), 2)
            self.assertFalse(Path(output).exists())

    def test_1500_combinations_of_status_responses(self):
        # Each test uses synthetic status replies, not Minecraft connections.
        cases = [None, {"responding": False}, {"responding": True}]
        for i in range(1500):
            first = cases[i % 3]
            second = cases[(i // 3) % 3]
            values = iter([first, second])
            calls = []
            def fake(*args, **kwargs):
                calls.append(1)
                return next(values)
            expected = ("online" if first == second == {"responding": True}
                        else "not_confirmed")
            self.assertEqual(evaluate(ADDR, probe=fake,
                                      pause=lambda _: None), expected)
            self.assertLessEqual(len(calls), 2)


class TestPostflight(unittest.TestCase):
    def test_no_address(self):
        from entrypoint import postflight
        self.assertEqual(postflight(""), "not_configured")

    def test_running_on_first_probe(self):
        from entrypoint import postflight
        times = []
        def probe(*a, **k):
            times.append(1)
            return {"responding": True}
        self.assertEqual(postflight(ADDR, probe=probe, pause=lambda _: None),
                         "responding")
        self.assertEqual(len(times), 1)

    def test_eventually_ready_after_network_errors(self):
        from entrypoint import postflight
        outputs = iter([None, None, {"responding": True}])
        sleep_calls = []
        self.assertEqual(postflight(ADDR, probe=lambda *a, **k: next(outputs),
                                    pause=lambda n: sleep_calls.append(n)),
                         "responding")
        self.assertEqual(sleep_calls, [7, 7])

    def test_not_confirmed_after_five_failures(self):
        from entrypoint import postflight
        calls = []
        result = postflight(ADDR, probe=lambda *a, **k: calls.append(1),
                            pause=lambda _: None)
        self.assertEqual(result, "not_confirmed")
        self.assertEqual(len(calls), 5)

    def test_attempts_capped_at_ten(self):
        from entrypoint import postflight
        calls = []
        result = postflight(ADDR, probe=lambda *a, **k: calls.append(1),
                            pause=lambda _: None, attempts=500)
        self.assertEqual(result, "not_confirmed")
        self.assertEqual(len(calls), 10)

    def test_invalid_address_before_probe(self):
        from entrypoint import postflight
        def unexpected(*args, **kwargs):
            raise AssertionError("Bad address should never be probed")
        with self.assertRaises(ValueError):
            postflight("127.0.0.1", probe=unexpected)

    def test_minecraft_up_early_skips_all_web(self):
        from unittest.mock import patch
        from entrypoint import main as run
        with patch.dict(os.environ, {"START_BACKEND": "browser",
                                     "MINECRAFT_ADDRESS": ADDR}):
            with patch("entrypoint.preflight", return_value=True), \
                 patch("entrypoint.postflight") as later, \
                 patch("seedloaf_start.main") as browser:
                self.assertEqual(run(), 0)
                later.assert_not_called()
                browser.assert_not_called()

    def test_check_only_never_postflights(self):
        from unittest.mock import patch
        from entrypoint import main as run
        with patch.dict(os.environ, {"START_BACKEND": "browser",
                                     "CHECK_ONLY": "true",
                                     "MINECRAFT_ADDRESS": ADDR}):
            with patch("entrypoint.preflight", return_value=False), \
                 patch("entrypoint.postflight") as later, \
                 patch("seedloaf_start.main", return_value=0):
                self.assertEqual(run(), 0)
                later.assert_not_called()

    def test_start_calls_postflight_once(self):
        from unittest.mock import patch
        from entrypoint import main as run
        with patch.dict(os.environ, {"START_BACKEND": "browser",
                                     "CHECK_ONLY": "false",
                                     "MINECRAFT_ADDRESS": ADDR}):
            with patch("entrypoint.preflight", return_value=False), \
                 patch("entrypoint.postflight", return_value="not_confirmed") as after, \
                 patch("seedloaf_start.main", return_value=0):
                self.assertEqual(run(), 0)
                after.assert_called_once_with(ADDR)

    def test_failure_never_calls_postflight(self):
        from unittest.mock import patch
        from entrypoint import main as run
        with patch.dict(os.environ, {"START_BACKEND": "browser",
                                     "CHECK_ONLY": "false",
                                     "MINECRAFT_ADDRESS": ADDR}):
            with patch("entrypoint.preflight", return_value=False), \
                 patch("entrypoint.postflight") as after, \
                 patch("seedloaf_start.main", return_value=1):
                self.assertEqual(run(), 1)
                after.assert_not_called()

    def test_ip_multicast_forbidden(self):
        for ip in ("224.0.0.1", "239.255.255.255", "240.0.0.1"):
            with self.subTest(ip=ip):
                with self.assertRaises(ValueError):
                    evaluate(ip)


if __name__ == "__main__":
    unittest.main()
