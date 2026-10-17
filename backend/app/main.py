"""Servidor web: API REST + interfaz estática.

Ejecutar desde la carpeta backend:  uvicorn app.main:app --reload
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import db
from .engine.calculo import PARAMETROS_DEFAULT, calcular, distribuir_perimetro

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"

app = FastAPI(title="AyT Proyectos", version="0.1.0")
db.inicializar()


def _proyecto(pid: str) -> dict:
    p = db.obtener_proyecto(pid)
    if not p:
        raise HTTPException(404, "Proyecto no encontrado")
    return p


@app.get("/api/parametros")
def parametros():
    return PARAMETROS_DEFAULT


@app.get("/api/catalogo")
def get_catalogo():
    return list(db.catalogo().values())


@app.post("/api/catalogo")
def post_modelo(m: dict):
    if not m.get("categoria") or not m.get("modelo"):
        raise HTTPException(422, "Faltan categoría o modelo")
    return db.guardar_modelo(m)


@app.delete("/api/catalogo/{mid}")
def delete_modelo(mid: str):
    if not db.borrar_modelo(mid):
        raise HTTPException(400, "Solo se pueden borrar modelos cargados por el usuario")
    return {"ok": True}


@app.get("/api/proyectos")
def get_proyectos():
    return db.listar_proyectos()


@app.post("/api/proyectos")
def post_proyecto(datos: dict):
    datos.pop("id", None)
    return db.guardar_proyecto(datos)


@app.get("/api/proyectos/{pid}")
def get_proyecto(pid: str):
    return _proyecto(pid)


@app.put("/api/proyectos/{pid}")
def put_proyecto(pid: str, datos: dict):
    _proyecto(pid)
    datos["id"] = pid
    return db.guardar_proyecto(datos)


@app.delete("/api/proyectos/{pid}")
def delete_proyecto(pid: str):
    if not db.borrar_proyecto(pid):
        raise HTTPException(404, "Proyecto no encontrado")
    return {"ok": True}


@app.post("/api/proyectos/{pid}/distribuir")
def post_distribuir(pid: str, opciones: dict | None = None):
    p = _proyecto(pid)
    try:
        p["elementos"] = distribuir_perimetro(p, db.catalogo(), opciones or {})
    except ValueError as e:
        raise HTTPException(422, str(e))
    if opciones:
        p["parametros"] = {**p.get("parametros", {}), **{k: v for k, v in opciones.items() if v is not None}}
    return db.guardar_proyecto(p)


@app.get("/api/proyectos/{pid}/calculo")
def get_calculo(pid: str):
    try:
        return calcular(_proyecto(pid), db.catalogo())
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.get("/api/proyectos/{pid}/materiales.csv")
def get_materiales_csv(pid: str):
    p = _proyecto(pid)
    res = calcular(p, db.catalogo())
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Categoría", "Descripción", "Modelo", "Cantidad", "Unidad"])
    for m in res["materiales"]:
        w.writerow([m["categoria"], m["descripcion"], m["modelo"], m["cantidad"], m["unidad"]])
    nombre = "".join(ch if ch.isalnum() or ch in " -_" else "_" for ch in p["nombre"]).strip() or "proyecto"
    return StreamingResponse(
        iter(["﻿" + buf.getvalue()]), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="Materiales - {nombre}.csv"'},
    )


app.mount("/static", StaticFiles(directory=FRONTEND), name="static")


@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")
