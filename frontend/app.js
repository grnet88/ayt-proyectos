/* AyT Proyectos — interfaz de diseño (v0.2: usuarios, escenarios y plantas). */
"use strict";

const api = async (metodo, ruta, cuerpo) => {
  const r = await fetch(ruta, {
    method: metodo,
    headers: cuerpo ? { "Content-Type": "application/json" } : {},
    body: cuerpo ? JSON.stringify(cuerpo) : undefined,
  });
  if (r.status === 401 && !ruta.startsWith("/api/ingresar")) {
    mostrarAcceso("ingreso", "Tu sesión terminó. Volvé a ingresar.");
    throw new Error("Sesión no iniciada");
  }
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
  altura_camara_m: "Altura de cámaras por defecto (m)",
  ppm_minimo: "PPM mínimo en el borde del alcance",
  dist_min_camara_m: "Zona ciega si no hay ángulo vertical (m)",
  reserva_utp_m: "Reserva UTP por cámara (m)",
  limite_utp_m: "Largo máximo UTP (m)",
  factor_fo: "Factor de fibra (recorrido)",
  reserva_fo_por_gabinete_m: "Reserva de fibra por gabinete (m)",
  factor_energia: "Factor de cable de energía",
  margen_ups: "Margen de UPS",
  angulo_quiebre: "Giro para considerar esquina (°)",
};

