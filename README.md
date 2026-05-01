# Radar BOE Albacete

Web estática para GitHub Pages con tres bloques separados:

1. **Concursos AGE**: bloque principal. Solo muestra concursos donde el documento BOE/XML/HTML/PDF contiene la provincia vigilada.
2. **Libres designaciones y comisiones**: movilidad/provisión con filtros de nivel, grupo y perfil.
3. **Oposiciones**: Junta CLM, SESCAM, UCLM, Diputación de Albacete y Ayuntamiento de Albacete.

## Probar en local

```bash
python -m http.server 8000
```

Abrir:

```text
http://localhost:8000
```

## Subir a GitHub Pages

1. Sube todos los archivos a la raíz del repositorio.
2. Activa Pages en `Settings > Pages > Deploy from branch > main / root`.
3. En `Settings > Actions > General`, marca `Read and write permissions`.
4. Ejecuta manualmente `Actions > Revisar BOE alertas selectivas > Run workflow`.

Ejemplo de prueba:

```text
fecha_desde: 2026-04-01
fecha_hasta: 2026-04-29
provincia: Albacete
reiniciar_datos: true
```

## Archivos clave

- `index.html`: pantalla inicial con 3 opciones.
- `assets/js/app.js`: filtros y renderizado.
- `scripts/scan_boe.py`: escáner BOE con lectura XML/HTML/PDF.
- `.github/workflows/boe-alertas.yml`: automatización.
- `data/config.json`: configuración.
- `data/alertas.json`: datos generados.
