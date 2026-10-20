import pytest

from app.engine.calculo import calcular
from app.engine.geo import Proyeccion, Recorrido
from app.engine.calculo import camaras_de_paso, PARAMETROS_DEFAULT

from .test_motor import CATALOGO, LAT0, LON0, proyecto_base


def linea(*xy):
    proj = Proyeccion(LAT0, LON0)
    return [list(reversed(proj.a_latlon(x, y))) for x, y in xy]


def test_camaras_de_paso_en_extremos_quiebres_y_cada_40_m():
    r = Recorrido([(0, 0), (100, 0), (100, 30)], cerrado=False)
    s = camaras_de_paso(r, PARAMETROS_DEFAULT)
    # 0, 33.3, 66.7, 100 (quiebre de 90°) y 130 (extremo)
    assert s == pytest.approx([0, 100 / 3, 200 / 3, 100, 130])


def test_canalizaciones_en_el_listado():
    p = proyecto_base(200, 200, central_xy=(0, 100))
    p["elementos"] += [
        {"type": "Feature", "id": "c1", "geometry": {"type": "LineString", "coordinates": linea((0, 100), (80, 100))},
         "properties": {"tipo": "canalizacion"}},
        {"type": "Feature", "id": "c2", "geometry": {"type": "LineString", "coordinates": linea((80, 100), (80, 112))},
         "properties": {"tipo": "canalizacion", "cruce": True}},
        {"type": "Feature", "id": "c3", "geometry": {"type": "LineString", "coordinates": linea((0, 0), (0, 50))},
         "properties": {"tipo": "canalizacion", "tipo_canal": "aerea", "diametro_mm": 25}},
        {"type": "Feature", "id": "cp", "geometry": {"type": "Point", "coordinates": linea((0, 100))[0]},
         "properties": {"tipo": "camara_paso", "medida": "60x60"}},
    ]
    r = calcular(p, CATALOGO)
    m = {i["descripcion"]: i["cantidad"] for i in r["materiales"] if i["categoria"] == "Obra civil"}
    assert m["Canalización enterrada (caño PEAD) Ø40 mm"] == 83  # 80 m x 1,03
    assert m["Zanjeo, tapada y señalización"] == 80
    assert m["Canalización aérea sobre cerco o postes (caño galvanizado) Ø25 mm"] == 52
    assert m["Cruce de calzada (perforación dirigida o rotura y reparación)"] == 12
    # c1: 0 (la reemplaza la manual de 60x60), 40 y 80; c2: 80 (ya está, compartida) y 92
    assert m["Cámara de paso 60x60 cm con tapa"] == 1
    assert m["Cámara de paso 40x40 cm con tapa"] == 3
