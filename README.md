# BOE Alertas C1 · GitHub Pages

Web estática para vigilar publicaciones del BOE relacionadas con:

- Concursos y provisión de puestos para AGE.
- Libre designación.
- Comisiones de servicio.
- Convocatorias/oposiciones de entidades locales, diputaciones y comunidades autónomas.
- Perfil principal: informática/TIC C1, con posibilidad de revisar administrativo C1 y C1/A2.
- Provincia por defecto: **Albacete**.

La web funciona en GitHub Pages porque solo usa HTML, CSS y JavaScript. La parte automática se hace con **GitHub Actions**, que consulta la API del BOE y actualiza `data/alertas.json`.

---

## Qué se ha añadido en esta versión

### 1. Buscar por la fecha que quieras

En la pantalla principal puedes usar:

- **Fecha exacta rápida**: busca solo ese día.
- **Fecha desde / Fecha hasta**: busca un rango completo.
- **Días hacia atrás**: si no indicas fechas, revisa los últimos X días.

### 2. Enlaces directos al BOE

Cada resultado incluye botones para:

- Abrir la disposición concreta en BOE.
- Abrir el PDF del BOE.
- Abrir el XML del BOE.
- Abrir el sumario completo de ese día.
- Abrir la API oficial de ese día.

### 3. Ejecución manual del workflow con fechas

En GitHub puedes ir a:

```text
Actions → Revisar BOE alertas C1 → Run workflow
```

Y rellenar:

```text
fecha_desde: 2026-04-01
fecha_hasta: 2026-04-29
provincia: Albacete
```

Eso actualizará `data/alertas.json` con ese rango.

---

## Cómo probar en local

No abras `index.html` con doble clic, porque algunos navegadores bloquean la lectura de `data/alertas.json`.

Abre una terminal dentro de la carpeta del proyecto y ejecuta:

```bash
python -m http.server 8000
```

Luego abre:

```text
http://localhost:8000
```

---

## Cómo subirlo a GitHub Pages

1. Crea un repositorio nuevo en GitHub, por ejemplo:

```text
boe-alertas-c1
```

2. Sube todos los archivos de este proyecto.

3. Ve a:

```text
Settings → Pages
```

4. En **Build and deployment**, selecciona:

```text
Deploy from a branch
```

5. Rama:

```text
main / root
```

6. Guarda.

La web quedará publicada en una URL similar a:

```text
https://TU_USUARIO.github.io/boe-alertas-c1/
```

---

## Cómo activar los avisos automáticos

El archivo:

```text
.github/workflows/boe-alertas.yml
```

revisa el BOE automáticamente de lunes a sábado.

Cuando detecta nuevas alertas:

1. Actualiza `data/alertas.json`.
2. Crea una issue en GitHub con los enlaces al BOE.
3. Si tienes activadas las notificaciones del repositorio, GitHub te avisará.

Para recibir avisos:

1. Entra en el repositorio.
2. Pulsa **Watch**.
3. Elige **All Activity** o configura tus notificaciones.

---

## Cómo buscar una fecha antigua

Desde GitHub:

```text
Actions → Revisar BOE alertas C1 → Run workflow
```

Ejemplo:

```text
fecha_desde: 2025-01-01
fecha_hasta: 2025-12-31
provincia: Albacete
```

El script tiene un límite de seguridad de 90 días por ejecución para no hacer consultas enormes. Si quieres revisar un año completo, hazlo por trimestres.

También puedes hacerlo en local:

```bash
python scripts/scan_boe.py --desde 2026-04-01 --hasta 2026-04-29 --provincia Albacete
```

---

## Archivos importantes

```text
index.html                         Web principal
assets/css/styles.css              Estilos visuales
assets/js/app.js                   Lógica de filtros y enlaces
scripts/scan_boe.py                Escáner BOE usado por GitHub Actions
data/config.json                   Palabras clave, provincias y perfiles
data/alertas.json                  Resultados que muestra la web
.github/workflows/boe-alertas.yml  Automatización diaria
```

---

## Sobre los concursos AGE y la provincia

En muchas publicaciones de concursos de la Administración General del Estado, el título del sumario no dice “Albacete”. Por ejemplo, puede aparecer algo como:

```text
Resolución por la que se convoca concurso específico para la provisión de puestos de trabajo...
```

La provincia aparece después dentro del PDF, en los anexos o en el listado de puestos.

Por eso este proyecto marca esos casos como:

```text
Revisar anexo
```

No los descarta automáticamente, porque podrían contener plazas en Albacete.

---

## Personalizar palabras clave

Edita:

```text
data/config.json
```

Puedes añadir más palabras en:

```json
"informatica": [
  "informática",
  "TIC",
  "sistemas",
  "programador"
]
```

También puedes añadir entidades:

```json
"entidades_prioritarias": [
  "Ayuntamiento de Albacete",
  "Diputación Provincial de Albacete",
  "Junta de Comunidades de Castilla-La Mancha",
  "SEPE"
]
```

---

## Limitaciones reales

GitHub Pages no ejecuta PHP, Python ni tareas en segundo plano. Por eso:

- La web muestra datos ya generados en `data/alertas.json`.
- GitHub Actions hace la revisión automática.
- El botón “Intentar consultar API desde navegador” puede funcionar o no según CORS del BOE/navegador.
- El método fiable es el workflow de GitHub Actions.

---

## Fuentes oficiales usadas

- API de datos abiertos del BOE.
- Sumario diario del BOE.
- RSS oficiales del BOE, incluyendo Sección II.B - Oposiciones y concursos.
