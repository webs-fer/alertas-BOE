const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const API_BASE = 'https://www.boe.es/datosabiertos/api/boe/sumario/';
const BOE_BASE = 'https://www.boe.es';

const DEFAULT_PROVINCES = [
  'Albacete', 'Alicante', 'Almería', 'Ávila', 'Badajoz', 'Barcelona', 'Burgos', 'Cáceres', 'Cádiz',
  'Castellón', 'Ciudad Real', 'Córdoba', 'Cuenca', 'Girona', 'Granada', 'Guadalajara', 'Huelva',
  'Huesca', 'Jaén', 'León', 'Lleida', 'La Rioja', 'Lugo', 'Madrid', 'Málaga', 'Murcia', 'Ourense',
  'Palencia', 'Pontevedra', 'Salamanca', 'Segovia', 'Sevilla', 'Soria', 'Tarragona', 'Teruel',
  'Toledo', 'Valencia', 'Valladolid', 'Zamora', 'Zaragoza', 'Ceuta', 'Melilla'
];

const state = {
  raw: [],
  visible: [],
  metadata: {},
  directResults: []
};

const labelTipo = {
  concurso: 'Concurso / provisión',
  libre_designacion: 'Libre designación',
  comision_servicio: 'Comisión servicio',
  oposicion: 'Oposición / convocatoria',
  otros: 'Otro aviso'
};

const perfilPalabras = {
  informatica: [
    'informatica',
    'informático',
    'informatico',
    'informaticos',
    'informáticos',
    'tecnologias de la informacion',
    'tecnologías de la información',
    'tic',
    'sistemas informaticos',
    'sistemas informáticos',
    'administracion de sistemas',
    'administración de sistemas',
    'microinformatica',
    'microinformática',
    'programador',
    'programadora',
    'ofimatica',
    'ofimática',
    'desarrollo de aplicaciones',
    'tecnico auxiliar de informatica',
    'técnico auxiliar de informática',
    'tecnico auxiliar informatico',
    'técnico auxiliar informático'
  ],
  administrativo: [
    'cuerpo administrativo',
    'escala administrativa',
    'auxiliar administrativo',
    'gestion administrativa',
    'gestión administrativa',
    'plaza de administrativo',
    'plazas de administrativo',
    'administrativos',
    'administrativo'
  ],
  c1a2: [
    'c1',
    'a2',
    'c1/a2',
    'c1-a2',
    'subgrupo c1',
    'subgrupo a2',
    'nivel 16',
    'nivel 17',
    'nivel 18',
    'nivel 19',
    'nivel 20',
    'nivel 21',
    'nivel 22'
  ]
};

function normalize(text = '') {
  return text
    .toString()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase();
}

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function addDays(date, days) {
  const d = new Date(date);
  d.setDate(d.getDate() + days);
  return d;
}

function formatApiDate(isoDate) {
  return isoDate.replaceAll('-', '');
}

function formatHumanDate(isoDate) {
  if (!isoDate) return 'Sin fecha';

  const onlyDate = isoDate.slice(0, 10);
  const [y, m, d] = onlyDate.split('-');

  if (!y || !m || !d) return isoDate;

  return `${d}/${m}/${y}`;
}

function sumarioUrl(isoDate) {
  if (!isoDate) return 'https://www.boe.es/boe/dias/';

  const [y, m, d] = isoDate.split('-');

  return `${BOE_BASE}/boe/dias/${y}/${m}/${d}/`;
}

function apiUrl(isoDate) {
  return `${API_BASE}${formatApiDate(isoDate)}`;
}

function ensureAbsolute(url) {
  if (!url) return '';
  if (url.startsWith('http')) return url;
  if (url.startsWith('/')) return `${BOE_BASE}${url}`;

  return `${BOE_BASE}/${url}`;
}

