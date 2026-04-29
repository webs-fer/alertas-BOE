#!/usr/bin/env python3
"""
Escáner BOE para GitHub Actions / uso local.

- Consulta la API oficial de sumarios del BOE por fecha.
- Extrae items de la Sección II.B y también posibles concursos/provisiones.
- Clasifica concursos, libre designación, comisiones y oposiciones.
- Guarda resultados en data/alertas.json con enlaces directos al BOE.

Uso local:
    python scripts/scan_boe.py --desde 2026-04-01 --hasta 2026-04-29 --provincia Albacete
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"
CONFIG_PATH = DATA_DIR / "config.json"
ALERTAS_PATH = DATA_DIR / "alertas.json"
ISSUE_PATH = DOCS_DIR / "last_issue.md"
NEW_COUNT_PATH = DOCS_DIR / "new_alert_count.txt"
BOE_API = "https://www.boe.es/datosabiertos/api/boe/sumario/{fecha}"
BOE_BASE = "https://www.boe.es"

ALL_PROVINCES = [
    "Albacete", "Alicante", "Almería", "Ávila", "Badajoz", "Barcelona", "Burgos", "Cáceres", "Cádiz",
    "Castellón", "Ciudad Real", "Córdoba", "Cuenca", "Girona", "Granada", "Guadalajara", "Huelva", "Huesca",
    "Jaén", "León", "Lleida", "La Rioja", "Lugo", "Madrid", "Málaga", "Murcia", "Ourense", "Palencia",
    "Pontevedra", "Salamanca", "Segovia", "Sevilla", "Soria", "Tarragona", "Teruel", "Toledo", "Valencia",
    "Valladolid", "Zamora", "Zaragoza", "Ceuta", "Melilla"
]

DEFAULT_CONFIG = {
    "provincias_vigiladas": ["Albacete"],
    "dias_revision_por_defecto": 30,
    "entidades_prioritarias": [
        "Ayuntamiento de Albacete",
        "Diputación Provincial de Albacete",
        "Junta de Comunidades de Castilla-La Mancha",
        "Comunidad Autónoma de Castilla-La Mancha",
        "Administración General del Estado"
    ],
    "tipos": {
        "concurso": ["concurso", "concurso específico", "concurso general", "provisión de puestos", "puestos de trabajo"],
        "libre_designacion": ["libre designación"],
        "comision_servicio": ["comisión de servicios", "comision de servicios", "comisión de servicio", "comision de servicio"],
        "oposicion": ["oposición", "oposicion", "convocatoria", "proceso selectivo", "pruebas selectivas", "bolsa de trabajo"]
    },
    "perfiles": {
        "informatica": [
            "informática", "informatico", "informáticos", "tecnologías de la información", "tecnologias de la informacion",
            "TIC", "sistemas", "programador", "administración de sistemas", "microinformática",
            "técnico auxiliar de informática", "tecnico auxiliar de informatica"
        ],
        "administrativo": ["administrativo", "administrativa", "auxiliar administrativo", "gestión administrativa", "gestion administrativa"],
        "c1a2": ["C1", "C1/A2", "C1-A2", "A2", "subgrupo C1", "subgrupo A2", "nivel 16", "nivel 17", "nivel 18", "nivel 19", "nivel 20", "nivel 21", "nivel 22"]
    },
    "departamentos_age_interes": ["Ministerio", "Delegación del Gobierno", "Subdelegación del Gobierno", "SEPE", "Servicio Público de Empleo Estatal", "Seguridad Social"]
}


def norm(text: Any) -> str:
    text = "" if text is None else str(text)
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return text.lower()


def iso_today() -> str:
    return dt.date.today().isoformat()


def parse_date(value: str) -> dt.date:
    return dt.datetime.strptime(value, "%Y-%m-%d").date()


def daterange(start: dt.date, end: dt.date) -> Iterable[dt.date]:
    current = start
    while current <= end:
        yield current
        current += dt.timedelta(days=1)


def load_config() -> Dict[str, Any]:
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            merged = DEFAULT_CONFIG.copy()
            loaded = json.load(f)
            merged.update(loaded)
            return merged
    return DEFAULT_CONFIG


def load_existing() -> Dict[str, Any]:
    if ALERTAS_PATH.exists():
        try:
            with ALERTAS_PATH.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"metadata": {}, "alertas": []}


def fetch_sumario(fecha: dt.date, retries: int = 2) -> Optional[bytes]:
    url = BOE_API.format(fecha=fecha.strftime("%Y%m%d"))
    headers = {
        "Accept": "application/xml",
        "User-Agent": "BOE-Alertas-C1-GitHubPages/1.0 (+https://pages.github.com/)"
    }
    request = urllib.request.Request(url, headers=headers)
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                print(f"[INFO] {fecha}: sin sumario o no publicado todavía (404)")
                return None
            print(f"[WARN] {fecha}: HTTP {exc.code} en intento {attempt + 1}")
        except Exception as exc:
            print(f"[WARN] {fecha}: {exc!r} en intento {attempt + 1}")
        time.sleep(1.5 * (attempt + 1))
    return None


def tag_name(element: ET.Element) -> str:
    return element.tag.split("}", 1)[-1] if "}" in element.tag else element.tag


def child_text(element: ET.Element, names: Iterable[str]) -> str:
    names_norm = {norm(n) for n in names}
    for child in list(element):
        if norm(tag_name(child)) in names_norm:
            return "".join(child.itertext()).strip()
    return ""


def first_attr(element: ET.Element, names: Iterable[str]) -> str:
    names_norm = {norm(n) for n in names}
    for key, value in element.attrib.items():
        if norm(key) in names_norm and value:
            return value.strip()
    return ""


def ctx_update(element: ET.Element, ctx: Dict[str, str]) -> Dict[str, str]:
    new = dict(ctx)
    t = norm(tag_name(element))
    if "seccion" in t:
        value = first_attr(element, ["num", "codigo", "nombre"]) or child_text(element, ["nombre", "titulo"])
        if value:
            new["seccion"] = value
    elif "departamento" in t:
        value = first_attr(element, ["nombre", "codigo"]) or child_text(element, ["nombre", "titulo"])
        if value:
            new["departamento"] = value
    elif "epigrafe" in t or "subseccion" in t:
        value = first_attr(element, ["nombre", "codigo"]) or child_text(element, ["nombre", "titulo"])
        if value:
            new["epigrafe"] = value
    return new


def walk_items(element: ET.Element, fecha: dt.date, ctx: Optional[Dict[str, str]] = None) -> Iterable[Dict[str, Any]]:
    ctx = ctx or {}
    ctx = ctx_update(element, ctx)
    t = norm(tag_name(element))
    if t == "item" or child_text(element, ["titulo"]) and (first_attr(element, ["id"]) or child_text(element, ["identificador"])):
        yield extract_item(element, fecha, ctx)
    for child in list(element):
        yield from walk_items(child, fecha, ctx)


def abs_url(url: str) -> str:
    if not url:
        return ""
    if url.startswith("http"):
        return url
    if url.startswith("/"):
        return BOE_BASE + url
    return BOE_BASE + "/" + url


def sumario_url(fecha: dt.date) -> str:
    return f"{BOE_BASE}/boe/dias/{fecha:%Y/%m/%d}/"


def api_url(fecha: dt.date) -> str:
    return BOE_API.format(fecha=fecha.strftime("%Y%m%d"))


def extract_item(element: ET.Element, fecha: dt.date, ctx: Dict[str, str]) -> Dict[str, Any]:
    item_id = first_attr(element, ["id"]) or child_text(element, ["identificador", "id"])
    titulo = child_text(element, ["titulo", "título"]) or " ".join("".join(element.itertext()).split())[:500]
    departamento = ctx.get("departamento") or child_text(element, ["departamento", "organismo"])
    seccion = ctx.get("seccion", "")
    epigrafe = ctx.get("epigrafe", "")

    url_htm = child_text(element, ["urlHtm", "urlHTML", "urlHtml", "url_html"])
    url_pdf = child_text(element, ["urlPdf", "urlPDF", "url_pdf"])
    url_xml = child_text(element, ["urlXml", "urlXML", "url_xml"])

    if item_id and not url_htm:
        url_htm = f"/diario_boe/txt.php?id={item_id}"
    if item_id and not url_xml:
        url_xml = f"/diario_boe/xml.php?id={item_id}"
    if item_id and not url_pdf:
        url_pdf = f"/boe/dias/{fecha:%Y/%m/%d}/pdfs/{item_id}.pdf"

    stable_id = item_id or hashlib.sha1(f"{fecha.isoformat()}|{titulo}".encode("utf-8")).hexdigest()[:16]
    return {
        "id": stable_id,
        "boeId": item_id,
        "fechaPublicacion": fecha.isoformat(),
        "titulo": titulo,
        "departamento": departamento,
        "seccion": seccion,
        "epigrafe": epigrafe,
        "enlaceBoeHtml": abs_url(url_htm),
        "enlacePdf": abs_url(url_pdf),
        "enlaceXml": abs_url(url_xml),
        "enlaceSumario": sumario_url(fecha),
        "enlaceApi": api_url(fecha),
        "fuente": "BOE"
    }


def parse_sumario(xml_bytes: bytes, fecha: dt.date) -> List[Dict[str, Any]]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        print(f"[WARN] {fecha}: XML no válido: {exc}")
        return []
    return list(walk_items(root, fecha))


def contains_any(text_norm: str, words: Iterable[str]) -> bool:
    return any(norm(word) in text_norm for word in words if word)


def detect_tipo(text_norm: str, config: Dict[str, Any]) -> str:
    # Orden intencionado: comisiones/libres antes de concurso genérico.
    for tipo in ["comision_servicio", "libre_designacion", "oposicion", "concurso"]:
        if contains_any(text_norm, config.get("tipos", {}).get(tipo, [])):
            return tipo
    return "otros"


def detect_perfiles(text_norm: str, config: Dict[str, Any]) -> List[str]:
    perfiles = []
    for perfil, words in config.get("perfiles", {}).items():
        if contains_any(text_norm, words):
            perfiles.append(perfil)
    return perfiles


def detect_provincias(text_norm: str) -> List[str]:
    return [p for p in ALL_PROVINCES if norm(p) in text_norm]


def detect_entidad(text_norm: str) -> str:
    if "ayuntamiento de albacete" in text_norm:
        return "Ayuntamiento de Albacete"
    if "diputacion provincial de albacete" in text_norm or "diputacion de albacete" in text_norm:
        return "Diputación de Albacete"
    if "castilla-la mancha" in text_norm or "castilla la mancha" in text_norm or "junta de comunidades" in text_norm:
        return "Castilla-La Mancha"
    if "servicio publico de empleo estatal" in text_norm or re.search(r"\bsepe\b", text_norm):
        return "SEPE"
    if "administracion general del estado" in text_norm:
        return "AGE"
    return ""


def is_section_iib(item: Dict[str, Any]) -> bool:
    joined = norm(f"{item.get('seccion','')} {item.get('epigrafe','')} {item.get('titulo','')}")
    return "ii.b" in joined or "oposiciones" in joined or "concursos" in joined


def is_state_concurso_revisable(item: Dict[str, Any], tipo: str, config: Dict[str, Any]) -> bool:
    full = norm(f"{item.get('titulo','')} {item.get('departamento','')} {item.get('epigrafe','')} {item.get('seccion','')}")
    if tipo != "concurso":
        return False
    if contains_any(full, config.get("departamentos_age_interes", [])):
        return True
    if "ministerio" in full or "administracion general del estado" in full:
        return True
    # Aunque no se detecte ministerio, todo concurso de II.B puede tener anexos con provincias.
    return is_section_iib(item)


def classify(item: Dict[str, Any], config: Dict[str, Any], provincias_vigiladas: List[str]) -> Optional[Dict[str, Any]]:
    full_norm = norm(" ".join(str(item.get(k, "")) for k in ["titulo", "departamento", "seccion", "epigrafe"]))
    tipo = detect_tipo(full_norm, config)
    perfiles = detect_perfiles(full_norm, config)
    provincias = detect_provincias(full_norm)
    entidad = detect_entidad(full_norm)

    target_provinces_norm = [norm(p) for p in provincias_vigiladas]
    target_province_hit = any(norm(p) in target_provinces_norm for p in provincias)
    target_entity_hit = any(norm(p) in full_norm for p in provincias_vigiladas) or bool(entidad)
    revisable_age = is_state_concurso_revisable(item, tipo, config)

    # Núcleo del filtro: no queremos todo el BOE, pero sí no perder concursos que esconden provincia en anexos.
    if tipo == "otros":
        return None
    if not (is_section_iib(item) or tipo in {"concurso", "oposicion", "libre_designacion", "comision_servicio"}):
        return None

    # Mantener avisos si hay provincia/entidad/perfil TIC/administrativo o si es concurso AGE revisable.
    has_relevant_profile = bool(set(perfiles) & {"informatica", "administrativo", "c1a2"})
    if not (target_province_hit or target_entity_hit or has_relevant_profile or revisable_age):
        # Para convocatorias locales/autonómicas, si no aparece provincia ni entidad, se descarta.
        return None

    if target_province_hit or target_entity_hit:
        precision = "alta"
    elif revisable_age:
        precision = "revisar_anexo"
    else:
        precision = "media"

    if precision == "revisar_anexo":
        motivo = (
            "Concurso/provisión detectado en BOE. La provincia concreta puede venir dentro del anexo PDF o del listado de puestos; "
            "conviene abrir la disposición y buscar la provincia vigilada."
        )
    elif target_province_hit or target_entity_hit:
        motivo = "Coincidencia directa con provincia, entidad o ámbito vigilado."
    else:
        motivo = "Coincidencia por perfil C1/TIC/administrativo o palabras clave; revisar el documento BOE."

    tags = sorted(set(provincias + perfiles + ([entidad] if entidad else []) + ([tipo] if tipo else [])))
    result = dict(item)
    result.update({
        "tipo": tipo,
        "perfiles": sorted(set(perfiles)),
        "provinciasDetectadas": provincias,
        "entidadDetectada": entidad,
        "precision": precision,
        "motivo": motivo,
        "tags": tags
    })
    return result


def merge_alerts(existing: List[Dict[str, Any]], new: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    by_key: Dict[str, Dict[str, Any]] = {}
    for item in existing:
        key = unique_key(item)
        by_key[key] = item

    added = []
    for item in new:
        key = unique_key(item)
        if key not in by_key:
            added.append(item)
        by_key[key] = {**by_key.get(key, {}), **item}

    merged = list(by_key.values())
    merged.sort(key=lambda x: (x.get("fechaPublicacion", ""), x.get("titulo", "")), reverse=True)
    return merged, added


def unique_key(item: Dict[str, Any]) -> str:
    if item.get("boeId"):
        return str(item["boeId"])
    if item.get("id"):
        return str(item["id"])
    return hashlib.sha1(f"{item.get('fechaPublicacion')}|{item.get('titulo')}".encode("utf-8")).hexdigest()


def write_outputs(payload: Dict[str, Any], added: List[Dict[str, Any]], args: argparse.Namespace) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    DOCS_DIR.mkdir(exist_ok=True)
    with ALERTAS_PATH.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")

    NEW_COUNT_PATH.write_text(str(len(added)), encoding="utf-8")
    ISSUE_PATH.write_text(build_issue_markdown(added, args), encoding="utf-8")


def build_issue_markdown(added: List[Dict[str, Any]], args: argparse.Namespace) -> str:
    if not added:
        return "No se han detectado alertas nuevas en esta revisión.\n"
    lines = [
        "# Nuevas alertas BOE detectadas",
        "",
        f"Provincia/filtro principal: **{args.provincia or 'configuración'}**",
        f"Rango revisado: **{args.desde or 'auto'} → {args.hasta or 'auto'}**",
        "",
        "> En concursos AGE, abre el PDF/anexo y busca la provincia, porque el título del sumario no siempre la contiene.",
        ""
    ]
    for item in added[:30]:
        title = item.get("titulo", "Sin título")
        lines.extend([
            f"## {item.get('fechaPublicacion')} · {title}",
            f"- Tipo: **{item.get('tipo', 'sin tipo')}**",
            f"- Precisión: **{item.get('precision', 'pendiente')}**",
            f"- Departamento: {item.get('departamento') or 'No disponible'}",
            f"- Motivo: {item.get('motivo') or 'Coincidencia detectada.'}",
            f"- BOE: {item.get('enlaceBoeHtml') or item.get('enlaceSumario')}",
            f"- PDF: {item.get('enlacePdf') or 'No disponible'}",
            f"- Sumario: {item.get('enlaceSumario')}",
            ""
        ])
    if len(added) > 30:
        lines.append(f"Se han omitido {len(added)-30} alertas más en esta issue. Revisa data/alertas.json.")
    return "\n".join(lines).strip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Escáner de alertas BOE para GitHub Pages")
    parser.add_argument("--desde", help="Fecha inicial YYYY-MM-DD")
    parser.add_argument("--hasta", help="Fecha final YYYY-MM-DD")
    parser.add_argument("--provincia", help="Provincia a vigilar, por defecto la del config")
    parser.add_argument("--dias", type=int, help="Días hacia atrás si no hay desde/hasta")
    parser.add_argument("--max-dias", type=int, default=90, help="Límite de días por ejecución para evitar workflows excesivos")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config()
    today = dt.date.today()
    default_days = int(args.dias or config.get("dias_revision_por_defecto", 30))

    if args.desde:
        desde = parse_date(args.desde)
    else:
        desde = today - dt.timedelta(days=max(0, default_days - 1))

    hasta = parse_date(args.hasta) if args.hasta else today
    if desde > hasta:
        desde, hasta = hasta, desde
    if hasta > today:
        hasta = today

    total_days = (hasta - desde).days + 1
    if total_days > args.max_dias:
        print(f"[WARN] Rango demasiado amplio ({total_days} días). Se limita a {args.max_dias} días desde la fecha final.")
        desde = hasta - dt.timedelta(days=args.max_dias - 1)

    provincias = [args.provincia] if args.provincia else config.get("provincias_vigiladas", ["Albacete"])
    provincias = [p for p in provincias if p]

    print(f"[INFO] Revisando BOE desde {desde} hasta {hasta}. Provincias: {', '.join(provincias)}")
    found: List[Dict[str, Any]] = []
    errors: List[str] = []

    for fecha in daterange(desde, hasta):
        xml = fetch_sumario(fecha)
        if not xml:
            continue
        try:
            items = parse_sumario(xml, fecha)
            print(f"[INFO] {fecha}: {len(items)} items en sumario")
            for item in items:
                classified = classify(item, config, provincias)
                if classified:
                    found.append(classified)
        except Exception as exc:
            msg = f"{fecha}: {exc!r}"
            print(f"[ERROR] {msg}")
            errors.append(msg)

    existing_payload = load_existing()
    existing_alerts = existing_payload.get("alertas", [])
    merged, added = merge_alerts(existing_alerts, found)

    payload = {
        "metadata": {
            "generatedBy": "scripts/scan_boe.py",
            "lastRun": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "rangoUltimaRevision": {"desde": desde.isoformat(), "hasta": hasta.isoformat()},
            "provinciasVigiladas": provincias,
            "fuente": "BOE Datos Abiertos - sumario diario",
            "totalAlertas": len(merged),
            "nuevasAlertas": len(added),
            "errores": errors
        },
        "alertas": merged
    }

    write_outputs(payload, added, args)
    print(f"[INFO] Alertas encontradas en ejecución: {len(found)}")
    print(f"[INFO] Nuevas alertas: {len(added)}")
    print(f"[INFO] Total acumulado: {len(merged)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
