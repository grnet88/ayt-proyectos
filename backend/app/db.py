"""Persistencia en SQLite (un archivo, sin servidor).

Modelo v2:
- proyecto: datos generales + plantas (exterior sobre mapa, pisos con plano propio).
- escenario: alternativa (Opción A / B) o etapa de obra de un proyecto. Cada escenario
  tiene sus propios elementos, parámetros y ediciones manuales del cómputo.
- usuarios, sesiones, auditoría y configuración (llave de recuperación).
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

RUTA_DB = Path(os.environ.get("AYT_DB", Path(__file__).resolve().parents[2] / "datos" / "ayt.db"))
CATALOGO_BASE = Path(__file__).with_name("catalogo_base.json")
VERSION_ESQUEMA = 2

PLANTA_EXTERIOR = {"id": "exterior", "nombre": "Exterior", "tipo": "mapa"}


@contextmanager
def conexion():
    RUTA_DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(RUTA_DB)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def _nuevo_id() -> str:
    return uuid.uuid4().hex[:12]


def inicializar() -> None:
    with conexion() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS config (clave TEXT PRIMARY KEY, valor TEXT);
            CREATE TABLE IF NOT EXISTS proyectos (
                id TEXT PRIMARY KEY, nombre TEXT NOT NULL, cliente TEXT, categoria TEXT,
                datos TEXT NOT NULL, creado REAL, actualizado REAL);
            CREATE TABLE IF NOT EXISTS escenarios (
                id TEXT PRIMARY KEY,
                proyecto_id TEXT NOT NULL REFERENCES proyectos(id) ON DELETE CASCADE,
                nombre TEXT NOT NULL, tipo TEXT NOT NULL DEFAULT 'alternativa', orden INTEGER DEFAULT 0,
                datos TEXT NOT NULL, actualizado REAL);
            CREATE TABLE IF NOT EXISTS catalogo (
                id TEXT PRIMARY KEY, categoria TEXT NOT NULL, datos TEXT NOT NULL, base INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS usuarios (
                id TEXT PRIMARY KEY, usuario TEXT UNIQUE NOT NULL, nombre TEXT, rol TEXT NOT NULL,
                clave_hash TEXT NOT NULL, activo INTEGER DEFAULT 1, fijo INTEGER DEFAULT 0,
                proyectos TEXT DEFAULT '[]', creado REAL);
            CREATE TABLE IF NOT EXISTS sesiones (
                token TEXT PRIMARY KEY, usuario_id TEXT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                expira REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS auditoria (
                id INTEGER PRIMARY KEY AUTOINCREMENT, fecha REAL, usuario TEXT, accion TEXT, detalle TEXT);
            """
        )
        _migrar(con)
        # el catálogo base se actualiza en cada arranque; lo cargado por el usuario no se toca
        for m in json.loads(CATALOGO_BASE.read_text(encoding="utf-8")):
            con.execute(
                "INSERT INTO catalogo (id, categoria, datos, base) VALUES (?, ?, ?, 1) "
                "ON CONFLICT(id) DO UPDATE SET categoria=excluded.categoria, datos=excluded.datos WHERE base=1",
                (m["id"], m["categoria"], json.dumps(m, ensure_ascii=False)),
            )


def _migrar(con: sqlite3.Connection) -> None:
    """v1 (prototipo) guardaba elementos y parámetros dentro del proyecto: pasan a un escenario."""
    fila = con.execute("SELECT valor FROM config WHERE clave='version_esquema'").fetchone()
    version = int(fila["valor"]) if fila else 1
    if version < 2:
        for p in con.execute("SELECT id, datos, actualizado FROM proyectos").fetchall():
            datos = json.loads(p["datos"])
            if con.execute("SELECT 1 FROM escenarios WHERE proyecto_id=?", (p["id"],)).fetchone():
                continue
            esc = {"elementos": datos.pop("elementos", []), "parametros": datos.pop("parametros", {}),
                   "computo": {"ajustes": {}, "libres": []}}
            for f in esc["elementos"]:
                f.setdefault("properties", {}).setdefault("planta", "exterior")
            datos.setdefault("plantas", [PLANTA_EXTERIOR])
            con.execute("UPDATE proyectos SET datos=? WHERE id=?", (json.dumps(datos, ensure_ascii=False), p["id"]))
            con.execute(
                "INSERT INTO escenarios (id, proyecto_id, nombre, tipo, orden, datos, actualizado) VALUES (?,?,?,?,?,?,?)",
                (_nuevo_id(), p["id"], "Opción A", "alternativa", 0, json.dumps(esc, ensure_ascii=False), p["actualizado"]),
            )
    con.execute("INSERT INTO config (clave, valor) VALUES ('version_esquema', ?) "
                "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor", (str(VERSION_ESQUEMA),))


