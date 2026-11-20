"""Seedloaf's documented Public Start page: no private account login.

This is a browser workflow, not a hidden API. It respects interactive website
verification and never claims success until Minecraft is observed responding.
No cookies, domain secret, browser HTML or screenshots are logged.
"""
import os
import re
import sys
import time
from urllib.parse import urlparse

PUBLIC_URL = "https://seedloaf.com/public-start"
PLACEHOLDERS = ("server", "domain", "subdomain", "minecraft", "address", "ip")
START_WORDS = ("start", "start server", "start world", "start minecraft",
               "start my server", "start world now", "encender", "iniciar",
               "iniciar servidor", "encender servidor", "start server now")
CHALLENGE_WORDS = ("just a moment", "verify you are human", "checking your browser",
                   "verifica que eres humano", "verifying you are human")

FORM_INFO = """(() => ({
  fields: Array.from(document.querySelectorAll('input')).map((e, i) => ({
    i, type: (e.type || 'text').toLowerCase(),
    name: (e.name || '').slice(0, 90),
    id: (e.id || '').slice(0, 90),
    placeholder: (e.placeholder || '').slice(0, 90),
    visible: !!e.getClientRects().length && !e.disabled,
    required: !!e.required
  })),
  controls: Array.from(document.querySelectorAll('button, input[type="submit"]'))
    .map((e, i) => ({
      i, text: ((e.innerText || e.value || '').trim()).slice(0, 90),
      aria: (e.getAttribute('aria-label') || '').slice(0, 90),
      type: e.type || '', visible: !!e.getClientRects().length && !e.disabled
    }))
}))()"""


def normalized(value):
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def domain_value(raw):
    """Accept Seedloaf hostname (with optional Java port) or its subdomain."""
    if not isinstance(raw, str) or not raw or len(raw) > 253:
        raise ValueError("DOMAIN no es valido.")
    raw = raw.strip().lower()
    if not raw or any(x in raw for x in ("/", "@", "?", "#", "\\", " ", "\n", "\r")):
        raise ValueError("DOMAIN debe contener solo el subdominio, sin URL.")
    host = raw.split(":", 1)[0]
    if ":" in raw:
        port = raw.rsplit(":", 1)[1]
        if not port.isdecimal() or not 1 <= int(port) <= 65535:
            raise ValueError("Puerto DOMAIN invalido.")
    name = host.removesuffix(".seedloaf.gg")
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", name):
        raise ValueError("DOMAIN no coincide con un subdominio Seedloaf.")
    # The DOMAIN secret was explicitly entered as the Public Start field value.
    # Preserve full hostname vs. short subdomain rather than guessing UI format.
    return host


def choose_controls(snapshot):
    """Fail closed unless one plain visible domain input and one Start control."""
    if not isinstance(snapshot, dict):
        return None, None, "bad_document"
    fields = snapshot.get("fields")
    buttons = snapshot.get("controls")
    if not isinstance(fields, list) or not isinstance(buttons, list):
        return None, None, "bad_document"
    candidates = []
    for field in fields:
        if not isinstance(field, dict) or not field.get("visible"):
            continue
        if field.get("type") not in ("text", "search", "url"):
            continue
        if type(field.get("i")) is not int or field["i"] < 0:
            return None, None, "bad_document"
        candidates.append(field)
    if len(candidates) != 1:
        return None, None, "field_count_" + str(len(candidates))
    choices = []
    for button in buttons:
        if not isinstance(button, dict) or not button.get("visible"):
            continue
        if type(button.get("i")) is not int or button["i"] < 0:
            return None, None, "bad_document"
        labels = (normalized(button.get("text")), normalized(button.get("aria")))
        if any(x in START_WORDS for x in labels):
            choices.append(button)
    if len(choices) != 1:
        return candidates[0], None, "button_count_" + str(len(choices))
    return candidates[0], choices[0], "ready"


def is_expected_public_page(url):
    try:
        u = urlparse(url)
        return (u.scheme == "https" and u.hostname == "seedloaf.com" and
                u.username is None and u.password is None and
                u.port in (None, 443) and u.path.rstrip("/") == "/public-start")
    except (ValueError, TypeError):
        return False


def challenge_detected(cdp):
    try:
        words = normalized(cdp.get_title() + " " + cdp.get_text("body")[:500])
        return any(x in words for x in CHALLENGE_WORDS)
    except Exception:
        return False


def wait_until(predicate, seconds=35, clock=time.monotonic, pause=time.sleep):
    end = clock() + seconds
    while clock() < end:
        if predicate():
            return True
        pause(1.2)
    return predicate()


