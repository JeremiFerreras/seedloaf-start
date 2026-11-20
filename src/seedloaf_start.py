"""Arranque seguro de Seedloaf: no automatiza Google OAuth ni Cloudflare."""
import os
import re
import sys
import unicodedata
import uuid
from urllib.parse import urlparse

LOGIN_URL = "https://accounts.seedloaf.com/sign-in"
START = {"start", "start server", "start world", "iniciar", "iniciar servidor", "encender", "encender servidor", "power on"}
STOP = {"stop", "stop server", "stop world", "detener", "detener servidor", "apagar", "apagar servidor", "power off"}
CHALLENGE = {"checking your browser", "verify you are human", "verifica que eres humano", "just a moment", "attention required"}


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
        labels = [norm(button.text), norm(button.get_attribute("aria-label")), norm(button.get_attribute("title"))]
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
    return u.scheme == "https" and u.hostname == "seedloaf.com" and u.path.startswith(f"/dashboard/{server_id}/")


def main():
    server_id = (os.getenv("SEEDLOAF_SERVER_ID") or "").strip()
    console = console_url(server_id)
    email = (os.getenv("USERNAME") or "").strip()
    password = os.getenv("PASSWORD") or ""
    if not email or not password:
        raise RuntimeError("Faltan secrets USERNAME/PASSWORD de una cuenta Seedloaf con correo y contrasena; Google OAuth no esta soportado")

    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException

    options = webdriver.ChromeOptions()
    for arg in ("--headless=new", "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1365,900"):
        options.add_argument(arg)
    driver = webdriver.Chrome(options=options)
    try:
        print("Abriendo acceso de Seedloaf por correo.")
        driver.get(LOGIN_URL)
        try:
            username = WebDriverWait(driver, 25).until(EC.visibility_of_element_located((By.ID, "identifier-field")))
            username.send_keys(email)
            username.send_keys(Keys.ENTER)
            field = WebDriverWait(driver, 25).until(EC.visibility_of_element_located((By.ID, "password-field")))
            field.send_keys(password)
            field.send_keys(Keys.ENTER)
            WebDriverWait(driver, 35).until(lambda d: urlparse(d.current_url).hostname == "seedloaf.com")
        except TimeoutException as exc:
            raise RuntimeError("Autenticacion no completada: formulario cambiado, login social o verificacion humana. No se elude el desafio.") from exc

        print("Abriendo consola del servidor configurado.")
        driver.get(console)
        def panel_ready(d):
            if not is_target(d.current_url, server_id):
                return False
            state, _ = classify_buttons(d.find_elements(By.CSS_SELECTOR, "button"))
            return state != "not_found"
        try:
            WebDriverWait(driver, 35).until(panel_ready)
        except TimeoutException as exc:
            if is_challenge(driver.title, driver.find_element(By.TAG_NAME, "body").text):
                raise RuntimeError("Se requiere verificacion humana; cancelado.") from exc
            raise RuntimeError("No se reconocio el boton Start del servidor; nada fue pulsado.") from exc

        state, start = classify_buttons(driver.find_elements(By.CSS_SELECTOR, "button"))
        if state == "already_running":
            print("El servidor ya esta encendido.")
            return 0
        if state != "can_start":
            raise RuntimeError("Botones ambiguos o desconocidos. No se inicia el servidor.")
        start.click()
        try:
            WebDriverWait(driver, 35).until(lambda d: classify_buttons(d.find_elements(By.CSS_SELECTOR, "button"))[0] == "already_running")
        except TimeoutException as exc:
            raise RuntimeError("Se pulso Start pero no se confirmo el cambio de estado; comprobar el panel.") from exc
        print("El panel confirma el servidor arrancando o encendido.")
        return 0
    finally:
        driver.quit()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"ERROR inesperado ({type(exc).__name__}). No se muestran datos sensibles.", file=sys.stderr)
        sys.exit(1)