# --------------------------------------------------------------------------- config


def config_obtener(clave: str) -> str | None:
    with conexion() as con:
        f = con.execute("SELECT valor FROM config WHERE clave=?", (clave,)).fetchone()
    return f["valor"] if f else None


def config_guardar(clave: str, valor: str) -> None:
    with conexion() as con:
        con.execute("INSERT INTO config (clave, valor) VALUES (?, ?) ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor",
                    (clave, valor))


def auditar(usuario: str | None, accion: str, detalle: str = "") -> None:
    with conexion() as con:
        con.execute("INSERT INTO auditoria (fecha, usuario, accion, detalle) VALUES (?,?,?,?)",
                    (time.time(), usuario, accion, detalle))


def auditoria(limite: int = 200) -> list[dict]:
    with conexion() as con:
        return [dict(f) for f in con.execute("SELECT * FROM auditoria ORDER BY id DESC LIMIT ?", (limite,))]


# --------------------------------------------------------------------------- catálogo


def catalogo() -> dict[str, dict]:
    with conexion() as con:
        filas = con.execute("SELECT datos, base FROM catalogo ORDER BY categoria, id").fetchall()
    out = {}
    for f in filas:
        m = json.loads(f["datos"])
        m["base"] = bool(f["base"])
        out[m["id"]] = m
    return out


def guardar_modelo(m: dict) -> dict:
    m = dict(m)
    m.pop("base", None)
    m.setdefault("id", f"usr-{uuid.uuid4().hex[:8]}")
    with conexion() as con:
        con.execute(
            "INSERT INTO catalogo (id, categoria, datos, base) VALUES (?, ?, ?, 0) "
            "ON CONFLICT(id) DO UPDATE SET categoria=excluded.categoria, datos=excluded.datos, base=0",
            (m["id"], m["categoria"], json.dumps(m, ensure_ascii=False)),
        )
    return m


def borrar_modelo(mid: str) -> bool:
    with conexion() as con:
        return con.execute("DELETE FROM catalogo WHERE id=? AND base=0", (mid,)).rowcount > 0


# --------------------------------------------------------------------------- proyectos


def listar_proyectos(ids: list[str] | None = None) -> list[dict]:
    with conexion() as con:
        filas = con.execute(
            "SELECT id, nombre, cliente, categoria, actualizado FROM proyectos ORDER BY actualizado DESC"
        ).fetchall()
    out = [dict(f) for f in filas]
    return out if ids is None else [p for p in out if p["id"] in ids]


def obtener_proyecto(pid: str) -> dict | None:
    with conexion() as con:
        f = con.execute("SELECT * FROM proyectos WHERE id=?", (pid,)).fetchone()
        if not f:
            return None
        escs = con.execute("SELECT id, nombre, tipo, orden FROM escenarios WHERE proyecto_id=? ORDER BY orden, rowid",
                           (pid,)).fetchall()
    datos = json.loads(f["datos"])
    datos.setdefault("plantas", [PLANTA_EXTERIOR])
    datos.update(id=f["id"], nombre=f["nombre"], cliente=f["cliente"], categoria=f["categoria"],
                 escenarios=[dict(e) for e in escs])
    return datos


def crear_proyecto(datos: dict) -> dict:
    pid = _nuevo_id()
    meta = {k: v for k, v in datos.items() if k not in ("id", "nombre", "cliente", "categoria", "escenarios",
                                                         "elementos", "parametros")}
    meta.setdefault("plantas", [PLANTA_EXTERIOR])
    ahora = time.time()
    esc = {"elementos": datos.get("elementos", []), "parametros": datos.get("parametros", {}),
           "computo": {"ajustes": {}, "libres": []}}
    with conexion() as con:
        con.execute("INSERT INTO proyectos (id, nombre, cliente, categoria, datos, creado, actualizado) VALUES (?,?,?,?,?,?,?)",
                    (pid, datos.get("nombre") or "Proyecto sin nombre", datos.get("cliente"), datos.get("categoria"),
                     json.dumps(meta, ensure_ascii=False), ahora, ahora))
        con.execute("INSERT INTO escenarios (id, proyecto_id, nombre, tipo, orden, datos, actualizado) VALUES (?,?,?,?,?,?,?)",
                    (_nuevo_id(), pid, "Opción A", "alternativa", 0, json.dumps(esc, ensure_ascii=False), ahora))
    return obtener_proyecto(pid)


