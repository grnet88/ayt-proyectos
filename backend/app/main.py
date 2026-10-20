"""Servidor web: API REST + interfaz estática.

Ejecutar desde la carpeta backend:  uvicorn app.main:app --reload
"""
from __future__ import annotations

import base64
import csv
import io
import mimetypes
import re
import shutil
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import auth, db
from .engine.calculo import PARAMETROS_DEFAULT, calcular, distribuir_perimetro

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
# Windows puede registrar .js como text/plain y el navegador rechaza los módulos (pdf.js)
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/javascript", ".mjs")
TIPOS_PLANO = {b"\x89PNG": ("png", "image/png"), b"\xff\xd8\xff": ("jpg", "image/jpeg")}
MAX_PLANO = 30 * 1024 * 1024
ARCHIVO_PLANO = re.compile(r"^[0-9a-f]{12}\.(png|jpg)$")
COOKIE = "ayt_sesion"
LOCALES = {"127.0.0.1", "::1", "localhost", "testclient"}

app = FastAPI(title="AyT Proyectos", version="0.2.0")
db.inicializar()


# --------------------------------------------------------------------------- dependencias


def usuario_actual(request: Request) -> dict:
    u = auth.usuario_de_sesion(request.cookies.get(COOKIE))
    if not u:
        raise HTTPException(401, "Sesión no iniciada")
    return u


def editor(u: dict = Depends(usuario_actual)) -> dict:
    if not auth.puede_editar(u):
        raise HTTPException(403, "Tu usuario es de solo lectura")
    return u


def superadmin(u: dict = Depends(usuario_actual)) -> dict:
    if u["rol"] != "superadmin":
        raise HTTPException(403, "Solo el superadministrador puede hacer esto")
    return u


def solo_local(request: Request) -> None:
    """La configuración inicial y la recuperación solo se aceptan desde la PC del servidor."""
    if (request.client.host if request.client else "") not in LOCALES:
        raise HTTPException(403, "Esta operación solo se puede hacer desde la PC donde corre el servidor")


def _proyecto(pid: str, u: dict) -> dict:
    p = db.obtener_proyecto(pid)
    if not p or not auth.puede_ver_proyecto(u, pid):
        raise HTTPException(404, "Proyecto no encontrado")
    return p


def _escenario(eid: str, u: dict) -> dict:
    e = db.obtener_escenario(eid)
    if not e or not auth.puede_ver_proyecto(u, e["proyecto_id"]):
        raise HTTPException(404, "Escenario no encontrado")
    return e


def _error(e: auth.ErrorAuth):
    raise HTTPException(400, str(e))


# --------------------------------------------------------------------------- sesión y configuración


@app.get("/api/estado")
def estado(request: Request):
    u = auth.usuario_de_sesion(request.cookies.get(COOKIE))
    return {"configurado": auth.configurado(), "usuario": u, "roles": auth.ROLES,
            "local": (request.client.host if request.client else "") in LOCALES}


@app.post("/api/configuracion-inicial", dependencies=[Depends(solo_local)])
def configuracion_inicial(datos: dict):
    try:
        llave = auth.configuracion_inicial(datos.get("clave", ""))
    except auth.ErrorAuth as e:
        _error(e)
    return {"llave": llave, "archivo": "aytroot-llave-recuperacion.key"}


@app.post("/api/recuperar", dependencies=[Depends(solo_local)])
def recuperar(datos: dict):
    try:
        llave = auth.recuperar(datos.get("llave", ""), datos.get("clave", ""))
    except auth.ErrorAuth as e:
        _error(e)
    return {"llave": llave, "archivo": "aytroot-llave-recuperacion.key"}


@app.post("/api/ingresar")
def ingresar(datos: dict, response: Response):
    try:
        token, u = auth.iniciar_sesion(datos.get("usuario", ""), datos.get("clave", ""))
    except auth.ErrorAuth as e:
        raise HTTPException(401, str(e))
    response.set_cookie(COOKIE, token, httponly=True, samesite="lax", max_age=auth.DURACION_SESION)
    return u


@app.post("/api/salir")
def salir(request: Request, response: Response):
    auth.cerrar_sesion(request.cookies.get(COOKIE))
    response.delete_cookie(COOKIE)
    return {"ok": True}


@app.post("/api/mi-clave")
def mi_clave(datos: dict, u: dict = Depends(usuario_actual)):
    try:
        auth.iniciar_sesion(u["usuario"], datos.get("actual", ""))  # verifica la actual
    except auth.ErrorAuth:
        raise HTTPException(400, "La contraseña actual no es correcta")
    try:
        auth.modificar_usuario(u["id"], {"clave": datos.get("nueva", "")}, u)
    except auth.ErrorAuth as e:
        _error(e)
    return {"ok": True}


# --------------------------------------------------------------------------- usuarios (superadmin)


