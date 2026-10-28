"""Razas: lista editable que se usa al registrar cerdos."""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from mysql.connector import errors

from db import consultar, ejecutar

bp = Blueprint("razas", __name__, url_prefix="/razas")


@bp.route("/", methods=["GET", "POST"])
def lista():
    if request.method == "POST":
        try:
            ejecutar("INSERT INTO razas (nombre) VALUES (%s)", (request.form["nombre"].strip(),))
            flash("Raza agregada.", "success")
        except errors.IntegrityError:
            flash("Esa raza ya existe.", "danger")
        return redirect(url_for("razas.lista"))
    razas = consultar(
        """SELECT r.id, r.nombre, COUNT(c.id) AS cerdos
           FROM razas r LEFT JOIN cerdos c ON c.raza_id = r.id
           GROUP BY r.id ORDER BY r.nombre"""
    )
    return render_template("razas.html", razas=razas)


@bp.route("/<int:id>/renombrar", methods=["POST"])
def renombrar(id):
    try:
        ejecutar("UPDATE razas SET nombre = %s WHERE id = %s", (request.form["nombre"].strip(), id))
        flash("Raza actualizada.", "success")
    except errors.IntegrityError:
        flash("Ya existe una raza con ese nombre.", "danger")
    return redirect(url_for("razas.lista"))


@bp.route("/<int:id>/eliminar", methods=["POST"])
def eliminar(id):
    try:
        ejecutar("DELETE FROM razas WHERE id = %s", (id,))
        flash("Raza eliminada.", "success")
    except errors.IntegrityError:
        # La base de datos no deja borrar una raza que algún cerdo está usando.
        flash("No se puede eliminar: hay cerdos registrados con esa raza.", "danger")
    return redirect(url_for("razas.lista"))
