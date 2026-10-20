"""Lectura de KML/KMZ (Google Earth) y DXF (AutoCAD) para importar geometría al proyecto.

Devuelve grupos de geometría que la interfaz deja asignar a un tipo de elemento (perímetro, muro,
obstáculo, cámara…). KML ya viene en lat/lon; DXF viene en coordenadas del dibujo y se ubica sobre
el mapa con la misma calibración de dos puntos que los planos.
"""
from __future__ import annotations

import io
import math
import zipfile
from xml.etree import ElementTree as ET

# $INSUNITS de AutoCAD → metros por unidad
UNIDADES_DXF = {0: None, 1: 0.0254, 2: 0.3048, 4: 0.001, 5: 0.01, 6: 1.0, 7: 1000.0, 14: 0.1}
MAX_VERTICES = 200_000


class ErrorImportacion(Exception):
    pass


def _grupo(grupos: dict, nombre: str) -> dict:
    return grupos.setdefault(nombre, {"nombre": nombre, "puntos": [], "lineas": []})


def _resultado(grupos: dict, **extra) -> dict:
    lista = [g for g in grupos.values() if g["puntos"] or g["lineas"]]
    if not lista:
        raise ErrorImportacion("El archivo no tiene puntos, líneas ni polígonos que se puedan importar.")
    return {"grupos": lista, **extra}


# --------------------------------------------------------------------------- KML / KMZ


def _coords_kml(texto: str) -> list[list[float]]:
    pts = []
    for t in (texto or "").split():
        partes = t.split(",")
        if len(partes) >= 2:
            pts.append([round(float(partes[0]), 8), round(float(partes[1]), 8)])
    return pts


def leer_kml(datos: bytes, nombre_archivo: str = "") -> dict:
    if datos[:2] == b"PK":  # KMZ: zip con un .kml adentro
        with zipfile.ZipFile(io.BytesIO(datos)) as z:
            kml = next((n for n in z.namelist() if n.lower().endswith(".kml")), None)
            if not kml:
                raise ErrorImportacion("El KMZ no contiene un archivo KML.")
            datos = z.read(kml)
    try:
        raiz = ET.fromstring(datos)
    except ET.ParseError as e:
        raise ErrorImportacion(f"KML inválido: {e}") from e

    def local(el):
        return el.tag.rsplit("}", 1)[-1]

    grupos: dict[str, dict] = {}

    def recorrer(el, carpeta: str):
        for hijo in el:
            t = local(hijo)
            if t in ("Folder", "Document"):
                nombre = next((c.text for c in hijo if local(c) == "name" and c.text), None)
                recorrer(hijo, nombre.strip() if t == "Folder" and nombre else carpeta)
            elif t == "Placemark":
                nombre = next((c.text.strip() for c in hijo if local(c) == "name" and c.text), "")
                for g in hijo.iter():
                    k = local(g)
                    if k not in ("Point", "LineString", "LinearRing"):
                        continue
                    coords = _coords_kml(next((c.text for c in g if local(c) == "coordinates"), ""))
                    if not coords:
                        continue
                    if k == "Point":
                        _grupo(grupos, carpeta or "Puntos")["puntos"].append({"coords": coords[0], "nombre": nombre})
                    else:
                        cerrada = k == "LinearRing" or (len(coords) > 3 and coords[0] == coords[-1])
                        defecto = "Polígonos" if cerrada else "Líneas"
                        _grupo(grupos, carpeta or defecto)["lineas"].append(
                            {"coords": coords, "cerrada": cerrada, "nombre": nombre})
            else:
                recorrer(hijo, carpeta)

    recorrer(raiz, "")
    return _resultado(grupos, origen="kml", georreferenciado=True)


# --------------------------------------------------------------------------- DXF


