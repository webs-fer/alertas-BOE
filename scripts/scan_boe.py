#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
BOE Alertas v5 - filtro fuerte para Informática/TIC en Albacete.

Objetivo:
- Priorizar plazas de informática/TIC/TAI.
- Mantener Administrativo C1 como secundario.
- Ocultar o descartar perfiles no útiles: Policía, Bomberos, Letrado, Peón, FHN, etc.
- Generar JSON y dashboard estático para GitHub Pages.

Uso:
    python scripts/scan_boe.py --desde 2026-04-01 --hasta 2026-04-29

Requisitos:
    pip install -r requirements.txt
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup


VERSION_FILTRO = "v5-perfil-informatica-prioritario"


CONFIG_DEFECTO: Dict[str, Any] = {
    "provincias": ["Albacete"],
    "priorizar_informatica": True,
    "incluir_administrativo_c1": True,
    "incluir_auxiliar_administrativo_c2": False,
    "incluir_libre_designacion": False,
    "incluir_promocion_interna": False,
    "incluir_perfiles_no_relacionados": False,
    "grupos_objetivo": ["C1", "C1/A2", "A2"],
    "nivel_minimo_deseado": 16,
    "modo_estricto": True,
    "prioridad_max_visible": 3,
    "sleep_segundos": 0.25,
    "timeout_segundos": 25,
    "user_agent": "BOE-Alertas-Informatica-v5/1.0 (+https://github.com/)",
}


# --------------------------------------------------------------------------------------
# Palabras clave
# --------------------------------------------------------------------------------------

KEYWORDS_INFORMATICA_FUERTES = [
    # Núcleo duro
    "informatico",
    "informatica",
    "informatico/a",
    "informatica/o",
    "tecnico de informatica",
    "tecnica de informatica",
    "tecnico/a de informatica",
    "tecnico auxiliar de informatica",
    "tecnica auxiliar de informatica",
    "tecnico especialista en informatica",
    "tecnica especialista en informatica",
    "tecnico superior de informatica",
    "tecnica superior de informatica",
    "tecnico medio de informatica",
    "tecnica media de informatica",
    "auxiliar informatico",
    "auxiliar informatica",
    "tai",

    # TIC / sistemas / soporte
    "tecnologias de la informacion",
    "tecnologias de informacion",
    "tecnologias de la informacion y las comunicaciones",
    "tic",
    "sistemas informaticos",
    "sistema informatico",
    "administrador de sistemas",
    "administradora de sistemas",
    "tecnico de sistemas",
    "tecnica de sistemas",
    "operador de sistemas",
    "operadora de sistemas",
    "operador informatico",
    "operadora informatica",
    "soporte informatico",
    "microinformatica",
    "redes y sistemas",
    "ciberseguridad",
    "seguridad informatica",
    "telecomunicaciones",

    # Desarrollo / datos
    "programador",
    "programadora",
    "analista programador",
    "analista-programador",
    "analista de sistemas",
    "desarrollador",
    "desarrolladora",
    "desarrollo de aplicaciones",
    "bases de datos",
    "administrador de bases de datos",
    "administradora de bases de datos",

    # Administración electrónica puede ser plaza TIC en algunas AAPP.
    "administracion electronica",
]


KEYWORDS_ADMINISTRATIVO_REALES = [
    "plaza de administrativo",
    "plaza de administrativa",
    "plazas de administrativo",
    "plazas de administrativa",
    "administrativo/a",
    "administrativa/o",
    "administrativo de administracion general",
    "administrativa de administracion general",
    "subescala administrativa",
    "administracion general, subescala administrativa",
    "escala de administracion general, subescala administrativa",
]


KEYWORDS_AUX_ADMIN = [
    "auxiliar administrativo",
    "auxiliar administrativa",
    "auxiliar administrativo/a",
    "auxiliar de administracion general",
    "auxiliares administrativos",
    "auxiliares administrativas",
]


KEYWORDS_DESCARTE_DURO = [
    "policia local",
    "agente de policia",
    "oficial de policia",
    "bombero",
    "bombera",
    "conductor bombero",
    "operador de radio mecanico conductor bombero",
    "operador/a de radio mecanico/a conductor/a bombero/a",
    "letrado",
    "letrada",
    "abogado",
    "abogada",
    "peon",
    "peon jardinero",
    "jardinero",
    "jardinera",
    "cuidador",
    "cuidadora",
    "maestro",
    "maestra",
    "maestro/a",
    "psicologo",
    "psicologa",
    "psicologo/a",
    "arquitecto",
    "arquitecta",
    "arquitecto/a",
    "ingeniero de caminos",
    "ingeniero industrial",
    "ingeniera industrial",
    "medico",
    "medica",
    "medico/a",
    "enfermero",
    "enfermera",
    "enfermero/a",
    "trabajador social",
    "trabajadora social",
    "tecnico deportivo",
    "monitor deportivo",
    "musico",
    "musica",
    "musico/a",
    "interventor",
    "interventora",
    "tesorero",
    "tesorera",
    "secretaria-intervencion",
    "secretario-interventor",
    "secretario/a-interventor/a",
    "habilitacion de caracter nacional",
    "funcionario de administracion local con habilitacion de caracter nacional",
    "funcionaria de administracion local con habilitacion de caracter nacional",
]


KEYWORDS_MOVILIDAD = [
    "concurso especifico",
    "concurso general",
    "libre designacion",
    "provision de puesto",
    "provision de puestos",
    "comision de servicios",
]