function getFilters() {
  const fechaExacta = $('#fechaExacta').value;

  if (fechaExacta) {
    $('#fechaDesde').value = fechaExacta;
    $('#fechaHasta').value = fechaExacta;
  }

  const checkedTipos = $$('input[name="tipo"]:checked').map((el) => el.value);

  const palabrasExtra = $('#palabrasExtra').value
    .split(',')
    .map((w) => normalize(w.trim()))
    .filter(Boolean);

  let desde = $('#fechaDesde').value;
  let hasta = $('#fechaHasta').value;

  const dias = Number($('#dias').value || 30);

  if (!desde && !hasta) {
    const end = new Date();
    const start = addDays(end, -Math.max(0, dias - 1));

    desde = start.toISOString().slice(0, 10);
    hasta = end.toISOString().slice(0, 10);
  }

  if (desde && !hasta) hasta = desde;
  if (hasta && !desde) desde = hasta;

  if (desde > hasta) {
    [desde, hasta] = [hasta, desde];
  }

  return {
    provincia: $('#provincia').value.trim() || 'Albacete',
    desde,
    hasta,
    perfil: $('#perfil').value,
    tipos: checkedTipos,
    estricto: $('#modoEstricto').checked,
    palabrasExtra
  };
}

function matchesFilters(item, filters) {
  const fecha = item.fechaPublicacion || item.fecha || '';

  if (filters.desde && fecha < filters.desde) return false;
  if (filters.hasta && fecha > filters.hasta) return false;

  if (filters.tipos.length && !filters.tipos.includes(item.tipo || 'otros')) {
    return false;
  }

  const fullText = normalize([
    item.titulo,
    item.departamento,
    item.seccion,
    item.epigrafe,
    item.motivo,
    item.entidadDetectada,
    ...(item.tags || []),
    ...(item.perfiles || []),
    ...(item.provinciasDetectadas || []),
    ...(item.provinciasConfirmadasDocumento || [])
  ].join(' '));

  const provincia = normalize(filters.provincia);

  const provinciasDetectadas = (item.provinciasDetectadas || []).map(normalize);
  const provinciasConfirmadas = (item.provinciasConfirmadasDocumento || []).map(normalize);

  const mencionaProvincia =
    fullText.includes(provincia) ||
    provinciasDetectadas.includes(provincia) ||
    provinciasConfirmadas.includes(provincia);

  const revisarAnexo = ['revisar_anexo', 'media_revisar_anexo'].includes(item.precision);

  /*
    Filtro territorial:
    - En modo estricto exigimos provincia visible/confirmada.
    - En modo amplio permitimos revisar más, pero con el JSON actual ya viene bastante limpio.
  */
  if (filters.estricto) {
    if (!mencionaProvincia && !revisarAnexo) return false;
  } else {
    if (provincia && !mencionaProvincia && !revisarAnexo && item.tipo !== 'concurso') {
      return false;
    }
  }

  /*
    Filtro por perfil:
    - Perfil "todos": muestra todo lo que ya viene en alertas.json.
    - Perfil concreto + modo estricto: exige perfil/palabra confirmada.
    - Perfil concreto + modo amplio: permite ver convocatorias de Albacete aunque el BOE no diga
      claramente si son de informática, C1 o administrativo.
  */
  if (filters.perfil !== 'todos') {
    const palabras = perfilPalabras[filters.perfil] || [];
    const perfilDetectado = (item.perfiles || []).map(normalize).includes(filters.perfil);
    const coincidePalabra = palabras.some((word) => fullText.includes(normalize(word)));
    const esConcursoRevisable = item.tipo === 'concurso' && revisarAnexo;

    const esProvinciaDirecta =
      provinciasDetectadas.includes(provincia) ||
      provinciasConfirmadas.includes(provincia) ||
      normalize(item.entidadDetectada || '').includes(provincia) ||
      normalize(item.titulo || '').includes(provincia);

    if (!perfilDetectado && !coincidePalabra && !esConcursoRevisable) {
      if (filters.estricto) {
        return false;
      }

      if (!esProvinciaDirecta) {
        return false;
      }
    }
  }

  if (filters.palabrasExtra.length) {
    const okExtra = filters.palabrasExtra.some((w) => fullText.includes(w));

    if (!okExtra) return false;
  }

  return true;
}

function applyFilters() {
  const filters = getFilters();

  const pool = state.directResults.length
    ? [...state.raw, ...state.directResults]
    : state.raw;

  state.visible = pool.filter((item) => matchesFilters(item, filters));

  state.visible.sort((a, b) => {
    const fechaCompare = (b.fechaPublicacion || '').localeCompare(a.fechaPublicacion || '');

    if (fechaCompare !== 0) return fechaCompare;

    return Number(a.prioridad || 9) - Number(b.prioridad || 9);
  });

  render(filters);
}

