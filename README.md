# Seedloaf Start 🎮

Fork de [dibope/mcserverstarter](https://github.com/dibope/mcserverstarter), adaptado para **encender un solo servidor de Seedloaf** usando GitHub Actions. No apaga el servidor ni lo enciende al modificar el código.

## Estado

- Preparado: workflow manual **Encender Seedloaf**, sin activación por push.
- Preparado: pruebas unitarias y controles para no pulsar el botón equivocado.
- Experimental: SeleniumBase **UC Mode** con navegador local Xvfb intenta gestionar la comprobación web antes del formulario.
- Pruebas reales: UC atravesó la verificación y completó el login en varias ejecuciones; llegó a pulsar Start y una comprobación posterior de solo lectura confirmó que el servidor estaba `already_running`.
- La verificación sigue siendo intermitente: hubo ejecuciones que continuaron bloqueadas. No puede garantizarse un encendido automático en el 100 % de los intentos.
- No implementado: enlace público de WhatsApp, Cloudflare Workers y autenticación por Google.

## Configuración necesaria

1. Abre **Actions** y habilita los workflows si aparece el botón de habilitación del fork.
2. **Google OAuth NO está admitido por el script original ni por esta adaptación.** Usa una cuenta secundaria de Seedloaf con correo y contraseña y concédele **solo rol Starter** mediante **Acceso**. Consulta la [documentación oficial](https://seedloaf.com/documentation/es/add-users). Si Seedloaf no permite dicha cuenta, esta automatización no será viable sin otro método oficial.
3. En **Settings → Secrets and variables → Actions → New repository secret**, crea:
   - `USERNAME`: email de esa cuenta secundaria de Seedloaf.
   - `PASSWORD`: contraseña de esa cuenta secundaria (nunca tu contraseña de Google).
   - `SEEDLOAF_SERVER_ID`: identificador UUID de la URL `/dashboard/<UUID>/console`.
4. Abre **Actions → Encender Seedloaf → Run workflow**. Para comprobar el estado sin encender nada, activa `check_only`. Para solicitar encendido, deja `check_only` desactivado. Revisa los logs y comprueba el estado real en Seedloaf. El script espera hasta 120 segundos tras pulsar Start para confirmar que aparece el botón Stop.

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

## Resultados reales en GitHub (noviembre de 2026)

- [UC abrió el formulario, inició sesión y llegó a Start](https://github.com/JeremiFerreras/seedloaf-start/actions/runs/44661437339). El clic no se confirmó durante los 35 s de espera antiguos, por eso el workflow falló.
- [Comprobación de estado de solo lectura exitosa](https://github.com/JeremiFerreras/seedloaf-start/actions/runs/44661848389): `CONSULTA_SOLO_LECTURA estado=already_running`. **No se pulsó Start en esta ejecución**.
- Varias ejecuciones siguen fallando en la verificación inicial de Cloudflare; el éxito no es garantizado. El aumento de espera a 120 s aún no tiene validación en un encendido nuevo desde apagado.
- Esta integración no implementa aún el enlace público de WhatsApp: esa fase requiere un disparador autorizado que no exponga tokens.

## Fiabilidad y pruebas automatizadas

- **79 pruebas unitarias**, incluyendo **13.296 situaciones sintéticas deterministas** de botones, redirecciones y estados (el conteo de casos no equivale a 13.296 inicios reales).
- **Dos pruebas de navegador reales contra HTML simulado:** un único clic Start seguido de transición retardada a Stop, y rechazo de una URL que no corresponde al servidor.
- La acción es **idempotente**: si aparece únicamente Stop, no vuelve a pulsar Start. Si hay botones contradictorios, elementos inestables o no se reconoce el control, falla sin hacer clic.
- Tras pulsar Start, espera hasta **120 segundos** para ver Stop en la consola exacta. Si no aparece, devuelve error de **resultado no confirmado**, pero no repite el clic (la solicitud original podría seguir procesándose).
- Cloudflare puede presentar un desafío antes del formulario. Se permite solo **una recuperación adicional** si sigue activo, sin intentos ilimitados ni reenvío de credenciales.
- El éxito indicado por Stop confirma **el estado representado por el panel**, no que el servidor de Minecraft ya responda a jugadores. Se necesita una comprobación adicional de conectividad para afirmar eso.
- No hay promesa de encendido en cada intento: las verificaciones externas y cambios de interfaz de Seedloaf están fuera del control de GitHub Actions.

### Cómo comprobarlo sin encender nada

1. Ve a **Actions → Encender Seedloaf → Run workflow**.
2. Marca `check_only` para revisar el panel en modo solo lectura.
3. Revisa el mensaje `CONSULTA_SOLO_LECTURA`. Si el estado es `already_running`, el panel indica encendido; si es `can_start`, indica apagado.
4. Para encender, ejecuta de nuevo dejando `check_only` **desmarcado**. Nunca ejecutes manualmente dos inicios mientras uno siga pendiente.

### Interpretación de resultados

| Mensaje | Significado |
| --- | --- |
| `START_PANEL_CONFIRMADO` | La consola mostró Stop en el servidor previsto |
| `START_SOLICITADO` sin confirmación | Se pulsó Start una vez; resultado indeterminado |
| `CONSULTA_SOLO_LECTURA` | Se leyó el estado sin pulsar Start |
| `DIAGNOSTICO ... challenge=1` | Verificación web bloquea o retrasa el acceso |
| `Estado no seguro` | Controles contradictorios, página incorrecta o elemento inestable |


## Version 2: reducir la dependencia de Cloudflare (noviembre 2026)

**Situacion real:** el plan **premium** de Seedloaf ofrece despertar automaticamente el servidor al intentar conectarse desde Minecraft. En el plan **gratuito** se necesita iniciar el servidor desde el panel. No se encontro una API publica de encendido documentada; por tanto no podemos garantizar un encendido gratis que nunca dependa de Cloudflare.

### Comprobacion opcional de Minecraft sin navegador

Si quieres, crea el secreto **MINECRAFT_ADDRESS** con el subdominio Java de tu servidor, por ejemplo **mi-mundo.seedloaf.gg** o **mi-mundo.seedloaf.gg:25565**.

- GitHub consulta primero el protocolo de estado de Minecraft. Si responde correctamente, omite el navegador: no necesita pasar por Cloudflare para constatar que el servidor responde.
- Si no responde, sigue con el backend seleccionado. La ausencia de respuesta no demuestra que el servidor este apagado.
- Solo se permiten subdominios **.seedloaf.gg**. La consulta no transmite contrasenas ni comandos.
- Un proxy podria responder aunque el mundo no este listo para jugadores. Esta comprobacion es para protocolo **Minecraft Java**, no Bedrock.

### Motor sin navegador para una futura API oficial

En **Actions -> Encender Seedloaf -> Run workflow**, la opcion **backend** permite elegir:

- **browser (predeterminado):** SeleniumBase con tus tres secretos actuales; puede seguir viendo Cloudflare.
- **official_api (experimental y sin habilitar):** integracion HTTP preparada para el caso de que Seedloaf facilite endpoints y un token oficiales. **No existe actualmente una API publica verificada para activarla.**

No introduzcas URLs extraidas de las herramientas de desarrollador de tu navegador ni reutilices cookies o tokens de sesion. El adaptador solo debe activarse despues de confirmar con Seedloaf un protocolo oficial y el permiso de automatizacion.

Cuando Seedloaf proporcione un protocolo oficial compatible, los secretos previstos son **SEEDLOAF_OFFICIAL_STATUS_URL**, **SEEDLOAF_OFFICIAL_START_URL** y **SEEDLOAF_OFFICIAL_API_TOKEN**. Las URL deben estar en HTTPS bajo seedloaf.com o api.seedloaf.com. El formato JSON implementado es un **contrato propuesto y sin verificar** con un campo status: running / starting / stopped. Debe ajustarse a la documentacion oficial antes de usarlo de verdad.

El motor:
- Consulta el estado antes de cualquier inicio. Evita enviar Start si ya esta encendido o arrancando.
- Reintenta solamente consultas GET, con limites. **Nunca repite automaticamente un POST Start**, ni cuando la red se corta despues de enviarlo.
- Rechaza redirecciones, respuestas HTML, errores de permisos, URLs no autorizadas y estados desconocidos.
- No vuelve silenciosamente a Selenium si falla la interfaz API.
- No confunde HTTP 202 (orden aceptada) con servidor de Minecraft disponible.

### Validacion y limite del resultado

La bateria automatica actual ejecuto **150 pruebas unitarias**, incluyendo fallos provocados en respuestas HTTP (401, 403, 429, 503), datos corruptos, tiempos de espera y validacion de dominios; ademas **2 pruebas con Chrome real** sobre HTML simulado. Incluye mas de 18.000 combinaciones sinteticas reproducibles, **no 18.000 arranques reales**.

Validacion: https://github.com/JeremiFerreras/seedloaf-start/actions/runs/44785963882

El flujo GitHub Actions continua **manual** y CI no accede a secretos ni inicia Seedloaf. Ninguna prueba de esta version demostro que un mundo apagado en el plan gratuito pueda encenderse sin Cloudflare. Se necesita un mecanismo oficial del proveedor para poder afirmar eso.

Fuentes:
- https://seedloaf.com/minecraft-server/2-players
- https://seedloaf.com/documentation/es/add-users
