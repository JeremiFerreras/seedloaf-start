"""Public Start selection tests: never contact Seedloaf, Cloudflare or DNS."""
import random
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from public_start import (
    FORM_INFO, PUBLIC_URL, choose_controls, domain_value, fill_and_submit,
    is_expected_public_page, run_public,
)


def snap(field=None, button=None):
    return {"fields": [field] if field else [], "controls": [button] if button else []}


def field(index=0, visible=True, typ="text"):
    return {"i": index, "type": typ, "visible": visible,
            "name": "domain", "id": "", "placeholder": "", "required": True}


def button(index=0, text="Start", visible=True):
    return {"i": index, "text": text, "aria": "", "type": "submit", "visible": visible}


class FakeCDP:
    def __init__(self, snapshot=None, url=PUBLIC_URL, challenge=False):
        self.snapshot = snapshot or snap(field(), button())
        self.url = url
        self.challenge = challenge
        self.events = []

    def get_current_url(self): return self.url
    def get_title(self): return "Just a moment..." if self.challenge else "Public Start"
    def get_text(self, selector): return "Verify you are human" if self.challenge else ""
    def evaluate(self, js):
        self.events.append("evaluate")
        return self.snapshot if js == FORM_INFO else True
    def type(self, selector, value): self.events.append(("type", selector, value))
    def click(self, selector): self.events.append(("click", selector))


class TestDomain(unittest.TestCase):
    def test_hostname(self):
        self.assertEqual(domain_value("serverdejfxdchess.seedloaf.gg"), "serverdejfxdchess.seedloaf.gg")

    def test_hostname_with_port(self):
        self.assertEqual(domain_value("serverdejfxdchess.seedloaf.gg:50690"), "serverdejfxdchess.seedloaf.gg")

    def test_bare_subdomain(self):
        self.assertEqual(domain_value("serverdejfxdchess"), "serverdejfxdchess")

    def test_not_other_hosts(self):
        for value in ("https://seedloaf.com", "evil.com", "127.0.0.1", "localhost:0",
                      "foo.seedloaf.gg.evil.com", "server/path", "user@host",
                      "a" * 70, "foo.seedloaf.gg:0", "foo.seedloaf.gg:99999", ""):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    domain_value(value)


class TestPageAndForm(unittest.TestCase):
    def test_public_route(self):
        self.assertTrue(is_expected_public_page(PUBLIC_URL))

    def test_reject_untrusted_route(self):
        for url in ("http://seedloaf.com/public-start",
                    "https://seedloaf.com.evil.test/public-start",
                    "https://seedloaf.com/dashboard",
                    "https://bad@seedloaf.com/public-start"):
            self.assertFalse(is_expected_public_page(url))

    def test_single_valid_form(self):
        _, selected, state = choose_controls(snap(field(), button()))
        self.assertEqual(state, "ready")
        self.assertEqual(selected["text"], "Start")

    def test_multiple_fields_not_guessed(self):
        ss = {"fields": [field(0), field(1)], "controls": [button()]}
        self.assertEqual(choose_controls(ss)[2], "field_count_2")

    def test_multiple_start_buttons_not_guessed(self):
        ss = {"fields": [field()], "controls": [button(0), button(1)]}
        self.assertEqual(choose_controls(ss)[2], "button_count_2")

    def test_disabled_hidden_input_ignored(self):
        self.assertEqual(choose_controls(snap(field(visible=False), button()))[2],
                         "field_count_0")

    def test_hidden_button_no_start(self):
        self.assertEqual(choose_controls(snap(field(), button(visible=False)))[2],
                         "button_count_0")

    def test_restart_does_not_start(self):
        self.assertEqual(choose_controls(snap(field(), button(text="Restart")))[2],
                         "button_count_0")

    def test_ambiguous_lists(self):
        self.assertEqual(choose_controls(None)[2], "bad_document")
        self.assertEqual(choose_controls({"fields": {}, "controls": []})[2], "bad_document")

    def test_check_only_does_not_submit(self):
        c = FakeCDP()
        self.assertEqual(run_public(c, "serverdejfxdchess", check_only=True), "ready")
        self.assertFalse(any(isinstance(x, tuple) and x[0] == "click" for x in c.events))

    def test_single_submission(self):
        c = FakeCDP()
        self.assertEqual(run_public(c, "serverdejfxdchess"), "submitted")
        self.assertEqual(len([x for x in c.events if isinstance(x, tuple)
                              and x[0] == "click"]), 1)
        self.assertEqual(len([x for x in c.events if isinstance(x, tuple)
                              and x[0] == "type"]), 1)

    def test_wrong_page_no_secret_entered(self):
        c = FakeCDP(url="https://evil.test/")
        with self.assertRaises(RuntimeError):
            run_public(c, "serverdejfxdchess")
        self.assertFalse(any(isinstance(x, tuple) for x in c.events))

    def test_changed_form_aborts(self):
        c = FakeCDP()
        f, b, _ = choose_controls(c.snapshot)
        c.snapshot = snap(field(), button(text="Stop"))
        with self.assertRaises(RuntimeError):
            fill_and_submit(c, f, b, "serverdejfxdchess")
        self.assertFalse(any(isinstance(x, tuple) for x in c.events))

    def test_challenge_is_not_treated_as_success(self):
        c = FakeCDP(snapshot=snap(), challenge=True)
        with patch("public_start.wait_until", return_value=False):
            with self.assertRaises(RuntimeError):
                run_public(c, "serverdejfxdchess")
        self.assertFalse(any(isinstance(x, tuple) for x in c.events))

    def test_3000_random_controls_fail_closed(self):
        rng = random.Random(20261120)
        for i in range(3000):
            ss = {"fields": [field(k, rng.choice([True, False]))
                             for k in range(rng.randint(0, 4))],
                  "controls": [button(k, rng.choice(["Start", "Stop", "Delete", "Restart"]),
                                      rng.choice([True, False]))
                               for k in range(rng.randint(0, 5))]}
            f, b, status = choose_controls(ss)
            if status == "ready":
                self.assertIsNotNone(f)
                self.assertEqual(b["text"], "Start")
                self.assertTrue(f["visible"])
                self.assertTrue(b["visible"])


if __name__ == "__main__":
    unittest.main()
