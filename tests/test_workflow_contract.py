"""Regression checks for the workflow; never contacts Seedloaf."""
import unittest
from pathlib import Path

WF = (Path(__file__).resolve().parents[1] / ".github/workflows/selenium.yml").read_text(encoding="utf-8")


class TestWorkflowSafety(unittest.TestCase):
    def test_preflight_before_browser_install(self):
        self.assertLess(WF.index("id: preflight"), WF.index("Instalar SeleniumBase UC"))

    def test_browser_install_skipped_when_already_online(self):
        self.assertIn(
            "steps.preflight.outputs.online != 'true' && "
            "(inputs.backend == 'browser' || inputs.backend == 'browser_cdp' || inputs.backend == 'public_start' || inputs.backend == '')", WF)

    def test_start_step_skipped_when_online(self):
        self.assertIn(
            "Encender mediante el backend elegido\n"
            "        if: ${{ steps.preflight.outputs.online != 'true' }}", WF)

    def test_missing_backend_defaults_to_browser(self):
        self.assertEqual(WF.count(
            "START_BACKEND: ${{ inputs.backend || 'browser' }}"), 2)

    def test_concurrency_disallows_simultaneous_starts(self):
        self.assertIn("cancel-in-progress: false", WF)
        self.assertIn("group: seedloaf-start-", WF)

    def test_readonly_flag_forwarded(self):
        self.assertIn("CHECK_ONLY: ${{ inputs.check_only }}", WF)

    def test_single_start_entrypoint(self):
        self.assertEqual(WF.count("run: python src/entrypoint.py"), 1)

    def test_no_secrets_echo(self):
        self.assertNotIn("secrets.GITHUB_TOKEN", WF)
        self.assertNotIn('echo "$PASSWORD"', WF)


if __name__ == "__main__":
    unittest.main()
