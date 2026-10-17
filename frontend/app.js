/* AyT Proyectos — interfaz de diseño sobre mapa (prototipo etapa 1). */
"use strict";

const api = async (metodo, ruta, cuerpo) => {
  const r = await fetch(ruta, {
    method: metodo,
    headers: cuerpo ? { "Content-Type": "application/json" } : {},
    body: cuerpo ? JSON.stringify(cuerpo) : undefined,
  });
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch (_) { /* sin cuerpo */ }
    throw new Error(msg);
  }
  return r.json();
};

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (n, d = 0) => (n == null ? "—" : Number(n).toLocaleString("es-AR", { maximumFractionDigits: d, minimumFractionDigits: d }));
const uid = (p) => `${p}-${Math.random().toString(16).slice(2, 10)}`;

const ETIQUETAS_PARAM = {
  seccion_mm2: "Sección cable de energía (mm²)",
  tension_v: "Tensión de alimentación (V)",
  limite_caida_pct: "Caída de tensión máxima (%)",
  rho_cobre: "Resistividad cobre (Ω·mm²/m)",
  dias_grabacion: "Días de grabación",
  dist_min_camara_m: "Zona ciega bajo cámara (m)",
  reserva_utp_m: "Reserva UTP por cámara (m)",
  limite_utp_m: "Largo máximo UTP (m)",
  factor_fo: "Factor de fibra (recorrido)",
  reserva_fo_por_gabinete_m: "Reserva de fibra por gabinete (m)",
  factor_energia: "Factor de cable de energía",
  margen_ups: "Margen de UPS",
  angulo_quiebre: "Giro para considerar esquina (°)",
};

const estado = {
  proyecto: null,
  catalogo: {},
  defaults: {},
  herramienta: null,
  seleccion: null,
  calculo: null,
  guardando: null,
};

// --------------------------------------------------------------------------- mapa

const mapa = L.map("mapa", { zoomControl: true, maxZoom: 21 }).setView([-32.95, -60.75], 15);
const bases = {
  "Satelital": L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
    maxZoom: 21, maxNativeZoom: 19, attribution: "Imágenes © Esri, Maxar, Earthstar Geographics",
  }),
  "Calles": L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 21, maxNativeZoom: 19, attribution: "© OpenStreetMap",
  }),
};
const etiquetas = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}", {
  maxZoom: 21, maxNativeZoom: 19,
});
bases["Satelital"].addTo(mapa);
etiquetas.addTo(mapa);
L.control.layers(bases, { "Nombres": etiquetas }).addTo(mapa);
L.control.scale({ imperial: false, maxWidth: 160 }).addTo(mapa);
mapa.pm.setLang("es");
mapa.pm.setGlobalOptions({ snappable: true, snapDistance: 15 });

const capaPerimetros = L.featureGroup().addTo(mapa);
const capaSectores = L.layerGroup().addTo(mapa);
const capaHuecos = L.layerGroup().addTo(mapa);
const capaRed = L.layerGroup().addTo(mapa);
const capaPuntos = L.layerGroup().addTo(mapa);

// Punto destino desde un origen, rumbo (°) y distancia (m). Suficiente para radios de cientos de metros.
function destino(lat, lon, rumbo, d) {
  const R = 6371008.8, b = (rumbo * Math.PI) / 180;
  return [lat + ((d * Math.cos(b)) / R) * (180 / Math.PI), lon + ((d * Math.sin(b)) / (R * Math.cos((lat * Math.PI) / 180))) * (180 / Math.PI)];
}

function sector(lat, lon, az, hfov, r, rmin) {
  if (hfov >= 360) return null;
  const pts = [], pasos = Math.max(8, Math.round(hfov / 4));
  for (let i = 0; i <= pasos; i++) pts.push(destino(lat, lon, az - hfov / 2 + (hfov * i) / pasos, r));
  for (let i = pasos; i >= 0; i--) pts.push(destino(lat, lon, az - hfov / 2 + (hfov * i) / pasos, rmin));
  return pts;
}

// --------------------------------------------------------------------------- elementos

