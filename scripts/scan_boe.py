#!/usr/bin/env python3
from __future__ import annotations

import argparse, datetime as dt, hashlib, io, json, re, time, unicodedata, urllib.error, urllib.request, xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from pypdf import PdfReader
except Exception:  # pypdf se instala en GitHub Actions; si falta, se usa XML/HTML.
    PdfReader = None

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / 'data'
DOCS_DIR = ROOT / 'docs'
CONFIG_PATH = DATA_DIR / 'config.json'
ALERTAS_PATH = DATA_DIR / 'alertas.json'
ISSUE_PATH = DOCS_DIR / 'last_issue.md'
NEW_COUNT_PATH = DOCS_DIR / 'new_alert_count.txt'
BOE_API = 'https://www.boe.es/datosabiertos/api/boe/sumario/{fecha}'
BOE_BASE = 'https://www.boe.es'
URL_CACHE: Dict[str, str] = {}
PDF_CACHE: Dict[str, str] = {}

ALL_PROVINCES = ['Albacete','Alicante','Almería','Ávila','Badajoz','Barcelona','Burgos','Cáceres','Cádiz','Castellón','Ciudad Real','Córdoba','Cuenca','Girona','Granada','Guadalajara','Huelva','Huesca','Jaén','León','Lleida','La Rioja','Lugo','Madrid','Málaga','Murcia','Ourense','Palencia','Pontevedra','Salamanca','Segovia','Sevilla','Soria','Tarragona','Teruel','Toledo','Valencia','Valladolid','Zamora','Zaragoza','Ceuta','Melilla']
DEFAULT_CONFIG = {
    'provincias_vigiladas': ['Albacete'],
    'dias_revision_por_defecto': 7,
    'incluir_concursos_age_sin_provincia_confirmada': False,
    'validar_provincia_en_documento_completo': True,
    'incluir_municipios_provincia': True,
    'nivel_minimo': 16,
    'nivel_maximo': 30,
}

ALLOWED_SECTION_CODES = {'2b', 'iib'}
NO_PERSONAL = [r'\bsubvencion(?:es)?\b', r'\bayuda(?:s)?\b', r'\bpremio(?:s)?\b', r'\bconcesion administrativa\b', r'\blicitacion\b', r'\bcontratacion\b', r'\badjudicacion\b', r'\bexplotacion\b', r'\bquiosco\b', r'\bhosteleria\b', r'\bvivienda\b', r'\btesoro publico\b', r'\bsubasta\b', r'\bmarina mercante\b']
EXCLUDE = [r'\bcorreccion(?:es)? de errores\b', r'\bse corrigen errores\b', r'\brelacion provisional\b', r'\brelacion definitiva\b', r'\badmitid[oa]s? y excluid[oa]s?\b', r'\baspirantes que han superado\b', r'\btribunal calificador\b', r'\bfija fecha\b', r'\bse resuelve\b', r'\bresuelve la convocatoria\b', r'\bresuelve el concurso\b', r'\bdeclara desiert[ao]\b', r'\botorga destino\b', r'\bnombra funcionari[oa]\b', r'\bnombramiento\b', r'\bejecucion de sentencia\b', r'\brecurso contencioso\b', r'\bemplaza\b', r'\bsentencia\b', r'\brecurso de amparo\b', r'\brecursos\b', r'\bcarrera fiscal\b', r'\bcarreras judicial y fiscal\b', r'\bministerio fiscal\b', r'\bletrad[oa]s? de la administracion de justicia\b', r'\bcuerpo de letrad[oa]s?\b', r'\bjuez/a\b', r'\bjueces\b', r'\bmagistrad[oa]s?\b']
OPENING = [r'\bse convoca\b', r'\bconvoca\b', r'\bconvocatoria para proveer\b', r'\breferente a la convocatoria para proveer\b', r'\bpruebas selectivas para ingreso\b', r'\bproceso selectivo para ingreso\b', r'\bprovision de puesto(?:s)? de trabajo\b', r'\bprovision de puesto(?:s)?\b']
CONCURSO = [r'\bconcurso general\b', r'\bconcurso especifico\b', r'\bconcurso de traslados\b', r'\bconcurso\b.*\bprovision de puesto(?:s)? de trabajo\b', r'\bconcurso\b.*\bpuesto(?:s)? de trabajo\b']
LIBRE = [r'\blibre designacion\b', r'\bprovision de puesto(?:s)? de trabajo por el sistema de libre designacion\b']
COMISION = [r'\bcomision de servicio(?:s)?\b', r'\bcomisiones de servicio(?:s)?\b']
OPOSICION = [r'\boposicion\b', r'\bpruebas selectivas\b', r'\bproceso selectivo\b', r'\bconvocatoria para proveer\b', r'\breferente a la convocatoria para proveer\b', r'\bbolsa de trabajo\b']
PROFILE = {
    'informatica': [r'\binformatica\b', r'\binformatic[oa]s?\b', r'\btecnologias? de la informacion\b', r'\btic\b', r'\bsistemas informaticos\b', r'\badministracion de sistemas\b', r'\bmicroinformatica\b', r'\bprogramador(?:a|es)?\b', r'\bofimatica\b', r'\btecnico auxiliar de informatica\b'],
    'administrativo': [r'\bcuerpo administrativo\b', r'\bescala administrativa\b', r'\bauxiliar administrativo\b', r'\bgestion administrativa\b', r'\badministrativos?\b'],
    'c1a2': [r'\bc1/a2\b', r'\bc1-a2\b', r'\bsubgrupo\s+c1\b', r'\bsubgrupo\s+a2\b', r'\bc1\b', r'\ba2\b', r'\bnivel\s+1[6-9]\b', r'\bnivel\s+2[0-9]\b', r'\bnivel\s+30\b']
}


