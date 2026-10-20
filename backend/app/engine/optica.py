"""Óptica de cámara sobre el terreno: altura, inclinación, zona ciega, alcance efectivo y PPM.

Convenciones:
- `altura_m`: altura de montaje sobre el piso.
- `inclinacion`: grados por debajo de la horizontal del eje óptico. Si no se indica, se usa la
  inclinación "automática": el borde superior del campo vertical toca el piso justo en el alcance
  de analítica, así no se desperdicia imagen por encima de lo que la analítica puede usar.
- PPM (píxeles por metro): si el modelo trae `resolucion_h` se calcula con el ancho de escena;
  si no, se deriva del DORI del datasheet (identificación = 250 PPM, IEC 62676-4).
"""
from __future__ import annotations

import math

PPM_DORI = {"d": 25, "o": 62, "r": 125, "i": 250}
NOMBRE_DORI = {"d": "detección", "o": "observación", "r": "reconocimiento", "i": "identificación"}


def _tan(g: float) -> float:
    return math.tan(math.radians(g))


def inclinacion_auto(altura: float, alcance: float, vfov: float) -> float:
    return min(89.0, math.degrees(math.atan2(altura, alcance)) + vfov / 2)


def ppm_a(distancia: float, modelo: dict) -> float | None:
    if distancia <= 0:
        return None
    if modelo.get("resolucion_h") and modelo.get("hfov") and modelo["hfov"] < 180:
        return modelo["resolucion_h"] / (2 * distancia * _tan(modelo["hfov"] / 2))
    di = (modelo.get("dori") or {}).get("i")
    return PPM_DORI["i"] * di / distancia if di else None


def distancia_para_ppm(ppm: float, modelo: dict) -> float | None:
    """Distancia horizontal máxima a la que la cámara entrega `ppm` (sin limitar por inclinación)."""
    ref = ppm_a(1.0, modelo)
    return ref / ppm if ref else None


def optica(props: dict, modelo: dict, p: dict) -> dict:
    """Devuelve la geometría efectiva de una cámara sobre el piso."""
    alcance = float(props.get("alcance") or modelo.get("alcance_analitica_m") or 0)
    altura = float(props.get("altura_m") or p["altura_camara_m"])
    hfov, vfov = float(modelo.get("hfov") or 0), modelo.get("vfov")
    r = {"altura_m": altura, "alcance_m": alcance, "inclinacion": None, "inclinacion_auto": True,
         "zona_ciega_m": float(p["dist_min_camara_m"]), "alcance_efectivo_m": alcance, "borde_lejano_m": None}
    if hfov < 360 and vfov:
        manual = props.get("inclinacion")
        incl = float(manual) if manual not in (None, "") else inclinacion_auto(altura, alcance, vfov)
        r["inclinacion"] = round(incl, 1)
        r["inclinacion_auto"] = manual in (None, "")
        abajo = min(incl + vfov / 2, 89.9)
        r["zona_ciega_m"] = altura / _tan(abajo) if abajo > 0 else 0.0
        arriba = incl - vfov / 2
        lejano = altura / _tan(arriba) if arriba > 0.05 else math.inf
        r["borde_lejano_m"] = None if math.isinf(lejano) else lejano
        r["alcance_efectivo_m"] = min(alcance, lejano)
        if r["zona_ciega_m"] >= r["alcance_efectivo_m"]:
            r["alcance_efectivo_m"] = r["zona_ciega_m"]  # la cámara mira casi al piso: no cubre nada útil
    r["ppm_borde"] = ppm_a(r["alcance_efectivo_m"], modelo)
    r["dori_m"] = {k: distancia_para_ppm(v, modelo) for k, v in PPM_DORI.items()}
    for k in ("zona_ciega_m", "alcance_efectivo_m", "borde_lejano_m", "ppm_borde"):
        if r[k] is not None:
            r[k] = round(r[k], 1)
    r["dori_m"] = {k: (round(v, 1) if v else None) for k, v in r["dori_m"].items()}
    return r
