// Importación de KML/KMZ (Google Earth) y DXF (AutoCAD).
// El servidor devuelve la geometría agrupada por carpeta (KML) o capa (DXF); acá se elige qué es cada
// grupo (perímetro, muro, obstáculo, cámara…). El DXF se ubica con la calibración de dos puntos.

const imp = { datos: null, capa: L.layerGroup().addTo(mapa), georef: null };

const TIPOS_LINEA = { "": "No importar", perimetro: "Perímetro", muro: "Muro / pared", obstaculo: "Obstáculo (cerrado)", referencia: "Solo dibujo de referencia" };
const TIPOS_PUNTO = { "": "No importar", camara: "Cámara", gabinete: "Gabinete", ups: "Fuente / UPS", central: "Rack central" };

function tipoSugerido(nombre, esPunto) {
  const n = nombre.toLowerCase();
  if (esPunto) return /cam|cctv|ptz|lpr/.test(n) ? "camara" : /gab/.test(n) ? "gabinete" : /ups|fuente/.test(n) ? "ups" : "";
  if (/cerco|perim|limite|límite/.test(n)) return "perimetro";
  if (/muro|pared|medianera/.test(n)) return "muro";
  if (/edific|casa|arbol|árbol|obst|construc/.test(n)) return "obstaculo";
  return "referencia";
}

$("#inp-importar").onchange = async (e) => {
  const archivo = e.target.files[0];
  e.target.value = "";
  if (!archivo) return;
  try {
    ayudaPlano("Leyendo el archivo…");
    const contenido = await leerComoDataURL(archivo);
    imp.datos = await api("POST", "/api/importar", { nombre: archivo.name, contenido });
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
  const filas = d.grupos.map((g, i) => {
    const cerradas = g.lineas.filter((l) => l.cerrada).length, abiertas = g.lineas.length - cerradas;
    const det = [abiertas && `${abiertas} línea(s)`, cerradas && `${cerradas} cerrada(s)`, g.puntos.length && `${g.puntos.length} punto(s)`].filter(Boolean).join(", ");
    const sel = (tipos, def, attr) => `<select ${attr}="${i}">${Object.entries(tipos).map(([k, v]) => `<option value="${k}" ${k === def ? "selected" : ""}>${v}</option>`).join("")}</select>`;
    return `<tr><td>${esc(g.nombre)}</td><td>${det}</td>
      <td>${g.lineas.length ? sel(TIPOS_LINEA, tipoSugerido(g.nombre, false), "data-lineas") : ""}</td>
      <td>${g.puntos.length ? sel(TIPOS_PUNTO, tipoSugerido(g.nombre, true), "data-puntos") : ""}</td></tr>`;
  }).join("");
  const unidades = d.origen === "dxf"
    ? `<p class="ayuda">Unidades del dibujo: ${d.metros_por_unidad ? `${d.metros_por_unidad} m por unidad` : "no indicadas"}. Después de elegir las capas vas a ubicar el dibujo con dos puntos, igual que un plano.</p>`
    : `<p class="ayuda">El archivo ya está georreferenciado: se ubica solo.</p>`;
  $("#importar-cuerpo").innerHTML = `<p><b>${esc(d.archivo)}</b></p>${unidades}
    <table><tr><th>${d.origen === "dxf" ? "Capa" : "Carpeta"}</th><th>Contenido</th><th>Líneas como</th><th>Puntos como</th></tr>${filas}</table>`;
  $("#btn-importar-ok").textContent = d.origen === "dxf" ? "Ubicar en el mapa" : "Importar";
  $("#dlg-importar").showModal();
}

function eleccion() {
  const sel = (attr, i) => $(`#importar-cuerpo [${attr}="${i}"]`)?.value || "";
  return imp.datos.grupos.map((g, i) => ({ g, lineas: sel("data-lineas", i), puntos: sel("data-puntos", i) }))
    .filter((x) => x.lineas || x.puntos);
}

$("#btn-importar-ok").onclick = () => {
  const elegidos = eleccion();
  if (!elegidos.length) { alert("Elegí al menos un grupo para importar."); return; }
  $("#dlg-importar").close();
  if (imp.datos.origen === "dxf") ubicarDxf(elegidos);
  else crearElementos(elegidos, (c) => L.latLng(c[1], c[0]));
};

// DXF: el "píxel" del dibujo es (x, −y) porque en CAD el eje y va hacia arriba
function ubicarDxf(elegidos) {
  const todos = elegidos.flatMap(({ g }) => [...g.lineas.flatMap((l) => l.coords), ...g.puntos.map((p) => p.coords)]);
  const xs = todos.map((c) => c[0]), ys = todos.map((c) => c[1]);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const b = mapa.getBounds(), c = mapa.getCenter();
  const anchoVista = b.getSouthWest().distanceTo(L.latLng(b.getSouth(), b.getEast()));
  const s = imp.datos.metros_por_unidad || (anchoVista * 0.6) / Math.max(x1 - x0, y1 - y0, 1e-9);
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
  const aviso = u && Math.abs(escala / u - 1) > 0.05 ? ` La escala calibrada difiere ${fmt(Math.abs(escala / u - 1) * 100, 0)} % de las unidades del dibujo.` : "";
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
  estado.escenario.elementos.push(...nuevos);
  dibujar();
  cambio();
  const grupo = L.featureGroup(nuevos.map((f) => L.geoJSON(f)));
  if (nuevos.length) mapa.fitBounds(grupo.getBounds(), { padding: [30, 30], maxZoom: 19 });
  ayudaPlano(`Importados ${nuevos.length} elemento(s). Las cámaras importadas quedan mirando al norte: giralas o redistribuí.`);
}
