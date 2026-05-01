#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import re
import time
import unicodedata
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from pypdf import PdfReader
except Exception:
    # pypdf se instala en GitHub Actions.
    # Si falta, el script seguirá funcionando con XML/HTML.
    PdfReader = None


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"
CONFIG_PATH = DATA_DIR / "config.json"
ALERTAS_PATH = DATA_DIR / "alertas.json"
ISSUE_PATH = DOCS_DIR / "last_issue.md"
NEW_COUNT_PATH = DOCS_DIR / "new_alert_count.txt"

BOE_API = "https://www.boe.es/datosabiertos/api/boe/sumario/{fecha}"
BOE_BASE = "https://www.boe.es"

URL_CACHE: Dict[str, str] = {}
PDF_CACHE: Dict[str, str] = {}

ALL_PROVINCES = [
    "Albacete", "Alicante", "Almería", "Ávila", "Badajoz", "Barcelona",
    "Burgos", "Cáceres", "Cádiz", "Castellón", "Ciudad Real", "Córdoba",
    "Cuenca", "Girona", "Granada", "Guadalajara", "Huelva", "Huesca",
    "Jaén", "León", "Lleida", "La Rioja", "Lugo", "Madrid", "Málaga",
    "Murcia", "Ourense", "Palencia", "Pontevedra", "Salamanca", "Segovia",
    "Sevilla", "Soria", "Tarragona", "Teruel", "Toledo", "Valencia",
    "Valladolid", "Zamora", "Zaragoza", "Ceuta", "Melilla"
]

DEFAULT_CONFIG = {
    "provincias_vigiladas": ["Albacete"],
    "dias_revision_por_defecto": 7,
    "incluir_concursos_age_sin_provincia_confirmada": False,
    "validar_provincia_en_documento_completo": True,
    "incluir_municipios_provincia": True,
    "nivel_minimo": 16,
    "nivel_maximo": 30,
}

ALLOWED_SECTION_CODES = {"2b", "iib"}

NO_PERSONAL = [
    r"\bsubvencion(?:es)?\b",
    r"\bayuda(?:s)?\b",
    r"\bpremio(?:s)?\b",
    r"\bconcesion administrativa\b",
    r"\blicitacion\b",
    r"\bcontratacion\b",
    r"\badjudicacion\b",
    r"\bexplotacion\b",
    r"\bquiosco\b",
    r"\bhosteleria\b",
    r"\bvivienda\b",
    r"\btesoro publico\b",
    r"\bsubasta\b",
    r"\bmarina mercante\b",
]

EXCLUDE = [
    r"\bcorreccion(?:es)? de errores\b",
    r"\bse corrigen errores\b",
    r"\brelacion provisional\b",
    r"\brelacion definitiva\b",
    r"\badmitid[oa]s? y excluid[oa]s?\b",
    r"\baspirantes que han superado\b",
    r"\btribunal calificador\b",
    r"\bfija fecha\b",
    r"\bse resuelve\b",
    r"\bresuelve la convocatoria\b",
    r"\bresuelve el concurso\b",
    r"\bdeclara desiert[ao]\b",
    r"\botorga destino\b",
    r"\bnombra funcionari[oa]\b",
    r"\bnombramiento\b",
    r"\bejecucion de sentencia\b",
    r"\brecurso contencioso\b",
    r"\bemplaza\b",
    r"\bsentencia\b",
    r"\brecurso de amparo\b",
    r"\brecursos\b",

    # Ruido jurídico/fiscal que no te interesa para TAI/C1/A2 informática o administrativo.
    r"\bcarrera fiscal\b",
    r"\bcarreras judicial y fiscal\b",
    r"\bministerio fiscal\b",
    r"\bletrad[oa]s? de la administracion de justicia\b",
    r"\bcuerpo de letrad[oa]s?\b",
    r"\bjuez/a\b",
    r"\bjueces\b",
    r"\bmagistrad[oa]s?\b",
]

