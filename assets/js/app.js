const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const MODULES = {
  concursos: {
    icon: '🏛️',
    eyebrow: '1. Concursos',
    title: 'Concursos AGE con Albacete confirmado',
    description: 'Pensado para concursos generales o específicos de la AGE donde el documento BOE contiene Albacete. Aquí están los filtros más importantes: nivel, grupo y perfil.',
    notice: 'Filtro principal: concursos de provisión de puestos. Por defecto solo se muestran documentos donde aparece Albacete. Revisa siempre el PDF/anexo para confirmar puesto, localidad, nivel, cuerpo y méritos.',
    tipos: ['concurso'],
    defaultPerfil: 'informatica',
    strict: true
  },
  movilidad: {
    icon: '🔁',
    eyebrow: '2. Movilidad',
    title: 'Libres designaciones y comisiones de servicio',
    description: 'Avisos de libre designación o comisiones con Albacete/CLM detectado. Puedes filtrar por nivel, grupo y perfil para localizar puestos C1 o C1/A2.',
    notice: 'En libre designación y comisiones, comprueba siempre requisitos, nivel, adscripción y plazo en el BOE o en la sede indicada. Si no aparece enlace de inscripción, abre la disposición BOE.',
    tipos: ['libre_designacion', 'comision_servicio'],
    defaultPerfil: 'todos',
    strict: true
  },
  oposiciones: {
    icon: '📝',
    eyebrow: '3. Oposiciones',
    title: 'Oposiciones Junta, SESCAM, UCLM, Diputación y Ayuntamiento',
    description: 'Bloque centrado en convocatorias de Castilla-La Mancha, especialmente Diputación de Albacete y Ayuntamiento de Albacete. El BOE puede no indicar el perfil completo; abre bases e inscripción.',
    notice: 'En convocatorias locales el BOE suele ser un anuncio breve. Para saber si es informática C1, revisa bases, BOP/DOCM y portal de inscripción. Modo estricto filtra por perfil confirmado; modo amplio muestra convocatorias revisables de Albacete/CLM.',
    tipos: ['oposicion'],
    defaultPerfil: 'informatica',
    strict: false
  }
};

const PROVINCES = ['Albacete','Alicante','Almería','Ávila','Badajoz','Barcelona','Burgos','Cáceres','Cádiz','Castellón','Ciudad Real','Córdoba','Cuenca','Girona','Granada','Guadalajara','Huelva','Huesca','Jaén','León','Lleida','La Rioja','Lugo','Madrid','Málaga','Murcia','Ourense','Palencia','Pontevedra','Salamanca','Segovia','Sevilla','Soria','Tarragona','Teruel','Toledo','Valencia','Valladolid','Zamora','Zaragoza','Ceuta','Melilla'];

const OFFICIAL_LINKS = {
  concursos: [
    ['BOE sumarios', 'https://www.boe.es/boe/dias/', 'Consulta manual por fecha'],
    ['Administración.gob', 'https://administracion.gob.es/pag_Home/empleoPublico.html', 'Empleo público AGE'],
    ['RSS BOE II.B', 'https://www.boe.es/rss/', 'Canales oficiales BOE']
  ],
  movilidad: [
    ['BOE sumarios', 'https://www.boe.es/boe/dias/', 'Libre designación y provisión'],
    ['Administración.gob', 'https://administracion.gob.es/pag_Home/empleoPublico.html', 'Empleo público AGE'],
    ['RSS BOE', 'https://www.boe.es/rss/', 'Seguimiento oficial']
  ],
  oposiciones: [
    ['Ayuntamiento Albacete', 'https://www.albacete.es/es/tu-ayuntamiento/empleo-publico', 'Empleo público municipal'],
    ['Diputación Albacete', 'https://aplicaciones.dipualba.es/empleopublico/', 'Convocatorias e instancia'],
    ['JCCM procesos', 'https://empleopublico.castillalamancha.es/procesos-selectivos', 'Procesos selectivos CLM'],
    ['SESCAM', 'https://sescam.castillalamancha.es/', 'Recursos humanos SESCAM'],
    ['UCLM convocatorias', 'https://convocatorias.rrhh.uclm.es/', 'PTGAS y otros procesos'],
    ['BOE sumarios', 'https://www.boe.es/boe/dias/', 'Anuncios BOE']
  ]
};