def unir_tramos(lineas: list[dict], tol: float) -> list[dict]:
    """Une líneas abiertas que comparten extremos (un cerco dibujado con LINE sueltas queda como una
    sola polilínea). Si una cadena termina donde empezó, queda cerrada."""
    abiertas = [dict(l, coords=list(l["coords"])) for l in lineas if not l["cerrada"]]
    resultado = [l for l in lineas if l["cerrada"]]
    cerca = lambda a, b: abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol  # noqa: E731
    while abiertas:
        cadena = abiertas.pop()
        creció = True
        while creció:
            creció = False
            for i, l in enumerate(abiertas):
                c = l["coords"]
                if cerca(cadena["coords"][-1], c[0]):
                    cadena["coords"] += c[1:]
                elif cerca(cadena["coords"][-1], c[-1]):
                    cadena["coords"] += c[::-1][1:]
                elif cerca(cadena["coords"][0], c[-1]):
                    cadena["coords"] = c[:-1] + cadena["coords"]
                elif cerca(cadena["coords"][0], c[0]):
                    cadena["coords"] = c[::-1][:-1] + cadena["coords"]
                else:
                    continue
                abiertas.pop(i)
                creció = True
                break
        if len(cadena["coords"]) > 3 and cerca(cadena["coords"][0], cadena["coords"][-1]):
            cadena["coords"] = cadena["coords"][:-1]
            cadena["cerrada"] = True
        resultado.append(cadena)
    return resultado


def _arco(cx, cy, r, a0, a1, segmentos_por_vuelta=48):
    if a1 <= a0:
        a1 += 360
    n = max(2, int(math.ceil((a1 - a0) / 360 * segmentos_por_vuelta)))
    return [[cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))] for i in range(n + 1)]


def leer_dxf(datos: bytes) -> dict:
    try:
        import ezdxf
        from ezdxf import recover
    except ImportError as e:  # pragma: no cover - dependencia declarada en requirements.txt
        raise ErrorImportacion("Falta la librería ezdxf en el servidor (pip install -r requirements.txt).") from e
    if datos[:6] == b"AC1015" or datos[:4] == b"AC10":
        raise ErrorImportacion("Es un archivo DWG. Desde AutoCAD usá Guardar como → DXF y cargá ese archivo.")
    try:
        doc, _ = recover.read(io.BytesIO(datos))
    except (ezdxf.DXFStructureError, ValueError) as e:
        raise ErrorImportacion(f"DXF inválido: {e}") from e

    unidades = UNIDADES_DXF.get(int(doc.header.get("$INSUNITS", 0) or 0))
    grupos: dict[str, dict] = {}
    vertices = 0

    def agregar_linea(capa, pts, cerrada):
        nonlocal vertices
        pts = [[round(x, 4), round(y, 4)] for x, y in pts]
        if len(pts) < 2:
            return
        vertices += len(pts)
        if vertices > MAX_VERTICES:
            raise ErrorImportacion("El dibujo es demasiado grande. Dejá solo las capas de cercos y muros y volvé a exportar.")
        _grupo(grupos, capa)["lineas"].append({"coords": pts, "cerrada": cerrada, "nombre": ""})

    def procesar(e, capa_bloque=None):
        capa = e.dxf.get("layer", "0") if capa_bloque is None or e.dxf.get("layer", "0") != "0" else capa_bloque
        t = e.dxftype()
        if t == "LINE":
            agregar_linea(capa, [(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)], False)
        elif t == "LWPOLYLINE":
            agregar_linea(capa, [p[:2] for p in e.get_points("xy")], bool(e.closed))
        elif t == "POLYLINE" and not (e.is_polygon_mesh or e.is_poly_face_mesh):
            agregar_linea(capa, [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices], bool(e.is_closed))
        elif t == "CIRCLE":
            c = e.dxf.center
            agregar_linea(capa, _arco(c[0], c[1], e.dxf.radius, 0, 360), True)
        elif t == "ARC":
            c = e.dxf.center
            agregar_linea(capa, _arco(c[0], c[1], e.dxf.radius, e.dxf.start_angle, e.dxf.end_angle), False)
        elif t in ("POINT",):
            _grupo(grupos, capa)["puntos"].append({"coords": [round(e.dxf.location[0], 4), round(e.dxf.location[1], 4)], "nombre": ""})
        elif t == "INSERT":
            # un bloque (p. ej. símbolo de cámara) se toma como un punto con el nombre del bloque
            _grupo(grupos, capa)["puntos"].append({"coords": [round(e.dxf.insert[0], 4), round(e.dxf.insert[1], 4)],
                                                    "nombre": e.dxf.name})

    for e in doc.modelspace():
        try:
            procesar(e)
        except ErrorImportacion:
            raise
        except Exception:  # noqa: BLE001 - una entidad rara no frena la importación
            continue
    tol = 0.01 / unidades if unidades else 0.01  # 1 cm
    for g in grupos.values():
        g["lineas"] = unir_tramos(g["lineas"], tol)
    return _resultado(grupos, origen="dxf", georreferenciado=False, metros_por_unidad=unidades)