OPENING = [
    r"\bse convoca\b",
    r"\bconvoca\b",
    r"\bconvocatoria para proveer\b",
    r"\breferente a la convocatoria para proveer\b",
    r"\bpruebas selectivas para ingreso\b",
    r"\bproceso selectivo para ingreso\b",
    r"\bprovision de puesto(?:s)? de trabajo\b",
    r"\bprovision de puesto(?:s)?\b",
]

CONCURSO = [
    r"\bconcurso general\b",
    r"\bconcurso especifico\b",
    r"\bconcurso de traslados\b",
    r"\bconcurso\b.*\bprovision de puesto(?:s)? de trabajo\b",
    r"\bconcurso\b.*\bpuesto(?:s)? de trabajo\b",
]

LIBRE = [
    r"\blibre designacion\b",
    r"\bprovision de puesto(?:s)? de trabajo por el sistema de libre designacion\b",
]

COMISION = [
    r"\bcomision de servicio(?:s)?\b",
    r"\bcomisiones de servicio(?:s)?\b",
]

OPOSICION = [
    r"\boposicion\b",
    r"\bpruebas selectivas\b",
    r"\bproceso selectivo\b",
    r"\bconvocatoria para proveer\b",
    r"\breferente a la convocatoria para proveer\b",
    r"\bbolsa de trabajo\b",
]

PROFILE = {
    "informatica": [
        r"\binformatica\b",
        r"\binformatic[oa]s?\b",
        r"\btecnologias? de la informacion\b",
        r"\btic\b",
        r"\bsistemas informaticos\b",
        r"\badministracion de sistemas\b",
        r"\bmicroinformatica\b",
        r"\bprogramador(?:a|es)?\b",
        r"\bofimatica\b",
        r"\btecnico auxiliar de informatica\b",
    ],
    "administrativo": [
        r"\bcuerpo administrativo\b",
        r"\bescala administrativa\b",
        r"\bauxiliar administrativo\b",
        r"\bgestion administrativa\b",
        r"\badministrativos?\b",
    ],
    "c1a2": [
        r"\bc1/a2\b",
        r"\bc1-a2\b",
        r"\bsubgrupo\s+c1\b",
        r"\bsubgrupo\s+a2\b",
        r"\bc1\b",
        r"\ba2\b",
        r"\bnivel\s+1[6-9]\b",
        r"\bnivel\s+2[0-9]\b",
        r"\bnivel\s+30\b",
    ],
}


def norm(text: Any) -> str:
    text = "" if text is None else str(text)
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", text.lower()).strip()


def re_any(text: str, patterns: Iterable[str]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def parse_date(value: str) -> dt.date:
    return dt.datetime.strptime(value, "%Y-%m-%d").date()


def daterange(start: dt.date, end: dt.date):
    while start <= end:
        yield start
        start += dt.timedelta(days=1)


def load_config() -> Dict[str, Any]:
    config = dict(DEFAULT_CONFIG)

    if CONFIG_PATH.exists():
        config.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))

    return config


def load_existing() -> Dict[str, Any]:
    if ALERTAS_PATH.exists():
        try:
            return json.loads(ALERTAS_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass

    return {
        "metadata": {},
        "alertas": []
    }


def request_bytes(url: str, accept: str = "*/*", retries: int = 2) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": accept,
            "User-Agent": "Radar-BOE-Albacete/2.1"
        }
    )

    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=35) as response:
                return response.read()

        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return b""

            print(f"[WARN] {url}: HTTP {exc.code}")

        except Exception as exc:
            print(f"[WARN] {url}: {exc!r}")

        time.sleep(1.5 * (attempt + 1))

    return b""


def fetch_sumario(fecha: dt.date) -> bytes:
    url = BOE_API.format(fecha=fecha.strftime("%Y%m%d"))
    return request_bytes(url, "application/xml")


