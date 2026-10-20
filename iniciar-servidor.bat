@echo off
REM Inicia AyT Proyectos como servidor de red (otras PC acceden por http://IP-DEL-SERVIDOR:8000).
REM La configuracion inicial y la recuperacion de aytroot solo funcionan abriendo http://localhost:8000 en esta PC.
cd /d "%~dp0"
if not exist .venv (
  python -m venv .venv
  .venv\Scripts\python -m pip install -r requirements.txt
)
cd backend
..\.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
