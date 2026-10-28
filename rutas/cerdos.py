"""Cerdos: lista con buscador y filtros, agregar, editar, eliminar y ficha."""
import uuid
from datetime import date
from pathlib import Path

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for
from mysql.connector import errors

from db import consultar, consultar_uno, ejecutar
from rutas import alimentacion, reproduccion, salidas, salud
from rutas.pesajes import historial as historial_pesajes

bp = Blueprint("cerdos", __name__, url_prefix="/cerdos")

EXTENSIONES_FOTO = {"jpg", "jpeg", "png", "webp"}


def carpeta_fotos():
    carpeta = Path(current_app.static_folder) / "fotos"
    carpeta.mkdir(exist_ok=True)
    return carpeta


@bp.route("/")
def lista():
    # Leemos los filtros que vienen en la dirección, por ejemplo:
    # /cerdos/?buscar=A12&corral=3&sexo=hembra&estado=activo
    filtros = {
        "buscar": request.args.get("buscar", "").strip(),
        "corral": request.args.get("corral", ""),
        "sexo": request.args.get("sexo", ""),
        "estado": request.args.get("estado", "activo"),
    }

    # Armamos el WHERE poco a poco: una condición por cada filtro usado.
    condiciones, params = [], []
    if filtros["buscar"]:
        condiciones.append("(c.arete LIKE %s OR c.nombre LIKE %s)")
        params += [f"%{filtros['buscar']}%"] * 2
    if filtros["corral"] == "sin":
        condiciones.append("c.corral_id IS NULL")
    elif filtros["corral"]:
        condiciones.append("c.corral_id = %s")
        params.append(filtros["corral"])
    if filtros["sexo"]:
        condiciones.append("c.sexo = %s")
        params.append(filtros["sexo"])
    if filtros["estado"] != "todos":
        condiciones.append("c.estado = %s")
        params.append(filtros["estado"])
    where = "WHERE " + " AND ".join(condiciones) if condiciones else ""

    cerdos = consultar(
        f"""SELECT c.*, r.nombre AS raza, co.nombre AS corral,
                   (SELECT p.peso_kg FROM pesajes p WHERE p.cerdo_id = c.id
                    ORDER BY p.fecha DESC, p.id DESC LIMIT 1) AS ultimo_peso
            FROM cerdos c
            LEFT JOIN razas r ON r.id = c.raza_id
            LEFT JOIN corrales co ON co.id = c.corral_id
            {where}
            ORDER BY c.arete""",
        params,
    )
    corrales = consultar("SELECT id, nombre FROM corrales ORDER BY nombre")
    return render_template("cerdos/lista.html", cerdos=cerdos, corrales=corrales, filtros=filtros)


@bp.route("/<int:id>")
def ficha(id):
    cerdo = consultar_uno(
        """SELECT c.*, r.nombre AS raza, co.nombre AS corral,
                  m.arete AS madre_arete, p.arete AS padre_arete,
                  u.nombre AS registrado_por
           FROM cerdos c
           LEFT JOIN razas r ON r.id = c.raza_id
           LEFT JOIN corrales co ON co.id = c.corral_id
           LEFT JOIN cerdos m ON m.id = c.madre_id
           LEFT JOIN cerdos p ON p.id = c.padre_id
           LEFT JOIN usuarios u ON u.id = c.usuario_id
           WHERE c.id = %s""",
        (id,),
    ) or abort(404)
    hijos = consultar(
        """SELECT id, arete, nombre, sexo, fecha_nacimiento, estado
           FROM cerdos WHERE madre_id = %s OR padre_id = %s
           ORDER BY fecha_nacimiento DESC""",
        (id, id),
    )
    return render_template(
        "cerdos/ficha.html",
        cerdo=cerdo,
        hijos=hijos,
        pesajes=historial_pesajes(id),
        salud=salud.historial(id),
        pendientes=salud.pendientes(cerdo_id=id),
        tipos=salud.TIPOS,
        repro=reproduccion.historial(cerdo),
        estados=reproduccion.ESTADOS_MONTA,
        comida=alimentacion.historial(cerdo),
        salida=salidas.de_cerdo(id),
        hoy=date.today(),
    )


def opciones_formulario(excluir_id=None):
    """Listas para los menús desplegables del formulario."""
    return {
        "razas": consultar("SELECT id, nombre FROM razas ORDER BY nombre"),
        "corrales": consultar("SELECT id, nombre FROM corrales ORDER BY nombre"),
        "madres": consultar(
            "SELECT id, arete, nombre FROM cerdos WHERE sexo = 'hembra' AND id <> %s ORDER BY arete",
            (excluir_id or 0,),
        ),
        "padres": consultar(
            "SELECT id, arete, nombre FROM cerdos WHERE sexo = 'macho' AND id <> %s ORDER BY arete",
            (excluir_id or 0,),
        ),
    }


