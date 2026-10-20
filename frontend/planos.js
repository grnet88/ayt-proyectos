// Planos superpuestos al mapa (imagen o PDF) con calibración de dos puntos.
//
// Georreferencia de un plano: transformación de similitud (escala + giro + traslado) guardada como
// { lat0, lon0, kr, ki }: el píxel (u, v) de la imagen (v hacia abajo) cae en el punto que está
// x, y metros al este y al norte de (lat0, lon0), con x + iy = (kr + i·ki)·(u − i·v).

const K_METROS = (Math.PI / 180) * 6371008.8;
mapa.createPane("planos").style.zIndex = 250; // sobre el satélite, debajo de cerco y cámaras

const planos = { capas: {}, calibrando: null, marcas: L.layerGroup().addTo(mapa), guardado: null };

function pixelALatLng(g, u, v) {
  const x = g.kr * u + g.ki * v, y = g.ki * u - g.kr * v;
  return L.latLng(g.lat0 + y / K_METROS, g.lon0 + x / (K_METROS * Math.cos((g.lat0 * Math.PI) / 180)));
}

function latLngAPixel(g, ll) {
  const x = (ll.lng - g.lon0) * K_METROS * Math.cos((g.lat0 * Math.PI) / 180), y = (ll.lat - g.lat0) * K_METROS;
  const n = g.kr * g.kr + g.ki * g.ki;
  return [(x * g.kr + y * g.ki) / n, -(y * g.kr - x * g.ki) / n];
}

const metrosPorPixel = (g) => Math.hypot(g.kr, g.ki);

// Capa Leaflet que ubica la imagen con una matriz CSS a partir de tres esquinas
const CapaPlano = L.Layer.extend({
  initialize(plano, url) { this.plano = plano; this.url = url; },
  onAdd(map) {
    this._img = L.DomUtil.create("img", "plano-img leaflet-zoom-hide");
    this._img.src = this.url;
    this._img.alt = this.plano.nombre;
    map.getPane("planos").appendChild(this._img);
    map.on("viewreset zoomend moveend", this._ubicar, this);
    this._ubicar();
  },
  onRemove(map) {
    map.off("viewreset zoomend moveend", this._ubicar, this);
    this._img.remove();
  },
  _ubicar() {
    const p = this.plano, g = p.georef, m = this._map;
    if (!g || !m) return;
    const a = m.latLngToLayerPoint(pixelALatLng(g, 0, 0));
    const b = m.latLngToLayerPoint(pixelALatLng(g, p.ancho, 0));
    const c = m.latLngToLayerPoint(pixelALatLng(g, 0, p.alto));
    Object.assign(this._img.style, {
      width: `${p.ancho}px`, height: `${p.alto}px`, opacity: p.opacidad ?? 0.6,
      transform: `matrix(${(b.x - a.x) / p.ancho}, ${(b.y - a.y) / p.ancho}, ${(c.x - a.x) / p.alto}, ${(c.y - a.y) / p.alto}, ${a.x}, ${a.y})`,
    });
  },
});

function dibujarPlanos() {
  for (const capa of Object.values(planos.capas)) capa.remove();
  planos.capas = {};
  for (const p of estado.proyecto?.planos || []) {
    if (!p.visible || !p.georef || (p.planta || "exterior") !== estado.planta) continue;
    planos.capas[p.id] = new CapaPlano(p, `/api/proyectos/${estado.proyecto.id}/planos/${p.archivo}`).addTo(mapa);
  }
  listaPlanos();
}

function guardarPlanos(demora = 0) {
  clearTimeout(planos.guardado);
  planos.guardado = setTimeout(() => guardarProyecto({ planos: estado.proyecto.planos }), demora);
}

