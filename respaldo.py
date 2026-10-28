"""Hace una copia de seguridad de la base de datos y de las fotos.

Ejecútalo con MySQL encendido:
    python respaldo.py

Crea una carpeta como respaldos/2026-10-27_1830/ con:
  - porcicola.sql  (todos los datos)
  - fotos/         (las fotos de los cerdos)

Para RECUPERAR los datos desde un respaldo (esto reemplaza los datos actuales):
    C:\\xampp\\mysql\\bin\\mysql.exe -u root porcicola < respaldos\\2026-10-27_1830\\porcicola.sql
y copia la carpeta fotos/ del respaldo dentro de static/.
"""
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from db import CONFIG

MYSQLDUMP = r"C:\xampp\mysql\bin\mysqldump.exe"  # programa de XAMPP que exporta la base de datos
CARPETA_PROYECTO = Path(__file__).parent


def main():
    destino = CARPETA_PROYECTO / "respaldos" / datetime.now().strftime("%Y-%m-%d_%H%M")
    destino.mkdir(parents=True, exist_ok=True)

    archivo_sql = destino / f"{CONFIG['database']}.sql"
    with open(archivo_sql, "w", encoding="utf-8") as salida:
        resultado = subprocess.run(
            [MYSQLDUMP, "-u", CONFIG["user"], "--routines", "--databases", CONFIG["database"]],
            stdout=salida, stderr=subprocess.PIPE, text=True,
        )
    if resultado.returncode != 0:
        print("No se pudo hacer el respaldo. ¿Está MySQL encendido en XAMPP?")
        print(resultado.stderr)
        return

    fotos = CARPETA_PROYECTO / "static" / "fotos"
    if fotos.exists():
        shutil.copytree(fotos, destino / "fotos")

    print(f"Respaldo listo en: {destino}")
    print("Consejo: copia esa carpeta a una memoria USB o a Google Drive de vez en cuando.")


if __name__ == "__main__":
    main()
