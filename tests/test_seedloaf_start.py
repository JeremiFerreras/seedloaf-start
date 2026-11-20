import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from seedloaf_start import classify_buttons, console_url, is_challenge, is_target, norm

SERVER_ID = "10a18fff-0237-49f3-a279-964412516d46"


class FakeButton:
    def __init__(self, text="", aria=None, title=None, visible=True, enabled=True):
        self.text = text
        self.data = {"aria-label": aria, "title": title}
        self.visible = visible
        self.enabled = enabled

    def get_attribute(self, name):
        return self.data.get(name)

    def is_displayed(self):
        return self.visible

    def is_enabled(self):
        return self.enabled


class Tests(unittest.TestCase):
    def test_exact_url(self):
        self.assertEqual(console_url(SERVER_ID), f"https://seedloaf.com/dashboard/{SERVER_ID}/console")

    def test_reject_invalid_id(self):
        for x in ("", "other", "https://evil.test", "../123"):
            with self.subTest(x=x):
                with self.assertRaises(ValueError):
                    console_url(x)

    def test_reject_wrong_domain_and_server(self):
        self.assertFalse(is_target(f"https://evil.test/dashboard/{SERVER_ID}/console", SERVER_ID))
        self.assertFalse(is_target("https://seedloaf.com/dashboard/other/console", SERVER_ID))
        self.assertTrue(is_target(console_url(SERVER_ID), SERVER_ID))

    def test_only_start_selectable(self):
        start = FakeButton("Start server")
        state, selected = classify_buttons([FakeButton("Delete"), FakeButton("Restart"), start])
        self.assertEqual(state, "can_start")
        self.assertIs(selected, start)

    def test_accessible_spanish_label(self):
        state, b = classify_buttons([FakeButton(aria="Iniciar servidor")])
        self.assertEqual(state, "can_start")
        self.assertIsNotNone(b)

    def test_already_running(self):
        state, b = classify_buttons([FakeButton("Start"), FakeButton("Stop")])
        self.assertEqual(state, "already_running")
        self.assertIsNone(b)

    def test_disabled_start(self):
        self.assertEqual(classify_buttons([FakeButton("Start", enabled=False)])[0], "not_found")

    def test_multiple_starts(self):
        self.assertEqual(classify_buttons([FakeButton("Start"), FakeButton("Start world")])[0], "ambiguous")

    def test_unknown(self):
        self.assertEqual(classify_buttons([FakeButton("Reset")])[0], "not_found")

    def test_challenge(self):
        self.assertTrue(is_challenge("Just a moment...", ""))
        self.assertTrue(is_challenge("", "Verify you are human"))
        self.assertFalse(is_challenge("Seedloaf", "Start server"))

    def test_normalization(self):
        self.assertEqual(norm("  INICIAR   SERVIDÓR  "), "iniciar servidor")


if __name__ == "__main__":
    unittest.main()
