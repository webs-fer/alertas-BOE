# BOE Alertas Informática v5

Proyecto preparado para vigilar el BOE y detectar alertas útiles para tu perfil:

1. **Informática / TIC / TAI / sistemas / redes / soporte / programación** → prioridad máxima.
2. **Administrativo C1 real** → prioridad alta/secundaria.
3. **Auxiliar Administrativo C2** → oculto por defecto.
4. **Policía, bomberos, peones, letrados, FHN, libre designación no útil** → descartado.

El proyecto genera:

- `outputs/alertas.json`: resultado completo.
- `docs/alertas.json`: JSON usado por la web.
- `docs/index.html`: dashboard visual para GitHub Pages.

---

## Estructura

```text
boe-alertas-informatica-v5/
├── scripts/
│   └── scan_boe.py
├── config/
│   └── user_profile.json
├── docs/
│   ├── index.html
│   ├── styles.css
│   ├── app.js
│   └── alertas.json
├── outputs/
│   └── .gitkeep
├── .github/
│   └── workflows/
│       └── scan_boe.yml
├── requirements.txt
└── README.md
```

---

## Instalación local

```bash
pip install -r requirements.txt
```

---

## Ejecutar una revisión concreta

Ejemplo:

```bash
python scripts/scan_boe.py --desde 2026-04-01 --hasta 2026-04-29
```

El script dejará los resultados en:

```text
outputs/alertas.json
docs/alertas.json
```

Y podrás abrir:

```text
docs/index.html
```

---

## Cómo subirlo a GitHub

1. Crea un repositorio nuevo en GitHub.
2. Sube todo el contenido de esta carpeta.
3. En GitHub entra en:

```text
Settings → Pages
```

4. Configura:

```text
Source: Deploy from a branch
Branch: main
Folder: /docs
```

5. Guarda.

Tu dashboard saldrá publicado como web de GitHub Pages.

---

## Activar actualización automática

El proyecto incluye este workflow:

```text
.github/workflows/scan_boe.yml
```

Hace una revisión diaria y también permite ejecutarlo manualmente desde:

```text
Actions → Scan BOE alertas → Run workflow
```

Para que pueda guardar los cambios generados, revisa en GitHub:

```text
Settings → Actions → General → Workflow permissions
```

Y activa:

```text
Read and write permissions
```

---

## Configuración importante

El archivo principal de configuración es:

```text
config/user_profile.json
```

Por defecto está pensado para ti:

```json
{
  "provincias": ["Albacete"],
  "priorizar_informatica": true,
  "incluir_administrativo_c1": true,
  "incluir_auxiliar_administrativo_c2": false,
  "incluir_libre_designacion": false,
  "incluir_promocion_interna": false,
  "modo_estricto": true
}
```

Si algún día quieres que también salgan auxiliares administrativos C2, cambia:

```json
"incluir_auxiliar_administrativo_c2": true
```

---

## Qué cambia respecto al filtro anterior

### Antes

El sistema encontraba bien Albacete, pero metía demasiado ruido:

- Policía local.
- Bomberos.
- Peón jardinero.
- Letrado.
- Libre designación A1/FHN.
- Plazas no relacionadas.

### Ahora

El filtro intenta extraer la **plaza real** del texto del BOE:

```text
Una plaza de Técnico/a de Informática...
Una plaza de Administrativo/a...
Una plaza de Peón Jardinero...
```

Y clasifica con estos campos:

```json
"perfilReal": "informatica_tic",
"relevanciaUsuario": "muy_alta",
"prioridadUsuario": 1,
"descartadaParaUsuario": false,
"visibleParaUsuario": true
```

---

## Prioridades

```text
Prioridad 1 → Informática / TIC / TAI / sistemas / redes / soporte / programación.
Prioridad 2 → Administrativo C1 real.
Prioridad 3 → Auxiliar Administrativo C2, solo si lo activas.
Prioridad 6 → Albacete sin perfil claro.
Prioridad 9 → Descartado.
```

---

## Nota

El BOE es la fuente oficial, pero antes de inscribirte revisa siempre:

- BOE HTML.
- PDF oficial.
- Bases de la convocatoria.
- Sede electrónica del organismo convocante.
