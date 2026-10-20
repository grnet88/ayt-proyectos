"""Geometría plana sobre una proyección local.

Para obras de escala barrial (unos pocos km) una proyección equirectangular
centrada en la obra tiene error despreciable (< 0,1 %), y evita depender de
librerías GIS. Todas las distancias están en metros y los ángulos en grados
(azimut: 0 = norte, sentido horario).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

R_TIERRA = 6371008.8


@dataclass(frozen=True)
class Proyeccion:
    lat0: float
    lon0: float

    def a_xy(self, lat: float, lon: float) -> tuple[float, float]:
        k = math.pi / 180 * R_TIERRA
        return ((lon - self.lon0) * k * math.cos(math.radians(self.lat0)), (lat - self.lat0) * k)

    def a_latlon(self, x: float, y: float) -> tuple[float, float]:
        k = math.pi / 180 * R_TIERRA
        return (self.lat0 + y / k, self.lon0 + x / (k * math.cos(math.radians(self.lat0))))

    @classmethod
    def para(cls, puntos_latlon: list[tuple[float, float]]) -> "Proyeccion":
        if not puntos_latlon:
            return cls(0.0, 0.0)
        lat = sum(p[0] for p in puntos_latlon) / len(puntos_latlon)
        lon = sum(p[1] for p in puntos_latlon) / len(puntos_latlon)
        return cls(lat, lon)


def dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def azimut(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Azimut de a hacia b (0 = norte, horario)."""
    return math.degrees(math.atan2(b[0] - a[0], b[1] - a[1])) % 360


def dif_angular(a: float, b: float) -> float:
    d = (a - b) % 360
    return min(d, 360 - d)


class Recorrido:
    """Polilínea (abierta o cerrada) con progresiva: distancia medida sobre el trazado."""

    def __init__(self, pts: list[tuple[float, float]], cerrado: bool):
        if cerrado and len(pts) > 1 and pts[0] == pts[-1]:
            pts = pts[:-1]
        self.cerrado = cerrado
        self.pts = list(pts) + ([pts[0]] if cerrado else [])
        self.acum = [0.0]
        for i in range(1, len(self.pts)):
            self.acum.append(self.acum[-1] + dist(self.pts[i - 1], self.pts[i]))

    @property
    def largo(self) -> float:
        return self.acum[-1]

    def punto(self, s: float) -> tuple[tuple[float, float], float]:
        """Punto y azimut del tramo en la progresiva s."""
        if self.cerrado:
            s %= self.largo
        s = max(0.0, min(s, self.largo))
        for i in range(1, len(self.pts)):
            if s <= self.acum[i] or i == len(self.pts) - 1:
                a, b = self.pts[i - 1], self.pts[i]
                seg = self.acum[i] - self.acum[i - 1]
                t = 0.0 if seg == 0 else (s - self.acum[i - 1]) / seg
                return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t), azimut(a, b)
        return self.pts[-1], 0.0

    def tramo(self, desde: float, hasta: float) -> list[tuple[float, float]]:
        """Puntos del recorrido entre dos progresivas, incluyendo los vértices intermedios."""
        pts = [self.punto(desde)[0]]
        pts += [self.pts[i] for i in range(1, len(self.pts) - 1) if desde < self.acum[i] < hasta]
        pts.append(self.punto(hasta)[0])
        return pts

    def proyectar(self, p: tuple[float, float]) -> tuple[float, float]:
        """Progresiva del punto más cercano del recorrido y distancia perpendicular."""
        mejor = (0.0, float("inf"))
        for i in range(1, len(self.pts)):
            a, b = self.pts[i - 1], self.pts[i]
            dx, dy = b[0] - a[0], b[1] - a[1]
            l2 = dx * dx + dy * dy
            t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2))
            q = (a[0] + dx * t, a[1] + dy * t)
            d = dist(p, q)
            if d < mejor[1]:
                mejor = (self.acum[i - 1] + t * math.sqrt(l2), d)
        return mejor

    def lados(self, angulo_quiebre: float) -> list[tuple[float, float]]:
        """Tramos (progresiva inicio, fin) entre vértices donde el trazado gira más que el umbral."""
        n = len(self.pts) - 1
        if n < 1:
            return []
        rumbos = [azimut(self.pts[i], self.pts[i + 1]) for i in range(n)]
        quiebres = []
        for i in range(n):
            if i == 0 and not self.cerrado:
                quiebres.append(0)
                continue
            if dif_angular(rumbos[i], rumbos[i - 1]) >= angulo_quiebre:
                quiebres.append(i)
        if not self.cerrado:
            return [(self.acum[a], self.acum[b] if b < n else self.largo)
                    for a, b in zip(quiebres, quiebres[1:] + [n])]
        if not quiebres:
            return [(0.0, self.largo)]
        out = []
        for k, a in enumerate(quiebres):
            b = quiebres[(k + 1) % len(quiebres)]
            ini, fin = self.acum[a], self.acum[b]
            out.append((ini, fin if fin > ini else fin + self.largo))
        return out

    def distancia(self, s1: float, s2: float) -> float:
        """Distancia mínima sobre el recorrido entre dos progresivas."""
        d = abs(s2 - s1)
        return min(d, self.largo - d) if self.cerrado else d

    def avance(self, desde: float, hasta: float) -> float:
        """Distancia con signo: positiva si el camino más corto va en el sentido del trazado."""
        if not self.cerrado:
            return hasta - desde
        d = (hasta - desde) % self.largo
        return d if d <= self.largo / 2 else d - self.largo


def _cruza(a, b, c, d) -> bool:
    """True si el segmento a-b cruza el segmento c-d (los toques en el extremo `a` no cuentan)."""
    def orient(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    o1, o2, o3, o4 = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
    if abs(o3) < 1e-9:  # la cámara está apoyada sobre el muro: no se bloquea a sí misma
        return False
    return (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0)


def visible(origen, p, bloqueos) -> bool:
    """Línea de vista 2D entre `origen` y `p`, cortada por segmentos de muros u obstáculos."""
    return not any(_cruza(origen, p, c, d) for c, d in bloqueos)


def en_sector(origen, az, hfov, d_min, d_max, p, bloqueos=()) -> bool:
    d = dist(origen, p)
    if d < d_min or d > d_max:
        return False
    if hfov < 360 and dif_angular(azimut(origen, p), az) > hfov / 2:
        return False
    return visible(origen, p, bloqueos) if bloqueos else True
