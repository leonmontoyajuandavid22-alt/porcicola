"""Alimentación: qué comida se dio, cuánta y cuánto costó, a un cerdo o a un corral."""
from datetime import date

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from db import consultar, consultar_uno, ejecutar

bp = Blueprint("alimentacion", __name__, url_prefix="/alimentacion")

# Para mostrar a quién se le dio: el arete del cerdo o el nombre del corral.
SQL_REGISTROS = """
    SELECT a.*, c.arete, c.nombre AS cerdo_nombre, co.nombre AS corral
    FROM alimentacion a
    LEFT JOIN cerdos c ON c.id = a.cerdo_id
    LEFT JOIN corrales co ON co.id = a.corral_id
"""


@bp.route("/")
def lista():
    hoy = date.today()
    filtros = {
        # Por defecto se muestra el mes actual: del día 1 hasta hoy.
        "desde": request.args.get("desde") or hoy.replace(day=1).isoformat(),
        "hasta": request.args.get("hasta") or hoy.isoformat(),
        "corral": request.args.get("corral", ""),
        "alimento": request.args.get("alimento", ""),
    }
    condiciones = ["a.fecha BETWEEN %s AND %s"]
    params = [filtros["desde"], filtros["hasta"]]
    if filtros["corral"]:
        # Lo que se le dio al corral, y también lo que se le dio a cerdos de ese corral.
        condiciones.append("(a.corral_id = %s OR c.corral_id = %s)")
        params += [filtros["corral"]] * 2
    if filtros["alimento"]:
        condiciones.append("a.tipo_alimento = %s")
        params.append(filtros["alimento"])
    where = " WHERE " + " AND ".join(condiciones)

    registros = consultar(SQL_REGISTROS + where + " ORDER BY a.fecha DESC, a.id DESC", params)

    # Resumen por tipo de alimento: total de kg y de dinero en el periodo.
    resumen = {}
    for r in registros:
        fila = resumen.setdefault(r["tipo_alimento"], {"kg": 0, "costo": 0})
        fila["kg"] += r["cantidad_kg"]
        fila["costo"] += r["costo"] or 0
    total = {"kg": sum(f["kg"] for f in resumen.values()), "costo": sum(f["costo"] for f in resumen.values())}

    return render_template(
        "alimentacion/lista.html",
        registros=registros,
        resumen=sorted(resumen.items()),
        total=total,
        filtros=filtros,
        # "para" llega desde la ficha de un cerdo, por ejemplo ?para=cerdo-5
        registro={"fecha": hoy.isoformat(), "destino": request.args.get("para", ""),
                  "volver": "ficha" if request.args.get("para") else ""},
        **opciones(),
    )


def opciones():
    return {
        "cerdos": consultar("SELECT id, arete, nombre FROM cerdos WHERE estado = 'activo' ORDER BY arete"),
        "corrales": consultar(
            """SELECT co.id, co.nombre, COUNT(c.id) AS n FROM corrales co
               LEFT JOIN cerdos c ON c.corral_id = co.id AND c.estado = 'activo'
               GROUP BY co.id ORDER BY co.nombre"""
        ),
        "alimentos": consultar("SELECT DISTINCT tipo_alimento FROM alimentacion ORDER BY tipo_alimento"),
        "hoy": date.today().isoformat(),
    }


def leer_destino(texto):
    """'cerdo-5' -> (5, None); 'corral-2' -> (None, 2). Si no es válido -> (None, None)."""
    tipo, _, id_ = (texto or "").partition("-")
    if tipo == "cerdo" and consultar_uno("SELECT id FROM cerdos WHERE id = %s", (id_,)):
        return int(id_), None
    if tipo == "corral" and consultar_uno("SELECT id FROM corrales WHERE id = %s", (id_,)):
        return None, int(id_)
    return None, None


def validar(f):
    if leer_destino(f.get("destino")) == (None, None):
        return "Elige a qué cerdo o corral se le dio el alimento."
    if not f.get("tipo_alimento", "").strip():
        return "Escribe el tipo de alimento."
    try:
        fecha = date.fromisoformat(f.get("fecha", ""))
        cantidad = float(f.get("cantidad_kg", ""))
        costo = float(f["costo"]) if f.get("costo") else 0
    except ValueError:
        return "Revisa la fecha, la cantidad y el costo."
    if fecha > date.today():
        return "La fecha no puede ser en el futuro."
    if not 0 < cantidad < 100000:
        return "La cantidad debe ser mayor que 0 kg."
    if costo < 0:
        return "El costo no puede ser negativo."
    return None


def valores(f):
    cerdo_id, corral_id = leer_destino(f["destino"])
    return (
        f["fecha"], cerdo_id, corral_id, f["tipo_alimento"].strip(),
        f["cantidad_kg"], f.get("costo") or None, f.get("observaciones", "").strip() or None,
    )


def volver(cerdo_id):
    if request.form.get("volver") == "ficha" and cerdo_id:
        return redirect(url_for("cerdos.ficha", id=cerdo_id) + "#alimentacion")
    return redirect(url_for("alimentacion.lista"))


@bp.route("/nuevo", methods=["POST"])
def nuevo():
    f = request.form
    error = validar(f)
    if error:
        flash(error, "danger")
    else:
        ejecutar(
            """INSERT INTO alimentacion (fecha, cerdo_id, corral_id, tipo_alimento, cantidad_kg, costo, observaciones, usuario_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            valores(f) + (g.usuario["id"],),
        )
        flash("Alimentación registrada.", "success")
    return volver(leer_destino(f.get("destino"))[0])


@bp.route("/<int:id>/editar", methods=["GET", "POST"])
def editar(id):
    registro = consultar_uno(SQL_REGISTROS + " WHERE a.id = %s", (id,)) or abort(404)
    if request.method == "POST":
        f = request.form
        error = validar(f)
        if not error:
            ejecutar(
                """UPDATE alimentacion SET fecha = %s, cerdo_id = %s, corral_id = %s, tipo_alimento = %s,
                       cantidad_kg = %s, costo = %s, observaciones = %s WHERE id = %s""",
                valores(f) + (id,),
            )
            flash("Registro de alimentación actualizado.", "success")
            return volver(leer_destino(f["destino"])[0])
        flash(error, "danger")
        registro.update(f.to_dict())
    else:
        registro["destino"] = f"cerdo-{registro['cerdo_id']}" if registro["cerdo_id"] else f"corral-{registro['corral_id']}"
        registro["volver"] = request.args.get("volver", "")
    return render_template("alimentacion/editar.html", registro=registro, **opciones())


@bp.route("/<int:id>/eliminar", methods=["POST"])
def eliminar(id):
    registro = consultar_uno("SELECT cerdo_id FROM alimentacion WHERE id = %s", (id,)) or abort(404)
    ejecutar("DELETE FROM alimentacion WHERE id = %s", (id,))
    flash("Registro de alimentación eliminado.", "success")
    return volver(registro["cerdo_id"])


def historial(cerdo):
    """Para la ficha: lo que se le dio a este cerdo y a su corral actual (últimos 30 registros)."""
    return consultar(
        SQL_REGISTROS + " WHERE a.cerdo_id = %s OR (a.corral_id = %s) ORDER BY a.fecha DESC, a.id DESC LIMIT 30",
        (cerdo["id"], cerdo["corral_id"] or 0),
    )
