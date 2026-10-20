// Importación de KML/KMZ (Google Earth) y DXF (AutoCAD).
// El servidor devuelve la geometría agrupada por carpeta (KML) o capa (DXF); acá se elige qué es cada
// grupo (perímetro, muro, obstáculo, cámara…). El DXF se ubica con la calibración de dos puntos.

const imp = { datos: null, capa: L.layerGroup().addTo(mapa), georef: null };

const TIPOS_LINEA = { "": "No importar", perimetro: "Perímetro", muro: "Muro / pared", obstaculo: "Obstáculo (cerrado)", referencia: "Solo dibujo de referencia" };
const TIPOS_PUNTO = { "": "No importar", camara: "Cámara", gabinete: "Gabinete", ups: "Fuente / UPS", central: "Rack central" };

function tipoSugerido(nombre, esPunto, dxf) {
  const n = nombre.toLowerCase();
  if (esPunto) return /cam|cctv|ptz|lpr/.test(n) ? "camara" : /gab/.test(n) ? "gabinete" : /ups|fuente/.test(n) ? "ups" : "";
  if (/cerco|perim/.test(n)) return "perimetro";
  // un DXF trae decenas de capas de arquitectura (límites, árboles, muros cortina…): se eligen a mano
  if (dxf) return "";
  if (/limite|límite/.test(n)) return "perimetro";
  if (/muro|pared|medianera/.test(n)) return "muro";
  if (/edific|casa|arbol|árbol|obst|construc/.test(n)) return "obstaculo";
  return "referencia";
}

$("#inp-importar").onchange = async (e) => {
  const archivo = e.target.files[0];
  e.target.value = "";
  if (!archivo) return;
  try {
    ayudaPlano(archivo.size > 20e6 ? "Leyendo el archivo… un plano grande puede tardar un minuto." : "Leyendo el archivo…");
    imp.datos = await api("POST", `/api/importar?nombre=${encodeURIComponent(archivo.name)}`, archivo);
    imp.datos.archivo = archivo.name;
    ayudaPlano("");
    dialogoImportar();
  } catch (err) {
    ayudaPlano("");
    alert(`No se pudo importar: ${err.message}`);
  }
};

function dialogoImportar() {
  const d = imp.datos;
  const dxf = d.origen === "dxf";
  const filas = d.grupos.map((g, i) => {
    const det = [g.n_lineas && `${g.n_lineas} línea(s)`, g.n_cerradas && `${g.n_cerradas} cerrada(s)`, g.n_puntos && `${g.n_puntos} punto(s)`].filter(Boolean).join(", ");
    const sel = (tipos, def, attr) => `<select ${attr}="${i}">${Object.entries(tipos).map(([k, v]) => `<option value="${k}" ${k === def ? "selected" : ""}>${v}</option>`).join("")}</select>`;
    return `<tr><td>${esc(g.nombre)}</td><td>${det}${g.vertices > 20000 ? ` <span class="ayuda">(${fmt(g.vertices, 0)} vértices)</span>` : ""}</td>
      <td>${g.n_lineas + g.n_cerradas ? sel(TIPOS_LINEA, tipoSugerido(g.nombre, false, dxf), "data-lineas") : ""}</td>
      <td>${g.n_puntos ? sel(TIPOS_PUNTO, tipoSugerido(g.nombre, true, dxf), "data-puntos") : ""}</td></tr>`;
  }).join("");
  const unidades = dxf
    ? `<p class="ayuda">Unidades del dibujo: ${d.metros_por_unidad ? `${d.metros_por_unidad} m por unidad` : "no indicadas"}. Elegí solo las capas que necesitás (cerco, muros, CCTV); después vas a ubicar el dibujo con dos puntos, igual que un plano. Si una capa tiene símbolos de varios colores aparece separada por color.</p>`
    : `<p class="ayuda">El archivo ya está georreferenciado: se ubica solo.</p>`;
  $("#importar-cuerpo").innerHTML = `<p><b>${esc(d.archivo)}</b></p>${unidades}
    <table><tr><th>${d.origen === "dxf" ? "Capa" : "Carpeta"}</th><th>Contenido</th><th>Líneas como</th><th>Puntos como</th></tr>${filas}</table>`;
  $("#btn-importar-ok").textContent = d.origen === "dxf" ? "Ubicar en el mapa" : "Importar";
  $("#dlg-importar").showModal();
}

function eleccion() {
  const sel = (attr, i) => $(`#importar-cuerpo [${attr}="${i}"]`)?.value || "";
  return imp.datos.grupos.map((g, i) => ({ g, i, lineas: sel("data-lineas", i), puntos: sel("data-puntos", i) }))
    .filter((x) => x.lineas || x.puntos);
}