KEYWORDS_OPOSICION = [
    "convocatoria para proveer",
    "proceso selectivo",
    "concurso-oposicion",
    "concurso oposicion",
    "oposicion",
    "turno libre",
    "personal funcionario y laboral",
]


# --------------------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------------------

def normalizar(texto: Optional[str]) -> str:
    if not texto:
        return ""
    texto = texto.lower()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    texto = texto.replace("º", "o").replace("ª", "a")
    texto = re.sub(r"[«»“”\"']", " ", texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def contains_any(texto: str, keywords: Iterable[str]) -> List[str]:
    """
    Busca keywords evitando falsos positivos en palabras cortas.

    Ejemplo:
    - TIC no debe saltar en "política", "artículo" o "biblioteca".
    - TAI no debe saltar en "fotovoltaica" o "Taibilla".
    """
    texto_norm = normalizar(texto)
    encontrados = []

    for kw in keywords:
        kw_norm = normalizar(kw)
        if not kw_norm:
            continue

        # Keywords muy cortas: exigir palabra completa.
        if kw_norm in {"tic", "tai"}:
            patron = r"(?<![a-z0-9])" + re.escape(kw_norm) + r"(?![a-z0-9])"
            if re.search(patron, texto_norm):
                encontrados.append(kw)
            continue

        # Resto de keywords: búsqueda normal.
        if kw_norm in texto_norm:
            encontrados.append(kw)

    return sorted(set(encontrados))


def fecha_iter(desde: dt.date, hasta: dt.date) -> Iterable[dt.date]:
    actual = desde
    while actual <= hasta:
        yield actual
        actual += dt.timedelta(days=1)


def cargar_config(path: Path) -> Dict[str, Any]:
    config = CONFIG_DEFECTO.copy()
    if path.exists():
        try:
            user_config = json.loads(path.read_text(encoding="utf-8"))
            config.update(user_config)
        except Exception as exc:
            print(f"[WARN] No se pudo leer config {path}: {exc}", file=sys.stderr)
    return config


def fetch_url(url: str, config: Dict[str, Any]) -> Optional[str]:
    headers = {"User-Agent": config.get("user_agent", CONFIG_DEFECTO["user_agent"])}
    try:
        r = requests.get(url, headers=headers, timeout=int(config.get("timeout_segundos", 25)))
        if r.status_code == 404:
            return None
        r.raise_for_status()
        if not r.encoding or r.encoding.lower() in {"iso-8859-1", "ascii"}:
            r.encoding = r.apparent_encoding or "utf-8"
        return r.text
    except Exception as exc:
        print(f"[WARN] Error descargando {url}: {exc}", file=sys.stderr)
        return None


def soup_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()


def dedupe(seq: Iterable[str]) -> List[str]:
    out = []
    seen = set()
    for item in seq:
        key = normalizar(item)
        if key and key not in seen:
            seen.add(key)
            out.append(item)
    return out


# --------------------------------------------------------------------------------------
# Descarga BOE
# --------------------------------------------------------------------------------------

def url_sumario(fecha: dt.date) -> str:
    return f"https://www.boe.es/boe/dias/{fecha:%Y/%m/%d}/"


def url_html_boe(boe_id: str) -> str:
    return f"https://www.boe.es/diario_boe/txt.php?id={boe_id}"


def url_xml_boe(boe_id: str) -> str:
    return f"https://www.boe.es/diario_boe/xml.php?id={boe_id}"


def url_pdf_boe(boe_id: str, fecha: dt.date) -> str:
    return f"https://www.boe.es/boe/dias/{fecha:%Y/%m/%d}/pdfs/{boe_id}.pdf"


def extraer_ids_sumario(html: str) -> List[str]:
    # BOE-A-2026-9255, BOE-B-..., etc. Nos interesan sobre todo BOE-A.
    ids = re.findall(r"BOE-[A-Z]-\d{4}-\d+", html or "")
    ids = [x for x in ids if x.startswith("BOE-A-")]
    return dedupe(ids)


def extraer_titulo_documento(html: str, fallback: str = "") -> str:
    soup = BeautifulSoup(html, "html.parser")

    # En txt.php suele aparecer en h3/h4/h5 o en meta og:title.
    meta = soup.find("meta", attrs={"property": "og:title"}) or soup.find("meta", attrs={"name": "title"})
    if meta and meta.get("content"):
        title = meta.get("content", "").strip()
        if title:
            return title

    for selector in ["h3", "h4", "h2", "title"]:
        tag = soup.find(selector)
        if tag:
            title = re.sub(r"\s+", " ", tag.get_text(" ", strip=True)).strip()
            title = re.sub(r"^BOE\.es\s*-\s*", "", title)
            if title:
                return title

    texto = soup_text(html)
    m = re.search(r"(Resoluci[oó]n[^.]{20,300}\.)", texto, re.IGNORECASE)
    if m:
        return m.group(1).strip()

    return fallback


# --------------------------------------------------------------------------------------
# Extracción semántica
# --------------------------------------------------------------------------------------

def extraer_plazas_reales(texto: str) -> List[str]:
    """
    Extrae frases donde normalmente aparece la plaza real convocada.
    Devuelve texto normalizado para favorecer clasificación, pero legible.
    """
    if not texto:
        return []

    t = normalizar(texto)
    patrones = [
        r"((?:una|un|varias|varios|\d+|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce)\s+plazas?\s+de\s+[^.;:]{5,320})",
        r"((?:una|un|varias|varios|\d+|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce)\s+puestos?\s+de\s+[^.;:]{5,320})",
        r"((?:una|un)\s+puesto\s+de\s+trabajo\s+[^.;:]{5,320})",
        r"(convocatoria\s+para\s+proveer\s+[^.;:]{5,320})",
        r"(se\s+convocan\s+[^.;:]{5,320})",
        r"(las\s+plazas?\s+convocadas?\s+[^.;:]{5,320})",
    ]

    resultados: List[str] = []
    for patron in patrones:
        for m in re.findall(patron, t):
            frase = re.sub(r"\s+", " ", m).strip(" .;:")
            # Evita frases absurdamente genéricas si no dicen nada de plaza/puesto.
            if len(frase) >= 15:
                resultados.append(frase)

    # Si el BOE dice "perteneciente a la escala..." cerca de una plaza, añadir contexto cercano.
    for m in re.finditer(r"(plaza[^.]{0,180}(?:escala|subescala|clase|grupo)[^.]{0,260})", t):
        resultados.append(re.sub(r"\s+", " ", m.group(1)).strip(" .;:"))

    return dedupe(resultados)[:15]


def extraer_plazo(texto: str) -> str:
    t = normalizar(texto)
    patrones = [
        r"(plazo de presentacion de solicitudes[^.]{20,360})",
        r"(plazo para la presentacion de solicitudes[^.]{20,360})",
        r"(las solicitudes[^.]{20,260}dias habiles[^.]{0,180})",
        r"(quince dias habiles[^.]{0,260})",
        r"(veinte dias habiles[^.]{0,260})",
    ]
    for patron in patrones:
        m = re.search(patron, t)
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip(" .;:")
    return ""


def detectar_categoria_y_tipo(texto: str) -> Tuple[str, str]:
    t = normalizar(texto)
    if "libre designacion" in t:
        return "movilidad", "libre_designacion"
    if "concurso especifico" in t:
        return "movilidad", "concurso_especifico"
    if "concurso general" in t:
        return "movilidad", "concurso_general"
    if "comision de servicios" in t:
        return "movilidad", "comision_servicios"
    if contains_any(t, KEYWORDS_OPOSICION):
        return "oposiciones", "oposicion"
    return "otros", "sin_clasificar"


def detectar_grupos(texto: str) -> List[str]:
    t = normalizar(texto)
    grupos = set()

    for m in re.findall(r"\b(?:subgrupo|grupo)\s+(a1|a2|c1|c2|e)\b", t):
        grupos.add(m.upper())

    # Muchas bases lo expresan como "Grupo C, Subgrupo C1".
    for m in re.findall(r"\b(c1|c2|a1|a2)\b", t):
        grupos.add(m.upper())

    if "c1/a2" in t or "c1-a2" in t:
        grupos.add("C1/A2")

    return sorted(grupos)


def detectar_niveles(texto: str) -> List[int]:
    t = normalizar(texto)
    niveles = []
    for m in re.findall(r"\bnivel\s+(\d{1,2})\b", t):
        try:
            n = int(m)
            if 1 <= n <= 30:
                niveles.append(n)
        except ValueError:
            pass
    return sorted(set(niveles))


def detectar_entidad(texto: str) -> str:
    t = texto or ""
    patrones = [
        r"(Ayuntamiento de [A-ZÁÉÍÓÚÜÑ][A-Za-zÁÉÍÓÚÜÑáéíóúüñ\s\-]+)",
        r"(Diputaci[oó]n Provincial de [A-ZÁÉÍÓÚÜÑ][A-Za-zÁÉÍÓÚÜÑáéíóúüñ\s\-]+)",
        r"(Diputaci[oó]n de [A-ZÁÉÍÓÚÜÑ][A-Za-zÁÉÍÓÚÜÑáéíóúüñ\s\-]+)",
        r"(Universidad de [A-ZÁÉÍÓÚÜÑ][A-Za-zÁÉÍÓÚÜÑáéíóúüñ\s\-]+)",
        r"(Direcci[oó]n General de [A-ZÁÉÍÓÚÜÑ][A-Za-zÁÉÍÓÚÜÑáéíóúüñ\s\-]+)",
    ]
    for patron in patrones:
        m = re.search(patron, t)
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip(" ,.")
    return ""


def detectar_provincias(texto: str, provincias: List[str]) -> List[str]:
    return [p for p in provincias if normalizar(p) in normalizar(texto)]


def contexts_for_hits(texto: str, hits: List[str], radio: int = 150) -> List[str]:
    t_norm = normalizar(texto)
    contextos = []
    for hit in hits:
        h = normalizar(hit)
        idx = t_norm.find(h)
        if idx >= 0:
            start = max(0, idx - radio)
            end = min(len(t_norm), idx + len(h) + radio)
            contextos.append(t_norm[start:end].strip())
    return dedupe(contextos)[:6]


def fingerprint_alerta(alerta: Dict[str, Any]) -> str:
    entidad = normalizar(alerta.get("entidadDetectada", ""))
    plazas = normalizar(" ".join(alerta.get("plazasExtraidas", [])[:2]))
    perfil = normalizar(alerta.get("perfilReal", ""))
    tipo = normalizar(alerta.get("tipo", ""))
    titulo = normalizar(alerta.get("titulo", ""))

    base = f"{entidad}|{plazas or titulo[:120]}|{perfil}|{tipo}"
    return base


def clasificar_para_usuario(alerta: Dict[str, Any], texto_documento: str, config: Dict[str, Any]) -> Dict[str, Any]:
    titulo = alerta.get("titulo", "")
    entidad = alerta.get("entidadDetectada", "")
    epigrafe = alerta.get("epigrafe", "")
    tags = " ".join(alerta.get("tags", []))
    plazas_extraidas = extraer_plazas_reales(texto_documento)
    texto_plazas = " ".join(plazas_extraidas)

    texto_total = " ".join([titulo, entidad, epigrafe, tags, texto_documento or ""])
    texto_clasificacion = texto_plazas if texto_plazas else texto_total

    t_total = normalizar(texto_total)
    t_clas = normalizar(texto_clasificacion)

    hits_info = contains_any(t_clas, KEYWORDS_INFORMATICA_FUERTES)
    hits_admin = contains_any(t_clas, KEYWORDS_ADMINISTRATIVO_REALES)
    hits_aux = contains_any(t_clas, KEYWORDS_AUX_ADMIN)
    hits_descarte = contains_any(t_clas, KEYWORDS_DESCARTE_DURO)

    es_libre_designacion = "libre designacion" in t_total
    es_promocion_interna = "promocion interna" in t_total
    grupos = detectar_grupos(texto_total)
    niveles = detectar_niveles(texto_total)

    resultado = {
        "plazasExtraidas": plazas_extraidas,
        "perfilReal": "",
        "relevanciaUsuario": "baja",
        "prioridadUsuario": 6,
        "descartadaParaUsuario": False,
        "visibleParaUsuario": False,
        "motivoRelevanciaUsuario": "",
        "matchesInformatica": hits_info,
        "matchesAdministrativo": hits_admin,
        "matchesAuxiliarAdministrativo": hits_aux,
        "matchesDescarte": hits_descarte,
        "contextosInformatica": contexts_for_hits(texto_clasificacion, hits_info),
        "gruposDetectados": grupos,
        "nivelesDetectados": niveles,
    }

    # 1) Informática/TIC manda sobre todo lo demás.
    if hits_info:
        prioridad = 1
        relevancia = "muy_alta"
        motivo = "Detectada plaza/perfil de informática, TIC, sistemas, redes, soporte o desarrollo."

        if es_libre_designacion and not config.get("incluir_libre_designacion", False):
            # No la oculto del todo porque el usuario quiere sobre todo informática,
            # pero la bajo para que revise requisitos/nivel.
            prioridad = 2
            relevancia = "alta"
            motivo += " Es libre designación: revisar requisitos y nivel antes de considerarla viable."

        if es_promocion_interna and not config.get("incluir_promocion_interna", False):
            prioridad = max(prioridad, 3)
            relevancia = "media"
            motivo += " Parece promoción interna: revisar si puedes participar."

        resultado.update({
            "perfilReal": "informatica_tic",
            "relevanciaUsuario": relevancia,
            "prioridadUsuario": prioridad,
            "descartadaParaUsuario": False,
            "visibleParaUsuario": True,
            "motivoRelevanciaUsuario": motivo,
        })
        return resultado

    # 2) Administrativo C1 real.
    if hits_admin and config.get("incluir_administrativo_c1", True):
        resultado.update({
            "perfilReal": "administrativo_c1_probable",
            "relevanciaUsuario": "alta",
            "prioridadUsuario": 2,
            "descartadaParaUsuario": False,
            "visibleParaUsuario": True,
            "motivoRelevanciaUsuario": "Detectada plaza real de Administrativo/a o subescala administrativa.",
        })
        return resultado

    # 3) Auxiliar Administrativo C2, opcional.
    if hits_aux:
        incluir_aux = config.get("incluir_auxiliar_administrativo_c2", False)
        resultado.update({
            "perfilReal": "auxiliar_administrativo_c2_probable",
            "relevanciaUsuario": "media" if incluir_aux else "baja",
            "prioridadUsuario": 3 if incluir_aux else 7,
            "descartadaParaUsuario": not incluir_aux,
            "visibleParaUsuario": bool(incluir_aux),
            "motivoRelevanciaUsuario": "Detectada plaza de Auxiliar Administrativo/a. Suele ser C2, por eso queda como secundaria u oculta según configuración.",
        })
        return resultado

    # 4) Descartes duros.
    if hits_descarte:
        resultado.update({
            "perfilReal": "otro_no_interesante",
            "relevanciaUsuario": "descartar",
            "prioridadUsuario": 9,
            "descartadaParaUsuario": True,
            "visibleParaUsuario": False,
            "motivoRelevanciaUsuario": "Perfil no relacionado con informática/TIC, TAI, Administrativo C1 ni movilidad útil para el usuario.",
        })
        return resultado

    # 5) Libre designación no informática.
    if es_libre_designacion and not config.get("incluir_libre_designacion", False):
        resultado.update({
            "perfilReal": "libre_designacion_no_prioritaria",
            "relevanciaUsuario": "descartar",
            "prioridadUsuario": 9,
            "descartadaParaUsuario": True,
            "visibleParaUsuario": False,
            "motivoRelevanciaUsuario": "Libre designación sin perfil informático ni administrativo C1 claro.",
        })
        return resultado

    # 6) Promoción interna no informática.
    if es_promocion_interna and not config.get("incluir_promocion_interna", False):
        resultado.update({
            "perfilReal": "promocion_interna_no_prioritaria",
            "relevanciaUsuario": "baja",
            "prioridadUsuario": 7,
            "descartadaParaUsuario": True,
            "visibleParaUsuario": False,
            "motivoRelevanciaUsuario": "Promoción interna sin perfil informático detectado.",
        })
        return resultado

    # 7) Albacete pero sin perfil claro.
    resultado.update({
        "perfilReal": "sin_perfil_claro",
        "relevanciaUsuario": "baja",
        "prioridadUsuario": 6,
        "descartadaParaUsuario": bool(config.get("modo_estricto", True)),
        "visibleParaUsuario": False if config.get("modo_estricto", True) else True,
        "motivoRelevanciaUsuario": "Provincia de interés detectada, pero no se ha identificado plaza de informática/TIC ni Administrativo C1.",
    })

    return resultado


# --------------------------------------------------------------------------------------
# Generación de alerta
# --------------------------------------------------------------------------------------

def crear_alerta_desde_boe_id(boe_id: str, fecha: dt.date, config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    html_url = url_html_boe(boe_id)
    html = fetch_url(html_url, config)
    if not html:
        return None

    texto = soup_text(html)
    titulo = extraer_titulo_documento(html, fallback=boe_id)
    entidad = detectar_entidad(" ".join([titulo, texto]))
    categoria, tipo = detectar_categoria_y_tipo(" ".join([titulo, texto]))

    provincias_doc = detectar_provincias(" ".join([titulo, texto]), config.get("provincias", ["Albacete"]))
    if not provincias_doc:
        # Filtro territorial duro: si no aparece provincia/municipio vigilado en el documento, no entra.
        return None

    plazo = extraer_plazo(texto)

    alerta: Dict[str, Any] = {
        "id": boe_id,
        "boeId": boe_id,
        "fechaPublicacion": fecha.isoformat(),
        "titulo": titulo,
        "departamento": "",
        "seccion": "",
        "epigrafe": "",
        "enlaceBoeHtml": html_url,
        "enlacePdf": url_pdf_boe(boe_id, fecha),
        "enlaceXml": url_xml_boe(boe_id),
        "enlaceSumario": url_sumario(fecha),
        "enlaceApi": f"https://www.boe.es/datosabiertos/api/boe/sumario/{fecha:%Y%m%d}",
        "fuente": "BOE",
        "categoria": categoria,
        "tipo": tipo,
        "perfiles": [],
        "provinciasDetectadas": provincias_doc,
        "provinciasConfirmadasDocumento": provincias_doc,
        "entidadDetectada": entidad,
        "precision": "alta",
        "plazoInscripcion": plazo,
        "enlaceInscripcion": html_url,
        "enlaceInscripcionTipo": "BOE / bases",
        "motivo": "",
        "tags": [],
    }

    clasif = clasificar_para_usuario(alerta, texto, config)
    alerta.update(clasif)

    # Compatibilidad con campo prioridad antiguo.
    alerta["prioridad"] = alerta.get("prioridadUsuario", 9)

    # Tags
    tags = set()
    for p in provincias_doc:
        tags.add(p)
    if entidad:
        tags.add(entidad)
    tags.add(tipo)
    tags.add(categoria)
    if alerta["perfilReal"]:
        tags.add(alerta["perfilReal"])
    if alerta.get("matchesInformatica"):
        tags.add("informatica")
    if alerta.get("matchesAdministrativo"):
        tags.add("administrativo")
    alerta["tags"] = sorted(tags)

    if alerta.get("descartadaParaUsuario"):
        alerta["motivo"] = alerta.get("motivoRelevanciaUsuario", "Descartada por perfil.")
    else:
        alerta["motivo"] = alerta.get("motivoRelevanciaUsuario", "Alerta relevante.")

    return alerta


def scan_boe(desde: dt.date, hasta: dt.date, config: Dict[str, Any]) -> Dict[str, Any]:
    alertas: List[Dict[str, Any]] = []
    errores: List[Dict[str, str]] = []

    for fecha in fecha_iter(desde, hasta):
        sumario_url = url_sumario(fecha)
        html_sumario = fetch_url(sumario_url, config)

        if html_sumario is None:
            continue

        boe_ids = extraer_ids_sumario(html_sumario)
        if not boe_ids:
            continue

        print(f"[INFO] {fecha.isoformat()} - {len(boe_ids)} documentos BOE-A detectados")

        for boe_id in boe_ids:
            try:
                alerta = crear_alerta_desde_boe_id(boe_id, fecha, config)
                if alerta:
                    alertas.append(alerta)
            except Exception as exc:
                errores.append({"boeId": boe_id, "fecha": fecha.isoformat(), "error": str(exc)})
                print(f"[WARN] Error procesando {boe_id}: {exc}", file=sys.stderr)

            sleep_s = float(config.get("sleep_segundos", 0.25))
            if sleep_s > 0:
                time.sleep(sleep_s)

    # Duplicados probables
    fp_seen: Dict[str, str] = {}
    for alerta in alertas:
        fp = fingerprint_alerta(alerta)
        alerta["fingerprint"] = fp
        alerta["posibleDuplicado"] = False
        alerta["duplicadoDe"] = ""
        if fp in fp_seen:
            alerta["posibleDuplicado"] = True
            alerta["duplicadoDe"] = fp_seen[fp]
        else:
            fp_seen[fp] = alerta["id"]

    alertas.sort(key=lambda a: (a.get("prioridadUsuario", 9), a.get("fechaPublicacion", "")), reverse=False)

    visibles = [a for a in alertas if a.get("visibleParaUsuario") and not a.get("descartadaParaUsuario")]
    prioritarias = [a for a in visibles if a.get("prioridadUsuario", 9) <= 2]
    secundarias = [a for a in visibles if a.get("prioridadUsuario", 9) == 3]
    descartadas = [a for a in alertas if a.get("descartadaParaUsuario") or not a.get("visibleParaUsuario")]

    resultado = {
        "metadata": {
            "generatedBy": "scripts/scan_boe.py",
            "versionFiltro": VERSION_FILTRO,
            "lastRun": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "rangoUltimaRevision": {
                "desde": desde.isoformat(),
                "hasta": hasta.isoformat(),
            },
            "provinciasVigiladas": config.get("provincias", ["Albacete"]),
            "fuente": "BOE - sumario diario + documento HTML",
            "totalAlertasDetectadasTerritorialmente": len(alertas),
            "totalVisiblesParaUsuario": len(visibles),
            "totalPrioritarias": len(prioritarias),
            "totalSecundarias": len(secundarias),
            "totalDescartadas": len(descartadas),
            "errores": errores,
            "configResumen": {
                "priorizar_informatica": config.get("priorizar_informatica"),
                "incluir_administrativo_c1": config.get("incluir_administrativo_c1"),
                "incluir_auxiliar_administrativo_c2": config.get("incluir_auxiliar_administrativo_c2"),
                "incluir_libre_designacion": config.get("incluir_libre_designacion"),
                "modo_estricto": config.get("modo_estricto"),
            },
        },
        "alertasPrioritarias": prioritarias,
        "alertasSecundarias": secundarias,
        "alertasDescartadas": descartadas,
        "alertas": visibles,
        "todasLasAlertas": alertas,
    }

    return resultado


# --------------------------------------------------------------------------------------
# Dashboard GitHub Pages
# --------------------------------------------------------------------------------------

def escribir_dashboard(resultado: Dict[str, Any], docs_dir: Path) -> None:
    docs_dir.mkdir(parents=True, exist_ok=True)

    (docs_dir / "alertas.json").write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    index_html = """<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>Radar BOE Informática - Albacete</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Dashboard de alertas BOE filtradas para plazas de Informática/TIC y Administrativo en Albacete.">
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <header class="hero">
    <div>
      <p class="eyebrow">BOE Alertas v5</p>
      <h1>Radar BOE Informática</h1>
      <p class="subtitle">Informática/TIC primero. Administrativo C1 después. Ruido descartado.</p>
    </div>
    <div class="hero-card">
      <span id="lastRun">Cargando…</span>
      <strong id="totalPrioritarias">0 prioritarias</strong>
    </div>
  </header>

  <main>
    <section class="toolbar">
      <button data-filter="prioritarias" class="active">Prioritarias</button>
      <button data-filter="informatica">Informática/TIC</button>
      <button data-filter="administrativo">Administrativo</button>
      <button data-filter="secundarias">Secundarias</button>
      <button data-filter="descartadas">Descartadas</button>
      <button data-filter="todas">Todas</button>
    </section>

    <section class="summary-grid">
      <article>
        <span>Prioritarias</span>
        <strong id="mPrioritarias">0</strong>
      </article>
      <article>
        <span>Secundarias</span>
        <strong id="mSecundarias">0</strong>
      </article>
      <article>
        <span>Descartadas</span>
        <strong id="mDescartadas">0</strong>
      </article>
      <article>
        <span>Total territorial</span>
        <strong id="mTotal">0</strong>
      </article>
    </section>

    <section id="cards" class="cards"></section>
  </main>

  <footer>
    <p>Generado automáticamente desde BOE. Revisa siempre las bases oficiales antes de inscribirte.</p>
  </footer>

  <script src="app.js"></script>
</body>
</html>
"""

    styles_css = r""":root {
  --bg: #07111f;
  --bg2: #0d1b2e;
  --card: rgba(255,255,255,.075);
  --card2: rgba(255,255,255,.105);
  --border: rgba(148, 163, 184, .25);
  --text: #e5edf8;
  --muted: #9fb0c8;
  --accent: #38bdf8;
  --good: #34d399;
  --warn: #fbbf24;
  --bad: #fb7185;
  --shadow: 0 20px 80px rgba(0,0,0,.35);
}

* { box-sizing: border-box; }

body {
  margin: 0;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
  color: var(--text);
  background:
    radial-gradient(circle at top left, rgba(56,189,248,.18), transparent 36rem),
    radial-gradient(circle at top right, rgba(52,211,153,.12), transparent 32rem),
    linear-gradient(135deg, var(--bg), var(--bg2));
  min-height: 100vh;
}

.hero {
  display: flex;
  align-items: stretch;
  justify-content: space-between;
  gap: 1.5rem;
  padding: 3rem clamp(1rem, 5vw, 5rem) 2rem;
}

.eyebrow {
  color: var(--accent);
  text-transform: uppercase;
  letter-spacing: .16em;
  font-size: .8rem;
  font-weight: 800;
}

h1 {
  font-size: clamp(2.1rem, 7vw, 5rem);
  margin: .2rem 0 .4rem;
  line-height: .95;
}

.subtitle {
  color: var(--muted);
  font-size: clamp(1rem, 2vw, 1.25rem);
  max-width: 780px;
}

.hero-card {
  min-width: min(320px, 100%);
  padding: 1.2rem;
  border: 1px solid var(--border);
  border-radius: 24px;
  background: var(--card);
  box-shadow: var(--shadow);
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.hero-card span { color: var(--muted); }
.hero-card strong { font-size: 1.8rem; margin-top: .35rem; }

main {
  padding: 0 clamp(1rem, 5vw, 5rem) 3rem;
}

.toolbar {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  gap: .75rem;
  flex-wrap: wrap;
  padding: 1rem 0;
  backdrop-filter: blur(16px);
}

button {
  border: 1px solid var(--border);
  background: rgba(255,255,255,.07);
  color: var(--text);
  padding: .75rem 1rem;
  border-radius: 999px;
  cursor: pointer;
  font-weight: 800;
}

button:hover, button.active {
  border-color: rgba(56,189,248,.8);
  background: rgba(56,189,248,.16);
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1rem;
  margin: 1rem 0 1.5rem;
}

.summary-grid article {
  border: 1px solid var(--border);
  background: var(--card);
  border-radius: 22px;
  padding: 1rem;
}

.summary-grid span {
  display: block;
  color: var(--muted);
  font-size: .9rem;
}

.summary-grid strong {
  display: block;
  margin-top: .3rem;
  font-size: 2rem;
}

.cards {
  display: grid;
  gap: 1rem;
}

.card {
  border: 1px solid var(--border);
  background: linear-gradient(135deg, var(--card), rgba(255,255,255,.045));
  border-radius: 26px;
  padding: 1.2rem;
  box-shadow: 0 16px 48px rgba(0,0,0,.22);
}

.card.priority-1 { border-color: rgba(52,211,153,.55); }
.card.priority-2 { border-color: rgba(56,189,248,.48); }
.card.priority-3 { border-color: rgba(251,191,36,.45); }
.card.discarded { opacity: .72; border-color: rgba(251,113,133,.38); }

.card-head {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: flex-start;
}

.card h2 {
  margin: 0;
  font-size: 1.16rem;
  line-height: 1.35;
}

.badge {
  display: inline-flex;
  align-items: center;
  white-space: nowrap;
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: .35rem .65rem;
  font-weight: 900;
  font-size: .78rem;
}

.badge.info { color: var(--good); border-color: rgba(52,211,153,.4); background: rgba(52,211,153,.1); }
.badge.admin { color: var(--accent); border-color: rgba(56,189,248,.4); background: rgba(56,189,248,.1); }
.badge.warn { color: var(--warn); border-color: rgba(251,191,36,.4); background: rgba(251,191,36,.1); }
.badge.bad { color: var(--bad); border-color: rgba(251,113,133,.4); background: rgba(251,113,133,.1); }

.meta {
  display: flex;
  flex-wrap: wrap;
  gap: .5rem;
  margin: .85rem 0;
  color: var(--muted);
  font-size: .9rem;
}

.reason {
  color: #d7e5f7;
  line-height: 1.55;
}

.plazas {
  margin-top: .8rem;
  padding: .8rem;
  border: 1px solid var(--border);
  border-radius: 16px;
  background: rgba(0,0,0,.18);
  color: #dce8f8;
}

.plazas strong {
  display: block;
  margin-bottom: .35rem;
}

.plazas ul {
  margin: .3rem 0 0;
  padding-left: 1.2rem;
}

.links {
  display: flex;
  flex-wrap: wrap;
  gap: .65rem;
  margin-top: 1rem;
}

.links a {
  color: var(--text);
  text-decoration: none;
  font-weight: 900;
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: .55rem .75rem;
  background: rgba(255,255,255,.06);
}

.links a:hover {
  border-color: var(--accent);
  color: white;
}

.empty {
  border: 1px dashed var(--border);
  border-radius: 24px;
  padding: 2rem;
  color: var(--muted);
  text-align: center;
}

footer {
  color: var(--muted);
  text-align: center;
  padding: 2rem;
}

@media (max-width: 850px) {
  .hero { flex-direction: column; }
  .summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .card-head { flex-direction: column; }
}

@media (max-width: 520px) {
  .summary-grid { grid-template-columns: 1fr; }
}
"""

    app_js = r"""let data = null;
let currentFilter = "prioritarias";

const $ = (sel) => document.querySelector(sel);
const cards = $("#cards");

async function load() {
  try {
    const res = await fetch("alertas.json", { cache: "no-store" });
    data = await res.json();
    hydrateSummary();
    render();
  } catch (err) {
    cards.innerHTML = `<div class="empty">No se pudo cargar alertas.json. Ejecuta primero scripts/scan_boe.py.</div>`;
    console.error(err);
  }
}

function hydrateSummary() {
  const m = data.metadata || {};
  $("#lastRun").textContent = `Última revisión: ${m.lastRun || "sin datos"}`;
  $("#totalPrioritarias").textContent = `${m.totalPrioritarias || 0} prioritarias`;
  $("#mPrioritarias").textContent = m.totalPrioritarias || 0;
  $("#mSecundarias").textContent = m.totalSecundarias || 0;
  $("#mDescartadas").textContent = m.totalDescartadas || 0;
  $("#mTotal").textContent = m.totalAlertasDetectadasTerritorialmente || 0;
}

function listForFilter(filter) {
  const prioritarias = data.alertasPrioritarias || [];
  const secundarias = data.alertasSecundarias || [];
  const descartadas = data.alertasDescartadas || [];
  const todas = data.todasLasAlertas || [];

  if (filter === "prioritarias") return prioritarias;
  if (filter === "secundarias") return secundarias;
  if (filter === "descartadas") return descartadas;
  if (filter === "todas") return todas;
  if (filter === "informatica") {
    return todas.filter(a => (a.perfilReal || "").includes("informatica") || (a.matchesInformatica || []).length);
  }
  if (filter === "administrativo") {
    return todas.filter(a => (a.perfilReal || "").includes("administrativo") || (a.matchesAdministrativo || []).length);
  }
  return prioritarias;
}

function badge(alerta) {
  const perfil = alerta.perfilReal || "sin_perfil";
  const prioridad = alerta.prioridadUsuario || 9;

  if (alerta.descartadaParaUsuario) return `<span class="badge bad">Descartada</span>`;
  if (perfil.includes("informatica")) return `<span class="badge info">Informática/TIC · P${prioridad}</span>`;
  if (perfil.includes("administrativo")) return `<span class="badge admin">Administrativo · P${prioridad}</span>`;
  if (prioridad === 3) return `<span class="badge warn">Secundaria · P3</span>`;
  return `<span class="badge bad">Baja relevancia</span>`;
}

function safe(v) {
  return String(v ?? "").replace(/[&<>"']/g, s => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;"
  }[s]));
}

function render() {
  const items = listForFilter(currentFilter);
  if (!items.length) {
    cards.innerHTML = `<div class="empty">No hay alertas para este filtro.</div>`;
    return;
  }

  cards.innerHTML = items.map(a => {
    const plazas = Array.isArray(a.plazasExtraidas) && a.plazasExtraidas.length
      ? `<div class="plazas"><strong>Plazas/frases detectadas</strong><ul>${a.plazasExtraidas.map(p => `<li>${safe(p)}</li>`).join("")}</ul></div>`
      : "";

    return `<article class="card priority-${a.prioridadUsuario || 9} ${a.descartadaParaUsuario ? "discarded" : ""}">
      <div class="card-head">
        <h2>${safe(a.titulo)}</h2>
        ${badge(a)}
      </div>

      <div class="meta">
        <span>${safe(a.fechaPublicacion)}</span>
        <span>${safe(a.entidadDetectada || "Entidad no detectada")}</span>
        <span>${safe(a.tipo)}</span>
        <span>${safe(a.perfilReal)}</span>
        ${a.posibleDuplicado ? `<span>⚠️ Posible duplicado de ${safe(a.duplicadoDe)}</span>` : ""}
      </div>

      <p class="reason">${safe(a.motivoRelevanciaUsuario || a.motivo || "")}</p>

      ${plazas}

      ${a.plazoInscripcion ? `<p class="reason"><strong>Plazo:</strong> ${safe(a.plazoInscripcion)}</p>` : ""}

      <div class="links">
        <a href="${safe(a.enlaceBoeHtml)}" target="_blank" rel="noopener">BOE HTML</a>
        <a href="${safe(a.enlacePdf)}" target="_blank" rel="noopener">PDF</a>
        <a href="${safe(a.enlaceXml)}" target="_blank" rel="noopener">XML</a>
      </div>
    </article>`;
  }).join("");
}

document.querySelectorAll("[data-filter]").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("[data-filter]").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    currentFilter = btn.dataset.filter;
    render();
  });
});

load();
"""

    (docs_dir / "index.html").write_text(index_html, encoding="utf-8")
    (docs_dir / "styles.css").write_text(styles_css, encoding="utf-8")
    (docs_dir / "app.js").write_text(app_js, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Escanea BOE y filtra alertas útiles para Informática/TIC en Albacete.")
    parser.add_argument("--desde", help="Fecha inicio YYYY-MM-DD. Por defecto: hace 30 días.")
    parser.add_argument("--hasta", help="Fecha fin YYYY-MM-DD. Por defecto: hoy.")
    parser.add_argument("--config", default="config/user_profile.json", help="Ruta del fichero de configuración.")
    parser.add_argument("--out", default="outputs/alertas.json", help="JSON de salida completo.")
    parser.add_argument("--docs", default="docs", help="Carpeta de GitHub Pages.")
    args = parser.parse_args()

    hoy = dt.date.today()
    hasta = dt.date.fromisoformat(args.hasta) if args.hasta else hoy
    desde = dt.date.fromisoformat(args.desde) if args.desde else hasta - dt.timedelta(days=30)

    config = cargar_config(Path(args.config))

    resultado = scan_boe(desde, hasta, config)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")

    escribir_dashboard(resultado, Path(args.docs))

    print("")
    print("=== RESUMEN ===")
    print(f"Filtro: {VERSION_FILTRO}")
    print(f"Rango: {desde.isoformat()} a {hasta.isoformat()}")
    print(f"Alertas territoriales: {resultado['metadata']['totalAlertasDetectadasTerritorialmente']}")
    print(f"Prioritarias: {resultado['metadata']['totalPrioritarias']}")
    print(f"Secundarias: {resultado['metadata']['totalSecundarias']}")
    print(f"Descartadas/ocultas: {resultado['metadata']['totalDescartadas']}")
    print(f"JSON: {out_path}")
    print(f"Dashboard: {Path(args.docs) / 'index.html'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
