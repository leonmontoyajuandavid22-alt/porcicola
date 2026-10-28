"""Salidas: ventas y muertes. Al registrar una, el cerdo cambia de estado solo."""
from datetime import date

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from mysql.connector import errors

from db import consultar, consultar_uno, ejecutar

bp = Blueprint("salidas", __name__, url_prefix="/salidas")

ESTADO_POR_TIPO = {"venta": "vendido", "muerte": "muerto"}

SQL_SALIDAS = """
    SELECT s.*, c.arete, c.nombre, c.fecha_nacimiento
    FROM salidas s JOIN cerdos c ON c.id = s.cerdo_id
"""


@bp.route("/")
def lista():
    hoy = date.today()
    filtros = {
        # Por defecto se muestra el año actual.
        "desde": request.args.get("desde") or hoy.replace(month=1, day=1).isoformat(),
        "hasta": request.args.get("hasta") or hoy.isoformat(),
        "tipo": request.args.get("tipo", ""),
    }
    sql = SQL_SALIDAS + " WHERE s.fecha BETWEEN %s AND %s"
    params = [filtros["desde"], filtros["hasta"]]
    if filtros["tipo"]:
        sql += " AND s.tipo = %s"
        params.append(filtros["tipo"])
    salidas = consultar(sql + " ORDER BY s.fecha DESC, s.id DESC", params)

    ventas = [s for s in salidas if s["tipo"] == "venta"]
    muertes = [s for s in salidas if s["tipo"] == "muerte"]
    kg_con_precio = sum(s["peso_kg"] for s in ventas if s["peso_kg"] and s["precio"])
    dinero_con_peso = sum(s["precio"] for s in ventas if s["peso_kg"] and s["precio"])
    resumen = {
        "ventas": len(ventas),
        "ingresos": sum(s["precio"] or 0 for s in ventas),
        "kg_vendidos": sum(s["peso_kg"] or 0 for s in ventas),
        # Precio promedio por kg: solo con las ventas que tienen peso y precio.
        "precio_kg": dinero_con_peso / kg_con_precio if kg_con_precio else None,
        "muertes": len(muertes),
    }
    # Causas de muerte agrupadas: {"Neumonía": 2, "Aplastamiento": 1}
    causas = {}
    for m in muertes:
        causas[m["causa"]] = causas.get(m["causa"], 0) + 1

    return render_template(
        "salidas/lista.html",
        salidas=salidas,
        resumen=resumen,
        causas=sorted(causas.items(), key=lambda par: -par[1]),
        filtros=filtros,
    )


def cerdos_sin_salida():
    return consultar(
        """SELECT c.id, c.arete, c.nombre FROM cerdos c
           LEFT JOIN salidas s ON s.cerdo_id = c.id
           WHERE s.id IS NULL ORDER BY c.arete"""
    )


def leer_numero(texto):
    try:
        return float(texto) if texto not in (None, "") else None
    except ValueError:
        return -1  # se rechaza en la validación


def validar(f, cerdo_id):
    cerdo = consultar_uno("SELECT fecha_nacimiento FROM cerdos WHERE id = %s", (cerdo_id or 0,))
    if not cerdo:
        return "Elige el cerdo."
    if f.get("tipo") not in ESTADO_POR_TIPO:
        return "Elige si fue venta o muerte."
    try:
        fecha = date.fromisoformat(f.get("fecha", ""))
    except ValueError:
        return "Escribe la fecha."
    if fecha > date.today():
        return "La fecha no puede ser en el futuro."
    if cerdo["fecha_nacimiento"] and fecha < cerdo["fecha_nacimiento"]:
        return "La fecha es anterior al nacimiento del cerdo."
    peso, precio = leer_numero(f.get("peso_kg")), leer_numero(f.get("precio"))
    if peso is not None and not 0 < peso < 500:
        return "El peso debe estar entre 0 y 500 kg."
    if f["tipo"] == "venta" and (precio is None or precio <= 0):
        return "Escribe el precio de la venta."
    if f["tipo"] == "muerte" and not f.get("causa", "").strip():
        return "Escribe la causa de la muerte."
    return None