def norm(text: Any) -> str:
    text = '' if text is None else str(text)
    text = unicodedata.normalize('NFD', text)
    text = ''.join(ch for ch in text if unicodedata.category(ch) != 'Mn')
    return re.sub(r'\s+', ' ', text.lower()).strip()

def re_any(text: str, patterns: Iterable[str]) -> bool:
    return any(re.search(p, text) for p in patterns)

def parse_date(v: str) -> dt.date:
    return dt.datetime.strptime(v, '%Y-%m-%d').date()

def daterange(a: dt.date, b: dt.date):
    while a <= b:
        yield a
        a += dt.timedelta(days=1)

def load_config() -> Dict[str, Any]:
    c = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        c.update(json.loads(CONFIG_PATH.read_text(encoding='utf-8')))
    return c

def load_existing() -> Dict[str, Any]:
    if ALERTAS_PATH.exists():
        try: return json.loads(ALERTAS_PATH.read_text(encoding='utf-8'))
        except Exception: pass
    return {'metadata': {}, 'alertas': []}

def request_bytes(url: str, accept: str = '*/*', retries: int = 2) -> bytes:
    req = urllib.request.Request(url, headers={'Accept': accept, 'User-Agent': 'Radar-BOE-Albacete/2.0'})
    for i in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=35) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404: return b''
            print(f'[WARN] {url}: HTTP {e.code}')
        except Exception as e:
            print(f'[WARN] {url}: {e!r}')
        time.sleep(1.5 * (i + 1))
    return b''

def fetch_sumario(fecha: dt.date) -> bytes:
    return request_bytes(BOE_API.format(fecha=fecha.strftime('%Y%m%d')), 'application/xml')

def fetch_text(url: str) -> str:
    if not url: return ''
    if url in URL_CACHE: return URL_CACHE[url]
    raw = request_bytes(url, 'application/xml,text/html,text/plain,*/*')
    txt = raw.decode('utf-8', errors='ignore') if raw else ''
    URL_CACHE[url] = txt
    return txt

def fetch_pdf_text(url: str) -> str:
    if not url or PdfReader is None: return ''
    if url in PDF_CACHE: return PDF_CACHE[url]
    raw = request_bytes(url, 'application/pdf')
    text = ''
    if raw:
        try:
            reader = PdfReader(io.BytesIO(raw))
            text = '\n'.join(page.extract_text() or '' for page in reader.pages)
        except Exception as e:
            print(f'[WARN] PDF no legible {url}: {e!r}')
    PDF_CACHE[url] = text
    return text

