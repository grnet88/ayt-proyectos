# AyT Proyectos

Aplicación para diseñar proyectos de seguridad electrónica integral (CCTV, control de accesos,
LPR, FaceID, térmicas, PTZ, redes de fibra y energía, gabinetes, obra civil y centrales de monitoreo).

Estado actual: **prototipo de la etapa 1, diseño perimetral sobre mapa satelital**. Ver
[docs/ESTADO.md](docs/ESTADO.md) para qué funciona hoy y cuáles son los próximos pasos, y
[docs/ROADMAP.md](docs/ROADMAP.md) para el plan completo.

## Cómo probarlo

Requiere Python 3.11 o superior y conexión a internet para ver el mapa satelital.

- **Windows:** doble clic en `iniciar.bat`. Abre el navegador en http://localhost:8000.
- **Linux:** `./iniciar.sh` y abrir http://localhost:8000.

Los proyectos se guardan en `datos/ayt.db` (SQLite). Para usar otra ubicación, definir la variable
de entorno `AYT_DB`.

## Uso rápido

1. Buscar la dirección o pegar coordenadas (`-32.95, -60.75`) en **Ubicación**.
2. **Perímetro cerrado**: clic en cada vértice del cerco y clic en el primero para cerrar.
3. **Rack central** (y **Fuente / UPS** si hay otros puntos de energía): clic donde van.
4. **Distribuir cámaras y gabinetes**: elige modelo, espaciado (vacío = 90 % del alcance de
   analítica) y cámaras por gabinete. Pone una cámara en cada esquina mirando a lo largo del lado.
5. Ajustar a mano: arrastrar, rotar, cambiar modelo, agregar cámaras sueltas (PTZ, LPR…).
6. Revisar **Resultados**: cobertura y puntos ciegos (en rojo sobre el cerco), caída de tensión
   por fuente, UPS sugerida, fibra, UTP, ancho de banda, almacenamiento y listado de materiales.
7. **Exportar listado** descarga el listado en CSV (abre en Excel).

## Estructura

```
backend/app/main.py            API REST (FastAPI) y servidor de la interfaz
backend/app/db.py              Persistencia SQLite (proyectos y catálogo)
backend/app/catalogo_base.json Catálogo inicial, cargado desde los datasheets de las obras de referencia
backend/app/engine/geo.py      Geometría (proyección local, recorridos, sectores de visión)
backend/app/engine/calculo.py  Distribución automática y cálculos (cobertura, red, energía, listado)
backend/tests/                 Pruebas del motor (pytest)
frontend/                      Interfaz web (Leaflet + Geoman, sin compilación)
```

## Desarrollo

```
pip install -r requirements-dev.txt
cd backend
python -m pytest -q
python -m uvicorn app.main:app --reload
```
