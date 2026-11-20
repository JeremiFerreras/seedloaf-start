"""Deterministic safety tests of the experimental CDP backend."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from seedloaf_cdp import (
    BUTTON_SNAPSHOT_JS, classify_snapshot, safe_mark_start, state_from_browser,
    wait_until, limited_challenge,
)
SERVER = "123e4567-e89b-42d3-a456-426614174000"
CONSOLE = "https://seedloaf.com/dashboard/" + SERVER + "/console"


def button(text, *, index=0, visible=True, enabled=True):
    return {"index": index, "text": text, "aria": "",
            "title": "", "visible": visible, "enabled": enabled}


class TestCDPSnapshot(unittest.TestCase):
    def test_one_start(self):
        state, item = classify_snapshot([button("Start")])
        self.assertEqual(state, "can_start")
        self.assertEqual(item["index"], 0)

    def test_stop_already_running(self):
        self.assertEqual(classify_snapshot([button("Stop")])[0],
                         "already_running")

    def test_two_starts_fails_closed(self):
        self.assertEqual(classify_snapshot([
            button("Start"), button("Start", index=1)])[0], "ambiguous")

    def test_start_stop_fails_closed(self):
        self.assertEqual(classify_snapshot([
            button("Start"), button("Stop", index=1)])[0], "ambiguous")

    def test_hidden_start_ignored(self):
        self.assertEqual(classify_snapshot([
            button("Start", visible=False)])[0], "not_found")

    def test_disabled_start_ignored(self):
        self.assertEqual(classify_snapshot([
            button("Start", enabled=False)])[0], "not_found")

    def test_restart_not_start(self):
        self.assertEqual(classify_snapshot([button("Restart")])[0], "not_found")

    def test_list_validation(self):
        for b in (None, {}, True, "", 3):
            with self.subTest(value=b):
                self.assertEqual(classify_snapshot(b)[0], "ambiguous")

    def test_bad_index_rejected(self):
        for index in (-1, None, "0", True):
            with self.subTest(index=index):
                self.assertEqual(classify_snapshot([
                    button("Start", index=index)])[0], "ambiguous")

    def test_no_controls(self):
        self.assertEqual(classify_snapshot([])[0], "not_found")

    def test_wrong_url_never_reads_controls(self):
        class C:
            def get_current_url(self): return "https://evil.test/"
            def evaluate(self, script):
                raise AssertionError("Should not inspect wrong site")
        self.assertEqual(state_from_browser(C(), SERVER), ("wrong_page", None))

    def test_exact_url_evaluates_snapshot(self):
        class C:
            def get_current_url(self): return CONSOLE
            def evaluate(self, script):
                self.script = script
                return [button("Start")]
        c = C()
        self.assertEqual(state_from_browser(c, SERVER)[0], "can_start")
        self.assertEqual(c.script, BUTTON_SNAPSHOT_JS)

    def test_marker_refuses_stale_button(self):
        class C:
            def evaluate(self, script):
                self.script = script
                return False
        c = C()
        self.assertFalse(safe_mark_start(c, button("Start")))
        self.assertIn("data-safe-seedloaf-start", c.script)

    def test_marker_requires_true(self):
        class C:
            def evaluate(self, script):
                return 1
        self.assertFalse(safe_mark_start(C(), button("Start")))

    def test_marker_validates_index(self):
        class C:
            def evaluate(self, script):
                raise AssertionError("Should not run malformed JS")
        for i in (True, -1, "0", None):
            self.assertFalse(safe_mark_start(C(), button("Start", index=i)))

    def test_wait_without_sleeps_if_ready(self):
        waits = []
        self.assertTrue(wait_until(lambda: True, 10,
                        clock=lambda: 0, pause=lambda n: waits.append(n)))
        self.assertEqual(waits, [])

    def test_wait_timeout_does_not_claim_success(self):
        clocks = iter([0, 2, 4, 6])
        self.assertFalse(wait_until(lambda: False, 3,
            clock=lambda: next(clocks), pause=lambda _: None))

    def test_no_captcha_when_login_field_present(self):
        class C:
            def is_element_visible(self, selector): return True
            def solve_captcha(self): raise AssertionError("Unnecessary CAPTCHA action")
        limited_challenge(C())

    def test_2000_random_button_injections(self):
        import random
        r = random.Random(20261120)
        for i in range(2000):
            bs = [button(r.choice(["Start", "Stop", "Restart", "Delete"]),
                         index=j, visible=r.choice([True, False]))
                  for j in range(r.randrange(0, 6))]
            state, selected = classify_snapshot(bs)
            if selected is not None:
                self.assertEqual(state, "can_start")
                self.assertTrue(selected["visible"])
                self.assertEqual(selected["text"], "Start")


if __name__ == "__main__":
    unittest.main()