const elementos = () => estado.proyecto?.elementos || [];
const porTipo = (t) => elementos().filter((f) => f.properties.tipo === t);
const buscar = (id) => elementos().find((f) => f.id === id);
const param = (k) => estado.proyecto?.parametros?.[k] ?? estado.defaults[k];

function iconoPara(f) {
  const t = f.properties.tipo, sel = estado.seleccion === f.id ? " sel" : "";
  if (t === "camara") {
    const m = estado.catalogo[f.properties.modelo] || {};
    const clase = m.tipo === "ptz" ? " ptz" : m.tipo === "lpr" ? " lpr" : "";
    return L.divIcon({ className: "", html: `<div class="icono-elemento icono-camara${clase}${sel}" style="width:14px;height:14px"></div>`, iconSize: [14, 14] });
  }
  const txt = { gabinete: "G", central: "R", ups: "U" }[t];
  const tam = t === "central" ? 22 : 18;
  return L.divIcon({ className: "", html: `<div class="icono-elemento icono-${t}${sel}" style="width:${tam}px;height:${tam}px">${txt}</div>`, iconSize: [tam, tam] });
}

function dibujar() {
  capaPerimetros.clearLayers();
  capaSectores.clearLayers();
  capaPuntos.clearLayers();
  capaRed.clearLayers();
  const verCob = $("#chk-coberturas").checked;

  for (const f of porTipo("perimetro")) {
    const latlngs = (f.geometry.type === "Polygon" ? f.geometry.coordinates[0] : f.geometry.coordinates).map(([lon, lat]) => [lat, lon]);
    const sel = estado.seleccion === f.id;
    const estilo = { color: sel ? "#ffeb3b" : "#ffffff", weight: sel ? 4 : 3, fill: false, dashArray: "6 4" };
    const capa = f.geometry.type === "Polygon" ? L.polygon(latlngs.slice(0, -1), estilo) : L.polyline(latlngs, estilo);
    capa.feature_id = f.id;
    capa.on("click", (e) => { L.DomEvent.stopPropagation(e); seleccionar(f.id); });
    capa.on("pm:edit", () => {
      const gj = capa.toGeoJSON().geometry;
      f.geometry = gj;
      cambio();
    });
    capa.addTo(capaPerimetros);
    if (sel && estado.editandoVertices) capa.pm.enable({ allowSelfIntersection: false });
  }

  // vínculos cámara-gabinete
  const gabs = Object.fromEntries(porTipo("gabinete").map((g) => [g.id, g]));
  for (const c of porTipo("camara")) {
    const g = gabs[c.properties.gabinete];
    if (!g) continue;
    L.polyline([[c.geometry.coordinates[1], c.geometry.coordinates[0]], [g.geometry.coordinates[1], g.geometry.coordinates[0]]],
      { color: "#ce93d8", weight: 1, opacity: 0.7, interactive: false }).addTo(capaRed);
  }

  for (const f of elementos()) {
    if (f.geometry.type !== "Point") continue;
    const [lon, lat] = f.geometry.coordinates;
    if (f.properties.tipo === "camara" && verCob) {
      const m = estado.catalogo[f.properties.modelo];
      if (m) {
        const r = Number(f.properties.alcance) || m.alcance_analitica_m;
        const color = m.tipo === "ptz" ? "#26a69a" : m.tipo === "lpr" ? "#a1887f" : "#42a5f5";
        const pts = sector(lat, lon, Number(f.properties.azimut) || 0, m.hfov, r, param("dist_min_camara_m"));
        const opciones = { color, weight: 1, fillOpacity: 0.18, interactive: false };
        (pts ? L.polygon(pts, opciones) : L.circle([lat, lon], { ...opciones, radius: r, dashArray: "4 4" })).addTo(capaSectores);
      }
    }
    const mk = L.marker([lat, lon], { icon: iconoPara(f), draggable: true, title: f.properties.nombre || f.properties.tipo });
    mk.on("click", (e) => { L.DomEvent.stopPropagation(e); seleccionar(f.id); });
    mk.on("dragend", () => {
      const p = mk.getLatLng();
      f.geometry.coordinates = [round7(p.lng), round7(p.lat)];
      delete f.properties.auto;
      cambio();
    });
    mk.addTo(capaPuntos);
  }
  dibujarHuecos();
}