@app.get("/api/usuarios")
def get_usuarios(_: dict = Depends(superadmin)):
    return auth.listar_usuarios()


@app.post("/api/usuarios")
def post_usuario(datos: dict, u: dict = Depends(superadmin)):
    try:
        nuevo = auth.crear_usuario(datos.get("usuario", ""), datos.get("nombre", ""), datos.get("rol", ""),
                                   datos.get("clave", ""), datos.get("proyectos"))
    except auth.ErrorAuth as e:
        _error(e)
    db.auditar(u["usuario"], "crear_usuario", nuevo["usuario"])
    return nuevo


@app.put("/api/usuarios/{uid}")
def put_usuario(uid: str, datos: dict, u: dict = Depends(superadmin)):
    try:
        return auth.modificar_usuario(uid, datos, u)
    except auth.ErrorAuth as e:
        _error(e)


@app.delete("/api/usuarios/{uid}")
def delete_usuario(uid: str, u: dict = Depends(superadmin)):
    try:
        auth.borrar_usuario(uid, u)
    except auth.ErrorAuth as e:
        _error(e)
    return {"ok": True}


@app.post("/api/llave-recuperacion")
def nueva_llave(u: dict = Depends(superadmin)):
    db.auditar(u["usuario"], "nueva_llave_recuperacion")
    return {"llave": auth.generar_llave(), "archivo": "aytroot-llave-recuperacion.key"}


@app.get("/api/auditoria")
def get_auditoria(_: dict = Depends(superadmin)):
    return db.auditoria()


# --------------------------------------------------------------------------- catálogo


@app.get("/api/parametros")
def parametros(_: dict = Depends(usuario_actual)):
    return PARAMETROS_DEFAULT


@app.get("/api/catalogo")
def get_catalogo(_: dict = Depends(usuario_actual)):
    return list(db.catalogo().values())


@app.post("/api/catalogo")
def post_modelo(m: dict, _: dict = Depends(editor)):
    if not m.get("categoria") or not m.get("modelo"):
        raise HTTPException(422, "Faltan categoría o modelo")
    return db.guardar_modelo(m)


@app.delete("/api/catalogo/{mid}")
def delete_modelo(mid: str, _: dict = Depends(editor)):
    if not db.borrar_modelo(mid):
        raise HTTPException(400, "Solo se pueden borrar modelos cargados por el usuario")
    return {"ok": True}


# --------------------------------------------------------------------------- proyectos


@app.get("/api/proyectos")
def get_proyectos(u: dict = Depends(usuario_actual)):
    return db.listar_proyectos(u["proyectos"] if u["rol"] == "visor" else None)


@app.post("/api/proyectos")
def post_proyecto(datos: dict, u: dict = Depends(editor)):
    p = db.crear_proyecto(datos)
    db.auditar(u["usuario"], "crear_proyecto", p["nombre"])
    return p


@app.get("/api/proyectos/{pid}")
def get_proyecto(pid: str, u: dict = Depends(usuario_actual)):
    return _proyecto(pid, u)


@app.put("/api/proyectos/{pid}")
def put_proyecto(pid: str, datos: dict, u: dict = Depends(editor)):
    _proyecto(pid, u)
    return db.actualizar_proyecto(pid, datos)


@app.delete("/api/proyectos/{pid}")
def delete_proyecto(pid: str, u: dict = Depends(editor)):
    p = _proyecto(pid, u)
    db.borrar_proyecto(pid)
    shutil.rmtree(_carpeta_planos(pid), ignore_errors=True)
    db.auditar(u["usuario"], "borrar_proyecto", p["nombre"])
    return {"ok": True}


@app.post("/api/proyectos/{pid}/escenarios")
def post_escenario(pid: str, datos: dict, u: dict = Depends(editor)):
    _proyecto(pid, u)
    e = db.crear_escenario(pid, datos.get("nombre") or "Nueva opción", datos.get("tipo") or "alternativa",
                           datos.get("copiar_de"))
    if not e:
        raise HTTPException(400, "No se pudo crear el escenario")
    return e


# --------------------------------------------------------------------------- planos (imágenes superpuestas)


def _carpeta_planos(pid: str) -> Path:
    return db.RUTA_DB.parent / "planos" / pid