const estado = {
  usuario: null,
  soloLectura: false,
  proyecto: null,
  escenario: null,
  planta: "exterior",
  catalogo: {},
  defaults: {},
  herramienta: null,
  seleccion: null,
  calculo: null,
  guardando: null,
  capasSector: {},
  marcadores: {},
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

// Óptica sobre el piso (misma lógica que backend/app/engine/optica.py)
const tanG = (g) => Math.tan((g * Math.PI) / 180);
function optica(p, m) {
  const alcance = Number(p.alcance) || m.alcance_analitica_m || 0;
  const altura = Number(p.altura_m) || param("altura_camara_m") || 4;
  const r = { altura, alcance, inclinacion: null, auto: true, ciega: param("dist_min_camara_m"), efectivo: alcance, lejano: null };
  if (m.hfov < 360 && m.vfov) {
    const manual = p.inclinacion !== undefined && p.inclinacion !== null && p.inclinacion !== "";
    const incl = manual ? Number(p.inclinacion) : Math.min(89, (Math.atan2(altura, alcance) * 180) / Math.PI + m.vfov / 2);
    Object.assign(r, { inclinacion: incl, auto: !manual });
    const abajo = Math.min(incl + m.vfov / 2, 89.9), arriba = incl - m.vfov / 2;
    r.ciega = abajo > 0 ? altura / tanG(abajo) : 0;
    r.lejano = arriba > 0.05 ? altura / tanG(arriba) : null;
    r.efectivo = Math.max(r.ciega, Math.min(alcance, r.lejano ?? Infinity));
  }
  return r;
}

// Muros y obstáculos como segmentos en metros locales alrededor de (lat0, lon0)
function bloqueosCerca(lat0, lon0, radio) {
  const kx = 111320 * Math.cos((lat0 * Math.PI) / 180), ky = 110540, segs = [];
  for (const f of [...porTipo("muro"), ...porTipo("obstaculo")]) {
    const c = f.geometry.type === "Polygon" ? f.geometry.coordinates[0] : f.geometry.coordinates;
    const pts = c.map(([lon, lat]) => [(lon - lon0) * kx, (lat - lat0) * ky]);
    for (let i = 0; i + 1 < pts.length; i++) {
      const [a, b] = [pts[i], pts[i + 1]];
      if (Math.min(Math.hypot(...a), Math.hypot(...b)) < radio + Math.hypot(b[0] - a[0], b[1] - a[1])) segs.push([a, b]);
    }
  }
  return segs;
}

// distancia hasta el primer corte del rayo con rumbo `az` (grados) contra los segmentos
function corteRayo(az, segs, rmax) {
  const dx = Math.sin((az * Math.PI) / 180), dy = Math.cos((az * Math.PI) / 180);
  let t = rmax;
  for (const [[ax, ay], [bx, by]] of segs) {
    const ex = bx - ax, ey = by - ay, den = dx * ey - dy * ex;
    if (Math.abs(den) < 1e-9) continue;
    const u = (ax * ey - ay * ex) / den, v = (ax * dy - ay * dx) / den;
    if (u > 0.05 && v >= 0 && v <= 1 && u < t) t = u;
  }
  return t;
}

function sector(lat, lon, az, hfov, r, rmin) {
  const segs = bloqueosCerca(lat, lon, r);
  const completo = hfov >= 360;
  if (completo && !segs.length) return null;
  const abertura = completo ? 360 : hfov, pasos = Math.max(8, Math.round(abertura / (segs.length ? 1.5 : 4)));
  const pts = [];
  for (let i = 0; i <= pasos; i++) {
    const a = az - abertura / 2 + (abertura * i) / pasos;
    pts.push(destino(lat, lon, a, Math.max(rmin, corteRayo(a, segs, r))));
  }
  if (!completo) for (let i = pasos; i >= 0; i--) pts.push(destino(lat, lon, az - hfov / 2 + (hfov * i) / pasos, rmin));
  return pts;
}

// --------------------------------------------------------------------------- elementos

const enPlanta = (f) => (f.properties.planta || "exterior") === estado.planta;
const elementos = () => (estado.escenario?.elementos || []).filter(enPlanta);
const porTipo = (t) => elementos().filter((f) => f.properties.tipo === t);
const buscar = (id) => elementos().find((f) => f.id === id);
const param = (k) => estado.escenario?.parametros?.[k] ?? estado.defaults[k];

const azimut = (f) => (Math.round(Number(f.properties.azimut) || 0) % 360 + 360) % 360;
const RUMBOS = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"];
const rumbo = (az) => RUMBOS[Math.round(az / 45) % 8];

function iconoPara(f) {
  const t = f.properties.tipo, sel = estado.seleccion === f.id ? " sel" : "", az = azimut(f);
  // el contenedor gira con la orientación y la muesca marca el frente; el texto se contra-gira para leerse derecho
  if (t === "camara") {
    const m = estado.catalogo[f.properties.modelo] || {};
    const clase = m.tipo === "ptz" ? " ptz" : m.tipo === "lpr" ? " lpr" : "";
    return L.divIcon({ className: "", iconSize: [14, 14],
      html: `<div class="girable" style="transform:rotate(${az}deg)"><div class="icono-elemento icono-camara${clase}${sel}" style="width:14px;height:14px"></div></div>` });
  }
  const txt = { gabinete: "G", central: "R", ups: "U" }[t];
  const tam = t === "central" ? 22 : 18;
  return L.divIcon({ className: "", iconSize: [tam, tam],
    html: `<div class="girable" style="transform:rotate(${az}deg)"><div class="icono-elemento icono-${t}${sel}" style="width:${tam}px;height:${tam}px"><span style="transform:rotate(${-az}deg)">${txt}</span></div></div>` });
}

// manija de giro: punto que se arrastra alrededor del elemento seleccionado
const RADIO_MANIJA = 48;
function posManija(lat, lon, az) {
  const c = mapa.latLngToLayerPoint([lat, lon]), r = (az * Math.PI) / 180;
  return mapa.layerPointToLatLng(L.point(c.x + RADIO_MANIJA * Math.sin(r), c.y - RADIO_MANIJA * Math.cos(r)));
}
function azimutHacia(lat, lon, latlng) {
  const c = mapa.latLngToLayerPoint([lat, lon]), p = mapa.latLngToLayerPoint(latlng);
  return (Math.round((Math.atan2(p.x - c.x, -(p.y - c.y)) * 180) / Math.PI) + 360) % 360;
}

function girar(f, az) {
  f.properties.azimut = ((Math.round(az) % 360) + 360) % 360;
  delete f.properties.auto;
}

function dibujar() {
  capaPerimetros.clearLayers();
  capaSectores.clearLayers();
  capaPuntos.clearLayers();
  capaRed.clearLayers();
  estado.capasSector = {};
  estado.marcadores = {};
  const verCob = $("#chk-coberturas").checked;

  for (const f of [...porTipo("perimetro"), ...porTipo("muro"), ...porTipo("obstaculo")]) {
    const latlngs = (f.geometry.type === "Polygon" ? f.geometry.coordinates[0] : f.geometry.coordinates).map(([lon, lat]) => [lat, lon]);
    const sel = estado.seleccion === f.id, t = f.properties.tipo;
    const estilo = t === "perimetro" ? { color: sel ? "#ffeb3b" : "#ffffff", weight: sel ? 4 : 3, fill: false, dashArray: "6 4" }
      : t === "muro" ? { color: sel ? "#ffeb3b" : "#ff7043", weight: sel ? 6 : 5 }
      : { color: sel ? "#ffeb3b" : "#78909c", weight: 2, fillColor: "#546e7a", fillOpacity: 0.55 };
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
        const o = optica(f.properties, m), r = o.efectivo;
        const color = m.tipo === "ptz" ? "#26a69a" : m.tipo === "lpr" ? "#a1887f" : "#42a5f5";
        const pts = sector(lat, lon, Number(f.properties.azimut) || 0, m.hfov, r, o.ciega);
        const opciones = { color, weight: 1, fillOpacity: 0.18, interactive: false };
        const capa = (pts ? L.polygon(pts, opciones) : L.circle([lat, lon], { ...opciones, radius: r, dashArray: "4 4" })).addTo(capaSectores);
        if (pts) capa.actualizar = (az) => capa.setLatLngs(sector(lat, lon, az, m.hfov, r, o.ciega));
        estado.capasSector[f.id] = capa;
      }
    }
    const mk = L.marker([lat, lon], { icon: iconoPara(f), draggable: !estado.soloLectura, title: f.properties.nombre || f.properties.tipo });
    mk.on("click", (e) => { L.DomEvent.stopPropagation(e); seleccionar(f.id); });
    mk.on("dragend", () => {
      const p = mk.getLatLng();
      f.geometry.coordinates = [round7(p.lng), round7(p.lat)];
      delete f.properties.auto;
      cambio();
    });
    mk.addTo(capaPuntos);
    estado.marcadores[f.id] = mk;
    if (estado.seleccion === f.id && !estado.soloLectura) manija(f, lat, lon);
  }
  dibujarHuecos();
}

