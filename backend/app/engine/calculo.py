"""Motor de cálculo del proyecto: distribución automática, cobertura, red, energía y listado.

Trabaja sobre el proyecto en formato GeoJSON (coordenadas [lon, lat]) y no
modifica la entrada. Los criterios replican la lógica de los proyectos de
referencia de AyT (p. ej. Cinco Lagos ABC: cámaras sobre el cerco, gabinetes
con switch PoE + ONU cada ~4 cámaras, fibra GPON y sintenax sobre el perímetro).
"""
from __future__ import annotations

import math
import uuid
from collections import Counter, defaultdict

from .geo import Proyeccion, Recorrido, dist, en_sector

PARAMETROS_DEFAULT = {
    "modelo_camara_perimetro": "dahua-ipc-hdw3849h-as-pv-28",
    "camaras_por_gabinete": 4,
    "espaciado_m": None,  # None = 90 % del alcance de analítica del modelo
    "sentido": "trazado",  # "trazado": miran en el sentido en que se dibujó el cerco; "inverso": al revés
    "angulo_quiebre": 25.0,  # giro (°) a partir del cual un vértice es esquina y lleva cámara
    "dist_min_camara_m": 2.0,  # zona ciega bajo la cámara
    "muestreo_cobertura_m": 1.0,
    "reserva_utp_m": 5.0,
    "limite_utp_m": 90.0,
    "factor_fo": 1.05,
    "reserva_fo_por_gabinete_m": 20.0,
    "factor_energia": 1.05,
    "reserva_energia_por_gabinete_m": 5.0,
    "tension_v": 220.0,
    "seccion_mm2": 10.0,
    "rho_cobre": 0.0225,  # ohm·mm²/m, cobre a temperatura de servicio (~70 °C)
    "factor_potencia": 0.9,
    "eficiencia_fuentes": 0.85,
    "consumo_gabinete_extra_w": 10.0,  # ventilación, ONU no listada, etc.
    "limite_caida_pct": 3.0,  # AEA: 3 % iluminación / 5 % fuerza motriz; se toma el conservador
    "margen_ups": 1.3,
    "dias_grabacion": 30,
    "tolerancia_perimetro_m": 30.0,  # a menos de esto un elemento se considera "sobre el cerco"
}


def _params(proyecto: dict) -> dict:
    p = dict(PARAMETROS_DEFAULT)
    p.update({k: v for k, v in (proyecto.get("parametros") or {}).items() if v is not None})
    return p


PLANTA_MAPA = "exterior"


def _en_mapa(f: dict) -> bool:
    return f.get("properties", {}).get("planta", PLANTA_MAPA) == PLANTA_MAPA


def _solo_mapa(proyecto: dict) -> dict:
    """Los cálculos sobre el mapa usan solo la planta exterior; las demás plantas tienen su propio plano."""
    return {**proyecto, "elementos": [f for f in proyecto.get("elementos", []) if _en_mapa(f)]}


def _por_tipo(proyecto: dict, tipo: str) -> list[dict]:
    return [f for f in proyecto.get("elementos", []) if f.get("properties", {}).get("tipo") == tipo]


def _anillo(feature: dict) -> tuple[list[list[float]], bool]:
    g = feature["geometry"]
    if g["type"] == "Polygon":
        return g["coordinates"][0], True
    if g["type"] == "LineString":
        return g["coordinates"], False
    raise ValueError(f"Geometría de perímetro no soportada: {g['type']}")


def _preparar(proyecto: dict):
    """Proyección local + recorrido del perímetro (el más largo si hay varios)."""
    todos = []
    for f in proyecto.get("elementos", []):
        g = f["geometry"]
        if g["type"] == "Point":
            todos.append((g["coordinates"][1], g["coordinates"][0]))
        elif g["type"] == "LineString":
            todos += [(c[1], c[0]) for c in g["coordinates"]]
        elif g["type"] == "Polygon":
            todos += [(c[1], c[0]) for c in g["coordinates"][0]]
    proj = Proyeccion.para(todos)
    recorridos = []
    for f in _por_tipo(proyecto, "perimetro"):
        coords, cerrado = _anillo(f)
        rec = Recorrido([proj.a_xy(c[1], c[0]) for c in coords], cerrado)
        if rec.largo > 0:
            recorridos.append(rec)
    recorridos.sort(key=lambda r: r.largo, reverse=True)
    return proj, (recorridos[0] if recorridos else None), recorridos