def tag(e: ET.Element) -> str:
    return e.tag.split('}', 1)[-1] if '}' in e.tag else e.tag

def child_text(e: ET.Element, names: Iterable[str]) -> str:
    names = {norm(n) for n in names}
    for c in list(e):
        if norm(tag(c)) in names:
            return ''.join(c.itertext()).strip()
    return ''

def first_attr(e: ET.Element, names: Iterable[str]) -> str:
    names = {norm(n) for n in names}
    for k, v in e.attrib.items():
        if norm(k) in names and v: return v.strip()
    return ''

def ctx_update(e: ET.Element, ctx: Dict[str, str]) -> Dict[str, str]:
    n = dict(ctx); t = norm(tag(e))
    if 'seccion' in t:
        v = first_attr(e, ['num','codigo','nombre']) or child_text(e, ['nombre','titulo'])
        if v: n['seccion'] = v
    elif 'departamento' in t:
        v = first_attr(e, ['nombre','codigo']) or child_text(e, ['nombre','titulo'])
        if v: n['departamento'] = v
    elif 'epigrafe' in t or 'subseccion' in t:
        v = first_attr(e, ['nombre','codigo']) or child_text(e, ['nombre','titulo'])
        if v: n['epigrafe'] = v
    return n

def walk(e: ET.Element, fecha: dt.date, ctx: Optional[Dict[str, str]] = None):
    ctx = ctx_update(e, ctx or {})
    if norm(tag(e)) == 'item' or (child_text(e, ['titulo']) and (first_attr(e, ['id']) or child_text(e, ['identificador']))):
        yield extract_item(e, fecha, ctx)
    for c in list(e): yield from walk(c, fecha, ctx)

def abs_url(u: str) -> str:
    if not u: return ''
    if u.startswith('http'): return u
    return BOE_BASE + (u if u.startswith('/') else '/' + u)

def extract_item(e: ET.Element, fecha: dt.date, ctx: Dict[str, str]) -> Dict[str, Any]:
    item_id = first_attr(e, ['id']) or child_text(e, ['identificador','id'])
    title = child_text(e, ['titulo','título']) or ' '.join(''.join(e.itertext()).split())[:500]
    url_h = child_text(e, ['urlHtm','urlHTML','urlHtml','url_html']) or (f'/diario_boe/txt.php?id={item_id}' if item_id else '')
    url_x = child_text(e, ['urlXml','urlXML','url_xml']) or (f'/diario_boe/xml.php?id={item_id}' if item_id else '')
    url_p = child_text(e, ['urlPdf','urlPDF','url_pdf']) or (f'/boe/dias/{fecha:%Y/%m/%d}/pdfs/{item_id}.pdf' if item_id else '')
    stable = item_id or hashlib.sha1(f'{fecha}|{title}'.encode()).hexdigest()[:16]
    return {'id': stable, 'boeId': item_id, 'fechaPublicacion': fecha.isoformat(), 'titulo': title, 'departamento': ctx.get('departamento',''), 'seccion': ctx.get('seccion',''), 'epigrafe': ctx.get('epigrafe',''), 'enlaceBoeHtml': abs_url(url_h), 'enlacePdf': abs_url(url_p), 'enlaceXml': abs_url(url_x), 'enlaceSumario': f'{BOE_BASE}/boe/dias/{fecha:%Y/%m/%d}/', 'enlaceApi': BOE_API.format(fecha=fecha.strftime('%Y%m%d')), 'fuente': 'BOE'}

def parse_sumario(xml: bytes, fecha: dt.date) -> List[Dict[str, Any]]:
    if not xml: return []
    try: root = ET.fromstring(xml)
    except ET.ParseError as e:
        print(f'[WARN] XML no válido {fecha}: {e}')
        return []
    return list(walk(root, fecha))

def section_code(item: Dict[str, Any]) -> str:
    return re.sub(r'[^0-9a-z]', '', norm(item.get('seccion','')))

def detect_tipo(txt: str) -> str:
    if re_any(txt, COMISION): return 'comision_servicio'
    if re_any(txt, LIBRE): return 'libre_designacion'
    if re_any(txt, CONCURSO): return 'concurso'
    if re_any(txt, OPOSICION): return 'oposicion'
    return 'otros'