def safe_document_diagnostic(cdp, state):
    """Only log counts and status, never values, field labels, DOM, or hostname."""
    try:
        snapshot = cdp.evaluate(FORM_INFO)
        nfields = len(snapshot.get("fields", []))
        nbuttons = len(snapshot.get("controls", []))
    except Exception:
        nfields, nbuttons = -1, -1
    print("PUBLIC_DIAG estado=" + state +
          " challenge=" + str(int(challenge_detected(cdp))) +
          " fields=" + str(nfields) + " controls=" + str(nbuttons),
          flush=True)


def fill_and_submit(cdp, field, button, subdomain):
    """Validate DOM identity twice. One submission only."""
    if not is_expected_public_page(cdp.get_current_url()):
        raise RuntimeError("Pagina distinta a Public Start.")
    again = cdp.evaluate(FORM_INFO)
    updated_field, updated_button, status = choose_controls(again)
    if status != "ready" or updated_field != field or updated_button != button:
        raise RuntimeError("El formulario cambio antes de enviar.")
    # Run JS only to locate exact matching elements; use real CDP events to fill.
    i, j = field["i"], button["i"]
    selector = f'input[data-seedloaf-domain="{i}"]'
    click_selector = f'button[data-seedloaf-submit="{j}"]'
    js = """(() => {
      const input = document.querySelectorAll('input')[FIELD_INDEX];
      const control = document.querySelectorAll('button, input[type="submit"]')[BUTTON_INDEX];
      if (!input || !control || !input.getClientRects().length ||
          !control.getClientRects().length || input.disabled || control.disabled)
          return false;
      input.setAttribute('data-seedloaf-domain', 'FIELD_INDEX');
      control.setAttribute('data-seedloaf-submit', 'BUTTON_INDEX');
      return true;
    })()""".replace("FIELD_INDEX", str(i)).replace("BUTTON_INDEX", str(j))
    if cdp.evaluate(js) is not True:
        raise RuntimeError("No se pudo marcar el formulario.")
    # No domain value is included in a JS expression/log.
    cdp.type(selector, subdomain)
    cdp.click(click_selector)
    print("PUBLIC_START_SOLICITADO: un envio (sin confirmacion de servidor).",
          flush=True)


def run_public(cdp, subdomain, *, check_only=False, timeout=45):
    if not is_expected_public_page(cdp.get_current_url()):
        raise RuntimeError("No se abrio la ruta HTTPS Public Start.")
    if challenge_detected(cdp):
        print("PUBLIC_DIAG estado=challenge_interactive", flush=True)
        # SeleniumBase documents one CDP Turnstile checkbox interaction.
        # This may fail and does not grant permission to bypass site policy.
        # Never loop, reload the challenge, or claim validation prematurely.
        try:
            cdp.solve_captcha()
            print("PUBLIC_DIAG verification_attempt=1", flush=True)
        except Exception as exc:
            print("PUBLIC_DIAG verification_error=" + type(exc).__name__,
                  flush=True)
    found = {"value": None}
    def scan():
        if not is_expected_public_page(cdp.get_current_url()):
            raise RuntimeError("Redireccion fuera de Public Start.")
        snapshot = cdp.evaluate(FORM_INFO)
        field, button, state = choose_controls(snapshot)
        found["value"] = (field, button, state)
        return state == "ready"

    if not wait_until(scan, timeout):
        state = found["value"][2] if found["value"] else "no_snapshot"
        safe_document_diagnostic(cdp, state)
        raise RuntimeError("Public Start no expuso un formulario utilizable.")
    field, button, _ = found["value"]
    if check_only:
        print("PUBLIC_CHECK_ONLY: formulario listo; no se envio Start.", flush=True)
        return "ready"
    fill_and_submit(cdp, field, button, subdomain)
    return "submitted"


def main():
    name = domain_value(os.environ.get("DOMAIN", ""))
    from seleniumbase import SB
    with SB(uc=True, xvfb=True, incognito=True, locale="en") as sb:
        sb.activate_cdp_mode(PUBLIC_URL)
        result = run_public(
            sb.cdp, name, check_only=os.environ.get("CHECK_ONLY", "").lower() == "true"
        )
    if result == "ready":
        return 0
    # A successful UI submission alone is not success. A single Start request
    # can take time: only read Minecraft status afterward, no second submission.
    from entrypoint import postflight
    address = (os.environ.get("MINECRAFT_ADDRESS") or "").strip()
    if address:
        status = postflight(address, attempts=10)
        print("PUBLIC_POSTFLIGHT estado=" + status, flush=True)
        if status == "responding":
            print("PUBLIC_CONFIRMED: servidor Minecraft responde.", flush=True)
            return 0
    print("PUBLIC_START_NO_CONFIRMADO: solicitud enviada, sin respuesta Minecraft.",
          flush=True)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("PUBLIC_ERROR: " + type(exc).__name__ +
              " (sin publicar datos sensibles).", file=sys.stderr)
        sys.exit(1)
