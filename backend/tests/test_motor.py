import json
from pathlib import Path

import pytest

from app.engine.calculo import calcular, distribuir_perimetro
from app.engine.geo import Proyeccion, Recorrido

CATALOGO = {m["id"]: m for m in json.loads((Path(__file__).parents[1] / "app" / "catalogo_base.json").read_text())}
LAT0, LON0 = -32.95, -60.75  # zona Rosario/Funes


def rectangulo(ancho_m, alto_m):
    proj = Proyeccion(LAT0, LON0)
    esquinas = [(0, 0), (ancho_m, 0), (ancho_m, alto_m), (0, alto_m), (0, 0)]
    return [[round(lon, 8), round(lat, 8)] for lat, lon in (proj.a_latlon(x, y) for x, y in esquinas)]


def proyecto_base(ancho=1000, alto=810, central_xy=(0, 400)):
    proj = Proyeccion(LAT0, LON0)
    lat, lon = proj.a_latlon(*central_xy)
    return {
        "nombre": "Prueba",
        "parametros": {},
        "elementos": [
            {"type": "Feature", "id": "per", "geometry": {"type": "Polygon", "coordinates": [rectangulo(ancho, alto)]},
             "properties": {"tipo": "perimetro"}},
            {"type": "Feature", "id": "rack", "geometry": {"type": "Point", "coordinates": [lon, lat]},
             "properties": {"tipo": "central", "nombre": "Rack"}},
        ],
    }


def test_recorrido_cerrado():
    r = Recorrido([(0, 0), (100, 0), (100, 50), (0, 50)], cerrado=True)
    assert r.largo == pytest.approx(300)
    assert r.distancia(10, 290) == pytest.approx(20)
    assert r.avance(290, 10) == pytest.approx(20)
    s, d = r.proyectar((50, -3))
    assert s == pytest.approx(50) and d == pytest.approx(3)


def test_distribucion_como_cinco_lagos():
    p = proyecto_base()  # 3620 m de perímetro
    p["elementos"] = distribuir_perimetro(p, CATALOGO, {"espaciado_m": 42.6, "camaras_por_gabinete": 4})
    cams = [f for f in p["elementos"] if f["properties"]["tipo"] == "camara"]
    gabs = [f for f in p["elementos"] if f["properties"]["tipo"] == "gabinete"]
    # 2 x 24 (lados de 1000 m) + 2 x 19 (lados de 810 m, 42,6 m de paso)
    assert len(cams) == 86
    assert len(gabs) == 22
    res = calcular(p, CATALOGO)
    assert res["resumen"]["perimetro_m"] == pytest.approx(3620, rel=1e-3)
    # fibra en dos ramales desde el rack: ~ perímetro + reservas
    assert 3600 < res["fibra"]["total_m"] < 4500
    assert all(g["switch"] == "PFS3009-8ET1GT-96-V2" for g in res["gabinetes"])
    # espaciado mayor al alcance analítico (36,4 m) deja huecos que se deben informar
    assert res["cobertura"]["pct"] < 100
    assert res["cobertura"]["huecos"]


def test_espaciado_automatico_cubre_todo():
    p = proyecto_base()
    p["elementos"] = distribuir_perimetro(p, CATALOGO)
    res = calcular(p, CATALOGO)
    assert res["cobertura"]["pct"] > 99
    assert not res["cobertura"]["huecos"]
    assert res["materiales"]


def test_caida_de_tension_alerta_con_seccion_chica():
    p = proyecto_base()
    p["elementos"] = distribuir_perimetro(p, CATALOGO)
    p["parametros"]["seccion_mm2"] = 2.5
    res = calcular(p, CATALOGO)
    assert any("caída de tensión" in a for a in res["advertencias"])
    # con 10 mm² y una sola fuente, 1800 m por ramal no alcanza (por eso Cinco Lagos lleva 3 UPS)
    p["parametros"]["seccion_mm2"] = 10
    assert max(e["caida_max_pct"] for e in calcular(p, CATALOGO)["energia"]) > 5
    proj = Proyeccion(LAT0, LON0)
    for i, xy in enumerate([(1000, 400), (500, 810)]):
        lat, lon = proj.a_latlon(*xy)
        p["elementos"].append({"type": "Feature", "id": f"ups{i}", "geometry": {"type": "Point", "coordinates": [lon, lat]},
                               "properties": {"tipo": "ups"}})
    res = calcular(p, CATALOGO)
    assert len(res["energia"]) == 3
    assert max(e["caida_max_pct"] for e in res["energia"]) < 5


def test_respeta_elementos_manuales():
    p = proyecto_base()
    p["elementos"].append({"type": "Feature", "id": "manual", "geometry": {"type": "Point", "coordinates": [LON0, LAT0]},
                           "properties": {"tipo": "camara", "modelo": "dahua-sd5a825ga-hnr", "azimut": 0}})
    p["elementos"] = distribuir_perimetro(p, CATALOGO)
    p["elementos"] = distribuir_perimetro(p, CATALOGO)  # dos veces: no duplica
    assert sum(1 for f in p["elementos"] if f["id"] == "manual") == 1
    autos = [f for f in p["elementos"] if f["properties"].get("auto") and f["properties"]["tipo"] == "camara"]
    assert len(autos) == 2 * 31 + 2 * 25  # ceil(1000/32.8), ceil(810/32.8)


def test_rack_alejado_del_cerco_se_vincula_por_el_punto_mas_cercano():
    p = proyecto_base(central_xy=(-120, 400))  # sala de monitoreo a 120 m del cerco
    p["elementos"] = distribuir_perimetro(p, CATALOGO)
    res = calcular(p, CATALOGO)
    assert len(res["fibra"]["tramos"]) == 2
    assert 3700 < res["fibra"]["total_m"] < 5000


def test_escalon_corto_no_lleva_camara_propia():
    # lado de 100 m con un escalón de 4 m en el medio: con lado mínimo el escalón no suma esquina
    pts = [(0, 0), (50, 0), (50, 4), (100, 4), (100, 60), (0, 60)]
    r = Recorrido(pts, cerrado=True)
    assert len(r.lados(25)) == 6
    assert len(r.lados(25, 15)) == 5
    assert sum(f - i for i, f in r.lados(25, 15)) == pytest.approx(r.largo)
