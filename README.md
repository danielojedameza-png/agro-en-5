# Agro en 5 · AGRODASIN

Las 5 noticias del agro del día. Gratis, con suscripción. Web actualizada cada hora y boletín por correo a las 5:30 a.m.

## Cómo funciona

| Pieza | Dónde corre | Qué hace | Costo |
|---|---|---|---|
| `web/index.html` | Netlify | Página con formulario y las 5 noticias | Plan gratis |
| `netlify/functions/suscribir.mjs` | Netlify | Registra al suscriptor en Brevo con doble confirmación | Plan gratis |
| `scripts/actualizar_noticias.py` | GitHub Actions, cada hora | Lee fuentes, puntúa, elige 5, escribe `datos/noticias.json` | Gratis en repo público |
| `scripts/enviar_boletin.py` | GitHub Actions, 5:20 a.m. | Envía el boletín a la lista de Brevo | Brevo gratis hasta 300 correos/día |
| API de Claude (opcional) | Desde el script | Redacta "resumen" y "por qué te importa" | Centavos de dólar al día con Haiku |

La página lee las noticias desde GitHub (`raw.githubusercontent.com`). Así Netlify no redespliega cada hora.

## Paso a paso

### 1. Repositorio en GitHub
1. Crea el repo **público** `agro-en-5` en la cuenta de AGRODASIN.
2. Sube todo este contenido:
   ```powershell
   cd agro-en-5
   git init
   git add .
   git commit -m "Agro en 5: versión inicial"
   git branch -M main
   git remote add origin https://github.com/[USUARIO_GITHUB]/agro-en-5.git
   git push -u origin main
   ```
3. En `web/index.html`, línea `NOTICIAS_URL`, cambia `[USUARIO_GITHUB]`.

### 2. Brevo (correo)
1. Crea cuenta en brevo.com con `contacto@agrodasin.org.co`.
2. Autentica el dominio `agrodasin.org.co` (registros SPF, DKIM y DMARC en el DNS). Sin esto, el boletín cae en spam.
3. Crea la lista "Agro en 5" y anota su **ID**.
4. En Contactos > Atributos crea, tipo texto: `NOMBRE`, `DEPARTAMENTO`, `MUNICIPIO`, `ACTIVIDAD`, `WHATSAPP`, `AUTORIZACION_DATOS`.
5. Crea una plantilla de **doble confirmación (DOI)** con la etiqueta `{{ doubleoptin }}` en el botón. Anota su **ID**.
6. Genera una clave API (SMTP & API > API Keys).

### 3. Secretos en GitHub
Settings > Secrets and variables > Actions:

| Nombre | Tipo | Valor |
|---|---|---|
| `BREVO_API_KEY` | Secret | Clave de Brevo |
| `BREVO_LISTA_ID` | Secret | ID de la lista |
| `BREVO_REMITENTE` | Secret | `boletin@agrodasin.org.co` (dominio autenticado) |
| `ANTHROPIC_API_KEY` | Secret | Opcional. Sin ella usa textos base |
| `TERRITORIO_TOKEN` | Secret | Opcional. Token fine-grained de GitHub, **solo lectura, permiso "Contents" y solo sobre el repo privado `territorio-agrodasin-backup`**. Sin él, se omite esa fuente y sigue solo con Google Noticias |
| `URL_WEB` | Variable | `https://agrodasin.org.co/agro-en-5` o el subdominio que uses |

### 4. Netlify
1. Add new site > Import from GitHub > `agro-en-5`. Netlify lee `netlify.toml`.
2. Site configuration > Environment variables: `BREVO_API_KEY`, `BREVO_LISTA_ID`, `BREVO_PLANTILLA_DOI_ID`, `URL_CONFIRMADO`.
3. Dominio: crea `noticias.agrodasin.org.co` (CNAME al sitio Netlify) o enlaza desde el menú de agrodasin.org.co.

### 5. Primera prueba
1. GitHub > Actions > "Agro en 5" > Run workflow, `enviar = no`. Debe aparecer `datos/noticias.json`.
2. Abre la web. El aviso amarillo de demostración debe desaparecer.
3. Prueba el formulario:
   ```bash
   curl -X POST https://[TU_SITIO].netlify.app/api/suscribir \
     -H "Content-Type: application/json" \
     -d '{"nombre":"Prueba","email":"tu_correo@gmail.com","departamento":"Bolívar","actividad":"Otro","acepto":true}'
   ```
   Esperado: `{"ok":true}` y un correo de confirmación.
4. Confirma el correo. Luego Run workflow con `enviar = si`. Debe llegar el boletín.

## Ajustes editoriales
- **Temas y búsquedas**: diccionario `CONSULTAS` en `actualizar_noticias.py`.
- **Qué pesa más**: `PESOS` (palabras clave), `REGION` (bono Caribe +4) y `FUENTES_PRIORITARIAS`.
- **Fuentes directas**: activa `FEEDS_DIRECTOS` solo después de verificar que la URL entrega RSS.
- **Diversidad**: `MAX_POR_CATEGORIA = 2`.
- **Territorio como fuente**: `leer_territorio()` trae `newsAndOpportunities.updated` del respaldo privado `territorio-agrodasin-backup` (requiere `TERRITORIO_TOKEN`). Ese repo se actualiza a mano — Daniel sube ahí la exportación de ChatGPT Sites cada vez que actualiza Territorio, no hay automatización de ese lado.

## Reglas que no se deben romper
- Solo título, fuente, enlace y resumen propio. Nunca copiar párrafos del medio.
- La IA solo resume lo que dice el título y el extracto. No inventa cifras.
- Sin autorización de datos marcada, no hay registro (Ley 1581 de 2012, Decreto 1074 de 2015).
- Publicar la política de tratamiento de datos de AGRODASIN y reemplazar `[URL_POLITICA_DATOS]` en la página.

## Fase 2 (cuando haya 300+ suscriptores)
- Audio diario de 3 minutos (formato podcast) con texto a voz a partir del mismo JSON.
- Canal de WhatsApp de AGRODASIN con el texto del día (publicación manual o semiautomática).
- Plan pago de Brevo o cambio de proveedor al pasar de 300 envíos diarios.