def _xy(proj: Proyeccion, f: dict) -> tuple[float, float]:
    lon, lat = f["geometry"]["coordinates"]
    return proj.a_xy(lat, lon)


def _punto(proj: Proyeccion, xy, tipo: str, **props) -> dict:
    lat, lon = proj.a_latlon(*xy)
    return {
        "type": "Feature",
        "id": f"{tipo[:3]}-{uuid.uuid4().hex[:8]}",
        "geometry": {"type": "Point", "coordinates": [round(lon, 7), round(lat, 7)]},
        "properties": {"tipo": tipo, "planta": PLANTA_MAPA, **props},
    }


# --------------------------------------------------------------------------- distribución


def distribuir_perimetro(proyecto: dict, catalogo: dict[str, dict], opciones: dict | None = None) -> list[dict]:
    """Devuelve la lista de elementos con cámaras y gabinetes generados sobre el perímetro.

    Reemplaza solo los elementos generados automáticamente (properties.auto = True);
    lo que el usuario ubicó a mano se respeta.
    """
    p = _params(proyecto)
    p.update({k: v for k, v in (opciones or {}).items() if v is not None})
    otras_plantas = [f for f in proyecto.get("elementos", []) if not _en_mapa(f)]
    proyecto = _solo_mapa(proyecto)
    proj, rec, _ = _preparar(proyecto)
    if rec is None:
        raise ValueError("Primero dibujá el perímetro.")
    modelo = catalogo.get(p["modelo_camara_perimetro"])
    if not modelo:
        raise ValueError("Modelo de cámara inexistente en el catálogo.")
    esp = float(p["espaciado_m"] or round(modelo["alcance_analitica_m"] * 0.9, 1))
    if esp <= 0:
        raise ValueError("El espaciado debe ser mayor a cero.")
    inverso = p["sentido"] == "inverso"

    conservar = otras_plantas + [f for f in proyecto.get("elementos", []) if not f["properties"].get("auto")]
    camaras, progresivas = [], []
    # Cada lado del cerco (entre quiebres marcados) arranca con una cámara en su esquina mirando
    # a lo largo del lado; así ninguna esquina queda ciega.
    for ini, fin in rec.lados(p["angulo_quiebre"]):
        largo = fin - ini
        n = max(1, math.ceil(largo / esp - 0.05))
        for k in range(n):
            s = (fin - k * largo / n) if inverso else (ini + k * largo / n)
            # en recorridos abiertos el extremo final no tiene tramo siguiente
            xy, az = rec.punto(s - 1e-6 if inverso else s + 1e-6)
            if inverso:
                az = (az + 180) % 360
            camaras.append(
                _punto(proj, xy, "camara", nombre=f"CAM {len(camaras) + 1:03d}", modelo=modelo["id"],
                       azimut=round(az, 1), auto=True)
            )
            progresivas.append(s % rec.largo if rec.cerrado else s)
    orden = sorted(range(len(camaras)), key=lambda i: progresivas[i])
    camaras = [camaras[i] for i in orden]
    progresivas = [progresivas[i] for i in orden]
    for i, c in enumerate(camaras):
        c["properties"]["nombre"] = f"CAM {i + 1:03d}"
    n = len(camaras)

    cpg = max(1, int(p["camaras_por_gabinete"]))
    gabinetes = []
    for g, ini in enumerate(range(0, n, cpg)):
        grupo = list(range(ini, min(ini + cpg, n)))
        s_med = (progresivas[grupo[0]] + progresivas[grupo[-1]]) / 2
        xy, _ = rec.punto(s_med)
        gab = _punto(proj, xy, "gabinete", nombre=f"GAB {g + 1:02d}", auto=True)
        gabinetes.append(gab)
        for i in grupo:
            camaras[i]["properties"]["gabinete"] = gab["id"]
    return conservar + gabinetes + camaras