def fetch_text(url: str) -> str:
    if not url:
        return ""

    if url in URL_CACHE:
        return URL_CACHE[url]

    raw = request_bytes(url, "application/xml,text/html,text/plain,*/*")
    text = raw.decode("utf-8", errors="ignore") if raw else ""

    URL_CACHE[url] = text

    return text


def fetch_pdf_text(url: str) -> str:
    if not url or PdfReader is None:
        return ""

    if url in PDF_CACHE:
        return PDF_CACHE[url]

    raw = request_bytes(url, "application/pdf")
    text = ""

    if raw:
        try:
            reader = PdfReader(io.BytesIO(raw))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            print(f"[WARN] PDF no legible {url}: {exc!r}")

    PDF_CACHE[url] = text

    return text


def tag(element: ET.Element) -> str:
    return element.tag.split("}", 1)[-1] if "}" in element.tag else element.tag


def child_text(element: ET.Element, names: Iterable[str]) -> str:
    names_norm = {norm(name) for name in names}

    for child in list(element):
        if norm(tag(child)) in names_norm:
            return "".join(child.itertext()).strip()

    return ""


def first_attr(element: ET.Element, names: Iterable[str]) -> str:
    names_norm = {norm(name) for name in names}

    for key, value in element.attrib.items():
        if norm(key) in names_norm and value:
            return value.strip()

    return ""


def ctx_update(element: ET.Element, ctx: Dict[str, str]) -> Dict[str, str]:
    new_ctx = dict(ctx)
    tag_name = norm(tag(element))

    if "seccion" in tag_name:
        value = first_attr(element, ["num", "codigo", "nombre"]) or child_text(element, ["nombre", "titulo"])
        if value:
            new_ctx["seccion"] = value

    elif "departamento" in tag_name:
        value = first_attr(element, ["nombre", "codigo"]) or child_text(element, ["nombre", "titulo"])
        if value:
            new_ctx["departamento"] = value

    elif "epigrafe" in tag_name or "subseccion" in tag_name:
        value = first_attr(element, ["nombre", "codigo"]) or child_text(element, ["nombre", "titulo"])
        if value:
            new_ctx["epigrafe"] = value

    return new_ctx


def walk(element: ET.Element, fecha: dt.date, ctx: Optional[Dict[str, str]] = None):
    ctx = ctx_update(element, ctx or {})

    is_item = norm(tag(element)) == "item"
    has_title_and_id = child_text(element, ["titulo"]) and (
        first_attr(element, ["id"]) or child_text(element, ["identificador"])
    )

    if is_item or has_title_and_id:
        yield extract_item(element, fecha, ctx)

    for child in list(element):
        yield from walk(child, fecha, ctx)


def abs_url(url: str) -> str:
    if not url:
        return ""

    if url.startswith("http"):
        return url

    return BOE_BASE + (url if url.startswith("/") else "/" + url)


def extract_item(element: ET.Element, fecha: dt.date, ctx: Dict[str, str]) -> Dict[str, Any]:
    item_id = first_attr(element, ["id"]) or child_text(element, ["identificador", "id"])

    title = child_text(element, ["titulo", "título"]) or " ".join(
        "".join(element.itertext()).split()
    )[:500]

    url_html = child_text(element, ["urlHtm", "urlHTML", "urlHtml", "url_html"])
    url_xml = child_text(element, ["urlXml", "urlXML", "url_xml"])
    url_pdf = child_text(element, ["urlPdf", "urlPDF", "url_pdf"])

    if item_id and not url_html:
        url_html = f"/diario_boe/txt.php?id={item_id}"

    if item_id and not url_xml:
        url_xml = f"/diario_boe/xml.php?id={item_id}"

    if item_id and not url_pdf:
        url_pdf = f"/boe/dias/{fecha:%Y/%m/%d}/pdfs/{item_id}.pdf"

    stable_id = item_id or hashlib.sha1(f"{fecha}|{title}".encode()).hexdigest()[:16]

    return {
        "id": stable_id,
        "boeId": item_id,
        "fechaPublicacion": fecha.isoformat(),
        "titulo": title,
        "departamento": ctx.get("departamento", ""),
        "seccion": ctx.get("seccion", ""),
        "epigrafe": ctx.get("epigrafe", ""),
        "enlaceBoeHtml": abs_url(url_html),
        "enlacePdf": abs_url(url_pdf),
        "enlaceXml": abs_url(url_xml),
        "enlaceSumario": f"{BOE_BASE}/boe/dias/{fecha:%Y/%m/%d}/",
        "enlaceApi": BOE_API.format(fecha=fecha.strftime("%Y%m%d")),
        "fuente": "BOE"
    }


