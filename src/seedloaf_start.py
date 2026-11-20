"""Encendido solicitado de un servidor Seedloaf.

Utiliza SeleniumBase UC Mode, navegador local en el runner y Xvfb.
No expone credenciales, cookies, tokens, capturas ni HTML.
No permite controlar otros servidores ni apagar/reiniciar.
"""
import os
import re
import sys
import time
import unicodedata
import uuid
from urllib.parse import urlparse

LOGIN_URL = "https://accounts.seedloaf.com/sign-in"
START = {"start", "start server", "start world", "iniciar", "iniciar servidor",
         "encender", "encender servidor", "power on"}
STOP = {"stop", "stop server", "stop world", "detener", "detener servidor",
        "apagar", "apagar servidor", "power off"}
CHALLENGE = {"checking your browser", "verify you are human", "verifica que eres humano",
             "just a moment", "attention required", "verifying you are human"}


def console_url(server_id):
    try:
        canonical = str(uuid.UUID(server_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("SEEDLOAF_SERVER_ID no es un UUID valido") from exc
    if canonical != server_id.lower():
        raise ValueError("SEEDLOAF_SERVER_ID no es un UUID canonico")
    return f"https://seedloaf.com/dashboard/{canonical}/console"


def norm(text):
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.strip().lower())


def classify_buttons(buttons):
    starts, stops = [], []
    for button in buttons:
        if not button.is_displayed() or not button.is_enabled():
            continue
        labels = [norm(button.text), norm(button.get_attribute("aria-label")),
                  norm(button.get_attribute("title"))]
        if any(label in STOP for label in labels):
            stops.append(button)
        elif any(label in START for label in labels):
            starts.append(button)
    if stops:
        return "already_running", None
    if len(starts) == 1:
        return "can_start", starts[0]
    return ("ambiguous" if starts else "not_found"), None


def is_challenge(title, body):
    text = norm((title or "") + " " + (body or "")[:1500])
    return any(marker in text for marker in CHALLENGE)


def is_target(url, server_id):
    u = urlparse(url)
    return u.scheme == "https" and u.hostname == "seedloaf.com" and u.path.startswith(
        f"/dashboard/{server_id}/"
    )


def diagnostic(driver, stage):
    """Informacion limitada a indicadores, sin datos de la sesion."""
    from selenium.webdriver.common.by import By
    try:
        u = urlparse(driver.current_url)
        host = u.hostname or ""
        domain = host if host in ("seedloaf.com", "accounts.seedloaf.com") else "other"
        title = norm(driver.title)
        body = norm(driver.find_element(By.TAG_NAME, "body").text)[:1500]
        combined = title + " " + body
        flags = {
            "challenge": is_challenge(title, body) or bool(driver.find_elements(
                By.CSS_SELECTOR, "iframe[src*='challenges.cloudflare.com']")),
            "invalid_credentials": any(t in combined for t in (
                "invalid password", "incorrect password", "invalid credentials",
                "incorrect credentials", "contrasena incorrecta", "credenciales invalidas")),
            "verify_email": any(t in combined for t in (
                "verify your email", "check your email", "verifica tu correo",
                "verification code")),
            "two_factor": any(t in combined for t in (
                "two-factor", "two factor", "authenticator")),
            "username_field": bool(driver.find_elements(By.ID, "identifier-field")),
            "password_field": bool(driver.find_elements(By.ID, "password-field")),
            "dashboard": host == "seedloaf.com" and "/dashboard" in u.path,
        }
        print("DIAGNOSTICO etapa=" + stage + " dominio=" + domain + " " +
              " ".join(f"{key}={int(bool(value))}" for key, value in flags.items()),
              flush=True)
    except Exception as exc:
        print("DIAGNOSTICO etapa=" + stage +
              " inspeccion_error=" + type(exc).__name__, flush=True)


def is_current_challenge(driver):
    from selenium.webdriver.common.by import By
    try:
        return (is_challenge(driver.title, driver.find_element(By.TAG_NAME, "body").text)
                or bool(driver.find_elements(
                    By.CSS_SELECTOR, "iframe[src*='challenges.cloudflare.com']")))
    except Exception:
        return False


def open_and_wait(sb, url):
    """El mismo navegador gestiona la pagina y la sesion, sin proxy externo."""
    driver = sb.driver
    driver.uc_open_with_reconnect(url, reconnect_time=5)
    if is_current_challenge(driver):
        print("Se detecto verificacion web. Intentando resolverla una sola vez "
              "desde el navegador local.", flush=True)
        try:
            # API de UC Mode disponible en el driver, no en SB.
            driver.uc_gui_handle_captcha()
        except Exception as exc:
            print("Verificacion no resuelta automaticamente: " +
                  type(exc).__name__, flush=True)
        time.sleep(2)


def do_start(sb, server_id, email, password):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException

    driver = sb.driver
    print("Abriendo acceso de Seedloaf con navegador UC, sin servicios externos.",
          flush=True)
    open_and_wait(sb, LOGIN_URL)
    diagnostic(driver, "initial_identifier")
    try:
        username = WebDriverWait(driver, 30).until(
            EC.visibility_of_element_located((By.ID, "identifier-field")))
    except TimeoutException as exc:
        diagnostic(driver, "identifier_timeout")
        raise RuntimeError("La verificacion web o el formulario impide entrar. "
                           "Consulta DIAGNOSTICO.") from exc

    username.send_keys(email)
    username.send_keys(Keys.ENTER)
    diagnostic(driver, "after_identifier")
    try:
        field = WebDriverWait(driver, 25).until(
            EC.visibility_of_element_located((By.ID, "password-field")))
    except TimeoutException as exc:
        diagnostic(driver, "password_field_timeout")
        raise RuntimeError("No aparecio el campo de contrasena.") from exc

    field.send_keys(password)
    field.send_keys(Keys.ENTER)
    try:
        WebDriverWait(driver, 35).until(
            lambda d: urlparse(d.current_url).hostname == "seedloaf.com")
    except TimeoutException as exc:
        diagnostic(driver, "after_password_timeout")
        raise RuntimeError("La autenticacion no se completo.") from exc

    diagnostic(driver, "authenticated")
    print("Abriendo consola del servidor configurado.", flush=True)
    open_and_wait(sb, console_url(server_id))

    def panel_ready(d):
        if not is_target(d.current_url, server_id):
            return False
        state, _ = classify_buttons(d.find_elements(By.CSS_SELECTOR, "button"))
        return state != "not_found"

    try:
        WebDriverWait(driver, 35).until(panel_ready)
    except TimeoutException as exc:
        diagnostic(driver, "panel_timeout")
        raise RuntimeError("No se encontro un control de encendido reconocible "
                           "en el panel correcto.") from exc

    state, start = classify_buttons(driver.find_elements(By.CSS_SELECTOR, "button"))
    if state == "already_running":
        print("El servidor ya estaba encendido. No se ejecuta otra accion.",
              flush=True)
        return 0
    if state != "can_start":
        raise RuntimeError("Botones ambiguos. No se hace clic.")

    start.click()
    try:
        WebDriverWait(driver, 35).until(
            lambda d: classify_buttons(d.find_elements(
                By.CSS_SELECTOR, "button"))[0] == "already_running")
    except TimeoutException as exc:
        diagnostic(driver, "start_confirmation_timeout")
        raise RuntimeError("Se pulso Start pero el panel no confirmo el estado.") from exc
    print("El panel muestra el control de detener: arranque solicitado.", flush=True)
    return 0


def main():
    server_id = (os.getenv("SEEDLOAF_SERVER_ID") or "").strip()
    console_url(server_id)
    email = (os.getenv("USERNAME") or "").strip()
    password = os.getenv("PASSWORD") or ""
    if not email or not password:
        raise RuntimeError("Faltan secrets USERNAME/PASSWORD de Seedloaf.")

    from seleniumbase import SB
    result = None
    with SB(uc=True, xvfb=True, incognito=True, locale="en") as sb:
        result = do_start(sb, server_id, email, password)
    # SeleniumBase puede registrar una excepcion del test sin devolver
    # exit code distinto de 0. Nunca reportar exito si falta confirmacion.
    if result != 0:
        raise RuntimeError("La automatizacion termino sin confirmar el resultado.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print("ERROR inesperado (" + type(exc).__name__ +
              "). No se muestran datos sensibles.", file=sys.stderr)
        sys.exit(1)
