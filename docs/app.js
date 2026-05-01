let data = null;
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