@app.post("/api/proyectos/{pid}/planos")
def post_plano(pid: str, datos: dict, u: dict = Depends(editor)):
    """Recibe la imagen como data URL (PNG o JPG; los PDF se convierten a PNG en el navegador)."""
    p = _proyecto(pid, u)
    try:
        crudo = base64.b64decode((datos.get("imagen") or "").split(",", 1)[-1], validate=True)
    except ValueError:
        raise HTTPException(422, "Imagen inválida")
    if len(crudo) > MAX_PLANO:
        raise HTTPException(413, "El plano supera los 30 MB")
    tipo = next((t for firma, t in TIPOS_PLANO.items() if crudo.startswith(firma)), None)
    if not tipo:
        raise HTTPException(422, "El plano debe ser PNG o JPG")
    fid = uuid.uuid4().hex[:12]
    carpeta = _carpeta_planos(pid)
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / f"{fid}.{tipo[0]}").write_bytes(crudo)
    plano = {"id": fid, "archivo": f"{fid}.{tipo[0]}", "nombre": (datos.get("nombre") or "Plano")[:120],
             "ancho": int(datos.get("ancho") or 0), "alto": int(datos.get("alto") or 0),
             "georef": datos.get("georef"), "opacidad": 0.6, "visible": True, "planta": datos.get("planta") or "exterior"}
    db.auditar(u["usuario"], "cargar_plano", f"{p['nombre']}: {plano['nombre']}")
    return db.actualizar_proyecto(pid, {"planos": [*p.get("planos", []), plano]})


@app.get("/api/proyectos/{pid}/planos/{archivo}")
def get_plano(pid: str, archivo: str, u: dict = Depends(usuario_actual)):
    p = _proyecto(pid, u)
    if not ARCHIVO_PLANO.match(archivo) or archivo not in {pl["archivo"] for pl in p.get("planos", [])}:
        raise HTTPException(404, "Plano no encontrado")
    ruta = _carpeta_planos(pid) / archivo
    if not ruta.exists():
        raise HTTPException(404, "Plano no encontrado")
    return FileResponse(ruta, media_type="image/png" if archivo.endswith(".png") else "image/jpeg")


@app.delete("/api/proyectos/{pid}/planos/{fid}")
def delete_plano(pid: str, fid: str, u: dict = Depends(editor)):
    p = _proyecto(pid, u)
    plano = next((pl for pl in p.get("planos", []) if pl["id"] == fid), None)
    if not plano:
        raise HTTPException(404, "Plano no encontrado")
    if ARCHIVO_PLANO.match(plano["archivo"]):
        (_carpeta_planos(pid) / plano["archivo"]).unlink(missing_ok=True)
    return db.actualizar_proyecto(pid, {"planos": [pl for pl in p["planos"] if pl["id"] != fid]})


# --------------------------------------------------------------------------- escenarios


@app.get("/api/escenarios/{eid}")
def get_escenario(eid: str, u: dict = Depends(usuario_actual)):
    return _escenario(eid, u)


@app.put("/api/escenarios/{eid}")
def put_escenario(eid: str, datos: dict, u: dict = Depends(editor)):
    _escenario(eid, u)
    return db.guardar_escenario(eid, datos)


@app.delete("/api/escenarios/{eid}")
def delete_escenario(eid: str, u: dict = Depends(editor)):
    _escenario(eid, u)
    r = db.borrar_escenario(eid)
    if r == "ultimo":
        raise HTTPException(400, "Un proyecto necesita al menos un escenario")
    return {"ok": True}


@app.post("/api/escenarios/{eid}/distribuir")
def post_distribuir(eid: str, opciones: dict | None = None, u: dict = Depends(editor)):
    e = _escenario(eid, u)
    try:
        e["elementos"] = distribuir_perimetro(e, db.catalogo(), opciones or {})
    except ValueError as err:
        raise HTTPException(422, str(err))
    if opciones:
        e["parametros"] = {**e.get("parametros", {}), **{k: v for k, v in opciones.items() if v is not None}}
    return db.guardar_escenario(eid, e)


@app.get("/api/escenarios/{eid}/calculo")
def get_calculo(eid: str, u: dict = Depends(usuario_actual)):
    try:
        return calcular(_escenario(eid, u), db.catalogo())
    except ValueError as err:
        raise HTTPException(422, str(err))


@app.get("/api/escenarios/{eid}/materiales.csv")
def get_materiales_csv(eid: str, u: dict = Depends(usuario_actual)):
    e = _escenario(eid, u)
    p = _proyecto(e["proyecto_id"], u)
    res = calcular(e, db.catalogo())
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Categoría", "Descripción", "Modelo", "Cantidad", "Unidad"])
    for m in res["materiales"]:
        w.writerow([m["categoria"], m["descripcion"], m["modelo"], m["cantidad"], m["unidad"]])
    nombre = "".join(ch if ch.isalnum() or ch in " -_" else "_" for ch in f"{p['nombre']} - {e['nombre']}").strip()
    return StreamingResponse(
        iter(["﻿" + buf.getvalue()]), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="Materiales - {nombre or "proyecto"}.csv"'},
    )


# --------------------------------------------------------------------------- interfaz

app.mount("/static", StaticFiles(directory=FRONTEND), name="static")


@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")


@app.get("/salud", response_class=PlainTextResponse)
def salud():
    return "ok"
