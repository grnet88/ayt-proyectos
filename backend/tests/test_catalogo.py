import json
from pathlib import Path

from test_auth_api import cliente, configurar, ingresar  # noqa: F401

APP = Path(__file__).parents[1] / "app"
CATALOGO = json.loads((APP / "catalogo_base.json").read_text(encoding="utf-8"))
ESQUEMA = json.loads((APP / "catalogo_esquema.json").read_text(encoding="utf-8"))
CATEGORIAS = {c["id"]: c for c in ESQUEMA["categorias"]}


def test_modelos_base_coinciden_con_el_esquema():
    assert len({m["id"] for m in CATALOGO}) == len(CATALOGO)
    for m in CATALOGO:
        assert m["categoria"] in CATEGORIAS, m["id"]
        for c in CATEGORIAS[m["categoria"]]["campos"] + ESQUEMA["comunes"]:
            v = m
            for k in c["clave"].split("."):
                v = v.get(k) if isinstance(v, dict) else None
            if v is None:
                continue
            if c["tipo"] == "num":
                assert isinstance(v, (int, float)) and not isinstance(v, bool), (m["id"], c["clave"])
            elif c["tipo"] == "bool":
                assert isinstance(v, bool), (m["id"], c["clave"])
            elif c["tipo"] == "opcion":
                assert v in [o[0] for o in c["opciones"]], (m["id"], c["clave"], v)


def test_hay_genericos_de_cada_familia_pedida():
    cats = {m["categoria"] for m in CATALOGO}
    assert {"rack", "gabinete_ext", "radio", "internet", "splitter", "cable_fo", "odf", "caja_fo", "sfp"} <= cats


def test_genericos_no_cambian_la_seleccion_automatica():
    from app.engine.calculo import _auto
    nuevos = [m for m in CATALOGO if m["categoria"] in ("switch", "ups") and m.get("generico")]
    assert nuevos and not any(_auto(m) for m in nuevos)


def test_api_esquema_y_categoria_desconocida(cliente):  # noqa: F811
    configurar(cliente)
    ingresar(cliente)
    assert {c["id"] for c in cliente.get("/api/catalogo/esquema").json()["categorias"]} == set(CATEGORIAS)
    assert cliente.post("/api/catalogo", json={"categoria": "nave", "modelo": "X"}).status_code == 422
    r = cliente.post("/api/catalogo", json={"categoria": "radio", "modelo": "Mi PtP", "ganancia_dbi": 23})
    assert r.status_code == 200 and r.json()["id"].startswith("usr-")