function render(filters) {
  $('#metricProvincia').textContent = filters.provincia || 'Todas';
  $('#metricTotal').textContent = state.visible.length;

  $('#metricConcursos').textContent = state.visible.filter((i) => i.tipo === 'concurso').length;

  $('#metricTic').textContent = state.visible.filter((i) => {
    const perfiles = i.perfiles || [];
    const titulo = normalize(i.titulo || '');

    return perfiles.includes('informatica') || titulo.includes('informat') || titulo.includes('tic');
  }).length;

  $('#tituloResultados').textContent =
    `${state.visible.length} alertas entre ${formatHumanDate(filters.desde)} y ${formatHumanDate(filters.hasta)}`;

  renderChips(filters);
  renderCards(state.visible);
}

function renderChips(filters) {
  const perfilTexto = {
    todos: 'Todos los perfiles',
    informatica: 'Informática / TIC C1',
    administrativo: 'Administrativo C1',
    c1a2: 'C1 / C1-A2 / A2'
  };

  const chips = [
    `📍 ${filters.provincia}`,
    `📅 ${formatHumanDate(filters.desde)} → ${formatHumanDate(filters.hasta)}`,
    `🧩 ${perfilTexto[filters.perfil] || filters.perfil}`,
    filters.estricto ? '✅ modo estricto' : '👀 modo amplio',
    ...filters.tipos.map((t) => labelTipo[t] || t)
  ];

  $('#chipsActivos').innerHTML = chips
    .map((c) => `<span class="chip">${escapeHtml(c)}</span>`)
    .join('');
}

