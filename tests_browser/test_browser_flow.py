"""Browser-level synthetic integration tests (no connection to Seedloaf)."""
import sys
import unittest
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from seedloaf_start import (
    action_for_state, confirmation_from_state, snapshot_state,
)

SERVER = "123e4567-e89b-42d3-a456-426614174000"
CONSOLE = f"https://seedloaf.com/dashboard/{SERVER}/console"


class TestSyntheticChromeFlow(unittest.TestCase):
    def test_click_once_and_confirm_dynamic_stop_button(self):
        from seleniumbase import SB
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait

        html = """
        <!doctype html><html><head><title>Fake Minecraft panel</title></head><body>
        <button id="restart">Restart</button>
        <button id="power" onclick="
          window.startClicks = (window.startClicks || 0) + 1;
          this.disabled = true;
          const b = this;
          setTimeout(() => {b.disabled = false; b.textContent = 'Stop';}, 350);
        ">Start</button>
        <button id="delete">Delete</button>
        </body></html>
        """
        with SB(uc=True, xvfb=True) as sb:
            driver = sb.driver
            driver.default_get("data:text/html;charset=utf-8," + quote(html))
            def state():
                return snapshot_state(
                    CONSOLE, SERVER, driver.find_elements(By.CSS_SELECTOR, "button"))
            status, start = state()
            self.assertEqual(status, "can_start")
            self.assertEqual(action_for_state(status), "start")
            self.assertEqual(action_for_state(status, True), "check_off")
            start.click()
            # The real application must never click twice during confirmation.
            WebDriverWait(driver, 8, poll_frequency=0.2).until(
                lambda _driver: confirmation_from_state(state()[0]))
            self.assertEqual(state()[0], "already_running")
            self.assertEqual(driver.execute_script("return window.startClicks"), 1)
            self.assertIsNone(state()[1])

    def test_untrusted_navigation_never_confirms_start(self):
        from seleniumbase import SB
        from selenium.webdriver.common.by import By

        with SB(uc=True, xvfb=True) as sb:
            sb.driver.default_get(
                "data:text/html,<html><body><button>Stop</button></body></html>")
            buttons = sb.driver.find_elements(By.CSS_SELECTOR, "button")
            self.assertEqual(
                snapshot_state("https://evil.example/dashboard/" + SERVER +
                               "/console", SERVER, buttons),
                ("wrong_page", None))
            self.assertEqual(
                snapshot_state("https://seedloaf.com/dashboard/other/console",
                               SERVER, buttons),
                ("wrong_page", None))


    def test_cdp_mode_can_inspect_and_click_local_page(self):
        """No Seedloaf requests: prove UC -> CDP works on GitHub's Xvfb."""
        from seleniumbase import SB
        from urllib.parse import quote
        page = ("<html><head><title>Safe CDP smoke</title></head><body>"
                "<button id='start' onclick='this.textContent=&quot;Stop&quot;'>Start</button>"
                "</body></html>")
        # Use same public version as production with a local data URL.
        with SB(uc=True, xvfb=True) as sb:
            sb.activate_cdp_mode("data:text/html," + quote(page))
            cdp = sb.cdp
            cdp.wait_for_element_visible("#start", timeout=12)
            from seedloaf_cdp import state_from_browser, safe_mark_start
            class LocalCDP:
                def get_current_url(self): return CONSOLE
                def evaluate(self, script): return cdp.evaluate(script)
            adapter = LocalCDP()
            state, selected = state_from_browser(adapter, SERVER)
            self.assertEqual(state, "can_start")
            self.assertTrue(safe_mark_start(adapter, selected))
            cdp.click('button[data-safe-seedloaf-start="single-click"]')
            self.assertEqual(state_from_browser(adapter, SERVER)[0],
                             "already_running")



    def test_cdp_enter_submits_two_step_login_form_offline(self):
        """Verify the CDP press_keys Enter semantics on a local-only form."""
        from seleniumbase import SB
        from urllib.parse import quote
        html = """
        <html><body>
        <form onsubmit="event.preventDefault();
           const p=document.getElementById('password-field');
           if (p.hidden) {p.hidden=false;} else {
             document.body.setAttribute('data-signed-in','yes');
           }">
          <input id="identifier-field" name="email">
          <input id="password-field" name="password" type="password" hidden>
          <button type="submit">Continue</button>
        </form></body></html>
        """
        with SB(uc=True, xvfb=True) as sb:
            sb.activate_cdp_mode("data:text/html," + quote(html))
            cdp = sb.cdp
            cdp.type("#identifier-field", "test@example.test")
            cdp.press_keys("#identifier-field", "\n")
            cdp.wait_for_element_visible("#password-field", timeout=10)
            cdp.type("#password-field", "dummy")
            cdp.press_keys("#password-field", "\n")
            self.assertEqual(
                cdp.evaluate("document.body.getAttribute('data-signed-in')"),
                "yes"
            )



    def test_public_start_real_cdp_form_single_submission(self):
        """Offline HTML: field discovered, filled once, Start clicked once."""
        from seleniumbase import SB
        from urllib.parse import quote
        from public_start import run_public
        html = """
        <html><head><title>Public Start test</title></head><body>
          <input id="domain" type="text" placeholder="Domain" required>
          <button onclick="document.body.setAttribute('data-starts',
            String(1 + Number(document.body.getAttribute('data-starts') || 0)))">
            Start
          </button>
        </body></html>
        """
        with SB(uc=True, xvfb=True) as sb:
            sb.activate_cdp_mode("data:text/html," + quote(html))
            cdp = sb.cdp
            class LocalPublicPage:
                def get_current_url(self): return "https://seedloaf.com/public-start"
                def get_title(self): return cdp.get_title()
                def get_text(self, selector): return cdp.get_text(selector)
                def evaluate(self, script): return cdp.evaluate(script)
                def type(self, selector, value): return cdp.type(selector, value)
                def click(self, selector): return cdp.click(selector)
            page = LocalPublicPage()
            self.assertEqual(run_public(page, "testserver"), "submitted")
            self.assertEqual(cdp.evaluate("document.querySelector('#domain').value"),
                             "testserver")
            self.assertEqual(cdp.evaluate("document.body.getAttribute('data-starts')"),
                             "1")


if __name__ == "__main__":
    unittest.main()