function manija(f, lat, lon) {
  const linea = L.polyline([[lat, lon], posManija(lat, lon, azimut(f))], { color: "#ffeb3b", weight: 2, dashArray: "3 3", interactive: false }).addTo(capaPuntos);
  const mk = L.marker(posManija(lat, lon, azimut(f)), {
    draggable: true, zIndexOffset: 1000, title: "Arrastrá para girar",
    icon: L.divIcon({ className: "", html: '<div class="manija-giro"></div>', iconSize: [14, 14] }),
  }).addTo(capaPuntos);
  mk.on("drag", (e) => {
    const az = azimutHacia(lat, lon, e.target.getLatLng());
    girar(f, az);
    linea.setLatLngs([[lat, lon], posManija(lat, lon, az)]);
    estado.capasSector[f.id]?.actualizar?.(az);
    estado.marcadores[f.id]?.setIcon(iconoPara(f));
    actualizarOrientacionInspector(f);
  });
  mk.on("dragend", () => { dibujar(); cambio(); });
  mk.on("click", (e) => L.DomEvent.stopPropagation(e));
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
mapa.on("zoomend", () => { if (estado.seleccion && estado.escenario) dibujar(); });

function seleccionar(id) {
  if (estado.seleccion !== id) estado.editandoVertices = false;
  estado.seleccion = id;
  dibujar();
  inspector();
}

function agregarPunto(tipo, latlng) {
  const n = porTipo(tipo).length + 1;
  const props = { tipo, planta: estado.planta };
  if (tipo === "camara") Object.assign(props, { nombre: `CAM M${String(n).padStart(2, "0")}`, modelo: $("#dist-modelo").value, azimut: 0 });
  if (tipo === "gabinete") props.nombre = `GAB M${String(n).padStart(2, "0")}`;
  if (tipo === "central") props.nombre = "Rack central";
  if (tipo === "ups") props.nombre = `UPS ${n}`;
  if (tipo === "central" && porTipo("central").length) {
    alert("Ya hay un rack central. Arrastralo para moverlo.");
    return;
  }
  const f = { type: "Feature", id: uid(tipo.slice(0, 3)), geometry: { type: "Point", coordinates: [round7(latlng.lng), round7(latlng.lat)] }, properties: props };
  estado.escenario.elementos.push(f);
  seleccionar(f.id);
  cambio();
}

function borrar(id) {
  estado.escenario.elementos = estado.escenario.elementos.filter((f) => f.id !== id);
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
    muro: "Clic en cada punto del muro o pared. Clic en el último punto para terminar. Corta la visión de las cámaras.",
    obstaculo: "Clic en cada vértice del obstáculo (edificio, árbol, contenedor). Clic en el primero para cerrar.",
  }[estado.herramienta];
  $("#ayuda-herr").textContent = ayuda || "Elegí una herramienta y hacé clic en el mapa. Los elementos se pueden arrastrar.";
  if (estado.herramienta === "perimetro") mapa.pm.enableDraw("Polygon", { finishOn: null });
  if (estado.herramienta === "perimetro-abierto" || estado.herramienta === "muro") mapa.pm.enableDraw("Line");
  if (estado.herramienta === "obstaculo") mapa.pm.enableDraw("Polygon", { finishOn: null });
}

mapa.on("pm:create", (e) => {
  const gj = e.layer.toGeoJSON().geometry;
  mapa.removeLayer(e.layer);
  const tipo = ["muro", "obstaculo"].includes(estado.herramienta) ? estado.herramienta : "perimetro";
  const nombre = { perimetro: "Perímetro", muro: "Muro", obstaculo: "Obstáculo" }[tipo];
  const f = { type: "Feature", id: uid(tipo.slice(0, 3)), geometry: gj, properties: { tipo, planta: estado.planta, nombre: `${nombre} ${porTipo(tipo).length + 1}` } };
  estado.escenario.elementos.push(f);
  usarHerramienta(null);
  seleccionar(f.id);
  cambio();
});

mapa.on("click", (e) => {
  if (typeof clicCalibracion === "function" && clicCalibracion(e)) return;
  if (estado.soloLectura) return;
  if (["camara", "gabinete", "central", "ups"].includes(estado.herramienta)) agregarPunto(estado.herramienta, e.latlng);
  else if (!estado.herramienta && estado.seleccion) seleccionar(null);
});