def detect_perfiles(txt: str) -> List[str]:
    return [k for k, pats in PROFILE.items() if re_any(txt, pats)]

def detect_provinces(txt: str, provinces: Iterable[str] = ALL_PROVINCES) -> List[str]:
    return [p for p in provinces if re.search(rf'\b{re.escape(norm(p))}\b', txt)]

def detect_entity(txt: str) -> str:
    if 'ayuntamiento de albacete' in txt: return 'Ayuntamiento de Albacete'
    if 'diputacion provincial de albacete' in txt or 'diputacion de albacete' in txt: return 'Diputación de Albacete'
    if 'sescam' in txt or 'servicio de salud de castilla-la mancha' in txt: return 'SESCAM'
    if 'universidad de castilla-la mancha' in txt or re.search(r'\buclm\b', txt): return 'UCLM'
    if 'castilla-la mancha' in txt or 'castilla la mancha' in txt or 'junta de comunidades' in txt: return 'Castilla-La Mancha'
    if 'servicio publico de empleo estatal' in txt or re.search(r'\bsepe\b', txt): return 'SEPE'
    if 'administracion general del estado' in txt: return 'AGE'
    return ''

def detect_levels(txt: str) -> List[int]:
    nums = set()
    for m in re.finditer(r'\bnivel\s*(?:cd)?\s*(1[6-9]|2[0-9]|30)\b', txt): nums.add(int(m.group(1)))
    for m in re.finditer(r'\b(?:n\.\s*c\.\s*d\.|niv(?:el)?\.?)\s*(1[6-9]|2[0-9]|30)\b', txt): nums.add(int(m.group(1)))
    return sorted(nums)

def detect_group(txt: str) -> str:
    parts = []
    if re.search(r'\bc1\b|\bsubgrupo\s+c1\b', txt): parts.append('C1')
    if re.search(r'\ba2\b|\bsubgrupo\s+a2\b', txt): parts.append('A2')
    if re.search(r'\bc2\b|\bsubgrupo\s+c2\b', txt): parts.append('C2')
    return '/'.join(parts)

def extract_plazo(txt: str) -> str:
    patterns = [
        r'plazo de presentacion de solicitudes[^\.\n]{0,260}',
        r'plazo para la presentacion de solicitudes[^\.\n]{0,260}',
        r'plazo de presentacion de instancias[^\.\n]{0,260}',
        r'plazo para presentacion de instancias[^\.\n]{0,260}',
        r'(?:veinte|20|diez|10|quince|15) dias habiles[^\.\n]{0,180}',
        r'del \d{1,2}/\d{1,2}/\d{4} al \d{1,2}/\d{1,2}/\d{4}[^\.\n]{0,120}'
    ]
    for p in patterns:
        m = re.search(p, txt)
        if m: return re.sub(r'\s+', ' ', m.group(0)).strip()[:260]
    return ''

def extract_best_link(item: Dict[str, Any], doc_text_raw: str) -> Tuple[str, str]:
    urls = re.findall(r'https?://[^\s<>"]+', doc_text_raw)
    prio = ['inscripcion','instancia','sede','empleo','convocatoria','bop','docm','dipualba','albacete','castillalamancha','uclm','sescam']
    for key in prio:
        for u in urls:
            if key in norm(u): return u.rstrip(').,;'), 'Inscripción / bases'
    return item.get('enlaceBoeHtml') or item.get('enlacePdf') or '', 'BOE / bases'

def full_document_text(item: Dict[str, Any]) -> Tuple[str, str]:
    raw_parts = []
    for key in ['enlaceXml','enlaceBoeHtml']:
        if item.get(key): raw_parts.append(fetch_text(item[key]))
    if item.get('enlacePdf'): raw_parts.append(fetch_pdf_text(item['enlacePdf']))
    raw = '\n'.join(p for p in raw_parts if p)
    return raw, norm(raw)

