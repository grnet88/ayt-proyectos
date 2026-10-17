#!/usr/bin/env sh
# Inicia AyT Proyectos en Linux/macOS. Requiere Python 3.11 o superior.
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install -r requirements.txt
fi
cd backend
exec ../.venv/bin/python -m uvicorn app.main:app --host "${HOST:-127.0.0.1}" --port "${PORT:-8000}"