document.querySelectorAll("[data-herr]").forEach((b) => b.addEventListener("click", () => usarHerramienta(b.dataset.herr)));
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") usarHerramienta(null);
  const f = !estado.soloLectura && estado.seleccion && !/INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName) ? buscar(estado.seleccion) : null;
  if (f && f.geometry.type === "Point" && (e.key === "r" || e.key === "R")) {
    girar(f, azimut(f) + (e.shiftKey ? -15 : 15));
    actualizarOrientacionInspector(f);
    dibujar();
    cambio();
  }
  if (e.key === "Delete" && !estado.soloLectura && estado.seleccion && !/INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName)) borrar(estado.seleccion);
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
  if (f.geometry.type === "Point") html += `
      <label>Orientación <span class="etiqueta" id="rumbo">${azimut(f)}° ${rumbo(azimut(f))}</span>
        <input data-prop="azimut" type="range" min="0" max="359" value="${azimut(f)}"></label>
      <div class="fila orientacion">
        <button type="button" data-girar="-15" title="Girar 15° a la izquierda (Shift+R)">⟲ 15°</button>
        <input data-prop="azimut" type="number" min="0" max="359" value="${azimut(f)}" title="Grados desde el norte, en sentido horario">
        <button type="button" data-girar="15" title="Girar 15° a la derecha (R)">15° ⟳</button>
      </div>
      <p class="ayuda edicion">También podés girarlo arrastrando el punto amarillo en el mapa, o con R / Shift+R.</p>`;
  if (p.tipo === "camara") {
    const m = estado.catalogo[p.modelo] || {};
    const gabs = porTipo("gabinete").map((g) => `<option value="${esc(g.id)}" ${g.id === p.gabinete ? "selected" : ""}>${esc(g.properties.nombre || g.id)}</option>`).join("");
    html += `
      <label>Modelo <select data-prop="modelo">${opcionesModelos("camara", p.modelo)}</select></label>
      <label>Alcance analítica (m) <input data-prop="alcance" type="number" step="0.5" placeholder="${esc(m.alcance_analitica_m ?? "")} (del modelo)" value="${esc(p.alcance ?? "")}"></label>
      <div class="fila">
        <label>Altura (m) <input data-prop="altura_m" type="number" step="0.1" min="0.5" placeholder="${esc(param("altura_camara_m"))}" value="${esc(p.altura_m ?? "")}"></label>
        <label>Inclinación (°) <input data-prop="inclinacion" type="number" step="0.5" min="0" max="90" placeholder="auto" value="${esc(p.inclinacion ?? "")}"></label>
      </div>
      <p class="ayuda" id="info-optica"></p>
      <label>Gabinete <select data-prop="gabinete"><option value="">Más cercano</option>${gabs}</select></label>
      <p class="ayuda">Ángulo ${fmt(m.hfov)}° · DORI D/O/R/I ${fmt(m.dori?.d, 1)} / ${fmt(m.dori?.o, 1)} / ${fmt(m.dori?.r, 1)} / ${fmt(m.dori?.i, 1)} m · IR ${fmt(m.ir_m)} m · ${fmt(m.consumo_w, 1)} W</p>`;
  }
  if (p.tipo === "gabinete" && estado.calculo) {
    const g = estado.calculo.gabinetes.find((x) => x.id === f.id);
    if (g) html += `<p class="ayuda">${g.camaras} cámaras · PoE ${fmt(g.poe_w)} W · ${esc(g.switch || "sin switch adecuado")} · UTP máx ${fmt(g.utp_max_m)} m · caída ${fmt(g.caida_pct, 2)}% (${esc(g.fuente || "")})</p>`;
  }
  if (p.tipo === "muro" || p.tipo === "obstaculo") {
    html += `<p class="ayuda">${p.tipo === "muro" ? "Muro o pared" : "Obstáculo"}: corta la visión de las cámaras (cálculo en planta, sin altura).</p>
      <button id="btn-vertices" class="edicion">${estado.editandoVertices ? "Terminar edición" : "Editar vértices"}</button>`;
  }
  if (p.tipo === "perimetro") {
    const c = estado.calculo?.cobertura;
    html += `<p class="ayuda">${f.geometry.type === "Polygon" ? "Cerrado" : "Abierto"}${c ? ` · ${fmt(c.largo_m)} m en total` : ""}</p>
      <button id="btn-vertices" class="edicion">${estado.editandoVertices ? "Terminar edición" : "Editar vértices"}</button>`;
  }
  if (p.auto) html += `<p class="ayuda">Generado automáticamente. Si lo modificás, pasa a ser manual y se conserva al redistribuir.</p>`;
  html += `<div class="fila edicion" style="margin-top:8px"><button class="peligro" id="btn-borrar-el">Borrar elemento</button></div>`;
  cuerpo.innerHTML = html;
  if (estado.soloLectura) cuerpo.querySelectorAll("input, select").forEach((el) => { el.disabled = true; });

  cuerpo.querySelectorAll("[data-prop]").forEach((inp) => inp.addEventListener("input", () => {
    const k = inp.dataset.prop;
    let v = inp.value;
    if (["azimut", "alcance", "altura_m", "inclinacion"].includes(k)) v = v === "" ? null : Number(v);
    if (k === "azimut") { if (v === null) return; girar(f, v); actualizarOrientacionInspector(f, inp); }
    else if (v === null || v === "") delete p[k]; else p[k] = v;
    if (p.tipo === "camara") infoOptica(f);
    delete p.auto;
    dibujar();
    cambio();
  }));
  if (p.tipo === "camara") infoOptica(f);
  cuerpo.querySelectorAll("[data-girar]").forEach((b) => b.onclick = () => {
    girar(f, azimut(f) + Number(b.dataset.girar));
    actualizarOrientacionInspector(f);
    dibujar();
    cambio();
  });
  cuerpo.querySelector("#btn-borrar-el").onclick = () => borrar(f.id);
  const bv = cuerpo.querySelector("#btn-vertices");
  if (bv) bv.onclick = () => { estado.editandoVertices = !estado.editandoVertices; dibujar(); inspector(); };
}

