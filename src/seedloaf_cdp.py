"""Experimental single-session CDP implementation of the Seedloaf start flow.

Runs only when START_BACKEND=browser_cdp. Does not fall back to WebDriver or
retry the Start click. No screenshot, cookie persistence, or page HTML logs.
"""
import json
import os
import sys
import time
import uuid

from seedloaf_start import (
    START, STOP, authenticated_dashboard, console_url, is_challenge, is_target,
    norm,
)

LOGIN_URL = "https://accounts.seedloaf.com/sign-in"
USERNAME = "#identifier-field"
PASSWORD = "#password-field"

BUTTON_SNAPSHOT_JS = """(() => Array.from(document.querySelectorAll('button')).map(
  (b, i) => ({
    index: i,
    visible: !!(b.getClientRects().length) &&
             getComputedStyle(b).visibility !== 'hidden',
    enabled: !b.disabled && b.getAttribute('aria-disabled') !== 'true',
    text: (b.innerText || '').trim(),
    aria: b.getAttribute('aria-label') || '',
    title: b.getAttribute('title') || ''
  })
))()"""


def classify_snapshot(buttons):
    """Observe raw button data; never interpret hidden or conflicting controls."""
    if not isinstance(buttons, list):
        return "ambiguous", None
    starting, stopping = [], []
    for b in buttons:
        if not isinstance(b, dict):
            return "ambiguous", None
        if b.get("visible") is not True or b.get("enabled") is not True:
            continue
        index = b.get("index")
        if not isinstance(index, int) or isinstance(index, bool) or index < 0:
            return "ambiguous", None
        labels = [norm(b.get(x)) for x in ("text", "aria", "title")]
        if any(label in STOP for label in labels):
            stopping.append(b)
        elif any(label in START for label in labels):
            starting.append(b)
    if len(starting) + len(stopping) > 1:
        return "ambiguous", None
    if stopping:
        return "already_running", None
    if starting:
        return "can_start", starting[0]
    return "not_found", None


def state_from_browser(cdp, server_id):
    if not is_target(cdp.get_current_url(), server_id):
        return "wrong_page", None
    return classify_snapshot(cdp.evaluate(BUTTON_SNAPSHOT_JS))


def safe_mark_start(cdp, item):
    """Mark one exact button, checking current labels to avoid a stale click."""
    if not isinstance(item, dict):
        return False
    i = item.get("index")
    if type(i) is not int or i < 0:
        return False
    raw = [str(item.get(k) or "") for k in ("text", "aria", "title")]
    values = json.dumps(raw)
    script = """(() => {
      const b = document.querySelectorAll('button')[INDEX];
      if (!b || b.disabled || b.getAttribute('aria-disabled') === 'true' ||
          !b.getClientRects().length) return false;
      const current = [(b.innerText || '').trim(),
        b.getAttribute('aria-label') || '', b.getAttribute('title') || ''];
      if (JSON.stringify(current) !== JSON.stringify(EXPECTED)) return false;
      b.setAttribute('data-safe-seedloaf-start', 'single-click');
      return true;
    })()""".replace("INDEX", str(i)).replace("EXPECTED", values)
    return cdp.evaluate(script) is True


def wait_until(condition, seconds=30, *, clock=time.monotonic, pause=time.sleep):
    deadline = clock() + seconds
    while clock() < deadline:
        if condition():
            return True
        pause(0.8)
    return condition()


def limited_challenge(cdp):
    """At most one supported check attempt in the existing browser session."""
    if cdp.is_element_visible(USERNAME):
        return
    try:
        title = cdp.get_title()
        body = cdp.get_text("body")[:1200]
    except Exception:
        title, body = "", ""
    if is_challenge(title, body):
        print("CDP_DIAGNOSTICO etapa=access challenge=1", flush=True)
        try:
            cdp.solve_captcha()
        except Exception as exc:
            print("CDP_DIAGNOSTICO verify_error=" +
                  type(exc).__name__, flush=True)


def run_browser(cdp, server_id, email, password, *, check_only=False):
    """Use CDP exclusively; never reconnect Chromedriver during the flow."""
    if not authenticated_dashboard("https://seedloaf.com/dashboard"):
        raise RuntimeError("Validacion de dominio inutilizable.")
    cdp.goto(LOGIN_URL)
    limited_challenge(cdp)
    if not wait_until(lambda: cdp.is_element_visible(USERNAME), 35):
        print("CDP_DIAGNOSTICO etapa=identifier_timeout challenge_possible=1",
              flush=True)
        raise RuntimeError("No aparecio el formulario de Seedloaf.")

    cdp.type(USERNAME, email)
    cdp.press_keys(USERNAME, "\n")
    if not wait_until(lambda: cdp.is_element_visible(PASSWORD), 30):
        raise RuntimeError("No aparecio el campo de contrasena.")
    cdp.type(PASSWORD, password)
    cdp.press_keys(PASSWORD, "\n")

    if not wait_until(lambda: authenticated_dashboard(cdp.get_current_url()), 50):
        raise RuntimeError("No se completo la autenticacion por CDP.")

    print("CDP_DIAGNOSTICO etapa=authenticated", flush=True)
    cdp.goto(console_url(server_id))

    def is_ready():
        state, _ = state_from_browser(cdp, server_id)
        return state in ("can_start", "already_running", "ambiguous")

    if not wait_until(is_ready, 55):
        raise RuntimeError("Consola del servidor no disponible o no reconocible.")
    state, btn = state_from_browser(cdp, server_id)

    if state == "already_running":
        print("CDP_RESULTADO already_running", flush=True)
        return 0
    if check_only:
        if state != "can_start":
            raise RuntimeError("Estado del panel ambiguo en modo lectura.")
        print("CDP_RESULTADO read_only_off", flush=True)
        return 0
    if state != "can_start":
        raise RuntimeError("Se cancela clic por estado inseguro: " + state)

    if not is_target(cdp.get_current_url(), server_id) or not safe_mark_start(cdp, btn):
        raise RuntimeError("El boton Start cambio antes del clic; se cancela.")
    cdp.click('button[data-safe-seedloaf-start="single-click"]')
    print("CDP_RESULTADO start_click_sent", flush=True)

    def confirmed():
        current, _ = state_from_browser(cdp, server_id)
        if current in ("wrong_page", "ambiguous"):
            raise RuntimeError("La consola cambio durante la confirmacion.")
        return current == "already_running"

    if not wait_until(confirmed, 120):
        raise RuntimeError("Start solicitado, pero el panel no confirmo Stop. "
                           "No se repite la orden.")
    print("CDP_RESULTADO panel_running (Minecraft no comprobado)", flush=True)
    return 0


def main():
    server_id = str(uuid.UUID((os.environ.get("SEEDLOAF_SERVER_ID") or "").strip()))
    email = (os.environ.get("USERNAME") or "").strip()
    password = os.environ.get("PASSWORD") or ""
    if not email or not password:
        raise RuntimeError("Faltan secretos de Seedloaf.")
    from seleniumbase import SB
    with SB(uc=True, xvfb=True, incognito=True, locale="en") as sb:
        sb.activate_cdp_mode(LOGIN_URL)
        return run_browser(sb.cdp, server_id, email, password,
                           check_only=(os.environ.get("CHECK_ONLY") or "").lower() == "true")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("CDP_ERROR " + type(exc).__name__ +
              ": operacion no confirmada; consulta los diagnosticos.",
              file=sys.stderr)
        sys.exit(1)
