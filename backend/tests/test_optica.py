import math

import pytest

from app.engine.calculo import calcular, distribuir_perimetro
from app.engine.geo import Proyeccion
from app.engine.optica import optica

from .test_motor import CATALOGO, LAT0, LON0, proyecto_base

P = {"altura_camara_m": 4.0, "dist_min_camara_m": 2.0}
CAM = CATALOGO["dahua-ipc-hdw3849h-as-pv-28"]  # hfov 106°, vfov 55°, DORI I 9,1 m, analítica 36,4 m


def test_inclinacion_automatica_lleva_el_borde_superior_al_alcance():
    o = optica({}, CAM, P)
    # atan(4 / 36,4) + 55/2 = 6,27 + 27,5
    assert o["inclinacion"] == pytest.approx(33.8, abs=0.05)
    assert o["inclinacion_auto"]
    assert o["borde_lejano_m"] == pytest.approx(36.4, abs=0.1)
    assert o["alcance_efectivo_m"] == pytest.approx(36.4)
    # zona ciega: 4 / tan(33,77 + 27,5)
    assert o["zona_ciega_m"] == pytest.approx(4 / math.tan(math.radians(61.27)), abs=0.1)
    # PPM con la resolución del catálogo (3840 px): 3840 / (2 · 36,4 · tan 53°)
    assert o["ppm_borde"] == pytest.approx(39.7, abs=0.1)
    # sin resolución, estimado por DORI: 250 PPM a 9,1 m → 62,5 a 36,4 m
    sin_res = {k: v for k, v in CAM.items() if k != "resolucion_h"}
    assert optica({}, sin_res, P)["ppm_borde"] == pytest.approx(62.5, abs=0.1)


def test_inclinacion_manual_acorta_el_alcance():
    o = optica({"inclinacion": 45, "altura_m": 6}, CAM, P)
    assert not o["inclinacion_auto"]
    assert o["borde_lejano_m"] == pytest.approx(6 / math.tan(math.radians(17.5)), abs=0.1)
    assert o["alcance_efectivo_m"] == o["borde_lejano_m"]
    assert o["zona_ciega_m"] == pytest.approx(6 / math.tan(math.radians(72.5)), abs=0.1)


def test_camara_horizontal_no_tiene_borde_lejano():
    o = optica({"inclinacion": 10}, CAM, P)
    assert o["borde_lejano_m"] is None
    assert o["alcance_efectivo_m"] == pytest.approx(36.4)


def test_ppm_con_resolucion_del_modelo():
    m = {**CAM, "resolucion_h": 3840}
    o = optica({"alcance": 20}, m, P)
    assert o["ppm_borde"] == pytest.approx(3840 / (2 * 20 * math.tan(math.radians(53))), abs=0.1)


def test_muro_bloquea_la_cobertura_y_avisa_inclinacion():
    p = proyecto_base(200, 200, central_xy=(0, 100))
    p["elementos"] = distribuir_perimetro(p, CATALOGO, {})
    base = calcular(p, CATALOGO)
    assert base["cobertura"]["pct"] == 100
    assert len(base["camaras"]) == len([f for f in p["elementos"] if f["properties"]["tipo"] == "camara"])
    # muro transversal que corta el lado inferior a 50 m de la esquina (de y=-5 a y=5)
    proj = Proyeccion(LAT0, LON0)
    muro = [list(reversed(proj.a_latlon(50, y))) for y in (-5, 5)]
    p["elementos"].append({"type": "Feature", "id": "muro1", "geometry": {"type": "LineString", "coordinates": muro},
                           "properties": {"tipo": "muro"}})
    con_muro = calcular(p, CATALOGO)
    assert con_muro["cobertura"]["pct"] < 100
    assert con_muro["cobertura"]["huecos"]
    # una cámara inclinada de más genera aviso
    cam = next(f for f in p["elementos"] if f["properties"]["tipo"] == "camara")
    cam["properties"]["inclinacion"] = 60
    r = calcular(p, CATALOGO)
    assert any("inclinada(s) de más" in a for a in r["advertencias"])