function infoOptica(f) {
  const m = estado.catalogo[f.properties.modelo], el = $("#info-optica");
  if (!m || !el) return;
  const o = optica(f.properties, m);
  const ppm = m.resolucion_h && m.hfov < 180 ? m.resolucion_h / (2 * o.efectivo * tanG(m.hfov / 2)) : m.dori?.i ? (250 * m.dori.i) / o.efectivo : null;
  const inc = o.inclinacion === null ? "" : `Inclinación ${fmt(o.inclinacion, 1)}°${o.auto ? " (automática)" : ""} · `;
  el.innerHTML = `${inc}zona ciega ${fmt(o.ciega, 1)} m · cubre hasta ${fmt(o.efectivo, 1)} m` +
    (ppm ? ` · <b>${fmt(ppm, 0)} PPM</b> en el borde` : "") +
    (o.lejano !== null && o.lejano < o.alcance * 0.8 ? ` · <span style="color:var(--aviso)">mira al piso: el alcance queda corto</span>` : "");
}

function actualizarOrientacionInspector(f, excepto) {
  const cuerpo = $("#inspector-cuerpo"), az = azimut(f);
  cuerpo.querySelectorAll('[data-prop="azimut"]').forEach((o) => { if (o !== excepto) o.value = az; });
  const r = cuerpo.querySelector("#rumbo");
  if (r) r.textContent = `${az}° ${rumbo(az)}`;
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
  if (estado.soloLectura) return;
  marcarEstado("Sin guardar…");
  clearTimeout(estado.guardando);
  estado.guardando = setTimeout(guardar, 500);
}

async function guardar() {
  const e = estado.escenario;
  if (!e || estado.soloLectura) return;
  try {
    marcarEstado("Guardando…");
    await api("PUT", `/api/escenarios/${e.id}`, { elementos: e.elementos, parametros: e.parametros, computo: e.computo });
    marcarEstado("Guardado");
    await recalcular();
  } catch (err) {
    marcarEstado("Error al guardar");
    console.error(err);
  }
}

async function guardarProyecto(cambios) {
  if (estado.soloLectura) return;
  Object.assign(estado.proyecto, cambios);
  await api("PUT", `/api/proyectos/${estado.proyecto.id}`, cambios);
}

async function recalcular() {
  if (!estado.escenario) return;
  try {
    estado.calculo = await api("GET", `/api/escenarios/${estado.escenario.id}/calculo`);
  } catch (e) {
    estado.calculo = null;
    console.error(e);
  }
  resultados();
  dibujarHuecos();
  if (estado.seleccion) inspector();
}

// --------------------------------------------------------------------------- proyectos

const recordar = (k, v) => { try { localStorage.setItem(k, v); } catch (_) { /* sin almacenamiento */ } };
const recuerdo = (k) => { try { return localStorage.getItem(k); } catch (_) { return null; } };

async function listarProyectos(seleccionar_id) {
  const lista = await api("GET", "/api/proyectos");
  $("#sel-proyecto").innerHTML = lista.map((p) => `<option value="${esc(p.id)}">${esc(p.nombre)}${p.cliente ? " · " + esc(p.cliente) : ""}</option>`).join("");
  if (seleccionar_id) $("#sel-proyecto").value = seleccionar_id;
  return lista;
}

function selectorEscenarios() {
  const p = estado.proyecto;
  $("#sel-escenario").innerHTML = p.escenarios.map((e) =>
    `<option value="${esc(e.id)}">${esc(e.nombre)}${e.tipo === "etapa" ? " (etapa)" : ""}</option>`).join("");
  if (estado.escenario) $("#sel-escenario").value = estado.escenario.id;
  $("#sel-planta").innerHTML = (p.plantas || [{ id: "exterior", nombre: "Exterior" }]).map((pl) =>
    `<option value="${esc(pl.id)}">${esc(pl.nombre)}</option>`).join("");
  $("#sel-planta").value = estado.planta;
  $("#sel-planta").title = "Planta. Los pisos de edificios con plano propio llegan en la etapa 5.";
}

async function abrir(id) {
  estado.proyecto = await api("GET", `/api/proyectos/${id}`);
  const p = estado.proyecto;
  $("#inp-nombre").value = p.nombre || "";
  $("#inp-cliente").value = p.cliente || "";
  $("#sel-categoria").value = p.categoria || "";
  if (p.vista) mapa.setView(p.vista.centro, p.vista.zoom);
  recordar("ayt-ultimo", id);
  if (typeof dibujarPlanos === "function") dibujarPlanos();
  const previo = recuerdo(`ayt-escenario-${id}`);
  await abrirEscenario(p.escenarios.some((e) => e.id === previo) ? previo : p.escenarios[0].id);
}

async function abrirEscenario(eid) {
  clearTimeout(estado.guardando);
  estado.escenario = await api("GET", `/api/escenarios/${eid}`);
  estado.escenario.parametros ||= {};
  estado.seleccion = null;
  estado.calculo = null;
  estado.planta = "exterior";
  recordar(`ayt-escenario-${estado.proyecto.id}`, eid);
  $("#lnk-csv").href = `/api/escenarios/${eid}/materiales.csv`;
  selectorEscenarios();
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
  const p = await api("POST", "/api/proyectos", { nombre, vista: { centro: [c.lat, c.lng], zoom: mapa.getZoom() } });
  await listarProyectos(p.id);
  await abrir(p.id);
}

