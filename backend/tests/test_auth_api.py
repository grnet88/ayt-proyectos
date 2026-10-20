import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    monkeypatch.setenv("AYT_DB", str(tmp_path / "prueba.db"))
    from app import db
    importlib.reload(db)
    from app import auth, main
    importlib.reload(auth)
    importlib.reload(main)
    return TestClient(main.app)


CLAVE = "clave-de-prueba-1"


def configurar(c):
    r = c.post("/api/configuracion-inicial", json={"clave": CLAVE})
    assert r.status_code == 200
    return r.json()["llave"]


def ingresar(c, usuario="aytroot", clave=CLAVE):
    r = c.post("/api/ingresar", json={"usuario": usuario, "clave": clave})
    assert r.status_code == 200, r.text
    return r.json()


def test_sin_sesion_no_hay_datos(cliente):
    assert cliente.get("/api/proyectos").status_code == 401
    assert cliente.get("/api/estado").json()["configurado"] is False


def test_configuracion_inicial_una_sola_vez(cliente):
    configurar(cliente)
    assert cliente.post("/api/configuracion-inicial", json={"clave": "otra-clave-9"}).status_code == 400
    assert cliente.post("/api/ingresar", json={"usuario": "aytroot", "clave": "mala"}).status_code == 401
    assert ingresar(cliente)["rol"] == "superadmin"


def test_clave_corta_rechazada(cliente):
    assert cliente.post("/api/configuracion-inicial", json={"clave": "corta"}).status_code == 400


def test_aytroot_no_se_puede_borrar_ni_cambiar_rol(cliente):
    configurar(cliente)
    ingresar(cliente)
    root = next(u for u in cliente.get("/api/usuarios").json() if u["usuario"] == "aytroot")
    assert cliente.delete(f"/api/usuarios/{root['id']}").status_code == 400
    r = cliente.put(f"/api/usuarios/{root['id']}", json={"rol": "visor", "activo": False})
    assert r.status_code == 200 and r.json()["rol"] == "superadmin" and r.json()["activo"]


def test_visor_solo_lectura_y_solo_sus_proyectos(cliente):
    configurar(cliente)
    ingresar(cliente)
    p1 = cliente.post("/api/proyectos", json={"nombre": "Barrio 1"}).json()
    cliente.post("/api/proyectos", json={"nombre": "Barrio 2"})
    cliente.post("/api/usuarios", json={"usuario": "cliente1", "nombre": "Cliente", "rol": "visor",
                                        "clave": "cliente-123", "proyectos": [p1["id"]]})
    cliente.post("/api/salir")
    ingresar(cliente, "cliente1", "cliente-123")
    lista = cliente.get("/api/proyectos").json()
    assert [p["nombre"] for p in lista] == ["Barrio 1"]
    eid = cliente.get(f"/api/proyectos/{p1['id']}").json()["escenarios"][0]["id"]
    assert cliente.get(f"/api/escenarios/{eid}/calculo").status_code == 200
    assert cliente.put(f"/api/escenarios/{eid}", json={"elementos": []}).status_code == 403
    assert cliente.post("/api/proyectos", json={"nombre": "x"}).status_code == 403
    assert cliente.get("/api/usuarios").status_code == 403


def test_llave_de_recuperacion(cliente):
    llave = configurar(cliente)
    assert cliente.post("/api/recuperar", json={"llave": "basura", "clave": "nueva-clave-1"}).status_code == 400
    r = cliente.post("/api/recuperar", json={"llave": llave, "clave": "nueva-clave-1"})
    assert r.status_code == 200
    llave2 = r.json()["llave"]
    ingresar(cliente, clave="nueva-clave-1")
    # la llave usada deja de valer; la nueva sí
    assert cliente.post("/api/recuperar", json={"llave": llave, "clave": "otra-clave-2"}).status_code == 400
    assert cliente.post("/api/recuperar", json={"llave": llave2, "clave": "otra-clave-2"}).status_code == 200


def test_escenarios_duplicar_y_borrar(cliente):
    configurar(cliente)
    ingresar(cliente)
    p = cliente.post("/api/proyectos", json={"nombre": "Barrio"}).json()
    eid = p["escenarios"][0]["id"]
    elem = [{"type": "Feature", "id": "c1", "geometry": {"type": "Point", "coordinates": [-60.75, -32.95]},
             "properties": {"tipo": "camara", "modelo": "dahua-sd5a825ga-hnr"}}]
    cliente.put(f"/api/escenarios/{eid}", json={"elementos": elem})
    b = cliente.post(f"/api/proyectos/{p['id']}/escenarios", json={"nombre": "Opción B", "copiar_de": eid}).json()
    assert b["elementos"][0]["id"] == "c1"
    assert len(cliente.get(f"/api/proyectos/{p['id']}").json()["escenarios"]) == 2
    assert cliente.delete(f"/api/escenarios/{b['id']}").status_code == 200
    assert cliente.delete(f"/api/escenarios/{eid}").status_code == 400  # queda al menos uno


def test_migracion_desde_prototipo(tmp_path, monkeypatch):
    import json
    import sqlite3
    ruta = tmp_path / "v1.db"
    con = sqlite3.connect(ruta)
    con.execute("CREATE TABLE proyectos (id TEXT PRIMARY KEY, nombre TEXT NOT NULL, cliente TEXT, categoria TEXT, "
                "datos TEXT NOT NULL, creado REAL, actualizado REAL)")
    datos = {"elementos": [{"type": "Feature", "id": "x", "geometry": {"type": "Point", "coordinates": [0, 0]},
                            "properties": {"tipo": "gabinete"}}], "parametros": {"seccion_mm2": 16}, "vista": {"zoom": 15}}
    con.execute("INSERT INTO proyectos VALUES ('p1', 'Viejo', NULL, NULL, ?, 0, 0)", (json.dumps(datos),))
    con.commit()
    con.close()
    monkeypatch.setenv("AYT_DB", str(ruta))
    from app import db
    importlib.reload(db)
    db.inicializar()
    p = db.obtener_proyecto("p1")
    assert p["vista"] == {"zoom": 15} and "elementos" not in p
    e = db.obtener_escenario(p["escenarios"][0]["id"])
    assert e["elementos"][0]["properties"]["planta"] == "exterior"
    assert e["parametros"] == {"seccion_mm2": 16}
