"""Adapter for a provider-approved HTTPS start API.

IMPORTANT: There is currently NO verified public Seedloaf start API.
This is an opt-in integration point ONLY if Seedloaf provides endpoints
and a dedicated scoped API token. Never point it at reverse-engineered endpoints.
The contract is documented in README and tested with fake transports.
"""
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from urllib.parse import urlsplit


class ProviderError(RuntimeError):
    """Generic, non-sensitive failure category."""


class TransientProviderError(ProviderError):
    """Retryable for GET only. Never automatically retry POST."""


@dataclass(frozen=True)
class ProviderConfig:
    status_url: str
    start_url: str
    api_token: str
    server_id: str


@dataclass(frozen=True)
class Response:
    http_code: int
    data: dict


def require_endpoint(value):
    """Only explicit HTTPS URLs controlled by Seedloaf, never third-party hosts."""
    if not isinstance(value, str) or not value:
        raise ProviderError("Falta una URL HTTPS aprobada por Seedloaf.")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except (ValueError, TypeError) as exc:
        raise ProviderError("URL de proveedor malformada.") from exc
    host = (parsed.hostname or "").lower()
    if (parsed.scheme != "https" or host not in ("seedloaf.com", "api.seedloaf.com")
            or port not in (None, 443) or parsed.username is not None
            or parsed.password is not None or not parsed.path.startswith("/")
            or parsed.path == "/" or parsed.query or parsed.fragment):
        raise ProviderError("Endpoint no permitido: debe ser HTTPS y del dominio Seedloaf.")
    return value


def config_from_env(env=None):
    env = env if env is not None else os.environ
    try:
        server_id = str(uuid.UUID(env.get("SEEDLOAF_SERVER_ID", "")))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ProviderError("SEEDLOAF_SERVER_ID no es un UUID valido.") from exc
    token = env.get("SEEDLOAF_OFFICIAL_API_TOKEN", "")
    if not isinstance(token, str) or not token.strip() or "\n" in token or "\r" in token:
        raise ProviderError("Falta un token API oficial valido.")
    return ProviderConfig(
        status_url=require_endpoint(env.get("SEEDLOAF_OFFICIAL_STATUS_URL", "")),
        start_url=require_endpoint(env.get("SEEDLOAF_OFFICIAL_START_URL", "")),
        api_token=token,
        server_id=server_id,
    )


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def request_json(method, url, token, server_id, timeout=10):
    """Exactly one HTTP attempt; never print request, token, URL or response body."""
    require_endpoint(url)
    if method not in ("GET", "POST"):
        raise ProviderError("Metodo HTTP no permitido.")
    data = None
    if method == "POST":
        data = json.dumps({"server_id": server_id}).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "SeedloafStart/2.0",
        },
    )
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=timeout) as response:
            code = response.status
            if code not in (200, 202):
                raise ProviderError("HTTP inesperado del proveedor: " + str(code))
            content_type = response.headers.get("Content-Type", "").lower()
            if "application/json" not in content_type:
                raise ProviderError("El proveedor no devolvio JSON.")
            payload = response.read(16_385)
            if len(payload) > 16_384:
                raise ProviderError("Respuesta demasiado grande.")
    except urllib.error.HTTPError as exc:
        code = exc.code
        if code in (429, 500, 502, 503, 504):
            raise TransientProviderError("Proveedor temporalmente indisponible: HTTP " + str(code)) from None
        raise ProviderError("El proveedor rechazo la solicitud: HTTP " + str(code)) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise TransientProviderError("Fallo de red al contactar al proveedor.") from None
    try:
        parsed = json.loads(payload.decode("utf-8"))
    except (UnicodeError, ValueError):
        raise ProviderError("JSON malformado del proveedor.") from None
    if not isinstance(parsed, dict):
        raise ProviderError("El proveedor no devolvio un objeto JSON.")
    return Response(code, parsed)


def parse_status(response):
    """Conservative proposed response contract, not verified Seedloaf API."""
    status = response.data.get("status")
    aliases = {
        "running": "running", "online": "running",
        "starting": "starting", "booting": "starting",
        "stopped": "stopped", "offline": "stopped",
    }
    if not isinstance(status, str) or status.lower() not in aliases:
        raise ProviderError("Estado no reconocido. No se enviara Start.")
    return aliases[status.lower()]


def _read_status(config, transport, pause, retries=2):
    for attempt in range(retries + 1):
        try:
            return parse_status(transport(
                "GET", config.status_url, config.api_token, config.server_id))
        except TransientProviderError:
            if attempt >= retries:
                raise
            pause(min(2 ** attempt, 4))
    raise ProviderError("Estado no disponible.")


def run_official(config, *, check_only=False, transport=request_json,
                 pause=time.sleep, status_checks=10):
    """GETs may retry; POST has ZERO automatic retries after any error/timeout.

    Uses *hypothetical* explicit status/start JSON contract. Only activate
    after Seedloaf issues official documentation/credentials for the endpoints.
    """
    status = _read_status(config, transport, pause)
    print("PROVEEDOR estado_inicial=" + status, flush=True)
    if status == "running":
        print("YA_ENCENDIDO: no se envia orden.", flush=True)
        return "running"
    if status == "starting":
        print("YA_ARRANCANDO: no se envia otra orden.", flush=True)
        return "starting"
    if check_only:
        print("CONSULTA_SOLO_LECTURA estado=stopped", flush=True)
        return "stopped"
    # POST ONCE. A lost response could mean it worked: never send it twice.
    try:
        response = transport(
            "POST", config.start_url, config.api_token, config.server_id)
    except TransientProviderError:
        print("START_INDETERMINADO: fallo de comunicacion; no se repite POST.",
              flush=True)
        raise
    # 200 or 202 require recognized status; 202 is NOT a confirmation of running.
    state = parse_status(response)
    if state == "stopped":
        raise ProviderError("Proveedor no confirmo ni acepto el arranque.")
    print("ORDEN_ACEPTADA estado=" + state, flush=True)
    if state == "running":
        return "running"
    for _ in range(max(0, min(status_checks, 30))):
        pause(5)
        try:
            state = _read_status(config, transport, pause, retries=0)
        except TransientProviderError:
            continue
        if state == "running":
            print("PANEL_PROVEEDOR_RUNNING: encendido reportado.", flush=True)
            return "running"
        if state == "stopped":
            raise ProviderError("Proveedor reporta detenido despues del Start.")
    print("ARRANQUE_PENDIENTE: orden aceptada sin confirmacion final.", flush=True)
    return "starting"


def main():
    config = config_from_env()
    check_only = (os.environ.get("CHECK_ONLY", "").lower() == "true")
    result = run_official(config, check_only=check_only)
    return 0 if result == "running" or (check_only and result == "stopped") else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProviderError as exc:
        print("PROVEEDOR_ERROR: " + str(exc), flush=True)
        raise SystemExit(1)