function listaPlanos() {
  const lista = estado.proyecto?.planos || [], cont = $("#lista-planos");
  if (!cont) return;
  cont.innerHTML = lista.length ? lista.map((p) => `
    <div class="plano" data-plano="${esc(p.id)}">
      <label class="check"><input type="checkbox" data-visible ${p.visible ? "checked" : ""}> ${esc(p.nombre)}</label>
      <input type="range" min="0.1" max="1" step="0.05" value="${p.opacidad ?? 0.6}" data-opacidad title="Transparencia">
      <span class="ayuda">${p.georef ? `1 px = ${fmt(metrosPorPixel(p.georef) * 100, 1)} cm` : "sin ubicar"}</span>
      <div class="fila edicion">
        <button data-calibrar>Calibrar</button>
        <button class="peligro" data-borrar-plano>Borrar</button>
      </div>
    </div>`).join("") : '<p class="ayuda">Sin planos. Podés superponer un plano del barrio o de la obra.</p>';
  cont.querySelectorAll("[data-plano]").forEach((fila) => {
    const p = lista.find((x) => x.id === fila.dataset.plano);
    fila.querySelector("[data-visible]").onchange = (e) => { p.visible = e.target.checked; dibujarPlanos(); guardarPlanos(); };
    fila.querySelector("[data-opacidad]").oninput = (e) => {
      p.opacidad = Number(e.target.value);
      planos.capas[p.id]?._ubicar();
      guardarPlanos(600);
    };
    fila.querySelector("[data-calibrar]").onclick = () => iniciarCalibracion(p);
    fila.querySelector("[data-borrar-plano]").onclick = async () => {
      if (!confirm(`¿Borrar el plano "${p.nombre}"?`)) return;
      estado.proyecto = { ...estado.proyecto, ...(await api("DELETE", `/api/proyectos/${estado.proyecto.id}/planos/${p.id}`)) };
      dibujarPlanos();
    };
  });
  if (estado.soloLectura) cont.querySelectorAll("input[type=range]").forEach((i) => { i.disabled = true; });
}

// --------------------------------------------------------------------------- carga (PNG, JPG o PDF)

function leerComoDataURL(archivo) {
  return new Promise((ok, mal) => {
    const r = new FileReader();
    r.onload = () => ok(r.result);
    r.onerror = () => mal(r.error);
    r.readAsDataURL(archivo);
  });
}

function medidas(url) {
  return new Promise((ok, mal) => {
    const img = new Image();
    img.onload = () => ok([img.naturalWidth, img.naturalHeight]);
    img.onerror = () => mal(new Error("No se pudo leer la imagen"));
    img.src = url;
  });
}

async function pdfAImagen(archivo) {
  const pdfjs = await import("/static/vendor/pdfjs/pdf.min.js");
  pdfjs.GlobalWorkerOptions.workerSrc = "/static/vendor/pdfjs/pdf.worker.min.js";
  const doc = await pdfjs.getDocument({ data: await archivo.arrayBuffer() }).promise;
  if (doc.numPages > 1) ayudaPlano(`El PDF tiene ${doc.numPages} páginas: se usa la primera.`);
  const pagina = await doc.getPage(1);
  const base = pagina.getViewport({ scale: 1 });
  const escala = Math.min(4, 6000 / Math.max(base.width, base.height)); // ~300 dpi sin pasar de 6000 px
  const vista = pagina.getViewport({ scale: escala });
  const lienzo = document.createElement("canvas");
  lienzo.width = Math.round(vista.width);
  lienzo.height = Math.round(vista.height);
  const ctx = lienzo.getContext("2d");
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, lienzo.width, lienzo.height);
  await pagina.render({ canvasContext: ctx, viewport: vista }).promise;
  return lienzo.toDataURL("image/png");
}

function ayudaPlano(texto) { $("#ayuda-plano").textContent = texto || ""; }

$("#inp-plano").onchange = async (e) => {
  const archivo = e.target.files[0];
  e.target.value = "";
  if (!archivo) return;
  try {
    ayudaPlano("Leyendo el plano…");
    const url = /\.pdf$/i.test(archivo.name) || archivo.type === "application/pdf" ? await pdfAImagen(archivo) : await leerComoDataURL(archivo);
    const [ancho, alto] = await medidas(url);
    // ubicación inicial: centrado en la vista, ocupando la mitad del ancho visible
    const b = mapa.getBounds(), c = mapa.getCenter();
    const anchoVista = b.getSouthWest().distanceTo(L.latLng(b.getSouth(), b.getEast()));
    const s = (anchoVista * 0.5) / ancho;
    const georef = { lat0: c.lat + (alto / 2) * s / K_METROS, lon0: c.lng - ((ancho / 2) * s) / (K_METROS * Math.cos((c.lat * Math.PI) / 180)), kr: s, ki: 0 };
    ayudaPlano("Subiendo…");
    estado.proyecto = { ...estado.proyecto, ...(await api("POST", `/api/proyectos/${estado.proyecto.id}/planos`,
      { nombre: archivo.name.replace(/\.[^.]+$/, ""), imagen: url, ancho, alto, georef, planta: estado.planta })) };
    dibujarPlanos();
    iniciarCalibracion(estado.proyecto.planos.at(-1));
  } catch (err) {
    ayudaPlano("");
    alert(`No se pudo cargar el plano: ${err.message}`);
  }
};