function dibujarHuecos() {
  capaHuecos.clearLayers();
  if (!$("#chk-huecos").checked || !estado.calculo) return;
  for (const h of estado.calculo.cobertura.huecos) {
    L.polyline(h.coords.map(([lon, lat]) => [lat, lon]), { color: "#ff1744", weight: 7, opacity: 0.85 })
      .bindTooltip(`Sin cobertura: ${fmt(h.largo_m)} m`)
      .addTo(capaHuecos);
  }
}

const round7 = (v) => Math.round(v * 1e7) / 1e7;

function seleccionar(id) {
  if (estado.seleccion !== id) estado.editandoVertices = false;
  estado.seleccion = id;
  dibujar();
  inspector();
}

function agregarPunto(tipo, latlng) {
  const n = porTipo(tipo).length + 1;
  const props = { tipo };
  if (tipo === "camara") Object.assign(props, { nombre: `CAM M${String(n).padStart(2, "0")}`, modelo: $("#dist-modelo").value, azimut: 0 });
  if (tipo === "gabinete") props.nombre = `GAB M${String(n).padStart(2, "0")}`;
  if (tipo === "central") props.nombre = "Rack central";
  if (tipo === "ups") props.nombre = `UPS ${n}`;
  if (tipo === "central" && porTipo("central").length) {
    alert("Ya hay un rack central. Arrastralo para moverlo.");
    return;
  }
  const f = { type: "Feature", id: uid(tipo.slice(0, 3)), geometry: { type: "Point", coordinates: [round7(latlng.lng), round7(latlng.lat)] }, properties: props };
  estado.proyecto.elementos.push(f);
  seleccionar(f.id);
  cambio();
}

function borrar(id) {
  estado.proyecto.elementos = elementos().filter((f) => f.id !== id);
  for (const c of porTipo("camara")) if (c.properties.gabinete === id) delete c.properties.gabinete;
  estado.seleccion = null;
  inspector();
  dibujar();
  cambio();
}

// --------------------------------------------------------------------------- herramientas

function usarHerramienta(h) {
  mapa.pm.disableDraw();
  estado.herramienta = estado.herramienta === h ? null : h;
  document.querySelectorAll("[data-herr]").forEach((b) => b.classList.toggle("activo", b.dataset.herr === estado.herramienta));
  const ayuda = {
    perimetro: "Clic en cada vértice del cerco. Clic en el primer punto para cerrar.",
    "perimetro-abierto": "Clic en cada vértice. Clic en el último punto para terminar.",
    camara: "Clic en el mapa para ubicar una cámara.",
    gabinete: "Clic en el mapa para ubicar un gabinete.",
    central: "Clic donde va el rack central (sala de monitoreo).",
    ups: "Clic donde hay una fuente de energía / UPS adicional.",
  }[estado.herramienta];
  $("#ayuda-herr").textContent = ayuda || "Elegí una herramienta y hacé clic en el mapa. Los elementos se pueden arrastrar.";
  if (estado.herramienta === "perimetro") mapa.pm.enableDraw("Polygon", { finishOn: null });
  if (estado.herramienta === "perimetro-abierto") mapa.pm.enableDraw("Line");
}

mapa.on("pm:create", (e) => {
  const gj = e.layer.toGeoJSON().geometry;
  mapa.removeLayer(e.layer);
  const f = { type: "Feature", id: uid("per"), geometry: gj, properties: { tipo: "perimetro", nombre: `Perímetro ${porTipo("perimetro").length + 1}` } };
  estado.proyecto.elementos.push(f);
  usarHerramienta(null);
  seleccionar(f.id);
  cambio();
});

mapa.on("click", (e) => {
  if (["camara", "gabinete", "central", "ups"].includes(estado.herramienta)) agregarPunto(estado.herramienta, e.latlng);
  else if (!estado.herramienta && estado.seleccion) seleccionar(null);
});

