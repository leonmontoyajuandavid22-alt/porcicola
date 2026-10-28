"""Crea la base de datos "porcicola" con todas sus tablas.

Ejecútalo con XAMPP (MySQL) encendido:
    python crear_base_datos.py

Se puede ejecutar varias veces sin problema: solo crea lo que falte.
Si no hay ningún usuario, te pide los datos del administrador.
"""
from getpass import getpass

import mysql.connector
from werkzeug.security import generate_password_hash

from db import CONFIG

# Cada tabla es un texto SQL. "IF NOT EXISTS" evita errores si ya existe.
# El orden importa: una tabla que apunta a otra (FOREIGN KEY) va después.
TABLAS = [
    # Personas que pueden entrar a la página.
    """CREATE TABLE IF NOT EXISTS usuarios (
        id INT AUTO_INCREMENT PRIMARY KEY,
        usuario VARCHAR(40) NOT NULL UNIQUE,
        nombre VARCHAR(100) NOT NULL,
        clave_hash VARCHAR(255) NOT NULL,
        es_admin BOOLEAN NOT NULL DEFAULT FALSE,
        creado TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS razas (
        id INT AUTO_INCREMENT PRIMARY KEY,
        nombre VARCHAR(60) NOT NULL UNIQUE
    )""",
    """CREATE TABLE IF NOT EXISTS corrales (
        id INT AUTO_INCREMENT PRIMARY KEY,
        nombre VARCHAR(60) NOT NULL UNIQUE,
        capacidad INT NULL,
        descripcion VARCHAR(255) NULL
    )""",
    # madre_id y padre_id apuntan a otros cerdos de la misma tabla.
    """CREATE TABLE IF NOT EXISTS cerdos (
        id INT AUTO_INCREMENT PRIMARY KEY,
        arete VARCHAR(30) NOT NULL UNIQUE,
        nombre VARCHAR(60) NULL,
        sexo ENUM('macho', 'hembra') NOT NULL,
        raza_id INT NULL,
        fecha_nacimiento DATE NULL,
        madre_id INT NULL,
        padre_id INT NULL,
        corral_id INT NULL,
        estado ENUM('activo', 'vendido', 'muerto') NOT NULL DEFAULT 'activo',
        foto VARCHAR(100) NULL,
        observaciones TEXT NULL,
        usuario_id INT NULL,
        creado TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (raza_id) REFERENCES razas(id),
        FOREIGN KEY (madre_id) REFERENCES cerdos(id) ON DELETE SET NULL,
        FOREIGN KEY (padre_id) REFERENCES cerdos(id) ON DELETE SET NULL,
        FOREIGN KEY (corral_id) REFERENCES corrales(id) ON DELETE SET NULL,
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL
    )""",
    # De aquí en adelante: tablas para las partes 2 a 6.
    # "ON DELETE CASCADE" = si se borra el cerdo, se borran sus registros.
    """CREATE TABLE IF NOT EXISTS pesajes (
        id INT AUTO_INCREMENT PRIMARY KEY,
        cerdo_id INT NOT NULL,
        fecha DATE NOT NULL,
        peso_kg DECIMAL(6,2) NOT NULL,
        observaciones VARCHAR(255) NULL,
        usuario_id INT NULL,
        FOREIGN KEY (cerdo_id) REFERENCES cerdos(id) ON DELETE CASCADE,
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL
    )""",
    """CREATE TABLE IF NOT EXISTS salud (
        id INT AUTO_INCREMENT PRIMARY KEY,
        cerdo_id INT NOT NULL,
        tipo ENUM('vacuna', 'desparasitacion', 'enfermedad', 'tratamiento') NOT NULL,
        fecha DATE NOT NULL,
        descripcion VARCHAR(255) NOT NULL,
        medicamento VARCHAR(100) NULL,
        dosis VARCHAR(60) NULL,
        proxima_fecha DATE NULL,
        costo DECIMAL(12,2) NULL,
        responsable VARCHAR(100) NULL,
        observaciones TEXT NULL,
        usuario_id INT NULL,
        FOREIGN KEY (cerdo_id) REFERENCES cerdos(id) ON DELETE CASCADE,
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL
    )""",
    """CREATE TABLE IF NOT EXISTS montas (
        id INT AUTO_INCREMENT PRIMARY KEY,
        cerda_id INT NOT NULL,
        verraco_id INT NULL,
        tipo ENUM('monta', 'inseminacion') NOT NULL,
        fecha DATE NOT NULL,
        fecha_probable_parto DATE NOT NULL,
        estado ENUM('pendiente', 'confirmada', 'fallida', 'parida') NOT NULL DEFAULT 'pendiente',
        observaciones TEXT NULL,
        usuario_id INT NULL,
        FOREIGN KEY (cerda_id) REFERENCES cerdos(id) ON DELETE CASCADE,
        FOREIGN KEY (verraco_id) REFERENCES cerdos(id) ON DELETE SET NULL,
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL
    )""",
    """CREATE TABLE IF NOT EXISTS partos (
        id INT AUTO_INCREMENT PRIMARY KEY,
        cerda_id INT NOT NULL,
        monta_id INT NULL,
        fecha DATE NOT NULL,
        lechones_vivos INT NOT NULL DEFAULT 0,
        lechones_muertos INT NOT NULL DEFAULT 0,
        fecha_destete DATE NULL,
        lechones_destetados INT NULL,
        observaciones TEXT NULL,
        usuario_id INT NULL,
        FOREIGN KEY (cerda_id) REFERENCES cerdos(id) ON DELETE CASCADE,
        FOREIGN KEY (monta_id) REFERENCES montas(id) ON DELETE SET NULL,
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL
    )""",
    # Alimentación: se llena cerdo_id O corral_id, según a quién se le dio.
    # Un corral con registros de alimentación no se puede borrar (para no
    # perder el historial de gastos).
    """CREATE TABLE IF NOT EXISTS alimentacion (
        id INT AUTO_INCREMENT PRIMARY KEY,
        fecha DATE NOT NULL,
        cerdo_id INT NULL,
        corral_id INT NULL,
        tipo_alimento VARCHAR(100) NOT NULL,
        cantidad_kg DECIMAL(8,2) NOT NULL,
        costo DECIMAL(12,2) NULL,
        observaciones VARCHAR(255) NULL,
        usuario_id INT NULL,
        FOREIGN KEY (cerdo_id) REFERENCES cerdos(id) ON DELETE CASCADE,
        FOREIGN KEY (corral_id) REFERENCES corrales(id),
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL
    )""",
    # Una salida por cerdo (UNIQUE): o se vendió o murió.
    """CREATE TABLE IF NOT EXISTS salidas (
        id INT AUTO_INCREMENT PRIMARY KEY,
        cerdo_id INT NOT NULL UNIQUE,
        tipo ENUM('venta', 'muerte') NOT NULL,
        fecha DATE NOT NULL,
        peso_kg DECIMAL(6,2) NULL,
        precio DECIMAL(12,2) NULL,
        comprador VARCHAR(100) NULL,
        causa VARCHAR(255) NULL,
        observaciones TEXT NULL,
        usuario_id INT NULL,
        FOREIGN KEY (cerdo_id) REFERENCES cerdos(id) ON DELETE CASCADE,
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL
    )""",
]

