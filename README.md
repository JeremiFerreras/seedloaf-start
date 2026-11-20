# Seedloaf Start 🎮

Fork de [dibope/mcserverstarter](https://github.com/dibope/mcserverstarter), adaptado para **encender un solo servidor de Seedloaf** usando GitHub Actions. No apaga el servidor ni lo enciende al modificar el código.

## Estado

- Preparado: workflow manual **Encender Seedloaf**, sin activación por push.
- Preparado: pruebas unitarias y controles para no pulsar el botón equivocado.
- Pendiente: prueba real de arranque en Seedloaf. El sitio puede cambiar o mostrar Cloudflare.
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
- Si el botón no coincide con las etiquetas esperadas, hay varios Start o aparece una verificación humana, falla sin intentar eludir protecciones.
- No registra credenciales ni almacena cachés de sesión. No contiene un comando Stop.
- Ningún push inicia Seedloaf. `workflow_dispatch` será la interfaz de activación futura.

## Pruebas

El flujo **Pruebas Seedloaf Start** revisa sintaxis y ejecuta pruebas sin credenciales después de cambios en código o workflows. Localmente:

```bash
python -m unittest discover -s tests -v
```

Estas pruebas no garantizan acceso a Seedloaf: todavía hay que verificar el login, los selectores HTML y el encendido real.