document.querySelectorAll("[data-herr]").forEach((b) => b.addEventListener("click", () => usarHerramienta(b.dataset.herr)));
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") usarHerramienta(null);
  if (e.key === "Delete" && estado.seleccion && !/INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName)) borrar(estado.seleccion);
});

// --------------------------------------------------------------------------- inspector

function opcionesModelos(cat, actual) {
  return Object.values(estado.catalogo).filter((m) => m.categoria === cat)
    .map((m) => `<option value="${esc(m.id)}" ${m.id === actual ? "selected" : ""}>${esc(m.marca || "")} ${esc(m.modelo)}</option>`).join("");
}

function inspector() {
  const f = buscar(estado.seleccion);
  $("#inspector").hidden = !f;
  if (!f) return;
  const p = f.properties, cuerpo = $("#inspector-cuerpo");
  let html = `<label>Nombre <input data-prop="nombre" value="${esc(p.nombre || "")}"></label>`;
  if (p.tipo === "camara") {
    const m = estado.catalogo[p.modelo] || {};
    const gabs = porTipo("gabinete").map((g) => `<option value="${esc(g.id)}" ${g.id === p.gabinete ? "selected" : ""}>${esc(g.properties.nombre || g.id)}</option>`).join("");
    html += `
      <label>Modelo <select data-prop="modelo">${opcionesModelos("camara", p.modelo)}</select></label>
      <label>Orientación (°) <input data-prop="azimut" type="range" min="0" max="359" value="${Number(p.azimut) || 0}">
        <input data-prop="azimut" type="number" min="0" max="359" value="${Number(p.azimut) || 0}"></label>
      <label>Alcance analítica (m) <input data-prop="alcance" type="number" step="0.5" placeholder="${esc(m.alcance_analitica_m ?? "")} (del modelo)" value="${esc(p.alcance ?? "")}"></label>
      <label>Gabinete <select data-prop="gabinete"><option value="">Más cercano</option>${gabs}</select></label>
      <p class="ayuda">Ángulo ${fmt(m.hfov)}° · DORI D/O/R/I ${fmt(m.dori?.d, 1)} / ${fmt(m.dori?.o, 1)} / ${fmt(m.dori?.r, 1)} / ${fmt(m.dori?.i, 1)} m · IR ${fmt(m.ir_m)} m · ${fmt(m.consumo_w, 1)} W</p>`;
  }
  if (p.tipo === "gabinete" && estado.calculo) {
    const g = estado.calculo.gabinetes.find((x) => x.id === f.id);
    if (g) html += `<p class="ayuda">${g.camaras} cámaras · PoE ${fmt(g.poe_w)} W · ${esc(g.switch || "sin switch adecuado")} · UTP máx ${fmt(g.utp_max_m)} m · caída ${fmt(g.caida_pct, 2)}% (${esc(g.fuente || "")})</p>`;
  }
  if (p.tipo === "perimetro") {
    const c = estado.calculo?.cobertura;
    html += `<p class="ayuda">${f.geometry.type === "Polygon" ? "Cerrado" : "Abierto"}${c ? ` · ${fmt(c.largo_m)} m en total` : ""}</p>
      <button id="btn-vertices">${estado.editandoVertices ? "Terminar edición" : "Editar vértices"}</button>`;
  }
  if (p.auto) html += `<p class="ayuda">Generado automáticamente. Si lo modificás, pasa a ser manual y se conserva al redistribuir.</p>`;
  html += `<div class="fila" style="margin-top:8px"><button class="peligro" id="btn-borrar-el">Borrar elemento</button></div>`;
  cuerpo.innerHTML = html;

  cuerpo.querySelectorAll("[data-prop]").forEach((inp) => inp.addEventListener("input", () => {
    const k = inp.dataset.prop;
    let v = inp.value;
    if (["azimut", "alcance"].includes(k)) v = v === "" ? null : Number(v);
    if (v === null || v === "") delete p[k]; else p[k] = v;
    if (k === "azimut") cuerpo.querySelectorAll('[data-prop="azimut"]').forEach((o) => { if (o !== inp) o.value = v; });
    delete p.auto;
    dibujar();
    cambio();
  }));
  cuerpo.querySelector("#btn-borrar-el").onclick = () => borrar(f.id);
  const bv = cuerpo.querySelector("#btn-vertices");
  if (bv) bv.onclick = () => { estado.editandoVertices = !estado.editandoVertices; dibujar(); inspector(); };
}

