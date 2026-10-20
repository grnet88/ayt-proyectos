"""Lectura de KML/KMZ (Google Earth) y DXF (AutoCAD) para importar geometría al proyecto.

Devuelve grupos de geometría que la interfaz deja asignar a un tipo de elemento (perímetro, muro,
obstáculo, cámara…). KML ya viene en lat/lon; DXF viene en coordenadas del dibujo y se ubica sobre
el mapa con la misma calibración de dos puntos que los planos.
"""
from __future__ import annotations

import io
import math
import zipfile
from pathlib import Path
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
    sola polilínea). Si una cadena termina donde empezó, queda cerrada. Los extremos se indexan en
    una grilla de lado tol, así un plano con cientos de miles de tramos se une en segundos."""
    abiertas = [dict(l, coords=list(l["coords"])) for l in lineas if not l["cerrada"]]
    resultado = [l for l in lineas if l["cerrada"]]
    celda = lambda p: (math.floor(p[0] / tol), math.floor(p[1] / tol))  # noqa: E731
    indice: dict[tuple, set] = {}
    for i, l in enumerate(abiertas):
        for p in (l["coords"][0], l["coords"][-1]):
            indice.setdefault(celda(p), set()).add(i)
    usadas = [False] * len(abiertas)

    def vecina(p, propia):
        cx, cy = celda(p)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in indice.get((cx + dx, cy + dy), ()):
                    if j != propia and not usadas[j]:
                        c = abiertas[j]["coords"]
                        for q in (c[0], c[-1]):
                            if abs(p[0] - q[0]) <= tol and abs(p[1] - q[1]) <= tol:
                                return j
        return None

    for i in range(len(abiertas) - 1, -1, -1):
        if usadas[i]:
            continue
        usadas[i] = True
        cadena = abiertas[i]
        coords = cadena["coords"]
        for extremo in ("fin", "inicio"):
            while True:
                p = coords[-1] if extremo == "fin" else coords[0]
                j = vecina(p, i)
                if j is None:
                    break
                usadas[j] = True
                c = abiertas[j]["coords"]
                cerca_ini = abs(p[0] - c[0][0]) <= tol and abs(p[1] - c[0][1]) <= tol
                if extremo == "fin":
                    coords += (c if cerca_ini else c[::-1])[1:]
                else:
                    coords[:0] = (c[::-1] if cerca_ini else c)[:-1]
        cerca = abs(coords[0][0] - coords[-1][0]) <= tol and abs(coords[0][1] - coords[-1][1]) <= tol
        if len(coords) > 3 and cerca:
            coords.pop()
            cadena["cerrada"] = True
        resultado.append(cadena)
    return resultado


def _arco(cx, cy, r, a0, a1, segmentos_por_vuelta=48):
    if a1 <= a0:
        a1 += 360
    n = max(2, int(math.ceil((a1 - a0) / 360 * segmentos_por_vuelta)))
    return [[cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))] for i in range(n + 1)]


MAX_VERTICES_ARCHIVO = 20_000_000


def _unidades_dxf(ruta: Path):
    """$INSUNITS del encabezado, sin cargar todo el archivo (el HEADER está al principio)."""
    with open(ruta, "rb") as fh:
        lineas = fh.read(4 * 1024 * 1024).decode("latin-1").splitlines()
    for i, l in enumerate(lineas[:-2]):
        if l.strip() == "$INSUNITS":
            try:
                return UNIDADES_DXF.get(int(lineas[i + 2].strip()))
            except ValueError:
                return None
        if l.strip() == "ENTITIES":
            break
    return None


def _centro(pts):
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return [round((min(xs) + max(xs)) / 2, 4), round((min(ys) + max(ys)) / 2, 4)]


def _puntos_hatch(e):
    pts = []
    for camino in e.paths:
        if hasattr(camino, "vertices"):
            pts += [(v[0], v[1]) for v in camino.vertices]
        for borde in getattr(camino, "edges", []):
            for attr in ("start", "end", "center"):
                v = getattr(borde, attr, None)
                if v is not None:
                    pts.append((v[0], v[1]))
    return pts


def _entidades(ruta: Path):
    """Entidades del modelspace leídas de a una (un DXF de 100 MB entra en ~50 MB de memoria).
    Si el archivo tiene errores de estructura se cae al lector tolerante de ezdxf."""
    import ezdxf
    from ezdxf.addons import iterdxf
    try:
        yield from iterdxf.modelspace(str(ruta))
        return
    except (ezdxf.DXFStructureError, ValueError, KeyError, IndexError):
        pass
    from ezdxf import recover
    try:
        doc, _ = recover.readfile(str(ruta))
    except (ezdxf.DXFStructureError, ValueError) as e:
        raise ErrorImportacion(f"DXF inválido: {e}") from e
    yield from doc.modelspace()


def leer_dxf(origen) -> dict:
    """Lee un DXF (ruta o bytes) y devuelve toda su geometría agrupada por capa.

    Los rellenos (HATCH, SOLID) se toman como un punto en su centro: en planos exportados desde
    PDF los símbolos de cámaras y gabinetes suelen quedar así."""
    try:
        import ezdxf  # noqa: F401
    except ImportError as e:  # pragma: no cover - dependencia declarada en requirements.txt
        raise ErrorImportacion("Falta la librería ezdxf en el servidor (pip install -r requirements.txt).") from e
    if isinstance(origen, (bytes, bytearray)):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "dibujo.dxf"
            ruta.write_bytes(origen)
            return leer_dxf(ruta)
    ruta = Path(origen)
    with open(ruta, "rb") as fh:
        if fh.read(4) == b"AC10":
            raise ErrorImportacion("Es un archivo DWG. Desde AutoCAD usá Guardar como → DXF y cargá ese archivo.")

    unidades = _unidades_dxf(ruta)
    grupos: dict[str, dict] = {}
    vertices = 0
    colores: dict[str, list] = {}  # color de cada punto, para separar símbolos de una misma capa

    def agregar_linea(capa, pts, cerrada):
        nonlocal vertices
        pts = [[round(x, 4), round(y, 4)] for x, y in pts]
        if len(pts) < 2:
            return
        vertices += len(pts)
        if vertices > MAX_VERTICES_ARCHIVO:
            raise ErrorImportacion("El dibujo es demasiado grande. Dejá solo las capas de cercos, muros y CCTV y volvé a exportar.")
        _grupo(grupos, capa)["lineas"].append({"coords": pts, "cerrada": cerrada, "nombre": ""})

    def agregar_punto(capa, xy, nombre="", color=None):
        _grupo(grupos, capa)["puntos"].append({"coords": [round(xy[0], 4), round(xy[1], 4)], "nombre": nombre})
        colores.setdefault(capa, []).append(color)

    def procesar(e):
        capa = e.dxf.get("layer", "0")
        t = e.dxftype()
        if t == "LINE":
            agregar_linea(capa, [(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)], False)
        elif t == "LWPOLYLINE":
            agregar_linea(capa, [p[:2] for p in e.get_points("xy")], bool(e.closed))
        elif t == "POLYLINE" and not (e.is_polygon_mesh or e.is_poly_face_mesh):
            agregar_linea(capa, [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices], bool(e.is_closed))
        elif t == "CIRCLE":
            c = e.dxf.center
            agregar_linea(capa, _arco(c.x, c.y, e.dxf.radius, 0, 360), True)
        elif t == "ARC":
            c = e.dxf.center
            agregar_linea(capa, _arco(c.x, c.y, e.dxf.radius, e.dxf.start_angle, e.dxf.end_angle), False)
        elif t == "POINT":
            agregar_punto(capa, (e.dxf.location.x, e.dxf.location.y))
        elif t == "INSERT":
            # un bloque (p. ej. símbolo de cámara) se toma como un punto con el nombre del bloque
            agregar_punto(capa, (e.dxf.insert.x, e.dxf.insert.y), e.dxf.name, e.dxf.get("color"))
        elif t == "HATCH":
            pts = _puntos_hatch(e)
            if pts:
                agregar_punto(capa, _centro(pts), color=e.dxf.get("color"))
        elif t == "SOLID":
            pts = [(e.dxf.get(f"vtx{i}").x, e.dxf.get(f"vtx{i}").y) for i in range(4) if e.dxf.hasattr(f"vtx{i}")]
            if pts:
                agregar_punto(capa, _centro(pts), color=e.dxf.get("color"))

    for e in _entidades(ruta):
        try:
            procesar(e)
        except ErrorImportacion:
            raise
        except Exception:  # noqa: BLE001 - una entidad rara no frena la importación
            continue
    tol = 0.01 / unidades if unidades else 0.01  # 1 cm
    for g in grupos.values():
        g["lineas"] = unir_tramos(g["lineas"], tol)
    _separar_por_color(grupos, colores)
    return _resultado(grupos, origen="dxf", georreferenciado=False, metros_por_unidad=unidades)


def _separar_por_color(grupos: dict, colores: dict) -> None:
    """Si en una capa hay símbolos de varios colores (cámaras amarillas, gabinetes naranjas…), los
    puntos de cada color quedan como un grupo aparte para asignarles tipos distintos."""
    for capa, cols in colores.items():
        distintos = sorted({c for c in cols if c is not None}, key=str)
        if len(distintos) < 2:
            continue
        g = grupos[capa]
        puntos, g["puntos"] = g["puntos"], []
        for c in distintos:
            _grupo(grupos, f"{capa} · color {c}")["puntos"] = [p for p, k in zip(puntos, cols) if k == c]
        g["puntos"] = [p for p, k in zip(puntos, cols) if k is None]


def conteo(grupo: dict) -> dict:
    """Resumen de un grupo para elegir capas sin mandar toda la geometría."""
    cerradas = sum(1 for l in grupo["lineas"] if l["cerrada"])
    return {"nombre": grupo["nombre"], "n_lineas": len(grupo["lineas"]) - cerradas, "n_cerradas": cerradas,
            "n_puntos": len(grupo["puntos"]),
            "vertices": sum(len(l["coords"]) for l in grupo["lineas"]) + len(grupo["puntos"])}
