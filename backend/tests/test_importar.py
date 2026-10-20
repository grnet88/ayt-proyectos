import io
import zipfile

import ezdxf
import pytest

from app.importar import ErrorImportacion, leer_dxf, leer_kml

KML = b"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>Barrio</name>
 <Folder><name>Cerco</name>
  <Placemark><name>Perimetro</name><Polygon><outerBoundaryIs><LinearRing><coordinates>
   -60.75,-32.95,0 -60.74,-32.95,0 -60.74,-32.94,0 -60.75,-32.95,0
  </coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>
 </Folder>
 <Folder><name>Camaras</name>
  <Placemark><name>CAM 1</name><Point><coordinates>-60.745,-32.95,0</coordinates></Point></Placemark>
  <Placemark><name>CAM 2</name><Point><coordinates>-60.741,-32.946,0</coordinates></Point></Placemark>
 </Folder>
</Document></kml>"""


def test_kml_por_carpetas():
    r = leer_kml(KML)
    g = {x["nombre"]: x for x in r["grupos"]}
    assert r["georreferenciado"] and set(g) == {"Cerco", "Camaras"}
    assert g["Cerco"]["lineas"][0]["cerrada"] and len(g["Cerco"]["lineas"][0]["coords"]) == 4
    assert [p["nombre"] for p in g["Camaras"]["puntos"]] == ["CAM 1", "CAM 2"]
    assert g["Camaras"]["puntos"][0]["coords"] == [-60.745, -32.95]


def test_kmz():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("doc.kml", KML)
    assert len(leer_kml(buf.getvalue())["grupos"]) == 2


def test_dxf_por_capas_con_unidades():
    doc = ezdxf.new()
    doc.header["$INSUNITS"] = 4  # milímetros
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (100000, 0), (100000, 50000), (0, 50000)], close=True, dxfattribs={"layer": "CERCO"})
    msp.add_line((10000, 10000), (10000, 30000), dxfattribs={"layer": "MUROS"})
    msp.add_circle((50000, 25000), 2000, dxfattribs={"layer": "ARBOLES"})
    blk = doc.blocks.new("CAMARA")
    blk.add_circle((0, 0), 100)
    msp.add_blockref("CAMARA", (5000, 0), dxfattribs={"layer": "CCTV"})
    buf = io.StringIO()
    doc.write(buf)
    r = leer_dxf(buf.getvalue().encode())
    g = {x["nombre"]: x for x in r["grupos"]}
    assert not r["georreferenciado"] and r["metros_por_unidad"] == 0.001
    assert set(g) == {"CERCO", "MUROS", "ARBOLES", "CCTV"}
    assert g["CERCO"]["lineas"][0]["cerrada"] and len(g["CERCO"]["lineas"][0]["coords"]) == 4
    assert g["ARBOLES"]["lineas"][0]["cerrada"]
    assert g["CCTV"]["puntos"][0] == {"coords": [5000, 0], "nombre": "CAMARA"}


def test_dwg_y_vacio_rechazados():
    with pytest.raises(ErrorImportacion):
        leer_dxf(b"AC1032" + b"\0" * 100)
    with pytest.raises(ErrorImportacion):
        leer_kml(b"<kml xmlns='http://www.opengis.net/kml/2.2'><Document/></kml>")


def test_dxf_cerco_con_lineas_sueltas_se_une():
    doc = ezdxf.new()
    doc.header["$INSUNITS"] = 6  # metros
    msp = doc.modelspace()
    esquinas = [(0, 0), (100, 0), (100, 60), (0, 60)]
    for i in (0, 2, 1, 3):  # desordenadas y una invertida
        a, b = esquinas[i], esquinas[(i + 1) % 4]
        msp.add_line(b if i == 2 else a, a if i == 2 else b, dxfattribs={"layer": "CERCO"})
    buf = io.StringIO()
    doc.write(buf)
    (g,) = leer_dxf(buf.getvalue().encode())["grupos"]
    assert len(g["lineas"]) == 1 and g["lineas"][0]["cerrada"] and len(g["lineas"][0]["coords"]) == 4


def test_dxf_rellenos_como_puntos_separados_por_color():
    doc = ezdxf.new()
    msp = doc.modelspace()
    for x, color in ((0, 2), (60, 2), (30, 32)):
        h = msp.add_hatch(color=color, dxfattribs={"layer": "CCTV"})
        h.paths.add_polyline_path([(x, 0), (x + 7, 0), (x + 7, 3), (x, 3)])
    msp.add_lwpolyline([(0, 10), (100, 10)], dxfattribs={"layer": "CCTV"})
    buf = io.StringIO()
    doc.write(buf)
    g = {x["nombre"]: x for x in leer_dxf(buf.getvalue().encode())["grupos"]}
    assert set(g) == {"CCTV", "CCTV · color 2", "CCTV · color 32"}
    assert [p["coords"] for p in g["CCTV · color 2"]["puntos"]] == [[3.5, 1.5], [63.5, 1.5]]
    assert len(g["CCTV · color 32"]["puntos"]) == 1 and len(g["CCTV"]["lineas"]) == 1 and not g["CCTV"]["puntos"]