// --------------------------------------------------------------------------- resultados

function resultados() {
  const r = estado.calculo, cont = $("#resultados");
  if (!r) { cont.innerHTML = `<p class="ayuda">Dibujá un perímetro para empezar.</p>`; return; }
  const s = r.resumen;
  const kpi = (v, t) => `<div class="kpi"><b>${v}</b><span>${t}</span></div>`;
  let html = `<div class="kpis">
    ${kpi(fmt(s.perimetro_m) + " m", "Perímetro")}
    ${kpi(s.cobertura_pct == null ? "—" : fmt(s.cobertura_pct, 1) + " %", "Cobertura analítica")}
    ${kpi(fmt(s.camaras), "Cámaras")}
    ${kpi(fmt(s.gabinetes), "Gabinetes")}
    ${kpi(fmt(s.fibra_m) + " m", "Fibra óptica")}
    ${kpi(fmt(s.energia_m) + " m", "Cable de energía")}
    ${kpi(fmt(s.mbps_total, 1) + " Mbps", "Tráfico de video")}
    ${kpi(fmt(s.almacenamiento_tb, 1) + " TB", `Grabación ${r.red.dias_grabacion} días`)}
  </div>`;
  html += `<ul class="avisos">${r.advertencias.length ? r.advertencias.map((a) => `<li>${esc(a)}</li>`).join("") : `<li class="ok">Sin observaciones.</li>`}</ul>`;

  if (r.energia.length) {
    html += `<details open><summary>Energía por fuente</summary><table><tr><th>Fuente</th><th class="num">Carga</th><th class="num">Cable</th><th class="num">Caída máx</th><th>UPS</th></tr>`;
    for (const e of r.energia) {
      const mal = e.caida_max_pct > param("limite_caida_pct");
      html += `<tr class="${mal ? "mal" : ""}"><td>${esc(e.fuente)}</td><td class="num">${fmt(e.carga_va)} VA</td><td class="num">${fmt(e.cable_m)} m</td><td class="num">${fmt(e.caida_max_pct, 2)} %</td><td>${esc(e.ups_sugerida || "—")}</td></tr>`;
    }
    html += `</table></details>`;
  }
  if (r.gabinetes.length) {
    html += `<details><summary>Gabinetes</summary><table><tr><th>Gabinete</th><th class="num">Cám.</th><th class="num">PoE</th><th class="num">UTP máx</th><th class="num">Caída</th></tr>`;
    for (const g of r.gabinetes) {
      const mal = !g.switch && g.camaras || g.utp_max_m > param("limite_utp_m") || g.caida_pct > param("limite_caida_pct");
      html += `<tr class="${mal ? "mal" : ""}"><td>${esc(g.nombre)}</td><td class="num">${g.camaras}</td><td class="num">${fmt(g.poe_w)} W</td><td class="num">${fmt(g.utp_max_m)} m</td><td class="num">${g.caida_pct == null ? "—" : fmt(g.caida_pct, 2) + " %"}</td></tr>`;
    }
    html += `</table></details>`;
  }
  if (r.materiales.length) {
    html += `<details open><summary>Listado de equipos y materiales</summary><table><tr><th>Ítem</th><th class="num">Cant.</th></tr>`;
    let cat = "";
    for (const m of r.materiales) {
      if (m.categoria !== cat) { cat = m.categoria; html += `<tr><th colspan="2">${esc(cat)}</th></tr>`; }
      html += `<tr><td>${esc(m.descripcion)}${m.modelo ? `<br><span class="ayuda">${esc(m.modelo)}</span>` : ""}</td><td class="num">${fmt(m.cantidad)} ${esc(m.unidad)}</td></tr>`;
    }
    html += `</table></details>`;
  }
  cont.innerHTML = html;
}

// --------------------------------------------------------------------------- guardado

function marcarEstado(t) { $("#estado").textContent = t; }