def parse_sumario(xml: bytes, fecha: dt.date) -> List[Dict[str, Any]]:
    if not xml:
        return []

    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        print(f"[WARN] XML no válido {fecha}: {exc}")
        return []

    return list(walk(root, fecha))


def section_code(item: Dict[str, Any]) -> str:
    return re.sub(r"[^0-9a-z]", "", norm(item.get("seccion", "")))


def detect_tipo(text: str) -> str:
    if re_any(text, COMISION):
        return "comision_servicio"

    if re_any(text, LIBRE):
        return "libre_designacion"

    if re_any(text, CONCURSO):
        return "concurso"

    if re_any(text, OPOSICION):
        return "oposicion"

    return "otros"


def detect_perfiles(text: str) -> List[str]:
    return [key for key, patterns in PROFILE.items() if re_any(text, patterns)]


def detect_provinces(text: str, provinces: Iterable[str] = ALL_PROVINCES) -> List[str]:
    return [
        province
        for province in provinces
        if re.search(rf"\b{re.escape(norm(province))}\b", text)
    ]


def detect_entity(text: str) -> str:
    if "ayuntamiento de albacete" in text:
        return "Ayuntamiento de Albacete"

    if "diputacion provincial de albacete" in text or "diputacion de albacete" in text:
        return "Diputación de Albacete"

    if "sescam" in text or "servicio de salud de castilla-la mancha" in text:
        return "SESCAM"

    if "universidad de castilla-la mancha" in text or re.search(r"\buclm\b", text):
        return "UCLM"

    if "castilla-la mancha" in text or "castilla la mancha" in text or "junta de comunidades" in text:
        return "Castilla-La Mancha"

    if "servicio publico de empleo estatal" in text or re.search(r"\bsepe\b", text):
        return "SEPE"

    if "administracion general del estado" in text:
        return "AGE"

    return ""


def detect_levels(text: str) -> List[int]:
    numbers = set()

    for match in re.finditer(r"\bnivel\s*(?:cd)?\s*(1[6-9]|2[0-9]|30)\b", text):
        numbers.add(int(match.group(1)))

    for match in re.finditer(r"\b(?:n\.\s*c\.\s*d\.|niv(?:el)?\.?)\s*(1[6-9]|2[0-9]|30)\b", text):
        numbers.add(int(match.group(1)))

    return sorted(numbers)


def detect_group(text: str) -> str:
    parts = []

    if re.search(r"\bc1\b|\bsubgrupo\s+c1\b", text):
        parts.append("C1")

    if re.search(r"\ba2\b|\bsubgrupo\s+a2\b", text):
        parts.append("A2")

    if re.search(r"\bc2\b|\bsubgrupo\s+c2\b", text):
        parts.append("C2")

    return "/".join(parts)


def extract_plazo(text: str) -> str:
    patterns = [
        r"plazo de presentacion de solicitudes[^\.\n]{0,260}",
        r"plazo para la presentacion de solicitudes[^\.\n]{0,260}",
        r"plazo de presentacion de instancias[^\.\n]{0,260}",
        r"plazo para presentacion de instancias[^\.\n]{0,260}",
        r"(?:veinte|20|diez|10|quince|15) dias habiles[^\.\n]{0,180}",
        r"del \d{1,2}/\d{1,2}/\d{4} al \d{1,2}/\d{1,2}/\d{4}[^\.\n]{0,120}",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)

        if match:
            return re.sub(r"\s+", " ", match.group(0)).strip()[:260]

    return ""