def actualizar_proyecto(pid: str, datos: dict) -> dict | None:
    actual = obtener_proyecto(pid)
    if not actual:
        return None
    meta = {k: v for k, v in actual.items() if k not in ("id", "nombre", "cliente", "categoria", "escenarios")}
    meta.update({k: v for k, v in datos.items() if k not in ("id", "nombre", "cliente", "categoria", "escenarios",
                                                              "elementos", "parametros")})
    with conexion() as con:
        con.execute("UPDATE proyectos SET nombre=?, cliente=?, categoria=?, datos=?, actualizado=? WHERE id=?",
                    (datos.get("nombre", actual["nombre"]) or "Proyecto sin nombre", datos.get("cliente", actual["cliente"]),
                     datos.get("categoria", actual["categoria"]), json.dumps(meta, ensure_ascii=False), time.time(), pid))
    return obtener_proyecto(pid)


def borrar_proyecto(pid: str) -> bool:
    with conexion() as con:
        return con.execute("DELETE FROM proyectos WHERE id=?", (pid,)).rowcount > 0


# --------------------------------------------------------------------------- escenarios


def obtener_escenario(eid: str) -> dict | None:
    with conexion() as con:
        f = con.execute("SELECT * FROM escenarios WHERE id=?", (eid,)).fetchone()
    if not f:
        return None
    datos = json.loads(f["datos"])
    datos.setdefault("computo", {"ajustes": {}, "libres": []})
    datos.update(id=f["id"], proyecto_id=f["proyecto_id"], nombre=f["nombre"], tipo=f["tipo"], orden=f["orden"])
    return datos


def guardar_escenario(eid: str, datos: dict) -> dict | None:
    actual = obtener_escenario(eid)
    if not actual:
        return None
    cuerpo = {k: datos.get(k, actual.get(k)) for k in ("elementos", "parametros", "computo")}
    with conexion() as con:
        con.execute("UPDATE escenarios SET nombre=?, tipo=?, datos=?, actualizado=? WHERE id=?",
                    (datos.get("nombre") or actual["nombre"], datos.get("tipo") or actual["tipo"],
                     json.dumps(cuerpo, ensure_ascii=False), time.time(), eid))
        con.execute("UPDATE proyectos SET actualizado=? WHERE id=?", (time.time(), actual["proyecto_id"]))
    return obtener_escenario(eid)


def crear_escenario(pid: str, nombre: str, tipo: str = "alternativa", copiar_de: str | None = None) -> dict | None:
    if not obtener_proyecto(pid):
        return None
    cuerpo = {"elementos": [], "parametros": {}, "computo": {"ajustes": {}, "libres": []}}
    if copiar_de:
        base = obtener_escenario(copiar_de)
        if not base or base["proyecto_id"] != pid:
            return None
        cuerpo = {k: base[k] for k in ("elementos", "parametros", "computo")}
    eid = _nuevo_id()
    with conexion() as con:
        orden = con.execute("SELECT COALESCE(MAX(orden), -1) + 1 FROM escenarios WHERE proyecto_id=?", (pid,)).fetchone()[0]
        con.execute("INSERT INTO escenarios (id, proyecto_id, nombre, tipo, orden, datos, actualizado) VALUES (?,?,?,?,?,?,?)",
                    (eid, pid, nombre, tipo, orden, json.dumps(cuerpo, ensure_ascii=False), time.time()))
    return obtener_escenario(eid)


def borrar_escenario(eid: str) -> str:
    """'ok', 'no_existe' o 'ultimo' (un proyecto siempre conserva al menos un escenario)."""
    e = obtener_escenario(eid)
    if not e:
        return "no_existe"
    with conexion() as con:
        n = con.execute("SELECT COUNT(*) FROM escenarios WHERE proyecto_id=?", (e["proyecto_id"],)).fetchone()[0]
        if n <= 1:
            return "ultimo"
        con.execute("DELETE FROM escenarios WHERE id=?", (eid,))
    return "ok"