$("#btn-importar-ok").onclick = async () => {
  const elegidos = eleccion();
  if (!elegidos.length) { alert("Elegí al menos un grupo para importar."); return; }
  if (imp.datos.token) {
    // del DXF solo viajan las capas elegidas
    try {
      const { grupos } = await api("POST", `/api/importar/${imp.datos.token}`, { grupos: elegidos.map((x) => x.i) });
      elegidos.forEach((x, k) => { x.g = grupos[k]; });
    } catch (err) { alert(`No se pudo importar: ${err.message}`); return; }
  }
  $("#dlg-importar").close();
  if (imp.datos.origen === "dxf") ubicarDxf(elegidos);
  else crearElementos(elegidos, (c) => L.latLng(c[1], c[0]));
};

// DXF: el "píxel" del dibujo es (x, −y) porque en CAD el eje y va hacia arriba
function ubicarDxf(elegidos) {
  let [x0, x1, y0, y1] = [Infinity, -Infinity, Infinity, -Infinity];
  for (const { g } of elegidos) for (const c of [...g.lineas.flatMap((l) => l.coords), ...g.puntos.map((p) => p.coords)]) {
    x0 = Math.min(x0, c[0]); x1 = Math.max(x1, c[0]); y0 = Math.min(y0, c[1]); y1 = Math.max(y1, c[1]);
  }
  const b = mapa.getBounds(), c = mapa.getCenter();
  const anchoVista = b.getSouthWest().distanceTo(L.latLng(b.getSouth(), b.getEast()));
  const extension = Math.max(x1 - x0, y1 - y0, 1e-9), u = imp.datos.metros_por_unidad;
  // si las unidades declaradas dejan el dibujo diminuto o gigante (p. ej. un PDF pasado a DXF), se
  // ajusta a la vista para poder marcar los dos puntos de calibración
  const s = u && extension * u > anchoVista * 0.05 && extension * u < anchoVista * 20 ? u : (anchoVista * 0.6) / extension;
  const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2, kx = K_METROS * Math.cos((c.lat * Math.PI) / 180);
  // el centro del dibujo cae en el centro de la vista
  imp.georef = { lat0: c.lat - (cy * s) / K_METROS, lon0: c.lng - (cx * s) / kx, kr: s, ki: 0 };
  imp.elegidos = elegidos;
  vistaPreviaDxf();
  calibrar(imp, () => { vistaPreviaDxf(); barraImportar(true); }, "DIBUJO");
  planos.calibrando.cancelado = () => barraImportar(true);
  barraImportar(false);
}

const dxfALatLng = (c) => pixelALatLng(imp.georef, c[0], -c[1]);

function vistaPreviaDxf() {
  imp.capa.clearLayers();
  for (const { g, lineas, puntos } of imp.elegidos) {
    if (lineas) for (const l of g.lineas) {
      const ll = l.coords.map(dxfALatLng);
      (l.cerrada ? L.polygon(ll, { color: "#ff9800", weight: 2, fillOpacity: 0.08, interactive: false })
        : L.polyline(ll, { color: "#ff9800", weight: 2, interactive: false })).addTo(imp.capa);
    }
    if (puntos) for (const p of g.puntos) L.circleMarker(dxfALatLng(p.coords), { radius: 4, color: "#ff9800", interactive: false }).addTo(imp.capa);
  }
}

function barraImportar(visible) {
  const barra = $("#barra-importar");
  barra.hidden = !visible;
  if (!visible) return;
  const escala = Math.hypot(imp.georef.kr, imp.georef.ki), u = imp.datos.metros_por_unidad;
  const aviso = u && Math.abs(escala / u - 1) > 0.05 ? ` Escala: ${fmt(escala, 4)} m por unidad (el archivo declara ${u}; pasa en dibujos que vienen de un PDF).` : "";
  $("#barra-importar-texto").textContent = `Revisá que el dibujo naranja coincida con el satélite.${aviso}`;
}

$("#btn-barra-calibrar").onclick = () => { barraImportar(false); calibrar(imp, () => { vistaPreviaDxf(); barraImportar(true); }, "DIBUJO"); planos.calibrando.cancelado = () => barraImportar(true); };
$("#btn-barra-cancelar").onclick = () => { imp.capa.clearLayers(); barraImportar(false); ayudaPlano("Importación cancelada."); };
$("#btn-barra-importar").onclick = () => {
  barraImportar(false);
  imp.capa.clearLayers();
  crearElementos(imp.elegidos, dxfALatLng);
};

