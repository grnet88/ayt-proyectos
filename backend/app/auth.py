"""Usuarios, roles, sesiones y llave de recuperación del superadministrador.

- `aytroot` es el superadministrador: fijo, no se puede borrar, desactivar ni cambiar de rol,
  y solo él puede cambiar su propia contraseña. Su contraseña se define en la configuración
  inicial (nunca está escrita en el código).
- La llave de recuperación es un archivo que se descarga una sola vez al configurar. Solo se
  guarda su huella (hash). Con el archivo, desde la misma PC del servidor, se puede definir
  una contraseña nueva para aytroot. Al usarla se genera una llave nueva y la anterior deja de valer.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import uuid

from . import db

SUPERADMIN = "aytroot"
ROLES = {
    "superadmin": "Superadministrador",
    "ingeniero": "Ingeniero",
    "relevador": "Relevador",
    "comercial": "Comercial",
    "visor": "Visor cliente",
}
ROLES_EDICION = {"superadmin", "ingeniero", "relevador"}
DURACION_SESION = 12 * 3600
LARGO_MINIMO = 8
ENCABEZADO_LLAVE = "AYT-PROYECTOS-LLAVE-RECUPERACION-v1"


class ErrorAuth(Exception):
    pass


# --------------------------------------------------------------------------- hash


def _hash(secreto: str, sal: bytes | None = None) -> str:
    sal = sal or secrets.token_bytes(16)
    h = hashlib.scrypt(secreto.encode("utf-8"), salt=sal, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${base64.b64encode(sal).decode()}${base64.b64encode(h).decode()}"


def _verificar(secreto: str, guardado: str) -> bool:
    try:
        _, sal, h = guardado.split("$")
        calc = _hash(secreto, base64.b64decode(sal)).split("$")[2]
        return hmac.compare_digest(calc, h)
    except (ValueError, TypeError):
        return False


def _validar_clave(clave: str) -> None:
    if len(clave or "") < LARGO_MINIMO:
        raise ErrorAuth(f"La contraseña debe tener al menos {LARGO_MINIMO} caracteres.")


# --------------------------------------------------------------------------- usuarios


def _publico(f) -> dict:
    return {"id": f["id"], "usuario": f["usuario"], "nombre": f["nombre"], "rol": f["rol"],
            "rol_nombre": ROLES.get(f["rol"], f["rol"]), "activo": bool(f["activo"]), "fijo": bool(f["fijo"]),
            "proyectos": json.loads(f["proyectos"] or "[]")}


def configurado() -> bool:
    with db.conexion() as con:
        return con.execute("SELECT 1 FROM usuarios WHERE usuario=?", (SUPERADMIN,)).fetchone() is not None


def configuracion_inicial(clave: str) -> str:
    """Crea aytroot y devuelve el contenido del archivo de llave de recuperación."""
    if configurado():
        raise ErrorAuth("El sistema ya está configurado.")
    _validar_clave(clave)
    with db.conexion() as con:
        con.execute("INSERT INTO usuarios (id, usuario, nombre, rol, clave_hash, activo, fijo, creado) "
                    "VALUES (?, ?, ?, 'superadmin', ?, 1, 1, ?)",
                    (uuid.uuid4().hex[:12], SUPERADMIN, "Superadministrador", _hash(clave), time.time()))
    db.auditar(SUPERADMIN, "configuracion_inicial")
    return generar_llave()


def listar_usuarios() -> list[dict]:
    with db.conexion() as con:
        return [_publico(f) for f in con.execute("SELECT * FROM usuarios ORDER BY fijo DESC, usuario")]


def obtener_usuario(uid: str) -> dict | None:
    with db.conexion() as con:
        f = con.execute("SELECT * FROM usuarios WHERE id=?", (uid,)).fetchone()
    return _publico(f) if f else None


def crear_usuario(usuario: str, nombre: str, rol: str, clave: str, proyectos: list[str] | None = None) -> dict:
    usuario = (usuario or "").strip().lower()
    if not usuario or usuario == SUPERADMIN:
        raise ErrorAuth("Nombre de usuario inválido.")
    if rol not in ROLES or rol == "superadmin":
        raise ErrorAuth("Rol inválido.")
    _validar_clave(clave)
    uid = uuid.uuid4().hex[:12]
    try:
        with db.conexion() as con:
            con.execute("INSERT INTO usuarios (id, usuario, nombre, rol, clave_hash, proyectos, creado) "
                        "VALUES (?,?,?,?,?,?,?)",
                        (uid, usuario, nombre, rol, _hash(clave), json.dumps(proyectos or []), time.time()))
    except Exception as e:  # noqa: BLE001 - usuario repetido
        raise ErrorAuth("Ese nombre de usuario ya existe.") from e
    return obtener_usuario(uid)


def modificar_usuario(uid: str, cambios: dict, actor: dict) -> dict:
    u = obtener_usuario(uid)
    if not u:
        raise ErrorAuth("Usuario inexistente.")
    if u["fijo"]:
        # aytroot: solo puede cambiar su propia contraseña y su nombre visible
        if actor["id"] != u["id"]:
            raise ErrorAuth("El superadministrador solo puede ser modificado por él mismo.")
        cambios = {k: v for k, v in cambios.items() if k in ("clave", "nombre")}
    sets, vals = [], []
    if "nombre" in cambios:
        sets.append("nombre=?"), vals.append(cambios["nombre"])
    if "rol" in cambios:
        if cambios["rol"] not in ROLES or cambios["rol"] == "superadmin":
            raise ErrorAuth("Rol inválido.")
        sets.append("rol=?"), vals.append(cambios["rol"])
    if "activo" in cambios:
        sets.append("activo=?"), vals.append(1 if cambios["activo"] else 0)
    if "proyectos" in cambios:
        sets.append("proyectos=?"), vals.append(json.dumps(list(cambios["proyectos"] or [])))
    if cambios.get("clave"):
        _validar_clave(cambios["clave"])
        sets.append("clave_hash=?"), vals.append(_hash(cambios["clave"]))
    if sets:
        with db.conexion() as con:
            con.execute(f"UPDATE usuarios SET {', '.join(sets)} WHERE id=?", (*vals, uid))
            if "clave" in cambios or cambios.get("activo") is False:
                con.execute("DELETE FROM sesiones WHERE usuario_id=? AND usuario_id<>?", (uid, actor["id"]))
    db.auditar(actor["usuario"], "modificar_usuario", f"{u['usuario']}: {', '.join(k for k in cambios if k != 'clave')}"
               + (" + contraseña" if cambios.get("clave") else ""))
    return obtener_usuario(uid)


def borrar_usuario(uid: str, actor: dict) -> None:
    u = obtener_usuario(uid)
    if not u:
        raise ErrorAuth("Usuario inexistente.")
    if u["fijo"]:
        raise ErrorAuth("El superadministrador no se puede borrar.")
    with db.conexion() as con:
        con.execute("DELETE FROM usuarios WHERE id=?", (uid,))
    db.auditar(actor["usuario"], "borrar_usuario", u["usuario"])


# --------------------------------------------------------------------------- sesiones


def iniciar_sesion(usuario: str, clave: str) -> tuple[str, dict]:
    with db.conexion() as con:
        f = con.execute("SELECT * FROM usuarios WHERE usuario=?", ((usuario or "").strip().lower(),)).fetchone()
    if not f or not f["activo"] or not _verificar(clave or "", f["clave_hash"]):
        db.auditar(usuario, "ingreso_fallido")
        raise ErrorAuth("Usuario o contraseña incorrectos.")
    token = secrets.token_urlsafe(32)
    with db.conexion() as con:
        con.execute("DELETE FROM sesiones WHERE expira < ?", (time.time(),))
        con.execute("INSERT INTO sesiones (token, usuario_id, expira) VALUES (?,?,?)",
                    (token, f["id"], time.time() + DURACION_SESION))
    db.auditar(f["usuario"], "ingreso")
    return token, _publico(f)


def usuario_de_sesion(token: str | None) -> dict | None:
    if not token:
        return None
    with db.conexion() as con:
        f = con.execute("SELECT u.* FROM sesiones s JOIN usuarios u ON u.id = s.usuario_id "
                        "WHERE s.token=? AND s.expira > ? AND u.activo=1", (token, time.time())).fetchone()
    return _publico(f) if f else None


def cerrar_sesion(token: str | None) -> None:
    if token:
        with db.conexion() as con:
            con.execute("DELETE FROM sesiones WHERE token=?", (token,))


# --------------------------------------------------------------------------- llave de recuperación


def generar_llave() -> str:
    """Genera una llave nueva (invalida la anterior) y devuelve el contenido del archivo."""
    secreto = secrets.token_urlsafe(48)
    db.config_guardar("llave_recuperacion", _hash(secreto))
    db.config_guardar("llave_recuperacion_fecha", str(time.time()))
    return (f"{ENCABEZADO_LLAVE}\n"
            f"# Llave de recuperación del usuario {SUPERADMIN} de AyT Proyectos.\n"
            f"# Guardala fuera de la PC del servidor (pendrive, caja fuerte). Quien la tenga y acceda\n"
            f"# a la PC del servidor puede definir una contraseña nueva para {SUPERADMIN}.\n"
            f"# Generada: {time.strftime('%Y-%m-%d %H:%M')}\n"
            f"{secreto}\n")


def _secreto_de_archivo(contenido: str) -> str:
    lineas = [ln.strip() for ln in (contenido or "").splitlines() if ln.strip() and not ln.startswith("#")]
    if len(lineas) != 2 or lineas[0] != ENCABEZADO_LLAVE:
        raise ErrorAuth("El archivo no es una llave de recuperación válida.")
    return lineas[1]


def recuperar(contenido_llave: str, clave_nueva: str) -> str:
    """Valida la llave, define la contraseña nueva de aytroot y devuelve una llave nueva."""
    guardada = db.config_obtener("llave_recuperacion")
    if not guardada or not _verificar(_secreto_de_archivo(contenido_llave), guardada):
        db.auditar(SUPERADMIN, "recuperacion_fallida")
        raise ErrorAuth("La llave no corresponde a esta instalación o ya fue usada.")
    _validar_clave(clave_nueva)
    with db.conexion() as con:
        uid = con.execute("SELECT id FROM usuarios WHERE usuario=?", (SUPERADMIN,)).fetchone()["id"]
        con.execute("UPDATE usuarios SET clave_hash=?, activo=1, rol='superadmin', fijo=1 WHERE id=?",
                    (_hash(clave_nueva), uid))
        con.execute("DELETE FROM sesiones WHERE usuario_id=?", (uid,))
    db.auditar(SUPERADMIN, "recuperacion_con_llave")
    return generar_llave()


# --------------------------------------------------------------------------- permisos


def puede_editar(u: dict) -> bool:
    return u["rol"] in ROLES_EDICION


def puede_ver_proyecto(u: dict, pid: str) -> bool:
    return u["rol"] != "visor" or pid in u["proyectos"]