// --------------------------------------------------------------------------- calibración con dos puntos

const PASOS_CALIBRACION = [
  "Calibrar 1/4: hacé clic sobre un punto reconocible del PLANO (una esquina, un poste).",
  "Calibrar 2/4: hacé clic en ese mismo punto sobre el SATÉLITE.",
  "Calibrar 3/4: hacé clic sobre un segundo punto del PLANO, lo más lejos posible del primero.",
  "Calibrar 4/4: hacé clic en ese segundo punto sobre el SATÉLITE.",
];

function iniciarCalibracion(p) {
  usarHerramienta(null);
  planos.calibrando = { plano: p, clics: [] };
  planos.marcas.clearLayers();
  p.visible = true;
  dibujarPlanos();
  document.body.classList.add("calibrando");
  ayudaPlano(`${PASOS_CALIBRACION[0]} Esc para cancelar.`);
}

function terminarCalibracion(mensaje) {
  planos.calibrando = null;
  planos.marcas.clearLayers();
  document.body.classList.remove("calibrando");
  ayudaPlano(mensaje);
}

// devuelve true si el clic fue para la calibración (app.js no lo procesa entonces)
function clicCalibracion(e) {
  const cal = planos.calibrando;
  if (!cal) return false;
  const i = cal.clics.length, enPlano = i % 2 === 0;
  cal.clics.push(enPlano ? latLngAPixel(cal.plano.georef, e.latlng) : e.latlng);
  L.circleMarker(e.latlng, { radius: 6, color: enPlano ? "#ff7043" : "#ffeb3b", weight: 3, fillOpacity: 0.3, interactive: false })
    .bindTooltip(`${enPlano ? "Plano" : "Satélite"} ${Math.floor(i / 2) + 1}`, { permanent: true, direction: "right" })
    .addTo(planos.marcas);
  if (cal.clics.length < 4) { ayudaPlano(`${PASOS_CALIBRACION[cal.clics.length]} Esc para cancelar.`); return true; }

  const [w1, z1ll, w2, z2ll] = cal.clics;
  const kx = K_METROS * Math.cos((z1ll.lat * Math.PI) / 180);
  const z2 = [(z2ll.lng - z1ll.lng) * kx, (z2ll.lat - z1ll.lat) * K_METROS]; // metros desde el satélite 1
  const dw = [w2[0] - w1[0], -(w2[1] - w1[1])]; // píxeles como complejo u − i·v
  const n = dw[0] ** 2 + dw[1] ** 2;
  if (n < 25) { terminarCalibracion("Los dos puntos del plano están demasiado cerca. Volvé a calibrar."); return true; }
  const kr = (z2[0] * dw[0] + z2[1] * dw[1]) / n, ki = (z2[1] * dw[0] - z2[0] * dw[1]) / n;
  // origen (píxel 0,0) = z1 − k·w1
  const w1c = [w1[0], -w1[1]];
  const ox = -(kr * w1c[0] - ki * w1c[1]), oy = -(kr * w1c[1] + ki * w1c[0]);
  cal.plano.georef = { lat0: z1ll.lat + oy / K_METROS, lon0: z1ll.lng + ox / kx, kr, ki };
  const giro = fmt((Math.atan2(-ki, kr) * 180) / Math.PI, 1);
  terminarCalibracion(`Plano ubicado: 1 px = ${fmt(Math.hypot(kr, ki) * 100, 1)} cm, giro ${giro}°.`);
  dibujarPlanos();
  guardarPlanos();
  return true;
}

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && planos.calibrando) terminarCalibracion("Calibración cancelada.");
});
