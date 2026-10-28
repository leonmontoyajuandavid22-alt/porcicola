"""Pesajes: historial de peso de cada cerdo."""
from datetime import date

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from db import consultar, consultar_uno, ejecutar

bp = Blueprint("pesajes", __name__, url_prefix="/pesajes")


@bp.route("/")
def lista():
    filtros = {
        "buscar": request.args.get("buscar", "").strip(),
        "corral": request.args.get("corral", ""),
    }
    condiciones, params = [], []
    if filtros["buscar"]:
        condiciones.append("(c.arete LIKE %s OR c.nombre LIKE %s)")
        params += [f"%{filtros['buscar']}%"] * 2
    if filtros["corral"]:
        condiciones.append("c.corral_id = %s")
        params.append(filtros["corral"])
    where = "WHERE " + " AND ".join(condiciones) if condiciones else ""

    # LIMIT 200: mostramos solo los pesajes más recientes para que la página no sea eterna.
    pesajes = consultar(
        f"""SELECT p.*, c.arete, c.nombre, u.nombre AS registrado_por
            FROM pesajes p
            JOIN cerdos c ON c.id = p.cerdo_id
            LEFT JOIN usuarios u ON u.id = p.usuario_id
            {where}
            ORDER BY p.fecha DESC, p.id DESC
            LIMIT 200""",
        params,
    )
    return render_template(
        "pesajes/lista.html",
        pesajes=pesajes,
        filtros=filtros,
        cerdos=cerdos_activos(),
        corrales=consultar("SELECT id, nombre FROM corrales ORDER BY nombre"),
        hoy=date.today().isoformat(),
    )


def cerdos_activos():
    return consultar("SELECT id, arete, nombre FROM cerdos WHERE estado = 'activo' ORDER BY arete")


def validar(cerdo_id, fecha, peso):
    """Devuelve un mensaje de error o None si los datos están bien."""
    cerdo = consultar_uno("SELECT fecha_nacimiento FROM cerdos WHERE id = %s", (cerdo_id,))
    if not cerdo:
        return "Elige un cerdo."
    try:
        fecha = date.fromisoformat(fecha)
        peso = float(peso)
    except ValueError:
        return "Revisa la fecha y el peso."
    if fecha > date.today():
        return "La fecha del pesaje no puede ser en el futuro."
    if cerdo["fecha_nacimiento"] and fecha < cerdo["fecha_nacimiento"]:
        return "La fecha del pesaje es anterior al nacimiento del cerdo."
    if not 0 < peso < 500:
        return "El peso debe estar entre 0 y 500 kg."
    return None


def volver(cerdo_id):
    """Después de guardar, regresa a la ficha del cerdo si venías de ahí."""
    if request.form.get("volver") == "ficha":
        return redirect(url_for("cerdos.ficha", id=cerdo_id) + "#peso")
    return redirect(url_for("pesajes.lista"))


@bp.route("/nuevo", methods=["POST"])
def nuevo():
    f = request.form
    error = validar(f.get("cerdo_id"), f.get("fecha", ""), f.get("peso_kg", ""))
    if error:
        flash(error, "danger")
    else:
        ejecutar(
            "INSERT INTO pesajes (cerdo_id, fecha, peso_kg, observaciones, usuario_id) VALUES (%s, %s, %s, %s, %s)",
            (f["cerdo_id"], f["fecha"], f["peso_kg"], f.get("observaciones", "").strip() or None, g.usuario["id"]),
        )
        flash("Pesaje registrado.", "success")
    return volver(f.get("cerdo_id"))