function cambio() {
  marcarEstado("Sin guardar…");
  clearTimeout(estado.guardando);
  estado.guardando = setTimeout(guardar, 500);
}

async function guardar() {
  const p = estado.proyecto;
  if (!p) return;
  try {
    marcarEstado("Guardando…");
    await api("PUT", `/api/proyectos/${p.id}`, p);
    marcarEstado("Guardado");
    await recalcular();
  } catch (e) {
    marcarEstado("Error al guardar");
    console.error(e);
  }
}

async function recalcular() {
  if (!estado.proyecto) return;
  try {
    estado.calculo = await api("GET", `/api/proyectos/${estado.proyecto.id}/calculo`);
  } catch (e) {
    estado.calculo = null;
    console.error(e);
  }
  resultados();
  dibujarHuecos();
  if (estado.seleccion) inspector();
}

// --------------------------------------------------------------------------- proyectos

async function listarProyectos(seleccionar_id) {
  const lista = await api("GET", "/api/proyectos");
  $("#sel-proyecto").innerHTML = lista.map((p) => `<option value="${esc(p.id)}">${esc(p.nombre)}${p.cliente ? " · " + esc(p.cliente) : ""}</option>`).join("");
  if (seleccionar_id) $("#sel-proyecto").value = seleccionar_id;
  return lista;
}

async function abrir(id) {
  estado.proyecto = await api("GET", `/api/proyectos/${id}`);
  estado.seleccion = null;
  estado.calculo = null;
  const p = estado.proyecto;
  $("#inp-nombre").value = p.nombre || "";
  $("#inp-cliente").value = p.cliente || "";
  $("#sel-categoria").value = p.categoria || "";
  $("#lnk-csv").href = `/api/proyectos/${p.id}/materiales.csv`;
  if (p.vista) mapa.setView(p.vista.centro, p.vista.zoom);
  try { localStorage.setItem("ayt-ultimo", id); } catch (_) { /* sin almacenamiento */ }
  formularioParametros();
  inspector();
  dibujar();
  marcarEstado("");
  await recalcular();
}

async function nuevo() {
  const nombre = prompt("Nombre del proyecto", "Proyecto nuevo");
  if (nombre === null) return;
  const c = mapa.getCenter();
  const p = await api("POST", "/api/proyectos", { nombre, elementos: [], parametros: {}, vista: { centro: [c.lat, c.lng], zoom: mapa.getZoom() } });
  await listarProyectos(p.id);
  await abrir(p.id);
}

$("#btn-nuevo").onclick = nuevo;
$("#sel-proyecto").onchange = (e) => abrir(e.target.value);
for (const [sel, k] of [["#inp-nombre", "nombre"], ["#inp-cliente", "cliente"], ["#sel-categoria", "categoria"]]) {
  $(sel).addEventListener("change", async (e) => {
    estado.proyecto[k] = e.target.value;
    await guardar();
    await listarProyectos(estado.proyecto.id);
  });
}
$("#btn-borrar").onclick = async () => {
  if (!estado.proyecto || !confirm(`¿Borrar el proyecto "${estado.proyecto.nombre}"? No se puede deshacer.`)) return;
  await api("DELETE", `/api/proyectos/${estado.proyecto.id}`);
  const lista = await listarProyectos();
  if (lista.length) await abrir(lista[0].id); else await nuevo();
};

let tVista;
mapa.on("moveend", () => {
  if (!estado.proyecto) return;
  clearTimeout(tVista);
  tVista = setTimeout(() => {
    const c = mapa.getCenter();
    estado.proyecto.vista = { centro: [c.lat, c.lng], zoom: mapa.getZoom() };
    api("PUT", `/api/proyectos/${estado.proyecto.id}`, estado.proyecto).catch(console.error);
  }, 800);
});

$("#chk-coberturas").onchange = dibujar;
$("#chk-huecos").onchange = dibujarHuecos;

// --------------------------------------------------------------------------- parámetros y distribución