$("#btn-nuevo").onclick = nuevo;
$("#sel-proyecto").onchange = (e) => abrir(e.target.value);
$("#sel-escenario").onchange = (e) => abrirEscenario(e.target.value);
$("#sel-planta").onchange = (e) => { estado.planta = e.target.value; estado.seleccion = null; inspector(); dibujar(); if (typeof dibujarPlanos === "function") dibujarPlanos(); };
for (const [sel, k] of [["#inp-nombre", "nombre"], ["#inp-cliente", "cliente"], ["#sel-categoria", "categoria"]]) {
  $(sel).addEventListener("change", async (e) => {
    await guardarProyecto({ [k]: e.target.value });
    await listarProyectos(estado.proyecto.id);
  });
}
$("#btn-borrar").onclick = async () => {
  if (!estado.proyecto || !confirm(`¿Borrar el proyecto "${estado.proyecto.nombre}" con todas sus opciones? No se puede deshacer.`)) return;
  await api("DELETE", `/api/proyectos/${estado.proyecto.id}`);
  const lista = await listarProyectos();
  if (lista.length) await abrir(lista[0].id); else await nuevo();
};

let tVista;
mapa.on("moveend", () => {
  if (!estado.proyecto || estado.soloLectura) return;
  clearTimeout(tVista);
  tVista = setTimeout(() => {
    const c = mapa.getCenter();
    guardarProyecto({ vista: { centro: [c.lat, c.lng], zoom: mapa.getZoom() } }).catch(console.error);
  }, 800);
});

$("#chk-coberturas").onchange = dibujar;
$("#chk-huecos").onchange = dibujarHuecos;

// --------------------------------------------------------------------------- escenarios (opciones y etapas)

function listaEscenarios() {
  const p = estado.proyecto;
  $("#lista-escenarios").innerHTML = `<table><tr><th>Nombre</th><th>Tipo</th><th></th></tr>${p.escenarios.map((e) => `
    <tr><td><input data-renombrar="${esc(e.id)}" value="${esc(e.nombre)}"></td>
    <td><select data-tipo="${esc(e.id)}"><option value="alternativa" ${e.tipo === "alternativa" ? "selected" : ""}>Opción</option>
      <option value="etapa" ${e.tipo === "etapa" ? "selected" : ""}>Etapa de obra</option></select></td>
    <td>${e.id === estado.escenario.id ? '<span class="etiqueta">abierta</span>' : `<button data-abrir="${esc(e.id)}">Abrir</button>`}
      <button class="peligro" data-borrar-esc="${esc(e.id)}">Borrar</button></td></tr>`).join("")}</table>`;
  const cont = $("#lista-escenarios");
  const refrescar = async () => { estado.proyecto = await api("GET", `/api/proyectos/${p.id}`); selectorEscenarios(); listaEscenarios(); };
  cont.querySelectorAll("[data-renombrar]").forEach((i) => i.onchange = async () => { await api("PUT", `/api/escenarios/${i.dataset.renombrar}`, { nombre: i.value }); await refrescar(); });
  cont.querySelectorAll("[data-tipo]").forEach((i) => i.onchange = async () => { await api("PUT", `/api/escenarios/${i.dataset.tipo}`, { tipo: i.value }); await refrescar(); });
  cont.querySelectorAll("[data-abrir]").forEach((b) => b.onclick = async () => { $("#dlg-escenarios").close(); await abrirEscenario(b.dataset.abrir); });
  cont.querySelectorAll("[data-borrar-esc]").forEach((b) => b.onclick = async () => {
    if (!confirm("¿Borrar esta opción con todos sus equipos? No se puede deshacer.")) return;
    try { await api("DELETE", `/api/escenarios/${b.dataset.borrarEsc}`); } catch (e) { alert(e.message); return; }
    const abierta = b.dataset.borrarEsc === estado.escenario.id;
    await refrescar();
    if (abierta) await abrirEscenario(estado.proyecto.escenarios[0].id);
  });
}

$("#btn-escenarios").onclick = () => { listaEscenarios(); $("#dlg-escenarios").showModal(); };
$("#frm-escenario").onsubmit = async (ev) => {
  ev.preventDefault();
  const f = ev.target;
  clearTimeout(estado.guardando);
  await guardar();
  const e = await api("POST", `/api/proyectos/${estado.proyecto.id}/escenarios`, {
    nombre: f.nombre.value, tipo: f.tipo.value, copiar_de: f.copiar.value === "actual" ? estado.escenario.id : null,
  });
  f.reset();
  estado.proyecto = await api("GET", `/api/proyectos/${estado.proyecto.id}`);
  $("#dlg-escenarios").close();
  await abrirEscenario(e.id);
};

// --------------------------------------------------------------------------- parámetros y distribución