# --------------------------------------------------------------------------- cálculo


def calcular(proyecto: dict, catalogo: dict[str, dict]) -> dict:
    proyecto = _solo_mapa(proyecto)
    p = _params(proyecto)
    proj, rec, recorridos = _preparar(proyecto)
    adv: list[str] = []
    tol = p["tolerancia_perimetro_m"]

    camaras = _por_tipo(proyecto, "camara")
    gabinetes = _por_tipo(proyecto, "gabinete")
    centrales = _por_tipo(proyecto, "central")
    ups_pts = _por_tipo(proyecto, "ups")

    def ubic(f):
        """(xy, progresiva sobre el cerco, distancia al cerco). Todo elemento se vincula al cerco
        por su punto más cercano; los cables se tienden sobre el cerco."""
        xy = _xy(proj, f)
        if rec is None:
            return xy, None, 0.0
        s, d = rec.proyectar(xy)
        return xy, s, d

    def distancia_red(a, b):
        """Distancia de cableado: por el cerco o directa (x1,2 por recorrido real), la menor."""
        (xa, sa, da), (xb, sb, db) = a, b
        directa = dist(xa, xb) * 1.2
        if rec is not None:
            return min(rec.distancia(sa, sb) + da + db, directa)
        return directa

    u_cam = {c["id"]: ubic(c) for c in camaras}
    u_gab = {g["id"]: ubic(g) for g in gabinetes}

    # ---------------- cámaras -> gabinetes
    asignacion: dict[str, list[dict]] = defaultdict(list)
    sin_modelo = 0
    for c in camaras:
        if c["properties"].get("modelo") not in catalogo:
            sin_modelo += 1
        gid = c["properties"].get("gabinete")
        if gid not in u_gab:
            gid = min(u_gab, key=lambda g: distancia_red(u_cam[c["id"]], u_gab[g]), default=None)
        if gid:
            asignacion[gid].append(c)
    if sin_modelo:
        adv.append(f"{sin_modelo} cámara(s) sin modelo de catálogo: no suman consumo ni ancho de banda.")
    if camaras and not gabinetes:
        adv.append("Hay cámaras pero ningún gabinete: no se puede calcular UTP ni switches.")

    switches = sorted(
        (m for m in catalogo.values() if m["categoria"] == "switch" and m.get("uso") == "gabinete"),
        key=lambda m: (m["puertos_poe"], m["budget_w"]),
    )

    det_gab, utp_total, cajas_utp_max = [], 0.0, 0.0
    for g in gabinetes:
        cams = asignacion.get(g["id"], [])
        poe = sum(catalogo.get(c["properties"].get("modelo"), {}).get("consumo_w", 0) for c in cams)
        utps = [distancia_red(u_cam[c["id"]], u_gab[g["id"]]) + p["reserva_utp_m"] for c in cams]
        utp_total += sum(utps)
        utp_max = max(utps, default=0.0)
        cajas_utp_max = max(cajas_utp_max, utp_max)
        sw = next((m for m in switches if m["puertos_poe"] >= len(cams) and m["budget_w"] >= poe), None)
        nombre = g["properties"].get("nombre") or g["id"]
        if cams and sw is None:
            adv.append(f"{nombre}: ningún switch del catálogo soporta {len(cams)} cámaras / {poe:.0f} W PoE.")
        if utp_max > p["limite_utp_m"]:
            adv.append(f"{nombre}: tramo UTP de {utp_max:.0f} m supera el límite de {p['limite_utp_m']:.0f} m.")
        consumo = poe + (sw["consumo_w"] if sw else 0) + p["consumo_gabinete_extra_w"]
        consumo += catalogo.get("tplink-xz000-g7", {}).get("consumo_w", 0)
        det_gab.append({
            "id": g["id"], "nombre": nombre, "camaras": len(cams), "poe_w": round(poe, 1),
            "switch": sw["modelo"] if sw else None, "switch_id": sw["id"] if sw else None,
            "utp_max_m": round(utp_max, 1), "consumo_w": round(consumo, 1),
        })

    # ---------------- fibra y energía: ramales desde cada fuente sobre el perímetro
    origen_fo = centrales[0] if centrales else None
    if gabinetes and not origen_fo:
        adv.append("Ubicá el rack central para calcular fibra y energía.")

    def ramales(fuente_ids: list[str], u_fuentes: dict):
        """Asigna cada gabinete a su fuente más cercana y arma ramales ordenados por distancia."""
        out: dict[tuple[str, int], list[tuple[float, dict]]] = defaultdict(list)
        for dg in det_gab:
            ug = u_gab[dg["id"]]
            fid = min(fuente_ids, key=lambda f: distancia_red(ug, u_fuentes[f]))
            uf = u_fuentes[fid]
            if rec is not None:
                av = rec.avance(uf[1], ug[1])
                out[(fid, 1 if av >= 0 else -1)].append((abs(av) + ug[2] + uf[2], dg))
            else:
                out[(fid, 0)].append((distancia_red(ug, uf), dg))
        for k in out:
            out[k].sort(key=lambda t: t[0])
        return out

    fibra = {"tramos": [], "total_m": 0.0}
    energia = []
    if origen_fo and det_gab:
        u_c = {origen_fo["id"]: ubic(origen_fo)}
        for (fid, sentido), lista in ramales([origen_fo["id"]], u_c).items():
            # sentido 0 = sin perímetro: un cable por gabinete (estrella)
            largo = sum(d for d, _ in lista) if sentido == 0 else lista[-1][0]
            largo = largo * p["factor_fo"] + p["reserva_fo_por_gabinete_m"] * len(lista)
            fibra["tramos"].append({"sentido": {1: "horario", -1: "antihorario", 0: "directo"}[sentido],
                                    "gabinetes": len(lista), "largo_m": round(largo, 1)})
            fibra["total_m"] += largo
        fibra["total_m"] = round(fibra["total_m"], 1)

        fuentes = [origen_fo] + ups_pts
        u_f = {f["id"]: ubic(f) for f in fuentes}
        nombres_f = {f["id"]: f["properties"].get("nombre") or ("Rack central" if f is origen_fo else f["id"])
                     for f in fuentes}
        por_fuente: dict[str, dict] = {}
        for (fid, sentido), lista in ramales(list(u_f), u_f).items():
            ef = p["eficiencia_fuentes"]
            cargas = [dg["consumo_w"] / ef / (p["tension_v"] * p["factor_potencia"]) for _, dg in lista]
            caida_v, prev, peor = 0.0, 0.0, 0.0
            if sentido == 0:
                for (d, dg), i in zip(lista, cargas):
                    v = 2 * p["rho_cobre"] * d * i / p["seccion_mm2"]
                    dg["caida_pct"] = round(v / p["tension_v"] * 100, 2)
                    peor = max(peor, dg["caida_pct"])
                largo = sum(d for d, _ in lista)
            else:
                for k, (d, dg) in enumerate(lista):
                    i_tramo = sum(cargas[k:])
                    caida_v += 2 * p["rho_cobre"] * (d - prev) * i_tramo / p["seccion_mm2"]
                    prev = d
                    dg["caida_pct"] = round(caida_v / p["tension_v"] * 100, 2)
                    peor = max(peor, dg["caida_pct"])
                largo = lista[-1][0]
            for _, dg in lista:
                dg["fuente"] = nombres_f[fid]
            largo = largo * p["factor_energia"] + p["reserva_energia_por_gabinete_m"] * len(lista)
            e = por_fuente.setdefault(fid, {"fuente": nombres_f[fid], "ramales": [], "carga_va": 0.0,
                                            "cable_m": 0.0, "caida_max_pct": 0.0})
            e["ramales"].append({"sentido": {1: "horario", -1: "antihorario", 0: "directo"}[sentido],
                                 "gabinetes": len(lista), "largo_m": round(largo, 1),
                                 "caida_max_pct": round(peor, 2)})
            e["carga_va"] += sum(dg["consumo_w"] for _, dg in lista) / ef / p["factor_potencia"]
            e["cable_m"] += largo
            e["caida_max_pct"] = max(e["caida_max_pct"], round(peor, 2))
        ups_cat = sorted((m for m in catalogo.values() if m["categoria"] == "ups"), key=lambda m: m["potencia_va"])
        for e in por_fuente.values():
            req = e["carga_va"] * p["margen_ups"]
            ups = next((m for m in ups_cat if m["potencia_va"] >= req), None)
            e.update(carga_va=round(e["carga_va"]), cable_m=round(e["cable_m"], 1),
                     ups_sugerida=ups["modelo"] if ups else None, ups_id=ups["id"] if ups else None)
            if e["caida_max_pct"] > p["limite_caida_pct"]:
                adv.append(f"{e['fuente']}: caída de tensión de {e['caida_max_pct']}% supera el "
                           f"{p['limite_caida_pct']}% con {p['seccion_mm2']} mm². Subí la sección o agregá una fuente.")
            if not ups:
                adv.append(f"{e['fuente']}: la carga ({req:.0f} VA con margen) supera las UPS del catálogo.")
            energia.append(e)

    # ---------------- cobertura sobre el perímetro
    cobertura = {"pct": None, "huecos": [], "largo_m": round(sum(r.largo for r in recorridos), 1)}
    sectores = []
    for c in camaras:
        m = catalogo.get(c["properties"].get("modelo"))
        if not m:
            continue
        alcance = c["properties"].get("alcance") or m["alcance_analitica_m"]
        sectores.append((u_cam[c["id"]][0], float(c["properties"].get("azimut", 0)), m["hfov"],
                         p["dist_min_camara_m"], float(alcance)))
    if recorridos:
        paso = max(0.25, float(p["muestreo_cobertura_m"]))
        cubierto_total = 0.0
        for r in recorridos:
            n = max(1, int(r.largo / paso))
            estado = []
            for i in range(n + (0 if r.cerrado else 1)):
                s = min(i * paso, r.largo)
                xy, _ = r.punto(s)
                estado.append((s, any(en_sector(o, az, hf, dmin, dmax, xy) for o, az, hf, dmin, dmax in sectores)))
            cubierto_total += sum(1 for _, ok in estado if ok) / len(estado) * r.largo
            # agrupar huecos contiguos
            hueco = None
            for s, ok in estado + [(r.largo, True)]:
                if not ok and hueco is None:
                    hueco = s
                elif ok and hueco is not None:
                    if s - hueco >= paso * 2:
                        pts = [r.punto(hueco + (s - hueco) * k / 8)[0] for k in range(9)]
                        cobertura["huecos"].append({
                            "desde_m": round(hueco, 1), "largo_m": round(s - hueco, 1),
                            "coords": [list(reversed([round(v, 7) for v in proj.a_latlon(*q)])) for q in pts],
                        })
                    hueco = None
        cobertura["pct"] = round(cubierto_total / cobertura["largo_m"] * 100, 1) if cobertura["largo_m"] else None
        if cobertura["huecos"]:
            largo_h = sum(h["largo_m"] for h in cobertura["huecos"])
            adv.append(f"Perímetro sin cobertura analítica: {len(cobertura['huecos'])} tramo(s), {largo_h:.0f} m en total.")

    # ---------------- red y grabación
    mbps = sum(catalogo.get(c["properties"].get("modelo"), {}).get("bitrate_mbps", 0) for c in camaras)
    tb = mbps * 86400 * p["dias_grabacion"] / 8 / 1e6
    red = {"mbps_total": round(mbps, 1), "almacenamiento_tb": round(tb, 1), "dias_grabacion": p["dias_grabacion"],
           "pon_requeridos": math.ceil(len(gabinetes) / 64) if gabinetes else 0}

    # ---------------- listado de equipos y materiales
    lista: list[dict] = []

    def item(cat, desc, cant, unidad="u", modelo=""):
        if cant:
            # clave estable: permite guardar ediciones manuales del cómputo que sobreviven al recálculo
            clave = "|".join((cat, desc.split(" (")[0], modelo)).lower()
            lista.append({"clave": clave, "categoria": cat, "descripcion": desc, "modelo": modelo,
                          "cantidad": cant, "unidad": unidad})

    for mid, cant in Counter(c["properties"].get("modelo") for c in camaras).most_common():
        m = catalogo.get(mid, {})
        item("CCTV", "Cámara", cant, modelo=m.get("modelo", mid or "sin modelo"))
    sobre_cerco = sum(1 for c in camaras if rec is not None and u_cam[c["id"]][2] <= tol)
    item("CCTV", "Brazo de caño metálico para cámara en poste", sobre_cerco)
    item("CCTV", "Canalización exterior en poste (caño flexible)", sobre_cerco)
    item("CCTV", "Licencia de canal de video", len(camaras))
    for sid, cant in Counter(d["switch_id"] for d in det_gab if d["switch_id"]).most_common():
        item("Red", "Switch PoE de gabinete", cant, modelo=catalogo[sid]["modelo"])
    item("Red", "Gabinete completo (térmica, disyuntor, zapatilla, PAT)", len(gabinetes))
    item("Red", "ONU GPON", len(gabinetes), modelo=catalogo.get("tplink-xz000-g7", {}).get("modelo", ""))
    item("Red", "Cable UTP Cat5e exterior", math.ceil(utp_total), "m")
    item("Red", "Cajas UTP de 305 m", math.ceil(utp_total / 305) if utp_total else 0, "u")
    if centrales:
        item("Central", "Rack principal 40U", 1, modelo="GLC-RACKP-40U-600")
        item("Central", "Router", 1, modelo=catalogo.get("mikrotik-ccr2004-16g-2s", {}).get("modelo", ""))
        item("Central", "Switch core PoE 24p", 1, modelo=catalogo.get("dahua-pfs4226-24gt-370", {}).get("modelo", ""))
        if gabinetes:
            item("Central", "OLT GPON", 1, modelo=catalogo.get("tplink-ds-p7001-08", {}).get("modelo", ""))
        item("Central", f"Servidor de grabación ({tb:.0f} TB para {p['dias_grabacion']} días)", 1)
    item("Fibra", "Fibra óptica (tendido y conexión)", math.ceil(fibra["total_m"]), "m")
    total_energia = sum(e["cable_m"] for e in energia)
    item("Energía", f"Cable sintenax 2x{p['seccion_mm2']:g} mm² (tendido y conexión)", math.ceil(total_energia), "m")
    for uid, cant in Counter(e["ups_id"] for e in energia if e.get("ups_id")).most_common():
        item("Energía", "UPS", cant, modelo=catalogo[uid]["modelo"])

    resumen = {
        "perimetro_m": cobertura["largo_m"],
        "camaras": len(camaras),
        "gabinetes": len(gabinetes),
        "cobertura_pct": cobertura["pct"],
        "fibra_m": fibra["total_m"],
        "energia_m": round(total_energia, 1),
        "utp_m": round(utp_total, 1),
        "mbps_total": red["mbps_total"],
        "almacenamiento_tb": red["almacenamiento_tb"],
    }
    return {"resumen": resumen, "advertencias": adv, "gabinetes": det_gab, "fibra": fibra,
            "energia": energia, "cobertura": cobertura, "red": red, "materiales": lista, "parametros": p}
