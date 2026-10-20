#!/usr/bin/env sh
# Inicia AyT Proyectos en Linux/macOS. Requiere Python 3.11 o superior.
set -e
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/python -m pip install -q -r requirements.txt  # instala o actualiza dependencias
cd backend
exec ../.venv/bin/python -m uvicorn app.main:app --host "${HOST:-127.0.0.1}" --port "${PORT:-8000}"