def extract_best_link(item: Dict[str, Any], doc_text_raw: str) -> Tuple[str, str]:
    urls = re.findall(r'https?://[^\s<>"]+', doc_text_raw)

    priority_keywords = [
        "inscripcion",
        "instancia",
        "sede",
        "empleo",
        "convocatoria",
        "bop",
        "docm",
        "dipualba",
        "albacete",
        "castillalamancha",
        "uclm",
        "sescam",
    ]

    for keyword in priority_keywords:
        for url in urls:
            if keyword in norm(url):
                return url.rstrip(").,;"), "Inscripción / bases"

    return item.get("enlaceBoeHtml") or item.get("enlacePdf") or "", "BOE / bases"


def full_document_text(item: Dict[str, Any]) -> Tuple[str, str]:
    raw_parts = []

    for key in ["enlaceXml", "enlaceBoeHtml"]:
        if item.get(key):
            raw_parts.append(fetch_text(item[key]))

    if item.get("enlacePdf"):
        raw_parts.append(fetch_pdf_text(item["enlacePdf"]))

    raw = "\n".join(part for part in raw_parts if part)

    return raw, norm(raw)


def is_age_concurso(item: Dict[str, Any], summary_text: str, tipo: str) -> bool:
    if tipo != "concurso" or section_code(item) not in ALLOWED_SECTION_CODES:
        return False

    if re_any(summary_text, NO_PERSONAL) or re_any(summary_text, EXCLUDE):
        return False

    epigrafe = norm(item.get("epigrafe", ""))

    return (
        "personal funcionario" in epigrafe
        or "ministerio" in summary_text
        or "agencia estatal" in summary_text
        or "subsecretaria" in summary_text
        or "secretaria de estado" in summary_text
        or "agencia espanola" in summary_text
    )


