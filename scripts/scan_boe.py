#!/usr/bin/env python3
"""
Escáner BOE para GitHub Actions / uso local.

Versión afinada para alertas de:
- Concursos AGE de provisión de puestos de trabajo, marcados como revisar anexo si no aparece la provincia.
- Libre designación / comisión de servicios solo cuando son convocatorias/provisión de puestos.
- Convocatorias de empleo público de entidades locales/autonómicas en la provincia vigilada.

Evita ruido habitual del BOE:
- Secciones 3 y 5B.
- Subvenciones, ayudas, licitaciones, concesiones, premios, sentencias y recursos.
- Fases posteriores de oposiciones: admitidos, nombramientos, tribunales, resoluciones, correcciones, etc.
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
    "dias_revision_por_defecto": 7,
    "modo_estricto_generacion": True,
    "entidades_prioritarias": [
        "Ayuntamiento de Albacete",
        "Diputación Provincial de Albacete",
        "Diputación de Albacete",
        "Junta de Comunidades de Castilla-La Mancha",
        "Comunidad Autónoma de Castilla-La Mancha",
        "Castilla-La Mancha",
        "Administración General del Estado",
        "SEPE",
        "Servicio Público de Empleo Estatal"
    ],
    "departamentos_age_interes": [
        "Ministerio", "Subsecretaría", "Secretaría de Estado", "Delegación del Gobierno", "Subdelegación del Gobierno",
        "Servicio Público de Empleo Estatal", "SEPE", "Seguridad Social", "Agencia Estatal", "Instituto Nacional",
        "Consejo Superior de Investigaciones Científicas", "Agencia Española"
    ]
}

# Solo queremos sección II.B para convocatorias/oposiciones/concursos.
# Las resoluciones de destinos y nombramientos suelen estar en II.A y no sirven para apuntarse.
ALLOWED_SECTION_CODES = {"2b", "iib"}

# Palabras que suelen indicar que NO es una convocatoria útil para inscribirse o concursar.
EXCLUDE_PATTERNS = [
    r"\bcorreccion(?:es)? de errores\b", r"\bse corrigen errores\b", r"\bcorrigen errores\b",
    r"\brelacion provisional\b", r"\brelacion definitiva\b", r"\badmitid[oa]s? y excluid[oa]s?\b",
    r"\baspirantes que han superado\b", r"\bpersonas que han superado\b",
    r"\btribunal calificador\b", r"\btribunales delegados\b", r"\bfija fecha\b",
    r"\bse resuelve\b", r"\bresuelve la convocatoria\b", r"\bresuelve el concurso\b",
    r"\bdeclara desiert[ao]\b", r"\botorga destino\b", r"\bnombra funcionari[oa]\b", r"\bnombramiento\b",
    r"\bejecuta sentencia\b", r"\bejecucion de sentencia\b", r"\brecurso contencioso\b", r"\bemplaza\b",
    r"\bsentencia\b", r"\brecurso de amparo\b", r"\brecursos\b",
]

# Palabras que indican que el BOE no es de personal/empleo sino subvenciones, concesiones, contratos, etc.
NO_PERSONAL_PATTERNS = [
    r"\bsubvencion(?:es)?\b", r"\bayuda(?:s)?\b", r"\bpremio(?:s)?\b",
    r"\bconcesion administrativa\b", r"\bconcesiones administrativas\b", r"\bderecho real de superficie\b",
    r"\blicitacion\b", r"\bcontratacion\b", r"\badjudicacion\b", r"\bexplotacion\b",
    r"\bquiosco\b", r"\bhosteleria\b", r"\bvivienda\b", r"\blocal\b",
    r"\btesoro publico\b", r"\bsubasta\b", r"\bmarina mercante\b", r"\btitulaciones nauticas\b",
]

# Convocatorias reales o provisión de puestos.
OPENING_PATTERNS = [
    r"\bse convoca\b", r"\bconvoca\b", r"\bconvocatoria para proveer\b", r"\breferente a la convocatoria para proveer\b",
    r"\bpruebas selectivas para ingreso\b", r"\bproceso selectivo para ingreso\b", r"\bproceso selectivo para la provision\b",
    r"\bprovision de puesto(?:s)? de trabajo\b", r"\bprovision de puesto(?:s)?\b",
]

CONCURSO_PUESTOS_PATTERNS = [
    r"\bconcurso general\b", r"\bconcurso especifico\b", r"\bconcurso de traslados\b",
    r"\bconcurso\b.*\bprovision de puesto(?:s)? de trabajo\b",
    r"\bconcurso\b.*\bpuesto(?:s)? de trabajo\b",
]

LIBRE_DESIGNACION_PATTERNS = [
    r"\blibre designacion\b", r"\bprovision de puesto(?:s)? de trabajo por el sistema de libre designacion\b"
]

COMISION_SERVICIO_PATTERNS = [
    r"\bcomision de servicio(?:s)?\b", r"\bcomisiones de servicio(?:s)?\b"
]

OPOSICION_PATTERNS = [
    r"\boposicion\b", r"\bpruebas selectivas\b", r"\bproceso selectivo\b",
    r"\bconvocatoria para proveer\b", r"\breferente a la convocatoria para proveer\b", r"\bbolsa de trabajo\b"
]

PROFILE_REGEX = {
    "informatica": [
        r"\binformatica\b", r"\binformatic[oa]s?\b", r"\btecnologias? de la informacion\b", r"\btic\b",
        r"\bsistemas informaticos\b", r"\badministracion de sistemas\b", r"\bmicroinformatica\b",
        r"\bprogramador(?:a|es)?\b", r"\bofimatica\b", r"\bdesarrollo de aplicaciones\b",
        r"\btecnico auxiliar de informatica\b", r"\btecnico especialista en ofimatica\b"
    ],
    "administrativo": [
        r"\bcuerpo administrativo\b", r"\bescala administrativa\b", r"\bauxiliar administrativo\b",
        r"\bgestion administrativa\b", r"\bplaza(?:s)? de administrativo\b", r"\badministrativo/a\b",
        r"\badministrativos?\b"
    ],
    "c1a2": [
        r"\bc1/a2\b", r"\bc1-a2\b", r"\bsubgrupo\s+c1\b", r"\bsubgrupo\s+a2\b",
        r"\bc1\b", r"\ba2\b", r"\bnivel\s+1[6-9]\b", r"\bnivel\s+2[0-2]\b"
    ]
}


def norm(text: Any) -> str:
    text = "" if text is None else str(text)
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.lower()
    text = re.sub(r"\s+", " ", text).strip()
    return text


def re_any(text_norm: str, patterns: Iterable[str]) -> bool:
    return any(re.search(pattern, text_norm) for pattern in patterns)


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
        "User-Agent": "BOE-Alertas-C1-GitHubPages/1.1 (+https://pages.github.com/)"
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


def section_code(item: Dict[str, Any]) -> str:
    raw = norm(item.get("seccion", ""))
    return re.sub(r"[^0-9a-z]", "", raw)


def is_allowed_section(item: Dict[str, Any]) -> bool:
    return section_code(item) in ALLOWED_SECTION_CODES


def detect_tipo(text_norm: str) -> str:
    if re_any(text_norm, COMISION_SERVICIO_PATTERNS):
        return "comision_servicio"
    if re_any(text_norm, LIBRE_DESIGNACION_PATTERNS):
        return "libre_designacion"
    if re_any(text_norm, CONCURSO_PUESTOS_PATTERNS):
        return "concurso"
    if re_any(text_norm, OPOSICION_PATTERNS):
        return "oposicion"
    return "otros"


def detect_perfiles(text_norm: str) -> List[str]:
    perfiles = []
    for perfil, patterns in PROFILE_REGEX.items():
        if re_any(text_norm, patterns):
            perfiles.append(perfil)
    return perfiles


def detect_provincias(text_norm: str) -> List[str]:
    return [p for p in ALL_PROVINCES if re.search(rf"\b{re.escape(norm(p))}\b", text_norm)]


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


def is_opening_or_provision(text_norm: str, tipo: str) -> bool:
    if tipo == "concurso":
        return re_any(text_norm, CONCURSO_PUESTOS_PATTERNS) and re_any(text_norm, [r"\bconvoca\b", r"\bprovision de puesto(?:s)? de trabajo\b", r"\bpuestos de trabajo\b"])
    if tipo in {"libre_designacion", "comision_servicio"}:
        return re_any(text_norm, OPENING_PATTERNS) or "provision de puesto" in text_norm
    if tipo == "oposicion":
        return re_any(text_norm, OPENING_PATTERNS)
    return False


def is_age_concurso_revisable(item: Dict[str, Any], text_norm: str, tipo: str, config: Dict[str, Any]) -> bool:
    if tipo != "concurso" or not is_allowed_section(item):
        return False
    if not re_any(text_norm, CONCURSO_PUESTOS_PATTERNS):
        return False
    if re_any(text_norm, NO_PERSONAL_PATTERNS):
        return False
    if re_any(text_norm, EXCLUDE_PATTERNS):
        return False

    epigrafe = norm(item.get("epigrafe", ""))
    dep_words = config.get("departamentos_age_interes", [])
    dep_hit = any(norm(word) in text_norm for word in dep_words)
    epigrafe_hit = "personal funcionario" in epigrafe and "concurso" in epigrafe
    return dep_hit or epigrafe_hit or "ministerio" in text_norm or "agencia estatal" in text_norm


def classify(item: Dict[str, Any], config: Dict[str, Any], provincias_vigiladas: List[str]) -> Optional[Dict[str, Any]]:
    full_norm = norm(" ".join(str(item.get(k, "")) for k in ["titulo", "departamento", "seccion", "epigrafe"]))

    # Filtro duro: evitar secciones que generan muchísimo ruido. Las convocatorias están en II.B.
    if not is_allowed_section(item):
        return None

    # Filtro duro: no-personal/empleo y fases posteriores.
    if re_any(full_norm, NO_PERSONAL_PATTERNS):
        return None

    tipo = detect_tipo(full_norm)
    if tipo == "otros":
        return None

    # En principio solo alertamos de convocatorias/provisión. Los concursos AGE se tratan aparte por anexos.
    age_revisable = is_age_concurso_revisable(item, full_norm, tipo, config)
    if not age_revisable:
        if re_any(full_norm, EXCLUDE_PATTERNS):
            return None
        if not is_opening_or_provision(full_norm, tipo):
            return None

    perfiles = detect_perfiles(full_norm)
    provincias = detect_provincias(full_norm)
    entidad = detect_entidad(full_norm)

    target_provinces_norm = [norm(p) for p in provincias_vigiladas]
    target_province_hit = any(norm(p) in target_provinces_norm for p in provincias)

    target_local_entity_hit = (
        "ayuntamiento de albacete" in full_norm
        or "diputacion provincial de albacete" in full_norm
        or "diputacion de albacete" in full_norm
        or ("castilla-la mancha" in full_norm or "castilla la mancha" in full_norm or "junta de comunidades" in full_norm)
    )

    # Núcleo fino:
    # 1) Todo lo de la provincia vigilada en II.B que sea convocatoria/provisión.
    # 2) Entidades prioritarias de Albacete/CLM.
    # 3) Concursos AGE de puestos: revisar anexo aunque no aparezca provincia.
    if not (target_province_hit or target_local_entity_hit or age_revisable):
        return None

    if target_province_hit or target_local_entity_hit:
        precision = "alta"
        prioridad = 1
        motivo = "Coincidencia directa con provincia o entidad vigilada en una convocatoria/provisión de personal."
    elif age_revisable:
        precision = "revisar_anexo"
        prioridad = 2
        motivo = (
            "Concurso AGE de provisión de puestos detectado. La provincia, nivel y cuerpo pueden venir dentro del anexo PDF; "
            "abre la disposición y busca Albacete, C1, C1/A2, nivel 16 o informática/administrativo."
        )
    else:
        precision = "media"
        prioridad = 3
        motivo = "Coincidencia indirecta; revisar manualmente."

    tags = sorted(set(provincias + perfiles + ([entidad] if entidad else []) + ([tipo] if tipo else [])))
    result = dict(item)
    result.update({
        "tipo": tipo,
        "perfiles": sorted(set(perfiles)),
        "provinciasDetectadas": provincias,
        "entidadDetectada": entidad,
        "precision": precision,
        "prioridad": prioridad,
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
    merged.sort(key=lambda x: (x.get("prioridad", 9), x.get("fechaPublicacion", ""), x.get("titulo", "")), reverse=False)
    merged.sort(key=lambda x: (x.get("fechaPublicacion", ""), -int(x.get("prioridad", 9))), reverse=True)
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
        "> En concursos AGE, abre el PDF/anexo y busca: Albacete, C1, C1/A2, nivel 16, informática, TIC, administrativo.",
        ""
    ]
    for item in sorted(added, key=lambda x: (x.get("prioridad", 9), x.get("fechaPublicacion", "")))[:30]:
        title = item.get("titulo", "Sin título")
        lines.extend([
            f"## {item.get('fechaPublicacion')} · {title}",
            f"- Prioridad: **{item.get('prioridad', 'N/D')}**",
            f"- Tipo: **{item.get('tipo', 'sin tipo')}**",
            f"- Precisión: **{item.get('precision', 'pendiente')}**",
            f"- Provincia detectada: {', '.join(item.get('provinciasDetectadas') or []) or 'No visible en el título'}",
            f"- Entidad: {item.get('entidadDetectada') or 'No disponible'}",
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
    parser.add_argument("--reiniciar", action="store_true", help="No conserva alertas antiguas; reescribe data/alertas.json solo con el rango actual")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config()
    today = dt.date.today()
    default_days = int(args.dias or config.get("dias_revision_por_defecto", 7))

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
            day_found = 0
            for item in items:
                classified = classify(item, config, provincias)
                if classified:
                    found.append(classified)
                    day_found += 1
            print(f"[INFO] {fecha}: {day_found} alertas útiles tras filtros finos")
        except Exception as exc:
            msg = f"{fecha}: {exc!r}"
            print(f"[ERROR] {msg}")
            errors.append(msg)

    existing_payload = load_existing()
    existing_alerts = [] if args.reiniciar else existing_payload.get("alertas", [])
    merged, added = merge_alerts(existing_alerts, found)

    payload = {
        "metadata": {
            "generatedBy": "scripts/scan_boe.py",
            "versionFiltro": "v3-fino",
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
