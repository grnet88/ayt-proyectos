"""Recuperación de emergencia de aytroot desde la PC del servidor.

Uso (desde la carpeta backend):
    python -m app.recuperar ruta/a/aytroot-llave-recuperacion.key

Pide la contraseña nueva, la aplica y escribe una llave nueva junto a la anterior
(la usada deja de valer).
"""
from __future__ import annotations

import getpass
import sys
from pathlib import Path

from . import auth, db


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    ruta = Path(argv[1])
    if not ruta.is_file():
        print(f"No encuentro el archivo {ruta}")
        return 1
    db.inicializar()
    ver = input("¿Mostrar la contraseña mientras la escribís? (s/n): ").strip().lower() == "s"
    leer = input if ver else getpass.getpass
    clave = leer("Contraseña nueva para aytroot: ")
    if clave != leer("Repetila: "):
        print("Las contraseñas no coinciden. No se cambió nada.")
        return 1
    try:
        nueva = auth.recuperar(ruta.read_text(encoding="utf-8"), clave)
    except auth.ErrorAuth as e:
        print(f"No se pudo recuperar: {e}")
        return 1
    destino = ruta.with_name("aytroot-llave-recuperacion-nueva.key")
    destino.write_text(nueva, encoding="utf-8")
    print(f"Listo. Contraseña de aytroot cambiada.\nLa llave usada ya no vale. Llave nueva: {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