const PROFILE_WORDS = {
  informatica: ['informatica','informático','informatico','tecnologias de la informacion','tecnologías de la información','tic','sistemas','administracion de sistemas','microinformatica','programador','ofimatica','técnico auxiliar de informática','tecnico auxiliar de informatica'],
  administrativo: ['administrativo','administrativa','cuerpo administrativo','escala administrativa','auxiliar administrativo','gestion administrativa'],
  c1a2: ['c1','a2','c1/a2','c1-a2','subgrupo c1','subgrupo a2','nivel 16','nivel 17','nivel 18','nivel 19','nivel 20','nivel 21','nivel 22']
};

const state = { raw: [], visible: [], module: null, metadata: {} };

function norm(text = '') {
  return String(text).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
}
function humanDate(iso) {
  if (!iso) return 'Sin fecha';
  const [y, m, d] = iso.slice(0, 10).split('-');
  return d && m && y ? `${d}/${m}/${y}` : iso;
}
function todayIso() { return new Date().toISOString().slice(0, 10); }
function addDays(date, days) { const d = new Date(date); d.setDate(d.getDate() + days); return d; }
function escapeHtml(v = '') { return String(v).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#039;'); }

function init() {
  $('#provinciasList').innerHTML = PROVINCES.map((p) => `<option value="${p}"></option>`).join('');
  populateLevels();
  setDefaultDates();
  bindEvents();
  loadData();
}

function bindEvents() {
  $$('.choice-card').forEach((button) => button.addEventListener('click', () => selectModule(button.dataset.module)));
  $('#btnBack').addEventListener('click', backToLanding);
  $('#filtersForm').addEventListener('submit', (event) => { event.preventDefault(); applyFilters(); });
  $('#btnReset').addEventListener('click', resetCurrentModule);
  $('#btnExport').addEventListener('click', exportCsv);
  $('#btnCopy').addEventListener('click', copyLinks);
  $('#fechaExacta').addEventListener('change', () => { const v = $('#fechaExacta').value; if (v) { $('#fechaDesde').value = v; $('#fechaHasta').value = v; } });
  $('#btnNotify').addEventListener('click', enableNotifications);
}

function populateLevels() {
  const levels = ['todos', ...Array.from({length: 15}, (_, i) => String(i + 16))];
  $('#nivelMin').innerHTML = levels.map((n) => `<option value="${n}" ${n === '16' ? 'selected' : ''}>${n === 'todos' ? 'Todos' : n}</option>`).join('');
  $('#nivelMax').innerHTML = levels.map((n) => `<option value="${n}" ${n === '30' ? 'selected' : ''}>${n === 'todos' ? 'Todos' : n}</option>`).join('');
}

function setDefaultDates() {
  const end = todayIso();
  const start = addDays(new Date(), -29).toISOString().slice(0, 10);
  $('#fechaDesde').value = start;
  $('#fechaHasta').value = end;
}

async function loadData() {
  try {
    const response = await fetch('data/alertas.json', { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    state.metadata = payload.metadata || {};
    state.raw = Array.isArray(payload.alertas) ? payload.alertas : [];
    $('#statTotal').textContent = state.raw.length;
    $('#statLastRun').textContent = state.metadata.lastRun ? `${humanDate(state.metadata.lastRun.slice(0,10))} ${state.metadata.lastRun.slice(11,16)}` : 'Sin revisión';
    $('#statProvince').textContent = (state.metadata.provinciasVigiladas || ['Albacete']).join(', ');
  } catch (error) {
    console.error(error);
    toast('No se ha podido cargar data/alertas.json. Sube el JSON o ejecuta el workflow.');
  }
}

function selectModule(moduleName) {
  state.module = moduleName;
  document.body.classList.toggle('module-oposiciones', moduleName === 'oposiciones');
  const module = MODULES[moduleName];
  $('#panel').hidden = false;
  $('#panel').scrollIntoView({ behavior: 'smooth', block: 'start' });
  $('#moduleIcon').textContent = module.icon;
  $('#moduleEyebrow').textContent = module.eyebrow;
  $('#moduleTitle').textContent = module.title;
  $('#moduleDescription').textContent = module.description;
  $('#moduleNotice').textContent = module.notice;
  $('#filtersTitle').textContent = moduleName === 'concursos' ? 'Concursos AGE por nivel y perfil' : moduleName === 'movilidad' ? 'Libres designaciones / comisiones' : 'Oposiciones y convocatorias';
  $('#perfil').value = module.defaultPerfil;
  $('#modoEstricto').checked = module.strict;
  renderOfficialLinks(moduleName);
  applyFilters();
}

function backToLanding() {
  state.module = null;
  $('#panel').hidden = true;
  document.body.classList.remove('module-oposiciones');
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function resetCurrentModule() {
  const module = MODULES[state.module || 'concursos'];
  $('#provincia').value = 'Albacete';
  $('#dias').value = 30;
  $('#fechaExacta').value = '';
  setDefaultDates();
  $('#nivelMin').value = '16';
  $('#nivelMax').value = '30';
  $('#grupo').value = state.module === 'oposiciones' ? 'todos' : 'c1';
  $('#perfil').value = module.defaultPerfil;
  $('#modoEstricto').checked = module.strict;
  $('#palabrasExtra').value = '';
  applyFilters();
}

function getFilters() {
  if ($('#fechaExacta').value) {
    $('#fechaDesde').value = $('#fechaExacta').value;
    $('#fechaHasta').value = $('#fechaExacta').value;
  }
  let desde = $('#fechaDesde').value;
  let hasta = $('#fechaHasta').value;
  if (!desde && !hasta) {
    const days = Number($('#dias').value || 30);
    hasta = todayIso();
    desde = addDays(new Date(), -Math.max(0, days - 1)).toISOString().slice(0, 10);
  }
  if (desde && !hasta) hasta = desde;
  if (hasta && !desde) desde = hasta;
  if (desde > hasta) [desde, hasta] = [hasta, desde];
  return {
    module: state.module,
    provincia: $('#provincia').value.trim() || 'Albacete',
    desde,
    hasta,
    nivelMin: $('#nivelMin').value,
    nivelMax: $('#nivelMax').value,
    grupo: $('#grupo').value,
    perfil: $('#perfil').value,
    estricto: $('#modoEstricto').checked,
    extra: $('#palabrasExtra').value.split(',').map((x) => norm(x.trim())).filter(Boolean)
  };
}

function applyFilters() {
  if (!state.module) return;
  const filters = getFilters();
  state.visible = state.raw.filter((item) => matchesModule(item, filters)).filter((item) => matchesFilters(item, filters));
  state.visible.sort((a, b) => (b.fechaPublicacion || '').localeCompare(a.fechaPublicacion || '') || Number(a.prioridad || 9) - Number(b.prioridad || 9));
  render(filters);
}

function matchesModule(item, filters) {
  const tipo = item.tipo || 'otros';
  if (filters.module === 'concursos') return tipo === 'concurso';
  if (filters.module === 'movilidad') return ['libre_designacion', 'comision_servicio'].includes(tipo);
  if (filters.module === 'oposiciones') return tipo === 'oposicion';
  return false;
}

function itemText(item) {
  return norm([
    item.titulo,
    item.departamento,
    item.epigrafe,
    item.seccion,
    item.entidadDetectada,
    item.motivo,
    item.plazoInscripcion,
    item.localidad,
    item.grupoDetectado,
    ...(item.tags || []),
    ...(item.perfiles || []),
    ...(item.provinciasDetectadas || []),
    ...(item.provinciasConfirmadasDocumento || []),
    ...(item.nivelesDetectados || [])
  ].join(' '));
}

function matchesFilters(item, filters) {
  const date = item.fechaPublicacion || '';
  if (filters.desde && date < filters.desde) return false;
  if (filters.hasta && date > filters.hasta) return false;

  const full = itemText(item);
  const province = norm(filters.provincia);
  const provinces = [...(item.provinciasDetectadas || []), ...(item.provinciasConfirmadasDocumento || [])].map(norm);
  const hasProvince = provinces.includes(province) || full.includes(province);
  if (filters.estricto && !hasProvince) return false;

  if (filters.module !== 'oposiciones') {
    const levels = (item.nivelesDetectados || []).map(Number).filter(Boolean);
    if (filters.nivelMin !== 'todos' && levels.length && !levels.some((n) => n >= Number(filters.nivelMin))) return false;
    if (filters.nivelMax !== 'todos' && levels.length && !levels.some((n) => n <= Number(filters.nivelMax))) return false;
    if (filters.grupo !== 'todos') {
      const groupText = norm(item.grupoDetectado || '') + ' ' + full;
      const okGroup = filters.grupo === 'c1a2'
        ? (groupText.includes('c1') || groupText.includes('a2'))
        : groupText.includes(filters.grupo);
      if (filters.estricto && !okGroup) return false;
    }
  }

  if (filters.perfil !== 'todos') {
    const perfiles = (item.perfiles || []).map(norm);
    const words = PROFILE_WORDS[filters.perfil] || [];
    const okPerfil = perfiles.includes(filters.perfil) || words.some((w) => full.includes(norm(w)));
    if (filters.estricto && !okPerfil) return false;
  }

  if (filters.extra.length && !filters.extra.some((w) => full.includes(w))) return false;

  if (filters.module === 'oposiciones') {
    const entity = norm(item.entidadDetectada || '') + ' ' + full;
    const wanted = ['ayuntamiento de albacete','diputacion de albacete','diputacion provincial de albacete','castilla-la mancha','castilla la mancha','junta de comunidades','sescam','servicio de salud de castilla-la mancha','uclm','universidad de castilla-la mancha'];
    if (filters.estricto && !wanted.some((w) => entity.includes(w))) return false;
  }

  return true;
}

function render(filters) {
  const module = MODULES[state.module];
  $('#moduleCount').textContent = state.visible.length;
  $('#resultTitle').textContent = `${state.visible.length} resultados entre ${humanDate(filters.desde)} y ${humanDate(filters.hasta)}`;
  renderChips(filters, module);
  renderCards(state.visible);
}

function renderChips(filters, module) {
  const labels = [`${module.icon} ${module.title}`, `📍 ${filters.provincia}`, `📅 ${humanDate(filters.desde)} → ${humanDate(filters.hasta)}`, filters.estricto ? '✅ estricto' : '👀 amplio'];
  if (filters.module !== 'oposiciones') labels.push(`Nivel ${filters.nivelMin}–${filters.nivelMax}`, `Grupo ${filters.grupo.toUpperCase()}`);
  labels.push(`Perfil: ${filters.perfil}`);
  $('#activeChips').innerHTML = labels.map((x) => `<span class="chip">${escapeHtml(x)}</span>`).join('');
}

function renderCards(items) {
  const container = $('#results');
  container.innerHTML = '';
  $('#emptyState').hidden = items.length > 0;
  const template = $('#resultTemplate');
  for (const item of items) {
    const node = template.content.cloneNode(true);
    node.querySelector('time').textContent = humanDate(item.fechaPublicacion);
    node.querySelector('time').dateTime = item.fechaPublicacion || '';
    node.querySelector('h3').textContent = item.titulo || 'Sin título';
    node.querySelector('.meta').textContent = buildMeta(item);
    node.querySelector('.reason').textContent = item.motivo || 'Aviso detectado por filtros BOE.';
    node.querySelector('.badges').innerHTML = buildBadges(item);
    node.querySelector('.detail-grid').innerHTML = buildDetails(item);
    node.querySelector('.tags').innerHTML = buildTags(item);
    node.querySelector('.card-actions').innerHTML = buildActions(item);
    container.appendChild(node);
  }
}

function buildMeta(item) {
  const parts = [];
  if (item.entidadDetectada) parts.push(item.entidadDetectada);
  if (item.departamento) parts.push(`Departamento: ${item.departamento}`);
  if (item.seccion) parts.push(`Sección: ${item.seccion}`);
  return parts.join(' · ') || 'Entidad no disponible';
}

function labelTipo(tipo) {
  return { concurso: 'Concurso', libre_designacion: 'Libre designación', comision_servicio: 'Comisión', oposicion: 'Oposición' }[tipo] || 'Aviso';
}
function buildBadges(item) {
  const badges = [`<span class="badge primary">${escapeHtml(labelTipo(item.tipo))}</span>`];
  if (item.precision === 'alta') badges.push('<span class="badge ok">Albacete confirmado</span>');
  if ((item.precision || '').includes('anexo')) badges.push('<span class="badge warn">Revisar anexo</span>');
  if (item.plazoInscripcion) badges.push('<span class="badge pink">Plazo detectado</span>');
  return badges.join('');
}
function buildDetails(item) {
  const niveles = (item.nivelesDetectados || []).join(', ') || 'No detectado';
  const grupo = item.grupoDetectado || 'No detectado';
  const provincia = [...new Set([...(item.provinciasDetectadas || []), ...(item.provinciasConfirmadasDocumento || [])])].join(', ') || 'No visible';
  const plazo = item.plazoInscripcion || 'No detectado en BOE';
  return [
    ['Provincia', provincia], ['Nivel', niveles], ['Grupo', grupo], ['Plazo', plazo]
  ].map(([k,v]) => `<div class="detail"><span>${escapeHtml(k)}</span><strong>${escapeHtml(v)}</strong></div>`).join('');
}
function buildTags(item) {
  const tags = [...new Set([...(item.tags || []), ...(item.perfiles || []), ...(item.nivelesDetectados || []).map((n) => `nivel ${n}`)].filter(Boolean))];
  return tags.map((t) => `<span class="tag">${escapeHtml(t)}</span>`).join('');
}
function buildActions(item) {
  const links = [];
  if (item.enlaceInscripcion) links.push(['Inscripción / bases', item.enlaceInscripcion, 'success']);
  if (item.enlaceBoeHtml) links.push(['Abrir BOE', item.enlaceBoeHtml, 'main']);
  if (item.enlacePdf) links.push(['PDF', item.enlacePdf, '']);
  if (item.enlaceXml) links.push(['XML', item.enlaceXml, '']);
  if (item.enlaceSumario) links.push(['Sumario', item.enlaceSumario, '']);
  return links.map(([label, href, cls]) => `<a class="${cls}" href="${href}" target="_blank" rel="noopener">${label}</a>`).join('');
}

function renderOfficialLinks(moduleName) {
  const links = OFFICIAL_LINKS[moduleName] || [];
  $('#officialGrid').innerHTML = links.map(([label, url, text]) => `<a href="${url}" target="_blank" rel="noopener">${escapeHtml(label)}<small>${escapeHtml(text)}</small></a>`).join('');
}

function exportCsv() {
  const headers = ['fecha','modulo','tipo','titulo','entidad','provincia','nivel','grupo','plazo','inscripcion','boe','pdf'];
  const rows = state.visible.map((i) => [i.fechaPublicacion,state.module,i.tipo,i.titulo,i.entidadDetectada,(i.provinciasDetectadas||[]).join('|'),(i.nivelesDetectados||[]).join('|'),i.grupoDetectado,i.plazoInscripcion,i.enlaceInscripcion,i.enlaceBoeHtml,i.enlacePdf]);
  const csv = [headers, ...rows].map((row) => row.map((v='') => `"${String(v).replaceAll('"','""')}"`).join(';')).join('\n');
  const blob = new Blob([csv], {type:'text/csv;charset=utf-8'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `radar-boe-${state.module || 'alertas'}-${todayIso()}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}
function copyLinks() {
  const text = state.visible.map((i) => `${i.fechaPublicacion} · ${i.titulo}\n${i.enlaceInscripcion || i.enlaceBoeHtml || i.enlacePdf}`).join('\n\n');
  navigator.clipboard.writeText(text || 'Sin resultados').then(() => toast('Enlaces copiados.'));
}
async function enableNotifications() {
  if (!('Notification' in window)) return toast('Este navegador no admite notificaciones.');
  const permission = await Notification.requestPermission();
  if (permission === 'granted') {
    toast('Notificaciones activadas mientras la web esté abierta.');
    if (state.visible.length) new Notification('Radar BOE', { body: `${state.visible.length} alertas visibles.` });
  } else toast('No se han concedido permisos.');
}
function toast(message) {
  const el = document.createElement('div');
  el.className = 'toast';
  el.textContent = message;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 4200);
}

init();