function renderCards(items) {
  const container = $('#resultados');

  container.innerHTML = '';
  $('#sinResultados').hidden = items.length > 0;

  const template = $('#cardTemplate');

  for (const item of items) {
    const node = template.content.cloneNode(true);

    const article = node.querySelector('.alert-card');
    const tipo = node.querySelector('.tipo');
    const precision = node.querySelector('.precision');
    const time = node.querySelector('time');
    const h3 = node.querySelector('h3');
    const dept = node.querySelector('.dept');
    const motivo = node.querySelector('.motivo');
    const tags = node.querySelector('.tags');
    const actions = node.querySelector('.card-actions');

    tipo.textContent = labelTipo[item.tipo] || item.tipo || 'Aviso';

    precision.textContent = precisionLabel(item.precision);
    precision.classList.add(precisionClass(item.precision));

    time.dateTime = item.fechaPublicacion || '';
    time.textContent = formatHumanDate(item.fechaPublicacion);

    h3.textContent = item.titulo || 'Sin título';

    dept.textContent = item.departamento
      ? `Departamento / entidad: ${item.departamento}`
      : 'Departamento / entidad no disponible';

    motivo.textContent = item.motivo || 'Resultado detectado por coincidencia de palabras clave.';

    const tagList = [
      ...(item.provinciasDetectadas || []),
      ...(item.provinciasConfirmadasDocumento || []),
      ...(item.perfiles || []),
      item.entidadDetectada,
      item.seccion
    ].filter(Boolean);

    const uniqueTags = [...new Set(tagList)];

    tags.innerHTML = uniqueTags
      .map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`)
      .join('');

    const links = buildLinks(item);

    actions.innerHTML = links
      .map((link) => `<a class="${link.primary ? 'primary-link' : ''}" href="${link.href}" target="_blank" rel="noopener">${link.label}</a>`)
      .join('');

    container.appendChild(article);
  }
}

function precisionLabel(value = '') {
  if (value === 'alta') return 'Alta coincidencia';
  if (value.includes('anexo')) return 'Revisar anexo';
  if (value === 'media') return 'Media coincidencia';
  if (value === 'age_sin_confirmar') return 'AGE sin confirmar';

  return 'Pendiente revisión';
}

function precisionClass(value = '') {
  if (value === 'alta') return 'alta';
  if (value.includes('anexo')) return 'revisar';

  return 'media';
}

function buildLinks(item) {
  const links = [];

  if (item.enlaceBoeHtml) {
    links.push({
      label: 'Abrir disposición BOE',
      href: item.enlaceBoeHtml,
      primary: true
    });
  }

  if (item.enlacePdf) {
    links.push({
      label: 'PDF BOE',
      href: item.enlacePdf
    });
  }

  if (item.enlaceXml) {
    links.push({
      label: 'XML BOE',
      href: item.enlaceXml
    });
  }

  links.push({
    label: 'Sumario del día',
    href: item.enlaceSumario || sumarioUrl(item.fechaPublicacion)
  });

  links.push({
    label: 'API BOE',
    href: item.enlaceApi || apiUrl(item.fechaPublicacion)
  });

  return links;
}

async function loadData() {
  populateProvinces();
  setDefaultDates();

  try {
    const response = await fetch('data/alertas.json', {
      cache: 'no-store'
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const payload = await response.json();

    state.metadata = payload.metadata || {};
    state.raw = Array.isArray(payload.alertas) ? payload.alertas : [];

    $('#ultimaRevision').textContent = state.metadata.lastRun
      ? `${formatHumanDate(state.metadata.lastRun.slice(0, 10))} ${state.metadata.lastRun.slice(11, 16) || ''}`
      : 'Sin revisión automática';

    $('#origenDatos').textContent = `${state.raw.length} alertas cargadas`;
  } catch (error) {
    console.error(error);

    $('#ultimaRevision').textContent = 'No se pudo cargar JSON';
    $('#origenDatos').textContent = 'Revisa data/alertas.json';

    toast('No he podido cargar data/alertas.json. Prueba con servidor local: python -m http.server 8000');
  }

  applyFilters();
}

function populateProvinces() {
  $('#provinciasList').innerHTML = DEFAULT_PROVINCES
    .map((p) => `<option value="${p}"></option>`)
    .join('');
}

function setDefaultDates() {
  const today = todayIso();
  const start = addDays(new Date(), -29).toISOString().slice(0, 10);

  $('#fechaDesde').value = start;
  $('#fechaHasta').value = today;
}

function cleanFilters() {
  $('#provincia').value = 'Albacete';
  $('#perfil').value = 'informatica';
  $('#dias').value = 30;
  $('#fechaExacta').value = '';
  $('#palabrasExtra').value = '';
  $('#modoEstricto').checked = true;

  $$('input[name="tipo"]').forEach((el) => {
    el.checked = true;
  });

  setDefaultDates();
  applyFilters();
}

function openCurrentSumario() {
  const f = $('#fechaExacta').value || $('#fechaDesde').value || $('#fechaHasta').value || todayIso();

  window.open(sumarioUrl(f), '_blank', 'noopener');
}

async function tryDirectApi() {
  const filters = getFilters();
  const dates = enumerateDates(filters.desde, filters.hasta).slice(0, 35);

  $('#apiAviso').textContent = 'Consultando API BOE desde el navegador…';

  state.directResults = [];

  try {
    for (const iso of dates) {
      const xmlText = await fetchBoeXml(iso);
      const items = parseBoeXml(xmlText, iso);

      state.directResults.push(
        ...items
          .map(classifyItem)
          .filter((item) => item.tipo !== 'otros')
      );
    }

    $('#apiAviso').textContent =
      `Consulta directa completada: ${state.directResults.length} posibles avisos leídos. Si no aparece nada, abre el sumario del día.`;

    applyFilters();
  } catch (error) {
    console.error(error);

    $('#apiAviso').textContent =
      'El navegador no ha podido leer directamente la API, normalmente por CORS. El workflow de GitHub Actions sí puede hacerlo y actualizar el JSON.';

    toast('No se pudo consultar la API desde el navegador. Usa el workflow manual de GitHub Actions o abre el sumario BOE.');
  }
}

async function fetchBoeXml(isoDate) {
  const response = await fetch(apiUrl(isoDate), {
    headers: {
      Accept: 'application/xml'
    },
    cache: 'no-store'
  });

  if (!response.ok) {
    throw new Error(`BOE API ${isoDate}: HTTP ${response.status}`);
  }

  return response.text();
}

function parseBoeXml(xmlText, isoDate) {
  const doc = new DOMParser().parseFromString(xmlText, 'application/xml');
  const parserError = doc.querySelector('parsererror');

  if (parserError) {
    throw new Error('XML no válido');
  }

  const items = Array.from(doc.querySelectorAll('item'));

  return items.map((item) => {
    const id = item.getAttribute('id') || textOf(item, 'identificador') || '';
    const titulo = textOf(item, 'titulo') || item.textContent.trim().slice(0, 240);
    const departamento = closestText(item, 'departamento') || textOf(item, 'departamento') || '';
    const seccion = closestSection(item) || '';

    const urlHtm = textOf(item, 'urlHtm') || textOf(item, 'urlHTML') || (id ? `/diario_boe/txt.php?id=${id}` : '');
    const urlPdf = textOf(item, 'urlPdf') || textOf(item, 'urlPDF') || (id ? `/boe/dias/${isoDate.slice(0, 4)}/${isoDate.slice(5, 7)}/${isoDate.slice(8, 10)}/pdfs/${id}.pdf` : '');
    const urlXml = textOf(item, 'urlXml') || textOf(item, 'urlXML') || (id ? `/diario_boe/xml.php?id=${id}` : '');

    return {
      id: id || `${isoDate}-${titulo.slice(0, 60)}`,
      fechaPublicacion: isoDate,
      titulo,
      departamento,
      seccion,
      enlaceBoeHtml: ensureAbsolute(urlHtm),
      enlacePdf: ensureAbsolute(urlPdf),
      enlaceXml: ensureAbsolute(urlXml),
      enlaceSumario: sumarioUrl(isoDate),
      enlaceApi: apiUrl(isoDate)
    };
  });
}

function textOf(root, selector) {
  const node = root.querySelector(selector);

  return node ? node.textContent.trim() : '';
}

function closestText(node, selector) {
  let current = node.parentElement;

  while (current) {
    if (current.matches && current.matches(selector)) {
      return current.getAttribute('nombre') || current.textContent.trim().slice(0, 120);
    }

    current = current.parentElement;
  }

  return '';
}

function closestSection(node) {
  let current = node.parentElement;

  while (current) {
    const tag = normalize(current.tagName || '');

    if (tag.includes('seccion')) {
      return current.getAttribute('num') ||
        current.getAttribute('nombre') ||
        current.getAttribute('codigo') ||
        current.textContent.trim().slice(0, 80);
    }

    current = current.parentElement;
  }

  return '';
}

function hasAnyPattern(full, patterns) {
  return patterns.some((pattern) => pattern.test(full));
}

function simpleSection(value = '') {
  return normalize(value).replace(/[^0-9a-z]/g, '');
}

function classifyItem(item) {
  const full = normalize(`${item.titulo} ${item.departamento} ${item.seccion}`);
  const section = simpleSection(item.seccion || '');

  const provincias = DEFAULT_PROVINCES.filter((p) => {
    return new RegExp(`\\b${normalize(p)}\\b`).test(full);
  });

  const noPersonal = [
    /\bsubvencion(es)?\b/,
    /\bayuda(s)?\b/,
    /\bpremio(s)?\b/,
    /\bconcesion administrativa\b/,
    /\blicitacion\b/,
    /\bcontratacion\b/,
    /\badjudicacion\b/,
    /\bexplotacion\b/,
    /\bquiosco\b/,
    /\bhosteleria\b/,
    /\bvivienda\b/,
    /\btesoro publico\b/,
    /\bsubasta\b/,
    /\bsentencia\b/,
    /\brecurso de amparo\b/,
    /\bcarrera fiscal\b/,
    /\bcarreras judicial y fiscal\b/,
    /\bministerio fiscal\b/,
    /\bletrad[oa]s? de la administracion de justicia\b/
  ];

  const excluirFases = [
    /\bcorreccion(es)? de errores\b/,
    /\brelacion provisional\b/,
    /\brelacion definitiva\b/,
    /\badmitid[oa]s? y excluid[oa]s?\b/,
    /\baspirantes que han superado\b/,
    /\btribunal calificador\b/,
    /\bse resuelve\b/,
    /\bresuelve la convocatoria\b/,
    /\bdeclara desiert[ao]\b/,
    /\bnombra funcionari[oa]\b/,
    /\bnombramiento\b/,
    /\bejecucion de sentencia\b/,
    /\bemplaza\b/
  ];

  const apertura = [
    /\bse convoca\b/,
    /\bconvoca\b/,
    /\bconvocatoria para proveer\b/,
    /\breferente a la convocatoria para proveer\b/,
    /\bpruebas selectivas para ingreso\b/,
    /\bproceso selectivo para ingreso\b/,
    /\bprovision de puesto(s)? de trabajo\b/
  ];

  let tipo = 'otros';

  if (/\bcomision de servicio(s)?\b/.test(full)) {
    tipo = 'comision_servicio';
  } else if (/\blibre designacion\b/.test(full)) {
    tipo = 'libre_designacion';
  } else if (
    /\bconcurso general\b/.test(full) ||
    /\bconcurso especifico\b/.test(full) ||
    /\bconcurso de traslados\b/.test(full) ||
    (/\bconcurso\b/.test(full) && /\bpuesto(s)? de trabajo\b/.test(full))
  ) {
    tipo = 'concurso';
  } else if (
    /\boposicion\b|\bpruebas selectivas\b|\bproceso selectivo\b|\bconvocatoria para proveer\b|\bbolsa de trabajo\b/.test(full)
  ) {
    tipo = 'oposicion';
  }

  const entidad = detectEntidad(full);

  /*
    Consulta directa desde navegador:
    No puede confirmar el documento completo como hace GitHub Actions.
    Por eso no generamos concursos AGE genéricos sin provincia confirmada.
  */
  const tieneProvinciaOEntidad =
    provincias.length > 0 ||
    Boolean(entidad);

  if (section !== '2b' || tipo === 'otros' || hasAnyPattern(full, noPersonal)) {
    return {
      ...item,
      tipo: 'otros',
      perfiles: [],
      provinciasDetectadas: provincias,
      provinciasConfirmadasDocumento: [],
      entidadDetectada: entidad,
      precision: 'descartado',
      motivo: 'Descartado por filtro fino.'
    };
  }

  if (hasAnyPattern(full, excluirFases) || !hasAnyPattern(full, apertura)) {
    return {
      ...item,
      tipo: 'otros',
      perfiles: [],
      provinciasDetectadas: provincias,
      provinciasConfirmadasDocumento: [],
      entidadDetectada: entidad,
      precision: 'descartado',
      motivo: 'Descartado por no ser convocatoria/provisión inicial.'
    };
  }

  if (!tieneProvinciaOEntidad) {
    return {
      ...item,
      tipo: 'otros',
      perfiles: [],
      provinciasDetectadas: provincias,
      provinciasConfirmadasDocumento: [],
      entidadDetectada: entidad,
      precision: 'descartado',
      motivo: 'Descartado en consulta directa porque no hay provincia/entidad confirmada.'
    };
  }

  const perfiles = [];

  const perfilRegex = {
    informatica: [
      /\binformatica\b/,
      /\binformatic[oa]s?\b/,
      /\btecnologias? de la informacion\b/,
      /\btic\b/,
      /\bsistemas informaticos\b/,
      /\badministracion de sistemas\b/,
      /\bmicroinformatica\b/,
      /\bprogramador(a|es)?\b/,
      /\bofimatica\b/
    ],
    administrativo: [
      /\bcuerpo administrativo\b/,
      /\bescala administrativa\b/,
      /\bauxiliar administrativo\b/,
      /\bgestion administrativa\b/,
      /\bplaza(s)? de administrativo\b/,
      /\badministrativos?\b/
    ],
    c1a2: [
      /\bc1\b/,
      /\ba2\b/,
      /\bc1\/a2\b/,
      /\bc1-a2\b/,
      /\bsubgrupo c1\b/,
      /\bsubgrupo a2\b/,
      /\bnivel 1[6-9]\b/,
      /\bnivel 2[0-2]\b/
    ]
  };

  for (const [perfil, patterns] of Object.entries(perfilRegex)) {
    if (hasAnyPattern(full, patterns)) {
      perfiles.push(perfil);
    }
  }

  const precision = provincias.length || entidad ? 'alta' : 'media';

  const motivo = 'Coincidencia detectada en una convocatoria/provisión de personal de la Sección II.B.';

  return {
    ...item,
    tipo,
    perfiles,
    provinciasDetectadas: provincias,
    provinciasConfirmadasDocumento: provincias,
    entidadDetectada: entidad,
    precision,
    prioridad: precision === 'alta' ? 1 : 3,
    motivo,
    tags: [...new Set([...perfiles, ...provincias, entidad, tipo].filter(Boolean))]
  };
}

function detectEntidad(full) {
  if (full.includes('ayuntamiento de albacete')) {
    return 'Ayuntamiento de Albacete';
  }

  if (full.includes('diputacion provincial de albacete') || full.includes('diputacion de albacete')) {
    return 'Diputación de Albacete';
  }

  if (full.includes('castilla-la mancha') || full.includes('castilla la mancha') || full.includes('junta de comunidades')) {
    return 'Castilla-La Mancha';
  }

  if (full.includes('servicio publico de empleo estatal') || /\bsepe\b/.test(full)) {
    return 'SEPE';
  }

  if (full.includes('administracion general del estado')) {
    return 'AGE';
  }

  return '';
}

function enumerateDates(desde, hasta) {
  const out = [];

  let d = new Date(`${desde}T00:00:00`);
  const end = new Date(`${hasta}T00:00:00`);

  while (d <= end) {
    out.push(d.toISOString().slice(0, 10));
    d.setDate(d.getDate() + 1);
  }

  return out;
}

function exportCsv() {
  const headers = [
    'fecha',
    'tipo',
    'precision',
    'titulo',
    'departamento',
    'provincias',
    'provincias_confirmadas_documento',
    'perfiles',
    'enlace_boe',
    'pdf',
    'sumario'
  ];

  const rows = state.visible.map((item) => [
    item.fechaPublicacion,
    labelTipo[item.tipo] || item.tipo,
    precisionLabel(item.precision),
    item.titulo,
    item.departamento,
    (item.provinciasDetectadas || []).join('|'),
    (item.provinciasConfirmadasDocumento || []).join('|'),
    (item.perfiles || []).join('|'),
    item.enlaceBoeHtml,
    item.enlacePdf,
    item.enlaceSumario
  ]);

  const csv = [headers, ...rows]
    .map((row) => row.map(csvCell).join(';'))
    .join('\n');

  downloadBlob(csv, `alertas-boe-${todayIso()}.csv`, 'text/csv;charset=utf-8');
}

function copyLinks() {
  const text = state.visible
    .map((item) => `${item.fechaPublicacion} · ${item.titulo}\n${item.enlaceBoeHtml || item.enlaceSumario}`)
    .join('\n\n');

  navigator.clipboard.writeText(text || 'Sin resultados')
    .then(() => toast('Enlaces copiados al portapapeles.'));
}

function csvCell(value = '') {
  const safe = String(value).replaceAll('"', '""');

  return `"${safe}"`;
}

function downloadBlob(content, filename, type) {
  const blob = new Blob([content], { type });

  const a = document.createElement('a');

  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();

  URL.revokeObjectURL(a.href);
}

function escapeHtml(value = '') {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function toast(message) {
  const box = document.createElement('div');

  box.className = 'toast';
  box.textContent = message;

  document.body.appendChild(box);

  setTimeout(() => box.remove(), 4200);
}

async function enableNotifications() {
  if (!('Notification' in window)) {
    toast('Tu navegador no permite notificaciones web.');
    return;
  }

  const permission = await Notification.requestPermission();

  if (permission === 'granted') {
    toast('Notificaciones activadas mientras tengas la web abierta.');

    if (state.visible.length) {
      new Notification('BOE Alertas C1', {
        body: `Tienes ${state.visible.length} alertas visibles con los filtros actuales.`
      });
    }
  } else {
    toast('No se han concedido permisos de notificación.');
  }
}

$('#filtrosForm').addEventListener('submit', (event) => {
  event.preventDefault();
  applyFilters();
});

$('#fechaExacta').addEventListener('change', () => {
  const v = $('#fechaExacta').value;

  if (v) {
    $('#fechaDesde').value = v;
    $('#fechaHasta').value = v;
  }
});

$('#btnLimpiar').addEventListener('click', cleanFilters);
$('#btnExportar').addEventListener('click', exportCsv);
$('#btnCopiar').addEventListener('click', copyLinks);
$('#btnAbrirSumario').addEventListener('click', openCurrentSumario);
$('#btnConsultarApi').addEventListener('click', tryDirectApi);
$('#btnNotificaciones').addEventListener('click', enableNotifications);

loadData();