function crearElementos(elegidos, aLatLng) {
  const nuevos = [];
  const nombres = { perimetro: "Perímetro", muro: "Muro", obstaculo: "Obstáculo", referencia: "Referencia" };
  for (const { g, lineas, puntos } of elegidos) {
    if (lineas) g.lineas.forEach((l, i) => {
      const ll = l.coords.map(aLatLng).map((p) => [round7(p.lng), round7(p.lat)]);
      if (lineas === "obstaculo" && !l.cerrada) return; // un obstáculo tiene que ser un área
      const poligono = l.cerrada && ["perimetro", "obstaculo"].includes(lineas);
      const geometry = poligono ? { type: "Polygon", coordinates: [[...ll, ll[0]]] }
        : { type: "LineString", coordinates: l.cerrada ? [...ll, ll[0]] : ll };
      nuevos.push({ type: "Feature", id: uid(lineas.slice(0, 3)), geometry,
        properties: { tipo: lineas, planta: estado.planta, nombre: l.nombre || `${nombres[lineas]} ${g.nombre}${g.lineas.length > 1 ? ` ${i + 1}` : ""}` } });
    });
    if (puntos) g.puntos.forEach((p, i) => {
      const ll = aLatLng(p.coords);
      const props = { tipo: puntos, planta: estado.planta, nombre: p.nombre || `${TIPOS_PUNTO[puntos]} ${i + 1}` };
      if (puntos === "camara") Object.assign(props, { modelo: $("#dist-modelo").value, azimut: 0 });
      nuevos.push({ type: "Feature", id: uid(puntos.slice(0, 3)), geometry: { type: "Point", coordinates: [round7(ll.lng), round7(ll.lat)] }, properties: props });
    });
  }
  if (nuevos.some((f) => f.properties.tipo === "central") && porTipo("central").length) {
    alert("El proyecto ya tiene rack central: los puntos marcados como rack no se importan.");
    for (let i = nuevos.length - 1; i >= 0; i--) if (nuevos[i].properties.tipo === "central") nuevos.splice(i, 1);
  }
  const orientadas = orientarAlCerco(nuevos);
  estado.escenario.elementos.push(...nuevos);
  dibujar();
  cambio();
  const grupo = L.featureGroup(nuevos.map((f) => L.geoJSON(f)));
  if (nuevos.length) mapa.fitBounds(grupo.getBounds(), { padding: [30, 30], maxZoom: 19 });
  const camaras = nuevos.filter((f) => f.properties.tipo === "camara").length;
  const nota = !camaras ? "" : orientadas === camaras ? " Las cámaras quedaron mirando a lo largo del cerco, en el sentido del trazado."
    : ` ${orientadas ? `${orientadas} cámara(s) quedaron mirando a lo largo del cerco; las` : "Las"} demás miran al norte: giralas o redistribuí.`;
  ayudaPlano(`Importados ${nuevos.length} elemento(s).${nota}`);
}

// Una cámara importada a menos de 30 m del perímetro se orienta a lo largo del lado más cercano,
// en el mismo sentido que usa la distribución automática. Devuelve cuántas orientó.
function orientarAlCerco(nuevos) {
  const anillos = [...porTipo("perimetro"), ...nuevos.filter((f) => f.properties.tipo === "perimetro")]
    .map((f) => f.geometry.type === "Polygon" ? f.geometry.coordinates[0] : f.geometry.coordinates);
  if (!anillos.length) return 0;
  const largo = (a) => a.slice(1).reduce((s, c, i) => s + L.latLng(c[1], c[0]).distanceTo(L.latLng(a[i][1], a[i][0])), 0);
  const anillo = anillos.reduce((m, a) => (largo(a) > largo(m) ? a : m));
  const lat0 = anillo[0][1], kx = K_METROS * Math.cos((lat0 * Math.PI) / 180);
  const xy = (c) => [c[0] * kx, c[1] * K_METROS];
  const inverso = (estado.escenario.parametros || {}).sentido === "inverso";
  let n = 0;
  for (const f of nuevos) {
    if (f.properties.tipo !== "camara") continue;
    const [px, py] = xy(f.geometry.coordinates);
    let mejor = { d: 30, az: null };
    for (let i = 0; i + 1 < anillo.length; i++) {
      const [ax, ay] = xy(anillo[i]), [bx, by] = xy(anillo[i + 1]);
      const dx = bx - ax, dy = by - ay, l2 = dx * dx + dy * dy;
      if (!l2) continue;
      const u = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / l2));
      const d = Math.hypot(px - ax - u * dx, py - ay - u * dy);
      if (d < mejor.d) mejor = { d, az: (Math.atan2(dx, dy) * 180) / Math.PI };
    }
    if (mejor.az === null) continue;
    f.properties.azimut = Math.round((mejor.az + (inverso ? 180 : 0) + 360) % 360);
    n++;
  }
  return n;
}