def is_age_concurso(item: Dict[str, Any], summary_txt: str, tipo: str) -> bool:
    if tipo != 'concurso' or section_code(item) not in ALLOWED_SECTION_CODES: return False
    if re_any(summary_txt, NO_PERSONAL) or re_any(summary_txt, EXCLUDE): return False
    ep = norm(item.get('epigrafe',''))
    return 'personal funcionario' in ep or 'ministerio' in summary_txt or 'agencia estatal' in summary_txt or 'subsecretaria' in summary_txt or 'secretaria de estado' in summary_txt or 'agencia espanola' in summary_txt

def classify(item: Dict[str, Any], config: Dict[str, Any], targets: List[str]) -> Optional[Dict[str, Any]]:
    summary_txt = norm(' '.join(str(item.get(k,'')) for k in ['titulo','departamento','seccion','epigrafe']))
    if section_code(item) not in ALLOWED_SECTION_CODES: return None
    if re_any(summary_txt, NO_PERSONAL): return None
    tipo = detect_tipo(summary_txt)
    if tipo == 'otros': return None
    age_concurso = is_age_concurso(item, summary_txt, tipo)
    if not age_concurso:
        if re_any(summary_txt, EXCLUDE): return None
        if not re_any(summary_txt, OPENING): return None

    doc_raw, doc_txt = full_document_text(item) if config.get('validar_provincia_en_documento_completo', True) else ('', '')
    combined = norm(summary_txt + ' ' + doc_txt)
    title_provinces = detect_provinces(summary_txt, targets)
    doc_provinces = detect_provinces(doc_txt, targets)
    all_target_provinces = sorted(set(title_provinces + doc_provinces), key=norm)
    entity = detect_entity(combined)

    is_target_local = any(norm(t) in combined for t in ['ayuntamiento de albacete','diputacion de albacete','diputacion provincial de albacete','castilla-la mancha','castilla la mancha','junta de comunidades','sescam','universidad de castilla-la mancha','uclm'])

    if age_concurso and not all_target_provinces and not config.get('incluir_concursos_age_sin_provincia_confirmada', False):
        return None
    if tipo in ['libre_designacion','comision_servicio'] and not (all_target_provinces or is_target_local):
        return None
    if tipo == 'oposicion' and not (all_target_provinces or is_target_local):
        return None

    perfiles = sorted(set(detect_perfiles(combined)))
    niveles = detect_levels(combined)
    grupo = detect_group(combined)
    plazo = extract_plazo(combined)
    ins_link, ins_label = extract_best_link(item, doc_raw)

    if tipo == 'concurso':
        categoria, priority, precision = 'concursos', 1, 'revisar_anexo' if age_concurso else 'alta'
        motivo = 'Concurso de provisión de puestos con provincia vigilada confirmada en el documento. Revisa anexo para nivel, cuerpo, méritos y localidad.'
    elif tipo in ['libre_designacion','comision_servicio']:
        categoria, priority, precision = 'movilidad', 1, 'alta'
        motivo = 'Provisión por libre designación o comisión con Albacete/CLM detectado. Revisa requisitos, nivel, perfil y plazo.'
    else:
        categoria, priority, precision = 'oposiciones', 1, 'alta'
        motivo = 'Convocatoria de oposición/proceso selectivo con provincia o entidad de interés detectada. Revisa bases y portal de inscripción.'

    result = dict(item)
    result.update({
        'categoria': categoria,
        'tipo': tipo,
        'perfiles': perfiles,
        'provinciasDetectadas': sorted(set(detect_provinces(summary_txt))),
        'provinciasConfirmadasDocumento': all_target_provinces,
        'entidadDetectada': entity,
        'precision': precision,
        'prioridad': priority,
        'nivelesDetectados': niveles,
        'grupoDetectado': grupo,
        'plazoInscripcion': plazo,
        'enlaceInscripcion': ins_link,
        'enlaceInscripcionTipo': ins_label,
        'motivo': motivo,
        'tags': sorted(set([categoria, tipo, entity, grupo] + perfiles + all_target_provinces + [f'nivel {n}' for n in niveles]), key=norm)
    })
    return result

def unique_key(item: Dict[str, Any]) -> str:
    return str(item.get('boeId') or item.get('id') or hashlib.sha1(f"{item.get('fechaPublicacion')}|{item.get('titulo')}".encode()).hexdigest())