function formularioParametros() {
  $("#parametros").innerHTML = Object.entries(ETIQUETAS_PARAM).map(([k, t]) =>
    `<label>${esc(t)} <input type="number" step="any" data-param="${k}" value="${esc(param(k))}" ${estado.soloLectura ? "disabled" : ""}></label>`).join("");
  $("#parametros").querySelectorAll("[data-param]").forEach((inp) => inp.addEventListener("change", () => {
    const par = estado.escenario.parametros;
    if (inp.value === "") delete par[inp.dataset.param];
    else par[inp.dataset.param] = Number(inp.value);
    dibujar();
    cambio();
  }));
  $("#dist-modelo").innerHTML = opcionesModelos("camara", param("modelo_camara_perimetro"));
  $("#dist-cpg").value = param("camaras_por_gabinete");
  $("#dist-esp").value = estado.escenario.parametros.espaciado_m ?? "";
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
  await guardar();
  const esp = $("#dist-esp").value;
  try {
    estado.escenario = await api("POST", `/api/escenarios/${estado.escenario.id}/distribuir`, {
      modelo_camara_perimetro: $("#dist-modelo").value,
      espaciado_m: esp === "" ? null : Number(esp),
      camaras_por_gabinete: Number($("#dist-cpg").value) || 4,
      sentido: $("#dist-sentido").value,
    });
    if (esp === "") delete estado.escenario.parametros.espaciado_m;
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


// --------------------------------------------------------------------------- acceso y usuarios

function descargar(nombre, texto) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([texto], { type: "text/plain" }));
  a.download = nombre;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
}

// botones "Mostrar" junto a cada contraseña
document.addEventListener("click", (e) => {
  const b = e.target.closest("button.ver");
  if (!b) return;
  const inp = b.parentElement.querySelector("input");
  const ver = inp.type === "password";
  inp.type = ver ? "text" : "password";
  b.textContent = ver ? "Ocultar" : "Mostrar";
});
document.querySelectorAll("dialog [data-cerrar]").forEach((b) => b.onclick = () => b.closest("dialog").close());

function mostrarAcceso(modo, mensaje = "") {
  $("#pantalla-acceso").hidden = !modo;
  for (const [id, m] of [["#frm-inicial", "inicial"], ["#frm-ingreso", "ingreso"], ["#frm-recuperar", "recuperar"]]) $(id).hidden = m !== modo;
  $("#msg-acceso").textContent = mensaje;
}

$("#frm-inicial").onsubmit = async (e) => {
  e.preventDefault();
  const f = e.target;
  if (f.clave.value !== f.clave2.value) { $("#msg-acceso").textContent = "Las contraseñas no coinciden."; return; }
  try {
    const r = await api("POST", "/api/configuracion-inicial", { clave: f.clave.value });
    descargar(r.archivo, r.llave);
    alert("Se descargó la llave de recuperación (aytroot-llave-recuperacion.key). Guardala fuera de esta PC: es la única forma de recuperar aytroot si perdés la contraseña.");
    await api("POST", "/api/ingresar", { usuario: "aytroot", clave: f.clave.value });
    f.reset();
    await inicio();
  } catch (err) { $("#msg-acceso").textContent = err.message; }
};

$("#frm-ingreso").onsubmit = async (e) => {
  e.preventDefault();
  const f = e.target;
  try {
    await api("POST", "/api/ingresar", { usuario: f.usuario.value, clave: f.clave.value });
    f.clave.value = "";
    await inicio();
  } catch (err) { $("#msg-acceso").textContent = err.message; }
};

$("#lnk-recuperar").onclick = (e) => { e.preventDefault(); mostrarAcceso("recuperar"); };
$("#lnk-volver").onclick = (e) => { e.preventDefault(); mostrarAcceso("ingreso"); };
$("#frm-recuperar").onsubmit = async (e) => {
  e.preventDefault();
  const f = e.target;
  if (f.clave.value !== f.clave2.value) { $("#msg-acceso").textContent = "Las contraseñas no coinciden."; return; }
  try {
    const llave = await f.llave.files[0].text();
    const r = await api("POST", "/api/recuperar", { llave, clave: f.clave.value });
    descargar(r.archivo, r.llave);
    f.reset();
    mostrarAcceso("ingreso", "Listo. Ingresá con la contraseña nueva. Se descargó una llave nueva: la anterior ya no vale.");
  } catch (err) { $("#msg-acceso").textContent = err.message; }
};

$("#btn-usuario").onclick = (e) => { e.stopPropagation(); $("#menu-usuario").hidden = !$("#menu-usuario").hidden; };
document.addEventListener("click", () => { $("#menu-usuario").hidden = true; });
$("#btn-salir").onclick = async () => { await api("POST", "/api/salir"); location.reload(); };

$("#btn-mi-clave").onclick = () => { $("#frm-clave").reset(); $("#dlg-clave").showModal(); };
$("#frm-clave").onsubmit = async (e) => {
  e.preventDefault();
  const f = e.target;
  if (f.nueva.value !== f.nueva2.value) { alert("Las contraseñas nuevas no coinciden."); return; }
  try {
    await api("POST", "/api/mi-clave", { actual: f.actual.value, nueva: f.nueva.value });
    $("#dlg-clave").close();
    alert("Contraseña actualizada.");
  } catch (err) { alert(err.message); }
};