RAZAS_INICIALES = ["Landrace", "Large White", "Duroc", "Pietrain", "Hampshire", "Cruce"]


def crear_admin(cur):
    print("\nNo hay usuarios todavía. Vamos a crear el administrador.")
    usuario = input("Usuario (ej. admin): ").strip() or "admin"
    nombre = input("Tu nombre: ").strip() or usuario
    while True:
        clave = getpass("Contraseña (no se ve mientras escribes): ")
        if len(clave) < 6:
            print("Debe tener al menos 6 caracteres.")
        elif clave != getpass("Repite la contraseña: "):
            print("No coinciden, intenta de nuevo.")
        else:
            break
    cur.execute(
        "INSERT INTO usuarios (usuario, nombre, clave_hash, es_admin) VALUES (%s, %s, %s, TRUE)",
        (usuario, nombre, generate_password_hash(clave)),
    )
    print(f"Administrador '{usuario}' creado.")


def main():
    # Primero nos conectamos sin elegir base, porque quizás aún no existe.
    sin_base = {k: v for k, v in CONFIG.items() if k != "database"}
    con = mysql.connector.connect(**sin_base)
    cur = con.cursor()
    base = CONFIG["database"]
    cur.execute(
        f"CREATE DATABASE IF NOT EXISTS {base} "
        "CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci"
    )
    cur.execute(f"USE {base}")

    # La primera versión del proyecto tenía otra tabla "cerdos".
    # No la borramos: la renombramos para no perder datos.
    if _existe(cur, "cerdos"):
        cur.execute("SHOW COLUMNS FROM cerdos LIKE 'nacimiento'")
        if cur.fetchall():
            cur.execute("RENAME TABLE cerdos TO cerdos_version_anterior")
            print("La tabla 'cerdos' antigua se renombró a 'cerdos_version_anterior'.")

    for sql in TABLAS:
        cur.execute(sql)
    print("Tablas listas.")

    for raza in RAZAS_INICIALES:
        cur.execute("INSERT IGNORE INTO razas (nombre) VALUES (%s)", (raza,))

    cur.execute("SELECT COUNT(*) FROM usuarios")
    if cur.fetchone()[0] == 0:
        crear_admin(cur)

    con.commit()
    cur.close()
    con.close()
    print(f"\n¡Base de datos '{base}' lista!")


def _existe(cur, tabla):
    cur.execute("SHOW TABLES LIKE %s", (tabla,))
    return bool(cur.fetchall())


if __name__ == "__main__":
    main()
