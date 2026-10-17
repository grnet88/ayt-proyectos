"""Persistencia en SQLite (un archivo, sin servidor). Pensado para migrar a PostgreSQL más adelante."""
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


@contextmanager
def conexion():
    RUTA_DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(RUTA_DB)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def inicializar() -> None:
    with conexion() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS proyectos (
                id TEXT PRIMARY KEY, nombre TEXT NOT NULL, cliente TEXT, categoria TEXT,
                datos TEXT NOT NULL, creado REAL, actualizado REAL);
            CREATE TABLE IF NOT EXISTS catalogo (
                id TEXT PRIMARY KEY, categoria TEXT NOT NULL, datos TEXT NOT NULL, base INTEGER DEFAULT 0);
            """
        )
        # el catálogo base se actualiza en cada arranque; lo cargado por el usuario no se toca
        for m in json.loads(CATALOGO_BASE.read_text(encoding="utf-8")):
            con.execute(
                "INSERT INTO catalogo (id, categoria, datos, base) VALUES (?, ?, ?, 1) "
                "ON CONFLICT(id) DO UPDATE SET categoria=excluded.categoria, datos=excluded.datos WHERE base=1",
                (m["id"], m["categoria"], json.dumps(m, ensure_ascii=False)),
            )


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


def listar_proyectos() -> list[dict]:
    with conexion() as con:
        filas = con.execute(
            "SELECT id, nombre, cliente, categoria, actualizado FROM proyectos ORDER BY actualizado DESC"
        ).fetchall()
    return [dict(f) for f in filas]


def obtener_proyecto(pid: str) -> dict | None:
    with conexion() as con:
        f = con.execute("SELECT * FROM proyectos WHERE id=?", (pid,)).fetchone()
    if not f:
        return None
    datos = json.loads(f["datos"])
    datos.update(id=f["id"], nombre=f["nombre"], cliente=f["cliente"], categoria=f["categoria"])
    return datos


def guardar_proyecto(datos: dict) -> dict:
    datos = dict(datos)
    pid = datos.pop("id", None) or uuid.uuid4().hex[:12]
    nombre = datos.pop("nombre", None) or "Proyecto sin nombre"
    cliente = datos.pop("cliente", None)
    categoria = datos.pop("categoria", None)
    datos.setdefault("elementos", [])
    datos.setdefault("parametros", {})
    ahora = time.time()
    with conexion() as con:
        con.execute(
            "INSERT INTO proyectos (id, nombre, cliente, categoria, datos, creado, actualizado) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET nombre=excluded.nombre, "
            "cliente=excluded.cliente, categoria=excluded.categoria, datos=excluded.datos, actualizado=excluded.actualizado",
            (pid, nombre, cliente, categoria, json.dumps(datos, ensure_ascii=False), ahora, ahora),
        )
    return obtener_proyecto(pid)


def borrar_proyecto(pid: str) -> bool:
    with conexion() as con:
        return con.execute("DELETE FROM proyectos WHERE id=?", (pid,)).rowcount > 0
