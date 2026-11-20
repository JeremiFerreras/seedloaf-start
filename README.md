# Seedloaf Start 🎮

Fork de [dibope/mcserverstarter](https://github.com/dibope/mcserverstarter), adaptado para **encender un solo servidor de Seedloaf** usando GitHub Actions. No apaga el servidor ni lo enciende al modificar el código.

## Estado

- Preparado: workflow manual **Encender Seedloaf**, sin activación por push.
- Preparado: pruebas unitarias y controles para no pulsar el botón equivocado.
- Experimental: SeleniumBase **UC Mode** con navegador local Xvfb intenta gestionar la comprobación web antes del formulario.
- Pendiente: prueba real de arranque en Seedloaf; el desafío de Cloudflare puede continuar bloqueando al navegador.
- No implementado: enlace público de WhatsApp, Cloudflare Workers y autenticación por Google.

## Configuración necesaria

1. Abre **Actions** y habilita los workflows si aparece el botón de habilitación del fork.
2. **Google OAuth NO está admitido por el script original ni por esta adaptación.** Usa una cuenta secundaria de Seedloaf con correo y contraseña y concédele **solo rol Starter** mediante **Acceso**. Consulta la [documentación oficial](https://seedloaf.com/documentation/es/add-users). Si Seedloaf no permite dicha cuenta, esta automatización no será viable sin otro método oficial.
3. En **Settings → Secrets and variables → Actions → New repository secret**, crea:
   - `USERNAME`: email de esa cuenta secundaria de Seedloaf.
   - `PASSWORD`: contraseña de esa cuenta secundaria (nunca tu contraseña de Google).
   - `SEEDLOAF_SERVER_ID`: identificador UUID de la URL `/dashboard/<UUID>/console`.
4. Apaga primero tu servidor si quieres comprobar que arranca; abre **Actions → Encender Seedloaf → Run workflow**. Examina los logs y comprueba el estado real en Seedloaf.

**No pegues contraseñas, cookies, tokens ni capturas con datos de sesión en el repositorio o en el chat.** No podemos añadir estos secretos por la conexión GitHub disponible.

## Protecciones

- El script comprueba el UUID; no navega a otros servidores por error.
- Si el servidor ya está encendido, evita pulsar Start de nuevo.
- Si el botón no coincide con las etiquetas esperadas, hay varios Start o la verificación web no se resuelve, falla sin pulsar controles desconocidos.
- No registra credenciales ni almacena cachés de sesión. No comparte cookies ni credenciales con proveedores de proxy externos. No contiene un comando Stop.
- Ningún push inicia Seedloaf. `workflow_dispatch` será la interfaz de activación futura.

## Pruebas

El flujo **Pruebas Seedloaf Start** revisa sintaxis y ejecuta pruebas sin credenciales después de cambios en código o workflows. Localmente:

```bash
python -m unittest discover -s tests -v
```

Estas pruebas no garantizan acceso a Seedloaf: todavía hay que verificar el login, los selectores HTML y el encendido real.

## Navegador experimental (noviembre de 2026)

- Usa [SeleniumBase](https://github.com/seleniumbase/SeleniumBase) `4.58.0` con UC Mode y Xvfb dentro de GitHub Actions, sin API de pago ni servicios de terceros.
- Solo se intenta resolver una verificación web por página. No se garantiza que la protección de Cloudflare permita automatización desde una IP de GitHub.
- No cambia ni necesita nuevos secretos. La prueba real puede fallar por la protección, el inicio de sesión o cambios del panel de Seedloaf.
- Si la cuenta o el sitio impone requisitos adicionales, respetarlos y preferir un inicio autorizado desde el propio proveedor.
