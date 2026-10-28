"""Archivo principal: arranca la página web.

Ejecútalo con:
    python app.py
y abre http://127.0.0.1:5000 en el navegador.
"""
import secrets
import socket
from datetime import date
from pathlib import Path

import mysql.connector
from flask import Flask, g, redirect, render_template, request, session, url_for

from db import consultar_uno
from rutas import panel, reproduccion, salud
from rutas.alimentacion import bp as alimentacion_bp
from rutas.cerdos import bp as cerdos_bp
from rutas.corrales import bp as corrales_bp
from rutas.login import bp as login_bp
from rutas.pesajes import bp as pesajes_bp
from rutas.razas import bp as razas_bp
from rutas.reproduccion import bp as reproduccion_bp
from rutas.salidas import bp as salidas_bp
from rutas.salud import bp as salud_bp

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # fotos de máximo 8 MB
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


def clave_secreta():
    """Flask necesita una clave secreta para firmar la sesión (el login).
    La creamos una sola vez y la guardamos en instance/clave_secreta.txt."""
    archivo = Path(app.instance_path) / "clave_secreta.txt"
    if not archivo.exists():
        archivo.parent.mkdir(exist_ok=True)
        archivo.write_text(secrets.token_hex(32))
    return archivo.read_text().strip()


app.secret_key = clave_secreta()

# Cada "blueprint" es un grupo de páginas que vive en la carpeta rutas/.
app.register_blueprint(login_bp)
app.register_blueprint(cerdos_bp)
app.register_blueprint(corrales_bp)
app.register_blueprint(razas_bp)
app.register_blueprint(pesajes_bp)
app.register_blueprint(salud_bp)
app.register_blueprint(reproduccion_bp)
app.register_blueprint(alimentacion_bp)
app.register_blueprint(salidas_bp)


@app.before_request
def exigir_login():
    """Se ejecuta antes de cada página. Si no has iniciado sesión,
    te manda a la página de login."""
    g.usuario = None
    if "usuario_id" in session:
        g.usuario = consultar_uno(
            "SELECT id, usuario, nombre, es_admin FROM usuarios WHERE id = %s",
            (session["usuario_id"],),
        )
    if g.usuario is None and request.endpoint not in ("login.entrar", "static"):
        return redirect(url_for("login.entrar"))


@app.route("/")
def inicio():
    """Panel de inicio con el resumen de la granja (los datos salen de rutas/panel.py)."""
    return render_template(
        "panel.html",
        tipos=salud.TIPOS,
        estados=reproduccion.ESTADOS_MONTA,
        **panel.resumen(),
    )


@app.errorhandler(mysql.connector.Error)
def error_base_datos(error):
    return render_template("error_bd.html", error=error), 500


# ---- Filtros para las plantillas: {{ cerdo.fecha_nacimiento|fecha }} ----

@app.template_filter("fecha")
def formato_fecha(valor):
    if isinstance(valor, str) and valor:
        valor = date.fromisoformat(valor)  # "2026-10-27" -> fecha
    return valor.strftime("%d/%m/%Y") if valor else "—"


def numero(valor):
    """12500.5 -> "12.500,50" (punto para los miles y coma para decimales, como en Colombia)."""
    decimales = 0 if valor == int(valor) else 2
    texto = f"{valor:,.{decimales}f}"  # 12,500.50
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


@app.template_filter("dinero")
def formato_dinero(valor):
    return "—" if valor is None else "$ " + numero(valor)


@app.template_filter("kg")
def formato_kg(valor):
    return "—" if valor is None else numero(valor) + " kg"


@app.template_filter("edad")
def edad(nacimiento):
    if not nacimiento:
        return "—"
    dias = (date.today() - nacimiento).days
    if dias < 60:
        return f"{dias} días"
    meses = dias // 30
    if meses < 24:
        return f"{meses} meses"
    return f"{meses // 12} años y {meses % 12} meses"


# Cambia esto a True para abrir la página desde el celular u otro computador
# conectado a la MISMA red Wi-Fi. Con False, solo se abre en este computador.
ABRIR_EN_RED = False


def ip_local():
    """La dirección de este computador en la red Wi-Fi (por ejemplo 192.168.1.20)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("8.8.8.8", 80))  # no envía nada: solo sirve para saber qué red se usa
        return s.getsockname()[0]


if __name__ == "__main__":
    if ABRIR_EN_RED:
        print(f"\n  Desde el celular abre:  http://{ip_local()}:5000\n")
        # debug=False: en la red no se debe mostrar el depurador de Flask, por seguridad.
        app.run(host="0.0.0.0", port=5000, debug=False)
    else:
        app.run(debug=True)