function formularioParametros() {
  $("#parametros").innerHTML = Object.entries(ETIQUETAS_PARAM).map(([k, t]) =>
    `<label>${esc(t)} <input type="number" step="any" data-param="${k}" value="${esc(param(k))}"></label>`).join("");
  $("#parametros").querySelectorAll("[data-param]").forEach((inp) => inp.addEventListener("change", () => {
    estado.proyecto.parametros ||= {};
    if (inp.value === "") delete estado.proyecto.parametros[inp.dataset.param];
    else estado.proyecto.parametros[inp.dataset.param] = Number(inp.value);
    dibujar();
    cambio();
  }));
  $("#dist-modelo").innerHTML = opcionesModelos("camara", param("modelo_camara_perimetro"));
  $("#dist-cpg").value = param("camaras_por_gabinete");
  $("#dist-esp").value = estado.proyecto.parametros?.espaciado_m ?? "";
  $("#dist-sentido").value = param("sentido");
  actualizarEspaciadoSugerido();
}

function actualizarEspaciadoSugerido() {
  const m = estado.catalogo[$("#dist-modelo").value];
  $("#dist-esp").placeholder = m ? `automático (${fmt(m.alcance_analitica_m * 0.9, 1)} m)` : "automático";
}
$("#dist-modelo").onchange = actualizarEspaciadoSugerido;

$("#btn-distribuir").onclick = async () => {
  if (!porTipo("perimetro").length) { alert("Primero dibujá el perímetro."); return; }
  clearTimeout(estado.guardando);
  await api("PUT", `/api/proyectos/${estado.proyecto.id}`, estado.proyecto);
  const esp = $("#dist-esp").value;
  try {
    estado.proyecto = await api("POST", `/api/proyectos/${estado.proyecto.id}/distribuir`, {
      modelo_camara_perimetro: $("#dist-modelo").value,
      espaciado_m: esp === "" ? null : Number(esp),
      camaras_por_gabinete: Number($("#dist-cpg").value) || 4,
      sentido: $("#dist-sentido").value,
    });
    if (esp === "") delete estado.proyecto.parametros.espaciado_m;
  } catch (e) { alert(e.message); return; }
  estado.seleccion = null;
  inspector();
  dibujar();
  await recalcular();
};

// --------------------------------------------------------------------------- búsqueda

$("#frm-buscar").onsubmit = async (e) => {
  e.preventDefault();
  const q = $("#inp-buscar").value.trim();
  const m = q.match(/^\s*(-?\d+(?:\.\d+)?)\s*[,; ]\s*(-?\d+(?:\.\d+)?)\s*$/);
  if (m) { mapa.setView([Number(m[1]), Number(m[2])], 17); return; }
  try {
    const r = await fetch(`https://nominatim.openstreetmap.org/search?format=json&limit=1&q=${encodeURIComponent(q)}`);
    const d = await r.json();
    if (d.length) mapa.setView([Number(d[0].lat), Number(d[0].lon)], 17); else alert("No se encontró la dirección.");
  } catch (_) { alert("No se pudo buscar la dirección (sin conexión)."); }
};

// --------------------------------------------------------------------------- catálogo

const CAMPOS_NUM = ["lente_mm", "hfov", "vfov", "ir_m", "alcance_analitica_m", "bitrate_mbps", "puertos_poe", "budget_w", "potencia_va", "consumo_w"];

function tablaCatalogo() {
  const filas = Object.values(estado.catalogo).sort((a, b) => a.categoria.localeCompare(b.categoria) || a.modelo.localeCompare(b.modelo));
  $("#tabla-catalogo").innerHTML = `<table><tr><th>Categoría</th><th>Marca</th><th>Modelo</th><th>Datos</th><th></th></tr>${filas.map((m) => {
    const datos = m.categoria === "camara" ? `${fmt(m.hfov)}° · analítica ${fmt(m.alcance_analitica_m, 1)} m · ${fmt(m.consumo_w, 1)} W`
      : m.categoria === "switch" ? `${m.puertos_poe} PoE · ${m.budget_w} W` : m.categoria === "ups" ? `${fmt(m.potencia_va)} VA` : "";
    return `<tr><td>${esc(m.categoria)}</td><td>${esc(m.marca || "")}</td><td>${esc(m.modelo)}</td><td>${esc(datos)}</td>
      <td><button data-editar="${esc(m.id)}">${m.base ? "Duplicar" : "Editar"}</button>${m.base ? "" : ` <button class="peligro" data-borrar="${esc(m.id)}">Borrar</button>`}</td></tr>`;
  }).join("")}</table>`;
  $("#tabla-catalogo").querySelectorAll("[data-editar]").forEach((b) => b.onclick = () => cargarModelo(estado.catalogo[b.dataset.editar]));
  $("#tabla-catalogo").querySelectorAll("[data-borrar]").forEach((b) => b.onclick = async () => {
    if (!confirm("¿Borrar este modelo?")) return;
    await api("DELETE", `/api/catalogo/${b.dataset.borrar}`);
    await cargarCatalogo();
    tablaCatalogo();
  });
}