def classify(item: Dict[str, Any], config: Dict[str, Any], targets: List[str]) -> Optional[Dict[str, Any]]:
    summary_text = norm(
        " ".join(
            str(item.get(key, ""))
            for key in ["titulo", "departamento", "seccion", "epigrafe"]
        )
    )

    # Solo Sección II.B.
    if section_code(item) not in ALLOWED_SECTION_CODES:
        return None

    # Fuera ruido no relacionado con personal.
    if re_any(summary_text, NO_PERSONAL):
        return None

    tipo = detect_tipo(summary_text)

    if tipo == "otros":
        return None

    age_concurso = is_age_concurso(item, summary_text, tipo)

    # Si no es un concurso AGE revisable, aplicamos exclusiones normales.
    if not age_concurso:
        if re_any(summary_text, EXCLUDE):
            return None

        if not re_any(summary_text, OPENING):
            return None

    # Texto completo del documento: XML + HTML + PDF.
    if config.get("validar_provincia_en_documento_completo", True):
        doc_raw, doc_text = full_document_text(item)
    else:
        doc_raw, doc_text = "", ""

    combined = norm(summary_text + " " + doc_text)

    title_provinces = detect_provinces(summary_text, targets)
    doc_provinces = detect_provinces(doc_text, targets)

    all_target_provinces = sorted(set(title_provinces + doc_provinces), key=norm)

    entity = detect_entity(combined)

    is_target_local = any(
        norm(target) in combined
        for target in [
            "ayuntamiento de albacete",
            "diputacion de albacete",
            "diputacion provincial de albacete",
            "castilla-la mancha",
            "castilla la mancha",
            "junta de comunidades",
            "sescam",
            "universidad de castilla-la mancha",
            "uclm",
        ]
    )

    # Filtro territorial duro:
    # Para que algo salga, debe estar vinculado a la provincia/entidad objetivo.
    # Evita que se cuelen concursos de CGPJ, Osakidetza, Andalucía, etc.
    has_target = bool(all_target_provinces) or is_target_local

    if tipo == "concurso":
        if age_concurso:
            # Concursos AGE: solo se aceptan si aparece Albacete en el documento,
            # salvo que config.json permita expresamente concursos AGE sin confirmar.
            if not has_target and not config.get("incluir_concursos_age_sin_provincia_confirmada", False):
                return None
        else:
            # Concursos NO AGE: si no tienen Albacete/CLM/entidad objetivo, fuera.
            if not has_target:
                return None

    if tipo in ["libre_designacion", "comision_servicio"] and not has_target:
        return None

    if tipo == "oposicion" and not has_target:
        return None

    perfiles = sorted(set(detect_perfiles(combined)))
    niveles = detect_levels(combined)
    grupo = detect_group(combined)
    plazo = extract_plazo(combined)
    ins_link, ins_label = extract_best_link(item, doc_raw)

    if tipo == "concurso":
        categoria = "concursos"
        priority = 1
        precision = "revisar_anexo" if age_concurso else "alta"
        motivo = (
            "Concurso de provisión de puestos vinculado a la provincia/entidad vigilada. "
            "Revisa anexo para nivel, cuerpo, méritos y localidad."
        )

    elif tipo in ["libre_designacion", "comision_servicio"]:
        categoria = "movilidad"
        priority = 1
        precision = "alta"
        motivo = (
            "Provisión por libre designación o comisión con Albacete/CLM detectado. "
            "Revisa requisitos, nivel, perfil y plazo."
        )

    else:
        categoria = "oposiciones"
        priority = 1
        precision = "alta"
        motivo = (
            "Convocatoria de oposición/proceso selectivo con provincia o entidad de interés detectada. "
            "Revisa bases y portal de inscripción."
        )

    result = dict(item)

    result.update({
        "categoria": categoria,
        "tipo": tipo,
        "perfiles": perfiles,
        "provinciasDetectadas": sorted(set(detect_provinces(summary_text))),
        "provinciasConfirmadasDocumento": all_target_provinces,
        "entidadDetectada": entity,
        "precision": precision,
        "prioridad": priority,
        "nivelesDetectados": niveles,
        "grupoDetectado": grupo,
        "plazoInscripcion": plazo,
        "enlaceInscripcion": ins_link,
        "enlaceInscripcionTipo": ins_label,
        "motivo": motivo,
        "tags": sorted(
            set(
                value
                for value in (
                    [categoria, tipo, entity, grupo]
                    + perfiles
                    + all_target_provinces
                    + [f"nivel {nivel}" for nivel in niveles]
                )
                if value
            ),
            key=norm
        )
    })

    return result


def unique_key(item: Dict[str, Any]) -> str:
    return str(
        item.get("boeId")
        or item.get("id")
        or hashlib.sha1(
            f"{item.get('fechaPublicacion')}|{item.get('titulo')}".encode()
        ).hexdigest()
    )


