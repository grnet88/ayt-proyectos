@echo off
REM Inicia AyT Proyectos en Windows. Requiere Python 3.11 o superior.
cd /d "%~dp0"
if not exist .venv python -m venv .venv
REM instala o actualiza dependencias (rapido si ya estan)
.venv\Scripts\python -m pip install -q -r requirements.txt
start "" http://localhost:8000
cd backend
..\.venv\Scripts\python -m uvicorn app.main:app --port 8000