def valores(f):
    venta = f["tipo"] == "venta"
    # Solo se guardan los campos que corresponden al tipo de salida.
    return (
        f["tipo"],
        f["fecha"],
        f.get("peso_kg") or None,
        (f.get("precio") or None) if venta else None,
        (f.get("comprador", "").strip() or None) if venta else None,
        None if venta else f["causa"].strip(),
        f.get("observaciones", "").strip() or None,
    )


def volver(cerdo_id):
    if request.form.get("volver") == "ficha":
        return redirect(url_for("cerdos.ficha", id=cerdo_id) + "#salida")
    return redirect(url_for("salidas.lista"))


def opciones():
    return {
        "cerdos": cerdos_sin_salida(),
        "hoy": date.today().isoformat(),
        "compradores": consultar("SELECT DISTINCT comprador FROM salidas WHERE comprador IS NOT NULL ORDER BY comprador"),
        "causas": consultar("SELECT DISTINCT causa FROM salidas WHERE causa IS NOT NULL ORDER BY causa"),
    }


@bp.route("/nueva", methods=["GET", "POST"])
def nueva():
    if request.method == "POST":
        f = request.form
        error = validar(f, f.get("cerdo_id"))
        if not error:
            try:
                ejecutar(
                    """INSERT INTO salidas (cerdo_id, tipo, fecha, peso_kg, precio, comprador, causa, observaciones, usuario_id)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (f["cerdo_id"],) + valores(f) + (g.usuario["id"],),
                )
            except errors.IntegrityError:
                error = "Ese cerdo ya tiene una salida registrada."
        if not error:
            ejecutar("UPDATE cerdos SET estado = %s WHERE id = %s", (ESTADO_POR_TIPO[f["tipo"]], f["cerdo_id"]))
            flash("Venta registrada." if f["tipo"] == "venta" else "Muerte registrada.", "success")
            return volver(f["cerdo_id"])
        flash(error, "danger")
        datos = f.to_dict()
    else:
        datos = {"fecha": date.today().isoformat(), "tipo": request.args.get("tipo", "venta"),
                 "cerdo_id": request.args.get("cerdo", ""), "volver": request.args.get("volver", "")}
        # Si el cerdo tiene pesajes, sugerimos el último peso.
        if datos["cerdo_id"]:
            ultimo = consultar_uno(
                "SELECT peso_kg FROM pesajes WHERE cerdo_id = %s ORDER BY fecha DESC, id DESC LIMIT 1",
                (datos["cerdo_id"],),
            )
            if ultimo:
                datos["peso_kg"] = ultimo["peso_kg"]
    return render_template("salidas/formulario.html", salida=datos, **opciones())


@bp.route("/<int:id>/editar", methods=["GET", "POST"])
def editar(id):
    salida = consultar_uno(SQL_SALIDAS + " WHERE s.id = %s", (id,)) or abort(404)
    if request.method == "POST":
        f = request.form
        error = validar(f, salida["cerdo_id"])
        if not error:
            ejecutar(
                """UPDATE salidas SET tipo = %s, fecha = %s, peso_kg = %s, precio = %s, comprador = %s,
                       causa = %s, observaciones = %s WHERE id = %s""",
                valores(f) + (id,),
            )
            ejecutar("UPDATE cerdos SET estado = %s WHERE id = %s", (ESTADO_POR_TIPO[f["tipo"]], salida["cerdo_id"]))
            flash("Salida actualizada.", "success")
            return volver(salida["cerdo_id"])
        flash(error, "danger")
        salida.update(f.to_dict())
    salida.setdefault("volver", request.args.get("volver", ""))
    return render_template("salidas/formulario.html", salida=salida, editando=True, **opciones())


@bp.route("/<int:id>/eliminar", methods=["POST"])
def eliminar(id):
    """Anula la salida: se borra y el cerdo vuelve a quedar activo."""
    salida = consultar_uno("SELECT cerdo_id FROM salidas WHERE id = %s", (id,)) or abort(404)
    ejecutar("DELETE FROM salidas WHERE id = %s", (id,))
    ejecutar("UPDATE cerdos SET estado = 'activo' WHERE id = %s", (salida["cerdo_id"],))
    flash("Salida anulada. El cerdo vuelve a estar activo.", "success")
    return volver(salida["cerdo_id"])


def de_cerdo(cerdo_id):
    return consultar_uno("SELECT * FROM salidas WHERE cerdo_id = %s", (cerdo_id,))
