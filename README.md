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


## Version 2.1 — Inicio mas rapido y pruebas de resistencia

**MINECRAFT_ADDRESS** ya acepta:
- nombre.seedloaf.gg (con puerto opcional, p. ej. nombre.seedloaf.gg:51229);
- una direccion IPv4 **publica** con puerto opcional, si Seedloaf te asigna una IP numerica.

No acepta IP privadas, localhost, multicast, URLs ni dominios de terceros. Esto evita que el workflow consulte por error dispositivos internos.

### Secuencia de encendido

1. GitHub hace **dos consultas de estado Minecraft Java** con una breve separacion. Si ambas responden, el servidor ya atiende el protocolo y se **omite incluso instalar SeleniumBase**, asi que no visita Cloudflare.
2. Cuando el servidor no responde, prepara el backend seleccionado. En el backend browser sigue el inicio habitual con los tres secretos.
3. Si pulsa Start, **solo lo hace una vez** y espera confirmacion del panel. Si la red cae tras el clic, no reintenta esa accion.
4. Tras un inicio confirmado por el backend y teniendo MINECRAFT_ADDRESS configurada, hace hasta **5 consultas de estado Java**, separadas por 7 segundos, para distinguir un mundo aun cargando de uno que ya responde. El resultado se registra en `POSTFLIGHT_MINECRAFT`. Una respuesta negativa no vuelve a pulsar Start.
5. La existencia de un proxy que responde al ping de Minecraft puede producir un falso positivo: los mensajes de estado Java **no demuestran** que el servidor este listo para entrar ni que todos los mods hayan cargado. Para confirmarlo se requiere una conexion real.

### Cloudflare

Esta version reduce los accesos innecesarios al formulario cuando Minecraft ya responde, **no** altera ni evita las protecciones de Cloudflare cuando Seedloaf esta apagado. Cloudflare no garantiza desafios de produccion para navegadores automatizados: el resultado continua sujeto a su configuracion.

El modo `official_api` permanece como adaptador **experimental sin API de Seedloaf confirmada**; no puede considerarse un encendido funcional alternativo. Para depender de ese modo seria necesario documentacion y credenciales oficiales del proveedor.

### Pruebas

- Pruebas de deteccion de direccion publica y rechazo de rangos privados/multicast.
- Inyeccion de respuestas tardias, intermitentes, caidas de red, errores de formato, estados desconocidos y falsos encendidos.
- Pruebas de que no se duplica Start tras un timeout y de que el workflow omite la instalacion del navegador cuando el servidor ya responde.
- Tests unitarios y pruebas de Chrome con HTML simulado en GitHub Actions. **Las pruebas de estres no representan miles de encendidos reales de Seedloaf.**



### Resultado del ensayo real de esta version