async function tablaUsuarios() {
  const lista = await api("GET", "/api/usuarios");
  $("#tabla-usuarios").innerHTML = `<table><tr><th>Usuario</th><th>Nombre</th><th>Rol</th><th>Estado</th><th></th></tr>${lista.map((u) => `
    <tr><td>${esc(u.usuario)}</td><td>${esc(u.nombre || "")}</td><td>${esc(u.rol_nombre)}</td><td>${u.activo ? "Activo" : "Inactivo"}</td>
    <td>${u.fijo ? '<span class="etiqueta">fijo</span>' : `<button data-editar-u="${esc(u.id)}">Editar</button>
      <button data-activo-u="${esc(u.id)}">${u.activo ? "Desactivar" : "Activar"}</button>
      <button class="peligro" data-borrar-u="${esc(u.id)}">Borrar</button>`}</td></tr>`).join("")}</table>`;
  const cont = $("#tabla-usuarios");
  cont.querySelectorAll("[data-editar-u]").forEach((b) => b.onclick = () => cargarUsuario(lista.find((u) => u.id === b.dataset.editarU)));
  cont.querySelectorAll("[data-activo-u]").forEach((b) => b.onclick = async () => {
    const u = lista.find((x) => x.id === b.dataset.activoU);
    await api("PUT", `/api/usuarios/${u.id}`, { activo: !u.activo });
    tablaUsuarios();
  });
  cont.querySelectorAll("[data-borrar-u]").forEach((b) => b.onclick = async () => {
    if (!confirm("¿Borrar este usuario?")) return;
    await api("DELETE", `/api/usuarios/${b.dataset.borrarU}`);
    tablaUsuarios();
  });
}

async function formularioUsuario(u) {
  const f = $("#frm-usuario");
  f.reset();
  f.rol.innerHTML = Object.entries(estado.roles).filter(([k]) => k !== "superadmin")
    .map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("");
  const proyectos = await api("GET", "/api/proyectos");
  $("#usuario-proyectos").innerHTML = proyectos.map((p) =>
    `<label class="check"><input type="checkbox" value="${esc(p.id)}" ${u?.proyectos?.includes(p.id) ? "checked" : ""}> ${esc(p.nombre)}</label>`).join("") || '<p class="ayuda">No hay proyectos.</p>';
  f.id.value = u?.id || "";
  f.usuario.value = u?.usuario || "";
  f.usuario.disabled = !!u;
  f.nombre.value = u?.nombre || "";
  f.rol.value = u?.rol || "ingeniero";
  f.clave.required = !u;
  $("#frm-usuario-titulo").textContent = u ? `Editar ${u.usuario}` : "Nuevo usuario";
  rolCambiado();
}
const cargarUsuario = (u) => formularioUsuario(u);
function rolCambiado() { $('#frm-usuario fieldset[data-rol="visor"]').hidden = $("#frm-usuario").rol.value !== "visor"; }
$("#frm-usuario").rol.onchange = rolCambiado;
$("#btn-usuario-limpiar").onclick = () => formularioUsuario(null);
$("#frm-usuario").onsubmit = async (e) => {
  e.preventDefault();
  const f = e.target;
  const datos = { nombre: f.nombre.value, rol: f.rol.value,
    proyectos: [...$("#usuario-proyectos").querySelectorAll("input:checked")].map((i) => i.value) };
  if (f.clave.value) datos.clave = f.clave.value;
  try {
    if (f.id.value) await api("PUT", `/api/usuarios/${f.id.value}`, datos);
    else await api("POST", "/api/usuarios", { ...datos, usuario: f.usuario.value });
  } catch (err) { alert(err.message); return; }
  await formularioUsuario(null);
  tablaUsuarios();
};
$("#btn-usuarios").onclick = async () => { await formularioUsuario(null); await tablaUsuarios(); $("#dlg-usuarios").showModal(); };
$("#btn-nueva-llave").onclick = async () => {
  if (!confirm("Se genera una llave nueva y la anterior deja de valer. ¿Continuar?")) return;
  const r = await api("POST", "/api/llave-recuperacion");
  descargar(r.archivo, r.llave);
};

// --------------------------------------------------------------------------- inicio

async function inicio() {
  const est = await api("GET", "/api/estado");
  estado.roles = est.roles;
  if (!est.configurado) {
    if (est.local) mostrarAcceso("inicial");
    else mostrarAcceso("ingreso", "El sistema todavía no está configurado. Abrilo desde la PC del servidor (http://localhost:8000).");
    return;
  }
  if (!est.usuario) { mostrarAcceso("ingreso"); return; }
  mostrarAcceso(null);
  const u = est.usuario;
  estado.usuario = u;
  estado.soloLectura = !["superadmin", "ingeniero", "relevador"].includes(u.rol);
  document.body.classList.toggle("solo-lectura", estado.soloLectura);
  document.body.classList.toggle("es-admin", u.rol === "superadmin");
  for (const id of ["#inp-nombre", "#inp-cliente", "#sel-categoria"]) $(id).disabled = estado.soloLectura;
  $("#btn-usuario").textContent = u.nombre && u.nombre !== u.rol_nombre ? `${u.nombre} · ${u.rol_nombre}` : `${u.usuario} · ${u.rol_nombre}`;
  estado.defaults = await api("GET", "/api/parametros");
  await cargarCatalogo();
  const lista = await listarProyectos();
  if (!lista.length) {
    if (estado.soloLectura) { $("#resultados").innerHTML = '<p class="ayuda">No tenés proyectos asignados.</p>'; return; }
    const c = mapa.getCenter();
    const p = await api("POST", "/api/proyectos", { nombre: "Proyecto nuevo", vista: { centro: [c.lat, c.lng], zoom: mapa.getZoom() } });
    await listarProyectos(p.id);
    return abrir(p.id);
  }
  const ultimo = recuerdo("ayt-ultimo");
  const id = lista.some((p) => p.id === ultimo) ? ultimo : lista[0].id;
  $("#sel-proyecto").value = id;
  await abrir(id);
}

inicio();