@bp.route("/varios", methods=["GET", "POST"])
def varios():
    """Pesar todos los cerdos de un corral de una sola vez."""
    corral_id = request.values.get("corral", "")
    if request.method == "POST":
        fecha = request.form["fecha"]
        guardados, errores = 0, []
        # Cada casilla de peso se llama "peso_<id del cerdo>", por ejemplo peso_12.
        for nombre_campo, peso in request.form.items():
            if not nombre_campo.startswith("peso_") or not peso.strip():
                continue  # casilla vacía: ese cerdo no se pesó
            cerdo_id = nombre_campo.removeprefix("peso_")
            error = validar(cerdo_id, fecha, peso)
            if error:
                arete = consultar_uno("SELECT arete FROM cerdos WHERE id = %s", (cerdo_id,))
                errores.append(f"{arete['arete'] if arete else cerdo_id}: {error}")
                continue
            ejecutar(
                "INSERT INTO pesajes (cerdo_id, fecha, peso_kg, usuario_id) VALUES (%s, %s, %s, %s)",
                (cerdo_id, fecha, peso, g.usuario["id"]),
            )
            guardados += 1
        if guardados:
            flash(f"Se registraron {guardados} pesaje(s).", "success")
        for error in errores:
            flash(error, "danger")
        if not guardados and not errores:
            flash("No escribiste ningún peso.", "warning")
        return redirect(url_for("pesajes.varios", corral=corral_id))

    cerdos = []
    if corral_id:
        # Para cada cerdo traemos también su último peso, para comparar.
        cerdos = consultar(
            """SELECT c.id, c.arete, c.nombre,
                      (SELECT p.peso_kg FROM pesajes p WHERE p.cerdo_id = c.id
                       ORDER BY p.fecha DESC, p.id DESC LIMIT 1) AS ultimo_peso,
                      (SELECT p.fecha FROM pesajes p WHERE p.cerdo_id = c.id
                       ORDER BY p.fecha DESC, p.id DESC LIMIT 1) AS ultima_fecha
               FROM cerdos c
               WHERE c.corral_id = %s AND c.estado = 'activo'
               ORDER BY c.arete""",
            (corral_id,),
        )
    return render_template(
        "pesajes/varios.html",
        cerdos=cerdos,
        corral_id=corral_id,
        corrales=consultar("SELECT id, nombre FROM corrales ORDER BY nombre"),
        hoy=date.today().isoformat(),
    )


@bp.route("/<int:id>/editar", methods=["GET", "POST"])
def editar(id):
    pesaje = consultar_uno(
        """SELECT p.*, c.arete, c.nombre FROM pesajes p
           JOIN cerdos c ON c.id = p.cerdo_id WHERE p.id = %s""",
        (id,),
    ) or abort(404)
    if request.method == "POST":
        f = request.form
        error = validar(pesaje["cerdo_id"], f.get("fecha", ""), f.get("peso_kg", ""))
        if error:
            flash(error, "danger")
            pesaje.update(f.to_dict())
        else:
            ejecutar(
                "UPDATE pesajes SET fecha = %s, peso_kg = %s, observaciones = %s WHERE id = %s",
                (f["fecha"], f["peso_kg"], f.get("observaciones", "").strip() or None, id),
            )
            flash("Pesaje actualizado.", "success")
            return volver(pesaje["cerdo_id"])
    return render_template("pesajes/editar.html", pesaje=pesaje, volver=request.values.get("volver", ""))


@bp.route("/<int:id>/eliminar", methods=["POST"])
def eliminar(id):
    pesaje = consultar_uno("SELECT cerdo_id FROM pesajes WHERE id = %s", (id,)) or abort(404)
    ejecutar("DELETE FROM pesajes WHERE id = %s", (id,))
    flash("Pesaje eliminado.", "success")
    return volver(pesaje["cerdo_id"])


def historial(cerdo_id):
    """Pesajes de un cerdo, del más antiguo al más reciente, con cuánto ganó
    desde el pesaje anterior y la ganancia diaria (kg por día)."""
    pesajes = consultar(
        """SELECT p.*, u.nombre AS registrado_por FROM pesajes p
           LEFT JOIN usuarios u ON u.id = p.usuario_id
           WHERE p.cerdo_id = %s ORDER BY p.fecha, p.id""",
        (cerdo_id,),
    )
    anterior = None
    for p in pesajes:
        p["diferencia"] = p["ganancia_diaria"] = None
        if anterior:
            p["diferencia"] = float(p["peso_kg"] - anterior["peso_kg"])
            dias = (p["fecha"] - anterior["fecha"]).days
            if dias > 0:
                p["ganancia_diaria"] = p["diferencia"] / dias
        anterior = p
    return pesajes