def merge(existing: List[Dict[str, Any]], new: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    by_key = {unique_key(item): item for item in existing}
    added = []

    for item in new:
        key = unique_key(item)

        if key not in by_key:
            added.append(item)

        by_key[key] = {
            **by_key.get(key, {}),
            **item
        }

    output = list(by_key.values())

    output.sort(
        key=lambda item: (
            item.get("fechaPublicacion") or "",
            -int(item.get("prioridad", 9))
        ),
        reverse=True
    )

    return output, added


def issue_md(added: List[Dict[str, Any]], args: argparse.Namespace) -> str:
    if not added:
        return "No se han detectado alertas nuevas.\n"

    lines = [
        "# Nuevas alertas BOE detectadas",
        "",
        f"Provincia: **{args.provincia or 'config'}**",
        f"Rango: **{args.desde or 'auto'} → {args.hasta or 'auto'}**",
        ""
    ]

    for item in added[:40]:
        lines += [
            f"## {item.get('fechaPublicacion')} · {item.get('titulo')}",
            f"- Bloque: **{item.get('categoria')}**",
            f"- Tipo: **{item.get('tipo')}**",
            f"- Nivel detectado: {', '.join(map(str, item.get('nivelesDetectados') or [])) or 'No detectado'}",
            f"- Grupo: {item.get('grupoDetectado') or 'No detectado'}",
            f"- Plazo: {item.get('plazoInscripcion') or 'No detectado'}",
            f"- Inscripción/bases: {item.get('enlaceInscripcion') or 'No disponible'}",
            f"- BOE: {item.get('enlaceBoeHtml')}",
            ""
        ]

    return "\n".join(lines).strip() + "\n"


def write(payload: Dict[str, Any], added: List[Dict[str, Any]], args: argparse.Namespace):
    DATA_DIR.mkdir(exist_ok=True)
    DOCS_DIR.mkdir(exist_ok=True)

    ALERTAS_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8"
    )

    NEW_COUNT_PATH.write_text(str(len(added)), encoding="utf-8")
    ISSUE_PATH.write_text(issue_md(added, args), encoding="utf-8")


def args_parse():
    parser = argparse.ArgumentParser()

    parser.add_argument("--desde")
    parser.add_argument("--hasta")
    parser.add_argument("--provincia")
    parser.add_argument("--dias", type=int)
    parser.add_argument("--max-dias", type=int, default=90)
    parser.add_argument("--reiniciar", action="store_true")

    return parser.parse_args()


def main() -> int:
    args = args_parse()
    config = load_config()

    today = dt.date.today()
    days = int(args.dias or config.get("dias_revision_por_defecto", 7))

    desde = parse_date(args.desde) if args.desde else today - dt.timedelta(days=max(0, days - 1))
    hasta = parse_date(args.hasta) if args.hasta else today

    if desde > hasta:
        desde, hasta = hasta, desde

    if hasta > today:
        hasta = today

    if (hasta - desde).days + 1 > args.max_dias:
        desde = hasta - dt.timedelta(days=args.max_dias - 1)

    targets = [args.provincia] if args.provincia else config.get("provincias_vigiladas", ["Albacete"])

    print(f"[INFO] Revisando {desde} → {hasta}. Provincia: {targets}")
    print(f"[INFO] Incluir concursos AGE sin provincia confirmada: {config.get('incluir_concursos_age_sin_provincia_confirmada', False)}")
    print(f"[INFO] Validar documento completo: {config.get('validar_provincia_en_documento_completo', True)}")

    found = []
    errors = []

    for fecha in daterange(desde, hasta):
        try:
            items = parse_sumario(fetch_sumario(fecha), fecha)
            day_count = 0

            for item in items:
                classified = classify(item, config, targets)

                if classified:
                    found.append(classified)
                    day_count += 1

            print(f"[INFO] {fecha}: {day_count} alertas útiles")

        except Exception as exc:
            message = f"{fecha}: {exc!r}"
            print("[ERROR]", message)
            errors.append(message)

    existing = [] if args.reiniciar else load_existing().get("alertas", [])
    merged, added = merge(existing, found)

    payload = {
        "metadata": {
            "generatedBy": "scripts/scan_boe.py",
            "versionFiltro": "v4.1-filtro-territorial-duro",
            "lastRun": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "rangoUltimaRevision": {
                "desde": desde.isoformat(),
                "hasta": hasta.isoformat()
            },
            "provinciasVigiladas": targets,
            "fuente": "BOE Datos Abiertos - sumario diario + documento XML/HTML/PDF",
            "totalAlertas": len(merged),
            "nuevasAlertas": len(added),
            "errores": errors
        },
        "alertas": merged
    }

    write(payload, added, args)

    print(f"[INFO] Nuevas: {len(added)} Total: {len(merged)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