def validar(f):
    """Revisa el formulario. Devuelve un mensaje de error o None si todo está bien."""
    if not f.get("arete", "").strip():
        return "El arete es obligatorio."
    if f.get("sexo") not in ("macho", "hembra"):
        return "Elige el sexo."
    if f.get("fecha_nacimiento") and date.fromisoformat(f["fecha_nacimiento"]) > date.today():
        return "La fecha de nacimiento no puede ser en el futuro."
    foto = request.files.get("foto")
    if foto and foto.filename and extension(foto.filename) not in EXTENSIONES_FOTO:
        return "La foto debe ser JPG, PNG o WEBP."
    return None


def extension(nombre_archivo):
    return nombre_archivo.rsplit(".", 1)[-1].lower() if "." in nombre_archivo else ""


def guardar_foto():
    """Guarda la foto subida con un nombre único y devuelve ese nombre (o None)."""
    foto = request.files.get("foto")
    if not foto or not foto.filename:
        return None
    nombre = f"{uuid.uuid4().hex}.{extension(foto.filename)}"
    foto.save(carpeta_fotos() / nombre)
    return nombre


def borrar_foto(nombre):
    if nombre:
        (carpeta_fotos() / nombre).unlink(missing_ok=True)


def valores(f):
    """Convierte el formulario en los valores para la base de datos.
    'or None' guarda vacío (NULL) cuando el campo no se llenó.
    El estado no está aquí: cambia solo al registrar una venta o una muerte (rutas/salidas.py)."""
    return (
        f["arete"].strip(),
        f.get("nombre", "").strip() or None,
        f["sexo"],
        f.get("raza_id") or None,
        f.get("fecha_nacimiento") or None,
        f.get("madre_id") or None,
        f.get("padre_id") or None,
        f.get("corral_id") or None,
        f.get("observaciones", "").strip() or None,
    )


@bp.route("/nuevo", methods=["GET", "POST"])
def nuevo():
    if request.method == "POST":
        error = validar(request.form)
        if not error:
            foto = guardar_foto()
            try:
                nuevo_id = ejecutar(
                    """INSERT INTO cerdos (arete, nombre, sexo, raza_id, fecha_nacimiento,
                           madre_id, padre_id, corral_id, observaciones, foto, usuario_id)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    valores(request.form) + (foto, g.usuario["id"]),
                )
                flash("Cerdo registrado.", "success")
                return redirect(url_for("cerdos.ficha", id=nuevo_id))
            except errors.IntegrityError:
                borrar_foto(foto)
                error = "Ya existe un cerdo con ese arete."
        flash(error, "danger")
    # Si vienes desde un corral, el formulario ya trae ese corral elegido.
    cerdo = request.form if request.method == "POST" else {"corral_id": request.args.get("corral")}
    return render_template("cerdos/formulario.html", cerdo=cerdo, **opciones_formulario())


@bp.route("/<int:id>/editar", methods=["GET", "POST"])
def editar(id):
    actual = consultar_uno("SELECT * FROM cerdos WHERE id = %s", (id,)) or abort(404)
    if request.method == "POST":
        f = request.form
        error = validar(f)
        if not error and str(id) in (f.get("madre_id"), f.get("padre_id")):
            error = "Un cerdo no puede ser su propio padre o madre."
        if not error:
            foto = actual["foto"]
            nueva = guardar_foto()
            if nueva or "quitar_foto" in f:
                borrar_foto(foto)
                foto = nueva
            try:
                ejecutar(
                    """UPDATE cerdos SET arete = %s, nombre = %s, sexo = %s, raza_id = %s,
                           fecha_nacimiento = %s, madre_id = %s, padre_id = %s, corral_id = %s,
                           observaciones = %s, foto = %s
                       WHERE id = %s""",
                    valores(f) + (foto, id),
                )
                flash("Datos del cerdo actualizados.", "success")
                return redirect(url_for("cerdos.ficha", id=id))
            except errors.IntegrityError:
                borrar_foto(nueva)
                error = "Ya existe otro cerdo con ese arete."
        flash(error, "danger")
        cerdo = dict(f, id=id, foto=actual["foto"], estado=actual["estado"])
    else:
        cerdo = actual
    return render_template("cerdos/formulario.html", cerdo=cerdo, editando=True, **opciones_formulario(id))


@bp.route("/<int:id>/eliminar", methods=["POST"])
def eliminar(id):
    cerdo = consultar_uno("SELECT arete, foto FROM cerdos WHERE id = %s", (id,)) or abort(404)
    ejecutar("DELETE FROM cerdos WHERE id = %s", (id,))
    borrar_foto(cerdo["foto"])
    flash(f"Cerdo {cerdo['arete']} eliminado, junto con todo su historial.", "success")
    return redirect(url_for("cerdos.lista"))