- [Ejecucion de encendido desde GitHub Actions](https://github.com/JeremiFerreras/seedloaf-start/actions/runs/44789704279): la direccion de Minecraft paso la validacion, pero el preflight indico `not_confirmed`, por lo que el sistema paso al navegador.
- Se iniciaron Chrome y SeleniumBase, pero la pagina de acceso siguio presentando un reto de Cloudflare (`challenge=1`) y no aparecio el formulario; la ejecucion **fallo sin llegar a Start**.
- Esto **no permite** concluir si el servidor Minecraft estaba apagado. Comprueba que `MINECRAFT_ADDRESS` sea la direccion **Java exacta**, incluyendo `:puerto` cuando Seedloaf proporciona uno que no es `25565`.
- El backend predeterminado ahora es `browser` incluso cuando un disparador externo omite ese parametro; antes esos disparos fallaban en la validacion de workflow.
- Si el servidor esta apagado, **la comprobacion de Minecraft no lo enciende**. Solo Seedloaf puede activar ese servidor mediante un mecanismo autorizado. No se recomienda almacenar cookies ni sesiones de acceso a Seedloaf en GitHub Actions.
- El comportamiento de Cloudflare es externo y variable. Ningun resultado de pruebas locales o simuladas demuestra un porcentaje de exito real al encender.

## Version 2.2 — Diagnostico sin Cloudflare y DNS SRV

- Con la direccion de Minecraft **sin puerto**, `minecraft_status_auto` consulta el registro DNS SRV `_minecraft._tcp` y usa el destino publicado; conserva el hostname original en el handshake de Minecraft Java. Si configuras un puerto explicito (por ejemplo `:50690`), respeta ese puerto sin pedir SRV.
- **La consulta de estado solo sirve para evitar accesos innecesarios a la web cuando Minecraft ya responde.** No arranca un servidor apagado.
- Nuevo workflow manual **Diagnostico Minecraft (sin Seedloaf web)**: usa `MINECRAFT_ADDRESS`, comprueba el destino configurado, registra si encuentra SRV y comprueba por separado el puerto `25565` para dominios Seedloaf con puerto personalizado. No inicia sesion, no pulsa Start, no publica la direccion.
- Para ejecutarlo: GitHub -> Actions -> Diagnostico Minecraft (sin Seedloaf web) -> Run workflow. Las salidas no revelan la direccion guardada como secreto.
- Un `no_response` no distingue entre servidor apagado, problemas de DNS o puerto inaccesible. El resultado del diagnostico no debe usarse como evidencia de un mundo encendido/apagado.
- **Resultado de una prueba real en GitHub:** `configured=no_response`, `srv_record=absent_or_unavailable`, `default_port_probe=no_response`. No hay prueba de acceso a Seedloaf en esta ejecucion. Registros: https://github.com/JeremiFerreras/seedloaf-start/actions/runs/44793784779
- Los proyectos de la comunidad que intentan disimular navegadores (por ejemplo SeleniumBase UC/CDP) no ofrecen ninguna garantia de que Cloudflare los admita. Cloudflare declara que los navegadores automatizados no estan soportados para resolver challenges de produccion: https://developers.cloudflare.com/cloudflare-challenges/reference/supported-browsers/
- No se almacenan ni exportan cookies de inicio de sesion a caches o artefactos de GitHub. No se alteran huellas digitales para saltar medidas del proveedor.

## Version 2.3: navegador experimental CDP (20 noviembre 2026)

- Se agrego **browser_cdp** como opcion manual en Actions -> Encender Seedloaf -> Run workflow. **browser** continua como predeterminado.
- Implementado sobre SeleniumBase CDP usando una unica sesion de navegador, sin mezclar comandos WebDriver con acciones CDP y sin volver a cargar la pagina de login innecesariamente.
- Solo permite clic en un unico control Start de la consola exacta del servidor, compara de nuevo la identidad del control antes de pulsarlo y **nunca** repite Start ante errores o timeouts.
- Se agregaron pruebas unitarias contra paginas falsas y pruebas reales de Chrome sobre HTML local de Start/Stop y login de dos pasos. Los tests no hacen peticiones a Seedloaf ni usan secretos.
- **Prueba CDP 1**: la verificacion de acceso siguio bloqueada antes de introducir credenciales: https://github.com/JeremiFerreras/seedloaf-start/actions/runs/44796161330
- **Prueba CDP 2**: alcanzo ambos campos del login y envio la contrasena, pero Seedloaf no completo el redireccionamiento a dashboard: https://github.com/JeremiFerreras/seedloaf-start/actions/runs/44796877369
- **Prueba CDP 3**: la verificacion de Cloudflare volvio a impedir que apareciese el campo de correo: https://github.com/JeremiFerreras/seedloaf-start/actions/runs/44797744561
- **Resultado global**: 0/3 ejecuciones CDP con arranque confirmado. Estas tres ejecuciones **no** permiten estimar estadisticamente una tasa de exito fiable.
- Si una cuenta requiere confirmacion de email o MFA, no se intenta eludir ese control. Los diagnosticos de autenticacion registran solamente indicadores de estado, nunca correo, contrasena, cookies, HTML o tokens.
- No se han guardado sesiones ni exportado cookies a artefactos o cachés de Actions. El workflow sigue en modo manual para evitar que un push arranque el servidor.
- No se recomienda usar FlareSolverr como solador de retos: su propio README advierte que los solvers de CAPTCHA no funcionan actualmente, y traslada cookies y HTML entre procesos. https://github.com/FlareSolverr/FlareSolverr
- La propia documentacion de Cloudflare establece que los navegadores automatizados no estan soportados para resolver retos de produccion: https://developers.cloudflare.com/cloudflare-challenges/reference/supported-browsers/
- La documentacion oficial de Seedloaf ofrece `Starter` y `Public Start` como mecanismos autorizados: https://seedloaf.com/documentation/es/add-users
- **Pendiente**: una interfaz oficial de encendido independiente del navegador, o comprobar una ejecucion desde apagado que alcance Start y verifique el protocolo Minecraft. No considerar browser_cdp estable ni garantizar que no aparezcan retos.

## Version 2.4 — Public Start sin cuenta privada (20 noviembre de 2026)

**Backend opcional `public_start` disponible** en GitHub -> Actions -> **Encender Seedloaf** -> **Run workflow** -> selecciona `public_start`. El motor de navegador anterior (`browser`) sigue como valor predeterminado porque Public Start todavía no ha completado un arranque real en GitHub Actions.

### Configuración

- Se usa el `Repository Secret` **DOMAIN**. Introduce exactamente lo que escribirías en el campo de Public Start: un subdominio corto (ejemplo `miservidor`) o un host `miservidor.seedloaf.gg`. Si incluyes `:puerto`, el software elimina el puerto para el formulario. **No se imprime el DOMAIN**.
- A diferencia del dashboard, este backend **no requiere USERNAME, PASSWORD ni SEEDLOAF_SERVER_ID**. El workflow conserva los secretos anteriores intactos para los otros backends.
- `MINECRAFT_ADDRESS` sigue siendo útil: el preflight evita abrir la web si Minecraft ya responde y el postflight (hasta 10 comprobaciones) solo confirma arranque cuando recibe una respuesta real al protocolo Minecraft Java.
- `check_only=true` solo comprueba que el formulario está disponible; nunca escribe DOMAIN ni solicita Start.

### Comportamiento seguro

- Abre `https://seedloaf.com/public-start`, exclusivamente por HTTPS.
- Si encuentra un desafío Cloudflare, hace **como máximo una** interacción con el método documentado `cdp.solve_captcha()`. No automatiza miles de intentos ni repite recargas/clics si el desafío no se resuelve.
- Exige un único campo de texto visible y un único control inequívoco Start; si hay campos o botones ambiguos, se detiene para evitar acciones incorrectas.
- Antes de escribir DOMAIN y hacer clic, comprueba de nuevo el origen, los elementos y su identidad. Tras un clic no envía una segunda solicitud, aunque la respuesta sea lenta o incierta.
- **Un envío del formulario no equivale a éxito.** Se informa éxito solo si un chequeo Minecraft Java confirma respuesta después de solicitar encendido. La verificación del protocolo tampoco garantiza que todos los mods estén listos para entrar.
- No descarga cookies, no guarda sesiones en GitHub, no publica capturas ni registra contenido del formulario.

### Prueba real, con resultado negativo

- Ejecución: https://github.com/JeremiFerreras/seedloaf-start/actions/runs/44800476592
- Resultado: `PUBLIC_DIAG estado=challenge_interactive`, seguido de `verification_attempt=1`. Después de esperar, `challenge=1 fields=1 controls=0` y error `Public Start no expuso un formulario utilizable`.
- **No se pulsó Start.** Este resultado confirma que Public Start elimina el login pero no necesariamente el control de Cloudflare. No hay demostración de arranque en producción con este backend.
- La página de Public Start respondió `403 Forbidden` desde la herramienta de consulta web. Los selectores reales de su formulario **no han podido confirmarse**, por eso se usa una selección conservadora que se aborta si cambia la interfaz.
- Documentación oficial: https://seedloaf.com/documentation/es/add-users y https://seedloaf.com/public-start