def merge(existing: List[Dict[str, Any]], new: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    by = {unique_key(x): x for x in existing}
    added = []
    for item in new:
        k = unique_key(item)
        if k not in by: added.append(item)
        by[k] = {**by.get(k, {}), **item}
    out = list(by.values())
    out.sort(key=lambda x: ((x.get('fechaPublicacion') or ''), -int(x.get('prioridad', 9))), reverse=True)
    return out, added

def issue_md(added: List[Dict[str, Any]], args: argparse.Namespace) -> str:
    if not added: return 'No se han detectado alertas nuevas.\n'
    lines = ['# Nuevas alertas BOE detectadas', '', f'Provincia: **{args.provincia or "config"}**', f'Rango: **{args.desde or "auto"} → {args.hasta or "auto"}**', '']
    for it in added[:40]:
        lines += [f"## {it.get('fechaPublicacion')} · {it.get('titulo')}", f"- Bloque: **{it.get('categoria')}**", f"- Tipo: **{it.get('tipo')}**", f"- Nivel detectado: {', '.join(map(str, it.get('nivelesDetectados') or [])) or 'No detectado'}", f"- Grupo: {it.get('grupoDetectado') or 'No detectado'}", f"- Plazo: {it.get('plazoInscripcion') or 'No detectado'}", f"- Inscripción/bases: {it.get('enlaceInscripcion') or 'No disponible'}", f"- BOE: {it.get('enlaceBoeHtml')}", '']
    return '\n'.join(lines).strip() + '\n'

def write(payload: Dict[str, Any], added: List[Dict[str, Any]], args: argparse.Namespace):
    DATA_DIR.mkdir(exist_ok=True); DOCS_DIR.mkdir(exist_ok=True)
    ALERTAS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    NEW_COUNT_PATH.write_text(str(len(added)), encoding='utf-8')
    ISSUE_PATH.write_text(issue_md(added, args), encoding='utf-8')

def args_parse():
    p = argparse.ArgumentParser()
    p.add_argument('--desde'); p.add_argument('--hasta'); p.add_argument('--provincia'); p.add_argument('--dias', type=int); p.add_argument('--max-dias', type=int, default=90); p.add_argument('--reiniciar', action='store_true')
    return p.parse_args()

def main() -> int:
    args = args_parse(); config = load_config(); today = dt.date.today()
    days = int(args.dias or config.get('dias_revision_por_defecto', 7))
    desde = parse_date(args.desde) if args.desde else today - dt.timedelta(days=max(0, days - 1))
    hasta = parse_date(args.hasta) if args.hasta else today
    if desde > hasta: desde, hasta = hasta, desde
    if hasta > today: hasta = today
    if (hasta - desde).days + 1 > args.max_dias: desde = hasta - dt.timedelta(days=args.max_dias - 1)
    targets = [args.provincia] if args.provincia else config.get('provincias_vigiladas', ['Albacete'])
    print(f'[INFO] Revisando {desde} → {hasta}. Provincia: {targets}')
    found, errors = [], []
    for fecha in daterange(desde, hasta):
        try:
            items = parse_sumario(fetch_sumario(fecha), fecha)
            day = 0
            for item in items:
                c = classify(item, config, targets)
                if c: found.append(c); day += 1
            print(f'[INFO] {fecha}: {day} alertas útiles')
        except Exception as e:
            msg = f'{fecha}: {e!r}'; print('[ERROR]', msg); errors.append(msg)
    existing = [] if args.reiniciar else load_existing().get('alertas', [])
    merged, added = merge(existing, found)
    payload = {'metadata': {'generatedBy': 'scripts/scan_boe.py', 'versionFiltro': 'v4-modulos-con-pdf', 'lastRun': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'), 'rangoUltimaRevision': {'desde': desde.isoformat(), 'hasta': hasta.isoformat()}, 'provinciasVigiladas': targets, 'fuente': 'BOE Datos Abiertos - sumario diario + documento XML/HTML/PDF', 'totalAlertas': len(merged), 'nuevasAlertas': len(added), 'errores': errors}, 'alertas': merged}
    write(payload, added, args)
    print(f'[INFO] Nuevas: {len(added)} Total: {len(merged)}')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
