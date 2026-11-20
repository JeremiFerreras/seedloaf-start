"""Offline integration of the experimental CDP flow; no Seedloaf login."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from seedloaf_cdp import (
    LOGIN_URL, BUTTON_SNAPSHOT_JS, run_browser,
)

SERVER = "123e4567-e89b-42d3-a456-426614174000"
CONSOLE = "https://seedloaf.com/dashboard/" + SERVER + "/console"


class FakeCDP:
    def __init__(self, state="can_start", blocked=False):
        self.state = state
        self.blocked = blocked
        self.url = LOGIN_URL
        self.stage = "identifier"
        self.goto_calls = []
        self.click_calls = 0
        self.typed = []
        self.solved = 0

    def get_current_url(self):
        return self.url

    def is_element_visible(self, selector):
        if self.blocked:
            return False
        if selector == "#identifier-field":
            return self.stage == "identifier"
        if selector == "#password-field":
            return self.stage == "password"
        return False

    def get_title(self):
        return "Just a moment..." if self.blocked else "Seedloaf Sign In"

    def get_text(self, selector):
        return "Checking your browser" if self.blocked else "Sign in"

    def solve_captcha(self):
        self.solved += 1

    def type(self, selector, text):
        self.typed.append(selector)

    def press_keys(self, selector, keys):
        if selector == "#identifier-field":
            self.stage = "password"
        elif selector == "#password-field":
            self.stage = "signed_in"
            self.url = "https://seedloaf.com/dashboard"

    def goto(self, url):
        self.url = url
        self.goto_calls.append(url)

    def evaluate(self, script):
        if script == BUTTON_SNAPSHOT_JS:
            if self.state == "no_controls":
                return []
            if self.state == "ambiguous":
                return [
                    {"index": 0, "visible": True, "enabled": True,
                     "text": "Start", "aria": "", "title": ""},
                    {"index": 1, "visible": True, "enabled": True,
                     "text": "Stop", "aria": "", "title": ""},
                ]
            text = "Start" if self.state == "can_start" else "Stop"
            return [{"index": 0, "visible": True, "enabled": True,
                     "text": text, "aria": "", "title": ""}]
        return True  # safe_mark_start checked the matching current labels

    def click(self, selector):
        assert selector == 'button[data-safe-seedloaf-start="single-click"]'
        self.click_calls += 1
        self.state = "already_running"


class TestCDPFlow(unittest.TestCase):
    def setUp(self):
        patcher = patch("seedloaf_cdp.wait_until",
                        side_effect=lambda fn, seconds: fn())
        self.addCleanup(patcher.stop)
        patcher.start()

    def test_start_once_from_login_to_stop(self):
        cdp = FakeCDP("can_start")
        self.assertEqual(run_browser(cdp, SERVER, "test@example.test",
                                     "dummy-password"), 0)
        self.assertEqual(cdp.goto_calls, [CONSOLE])
        self.assertEqual(cdp.click_calls, 1)
        self.assertEqual(cdp.typed, ["#identifier-field", "#password-field"])

    def test_no_duplicate_start_if_running(self):
        cdp = FakeCDP("already_running")
        self.assertEqual(run_browser(cdp, SERVER, "test@example.test",
                                     "dummy-password"), 0)
        self.assertEqual(cdp.click_calls, 0)

    def test_readonly_never_clicks(self):
        cdp = FakeCDP("can_start")
        self.assertEqual(run_browser(cdp, SERVER, "test@example.test",
                                     "dummy-password", check_only=True), 0)
        self.assertEqual(cdp.click_calls, 0)

    def test_ambiguous_buttons_abort(self):
        cdp = FakeCDP("ambiguous")
        with self.assertRaises(RuntimeError):
            run_browser(cdp, SERVER, "test@example.test", "dummy-password")
        self.assertEqual(cdp.click_calls, 0)

    def test_no_controls_abort(self):
        cdp = FakeCDP("no_controls")
        with self.assertRaises(RuntimeError):
            run_browser(cdp, SERVER, "test@example.test", "dummy-password")
        self.assertEqual(cdp.click_calls, 0)

    def test_challenge_does_not_submit_any_credentials(self):
        cdp = FakeCDP(blocked=True)
        with self.assertRaises(RuntimeError):
            run_browser(cdp, SERVER, "test@example.test", "dummy-password")
        self.assertEqual(cdp.click_calls, 0)
        self.assertEqual(cdp.typed, [])
        self.assertEqual(cdp.solved, 1)

    def test_wrong_initial_site_aborts(self):
        cdp = FakeCDP()
        cdp.url = "https://evil.example/login"
        with self.assertRaises(RuntimeError):
            run_browser(cdp, SERVER, "test@example.test", "dummy-password")
        self.assertEqual(cdp.typed, [])
        self.assertEqual(cdp.goto_calls, [])


if __name__ == "__main__":
    unittest.main()
