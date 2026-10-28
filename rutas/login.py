"""Inicio y cierre de sesión, cambio de contraseña y lista de usuarios."""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, session, url_for
from mysql.connector import errors
from werkzeug.security import check_password_hash, generate_password_hash

from db import consultar, consultar_uno, ejecutar

bp = Blueprint("login", __name__)


@bp.route("/login", methods=["GET", "POST"])
def entrar():
    if request.method == "POST":
        usuario = consultar_uno(
            "SELECT * FROM usuarios WHERE usuario = %s",
            (request.form["usuario"].strip(),),
        )
        # check_password_hash compara la contraseña escrita con la guardada cifrada.
        if usuario and check_password_hash(usuario["clave_hash"], request.form["clave"]):
            session.clear()
            session["usuario_id"] = usuario["id"]
            return redirect(url_for("inicio"))
        flash("Usuario o contraseña incorrectos.", "danger")
    return render_template("login.html")


@bp.route("/salir")
def salir():
    session.clear()
    return redirect(url_for("login.entrar"))


@bp.route("/cambiar-clave", methods=["GET", "POST"])
def cambiar_clave():
    if request.method == "POST":
        f = request.form
        actual = consultar_uno("SELECT clave_hash FROM usuarios WHERE id = %s", (g.usuario["id"],))
        if not check_password_hash(actual["clave_hash"], f["actual"]):
            flash("La contraseña actual no es correcta.", "danger")
        elif len(f["nueva"]) < 6:
            flash("La nueva contraseña debe tener al menos 6 caracteres.", "danger")
        elif f["nueva"] != f["repetir"]:
            flash("Las contraseñas nuevas no coinciden.", "danger")
        else:
            ejecutar(
                "UPDATE usuarios SET clave_hash = %s WHERE id = %s",
                (generate_password_hash(f["nueva"]), g.usuario["id"]),
            )
            flash("Contraseña cambiada.", "success")
            return redirect(url_for("inicio"))
    return render_template("cambiar_clave.html")


# ---- Usuarios: solo el administrador puede verlos y crearlos ----

def solo_admin():
    if not g.usuario["es_admin"]:
        abort(403)


@bp.route("/usuarios", methods=["GET", "POST"])
def usuarios():
    solo_admin()
    if request.method == "POST":
        f = request.form
        if len(f["clave"]) < 6:
            flash("La contraseña debe tener al menos 6 caracteres.", "danger")
        else:
            try:
                ejecutar(
                    "INSERT INTO usuarios (usuario, nombre, clave_hash, es_admin) VALUES (%s, %s, %s, %s)",
                    (f["usuario"].strip(), f["nombre"].strip(),
                     generate_password_hash(f["clave"]), "es_admin" in f),
                )
                flash(f"Usuario {f['usuario']} creado.", "success")
            except errors.IntegrityError:
                flash("Ya existe un usuario con ese nombre de usuario.", "danger")
        return redirect(url_for("login.usuarios"))
    lista = consultar("SELECT id, usuario, nombre, es_admin, creado FROM usuarios ORDER BY nombre")
    return render_template("usuarios.html", usuarios=lista)


@bp.route("/usuarios/<int:id>/eliminar", methods=["POST"])
def eliminar_usuario(id):
    solo_admin()
    if id == g.usuario["id"]:
        flash("No puedes eliminar tu propio usuario.", "danger")
    else:
        ejecutar("DELETE FROM usuarios WHERE id = %s", (id,))
        flash("Usuario eliminado.", "success")
    return redirect(url_for("login.usuarios"))
