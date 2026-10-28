"""Corrales: agregar, ver, editar y eliminar."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from mysql.connector import errors

from db import consultar, consultar_uno, ejecutar

bp = Blueprint("corrales", __name__, url_prefix="/corrales")


@bp.route("/")
def lista():
    # LEFT JOIN + COUNT cuenta cuántos cerdos activos hay en cada corral.
    corrales = consultar(
        """SELECT co.*, COUNT(c.id) AS cerdos_activos
           FROM corrales co
           LEFT JOIN cerdos c ON c.corral_id = co.id AND c.estado = 'activo'
           GROUP BY co.id
           ORDER BY co.nombre"""
    )
    return render_template("corrales/lista.html", corrales=corrales)


def datos_del_formulario():
    f = request.form
    return (f["nombre"].strip(), f["capacidad"] or None, f["descripcion"].strip() or None)


@bp.route("/nuevo", methods=["GET", "POST"])
def nuevo():
    if request.method == "POST":
        try:
            ejecutar(
                "INSERT INTO corrales (nombre, capacidad, descripcion) VALUES (%s, %s, %s)",
                datos_del_formulario(),
            )
            flash("Corral creado.", "success")
            return redirect(url_for("corrales.lista"))
        except errors.IntegrityError:
            flash("Ya existe un corral con ese nombre.", "danger")
    return render_template("corrales/formulario.html", corral=request.form)


@bp.route("/<int:id>/editar", methods=["GET", "POST"])
def editar(id):
    corral = consultar_uno("SELECT * FROM corrales WHERE id = %s", (id,)) or abort(404)
    if request.method == "POST":
        try:
            ejecutar(
                "UPDATE corrales SET nombre = %s, capacidad = %s, descripcion = %s WHERE id = %s",
                datos_del_formulario() + (id,),
            )
            flash("Corral actualizado.", "success")
            return redirect(url_for("corrales.lista"))
        except errors.IntegrityError:
            flash("Ya existe un corral con ese nombre.", "danger")
            corral = request.form
    return render_template("corrales/formulario.html", corral=corral, editando=True)


@bp.route("/<int:id>/eliminar", methods=["POST"])
def eliminar(id):
    activos = consultar_uno(
        "SELECT COUNT(*) AS n FROM cerdos WHERE corral_id = %s AND estado = 'activo'", (id,)
    )["n"]
    if activos:
        flash(f"Este corral tiene {activos} cerdo(s) activo(s). Muévelos a otro corral antes de eliminarlo.", "danger")
        return redirect(url_for("corrales.lista"))
    try:
        ejecutar("DELETE FROM corrales WHERE id = %s", (id,))
        flash("Corral eliminado.", "success")
    except errors.IntegrityError:
        flash("Este corral tiene registros de alimentación, por eso no se puede eliminar.", "danger")
    return redirect(url_for("corrales.lista"))