function mostrarCampos() {
  const cat = $("#frm-modelo").categoria.value;
  $("#frm-modelo").querySelectorAll("fieldset[data-cat]").forEach((fs) => { fs.hidden = fs.dataset.cat !== cat; });
}

function cargarModelo(m) {
  const f = $("#frm-modelo");
  f.reset();
  f.id.value = m.base ? "" : m.id;
  $("#frm-modelo-titulo").textContent = m.base ? `Duplicar ${m.modelo}` : `Editar ${m.modelo}`;
  for (const el of f.elements) {
    if (!el.name || el.name === "id") continue;
    if (el.name.startsWith("dori_")) el.value = m.dori?.[el.name.slice(5)] ?? "";
    else if (m[el.name] != null) el.value = m[el.name];
  }
  if (m.base) f.modelo.value = `${m.modelo} (copia)`;
  mostrarCampos();
}

$("#frm-modelo").categoria.onchange = mostrarCampos;
$("#btn-modelo-limpiar").onclick = () => { $("#frm-modelo").reset(); $("#frm-modelo-titulo").textContent = "Agregar modelo"; mostrarCampos(); };
$("#frm-modelo").onsubmit = async (e) => {
  e.preventDefault();
  const f = e.target, m = {};
  for (const el of f.elements) {
    if (!el.name || el.closest("fieldset[hidden]") || el.value === "") continue;
    if (el.name.startsWith("dori_")) { (m.dori ||= {})[el.name.slice(5)] = Number(el.value); continue; }
    m[el.name] = CAMPOS_NUM.includes(el.name) ? Number(el.value) : el.value;
  }
  if (m.categoria === "camara") {
    m.alcance_analitica_m ??= m.dori?.o ?? m.ir_m ?? 20;
    m.hfov ??= 90;
    m.poe = true;
  }
  if (m.categoria === "switch") m.uso ||= "gabinete";
  await api("POST", "/api/catalogo", m);
  await cargarCatalogo();
  tablaCatalogo();
  $("#btn-modelo-limpiar").click();
};

$("#btn-catalogo").onclick = () => { tablaCatalogo(); mostrarCampos(); $("#dlg-catalogo").showModal(); };
$("#btn-cerrar-cat").onclick = () => { $("#dlg-catalogo").close(); formularioParametros(); dibujar(); recalcular(); };

async function cargarCatalogo() {
  estado.catalogo = Object.fromEntries((await api("GET", "/api/catalogo")).map((m) => [m.id, m]));
}

// --------------------------------------------------------------------------- inicio

(async function inicio() {
  estado.defaults = await api("GET", "/api/parametros");
  await cargarCatalogo();
  const lista = await listarProyectos();
  let ultimo = null;
  try { ultimo = localStorage.getItem("ayt-ultimo"); } catch (_) { /* sin almacenamiento */ }
  if (!lista.length) {
    const c = mapa.getCenter();
    const p = await api("POST", "/api/proyectos", { nombre: "Proyecto nuevo", elementos: [], parametros: {}, vista: { centro: [c.lat, c.lng], zoom: mapa.getZoom() } });
    await listarProyectos(p.id);
    return abrir(p.id);
  }
  const id = lista.some((p) => p.id === ultimo) ? ultimo : lista[0].id;
  $("#sel-proyecto").value = id;
  await abrir(id);
})();
