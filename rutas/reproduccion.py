"""Reproducción: montas o inseminaciones, partos y destetes."""
from datetime import date, timedelta

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from db import consultar, consultar_uno, ejecutar

bp = Blueprint("reproduccion", __name__, url_prefix="/reproduccion")

DIAS_GESTACION = 114  # una cerda está preñada unos 114 días (3 meses, 3 semanas y 3 días)
DIAS_DESTETE = 21     # a partir de cuántos días después del parto se avisa del destete

ESTADOS_MONTA = {
    "pendiente": "Sin confirmar",
    "confirmada": "Preñez confirmada",
    "fallida": "Fallida",
    "parida": "Parida",
}

SQL_MONTAS = """
    SELECT m.*, c.arete AS cerda_arete, c.nombre AS cerda_nombre, v.arete AS verraco_arete
    FROM montas m
    JOIN cerdos c ON c.id = m.cerda_id
    LEFT JOIN cerdos v ON v.id = m.verraco_id
"""
SQL_PARTOS = """
    SELECT p.*, c.arete AS cerda_arete, c.nombre AS cerda_nombre
    FROM partos p JOIN cerdos c ON c.id = p.cerda_id
"""


@bp.route("/")
def inicio():
    return render_template(
        "reproduccion/inicio.html",
        proximos=proximos_partos(),
        destetes=destetes_pendientes(),
        montas=consultar(SQL_MONTAS + " ORDER BY m.fecha DESC, m.id DESC LIMIT 100"),
        partos=consultar(SQL_PARTOS + " ORDER BY p.fecha DESC, p.id DESC LIMIT 100"),
        estados=ESTADOS_MONTA,
        dias_destete=DIAS_DESTETE,
        hoy=date.today(),
    )


def proximos_partos(dias=None):
    """Montas que siguen abiertas (sin confirmar o confirmadas), por fecha de parto.
    Si se da 'dias', solo las que paren dentro de ese número de días."""
    sql = SQL_MONTAS + " WHERE m.estado IN ('pendiente', 'confirmada') AND c.estado = 'activo'"
    params = []
    if dias is not None:
        sql += " AND m.fecha_probable_parto <= %s"
        params.append(date.today() + timedelta(days=dias))
    return consultar(sql + " ORDER BY m.fecha_probable_parto", params)


def destetes_pendientes():
    return consultar(
        SQL_PARTOS + """ WHERE p.fecha_destete IS NULL AND p.lechones_vivos > 0 AND c.estado = 'activo'
                         ORDER BY p.fecha"""
    )


def volver(cerdo_id):
    if request.form.get("volver") == "ficha" and cerdo_id:
        return redirect(url_for("cerdos.ficha", id=cerdo_id) + "#reproduccion")
    return redirect(url_for("reproduccion.inicio"))


def leer_fecha(texto):
    """Convierte '2026-10-27' en fecha. Devuelve None si está vacío o mal escrito."""
    try:
        return date.fromisoformat(texto) if texto else None
    except ValueError:
        return None


def leer_entero(texto):
    try:
        return int(texto) if texto not in (None, "") else None
    except ValueError:
        return -1  # se rechaza en la validación por ser negativo


def hembras_activas():
    return consultar("SELECT id, arete, nombre FROM cerdos WHERE sexo = 'hembra' AND estado = 'activo' ORDER BY arete")


# ------------------------------------------------------------------ MONTAS

def validar_monta(f, monta_id=None, revisar_abierta=True):
    cerda = consultar_uno("SELECT sexo FROM cerdos WHERE id = %s", (f.get("cerda_id") or 0,))
    if not cerda or cerda["sexo"] != "hembra":
        return "Elige la cerda."
    if f.get("verraco_id"):
        verraco = consultar_uno("SELECT sexo FROM cerdos WHERE id = %s", (f["verraco_id"],))
        if not verraco or verraco["sexo"] != "macho":
            return "El verraco debe ser un macho."
    if f.get("tipo") not in ("monta", "inseminacion"):
        return "Elige si fue monta o inseminación."
    fecha = leer_fecha(f.get("fecha"))
    if not fecha:
        return "Escribe la fecha."
    if fecha > date.today():
        return "La fecha no puede ser en el futuro."
    if not revisar_abierta:
        return None
    # Una cerda no puede tener dos montas abiertas al tiempo.
    abierta = consultar_uno(
        """SELECT fecha FROM montas WHERE cerda_id = %s AND estado IN ('pendiente', 'confirmada')
           AND id <> %s""",
        (f["cerda_id"], monta_id or 0),
    )
    if abierta:
        return (f"Esta cerda ya tiene una monta abierta del {abierta['fecha']:%d/%m/%Y}. "
                "Regístrale el parto o márcala como fallida antes de registrar otra.")
    return None


def valores_monta(f):
    fecha = date.fromisoformat(f["fecha"])
    return (
        f["cerda_id"],
        f.get("verraco_id") or None,
        f["tipo"],
        fecha,
        fecha + timedelta(days=DIAS_GESTACION),  # fecha probable de parto, calculada sola
        f.get("observaciones", "").strip() or None,
    )


def opciones_monta():
    return {
        "cerdas": hembras_activas(),
        "verracos": consultar("SELECT id, arete, nombre FROM cerdos WHERE sexo = 'macho' AND estado = 'activo' ORDER BY arete"),
        "hoy": date.today().isoformat(),
        "dias_gestacion": DIAS_GESTACION,
    }


@bp.route("/montas/nueva", methods=["GET", "POST"])
def nueva_monta():
    if request.method == "POST":
        f = request.form
        error = validar_monta(f)
        if not error:
            ejecutar(
                """INSERT INTO montas (cerda_id, verraco_id, tipo, fecha, fecha_probable_parto, observaciones, usuario_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                valores_monta(f) + (g.usuario["id"],),
            )
            parto = date.fromisoformat(f["fecha"]) + timedelta(days=DIAS_GESTACION)
            flash(f"Monta registrada. Fecha probable de parto: {parto:%d/%m/%Y}.", "success")
            return volver(f["cerda_id"])
        flash(error, "danger")
        datos = f.to_dict()
    else:
        datos = {"fecha": date.today().isoformat(), "tipo": "monta",
                 "cerda_id": request.args.get("cerda", ""), "volver": request.args.get("volver", "")}
    return render_template("reproduccion/monta.html", monta=datos, **opciones_monta())


@bp.route("/montas/<int:id>/editar", methods=["GET", "POST"])
def editar_monta(id):
    monta = consultar_uno("SELECT * FROM montas WHERE id = %s", (id,)) or abort(404)
    if request.method == "POST":
        f = request.form
        # Si la monta ya está cerrada (fallida o parida), no choca con otras abiertas.
        error = validar_monta(f, monta_id=id, revisar_abierta=monta["estado"] in ("pendiente", "confirmada"))
        if not error:
            ejecutar(
                """UPDATE montas SET cerda_id = %s, verraco_id = %s, tipo = %s, fecha = %s,
                       fecha_probable_parto = %s, observaciones = %s WHERE id = %s""",
                valores_monta(f) + (id,),
            )
            flash("Monta actualizada.", "success")
            return volver(f["cerda_id"])
        flash(error, "danger")
        monta.update(f.to_dict())
    monta.setdefault("volver", request.args.get("volver", ""))
    return render_template("reproduccion/monta.html", monta=monta, editando=True, **opciones_monta())


@bp.route("/montas/<int:id>/estado", methods=["POST"])
def cambiar_estado(id):
    """Botones 'Confirmar preñez', 'Fallida' y 'Reabrir'."""
    monta = consultar_uno("SELECT cerda_id, estado FROM montas WHERE id = %s", (id,)) or abort(404)
    nuevo = request.form.get("estado")
    if nuevo not in ("pendiente", "confirmada", "fallida") or monta["estado"] == "parida":
        abort(400)
    if nuevo != "fallida":
        abierta = consultar_uno(
            "SELECT id FROM montas WHERE cerda_id = %s AND estado IN ('pendiente', 'confirmada') AND id <> %s",
            (monta["cerda_id"], id),
        )
        if abierta:
            flash("No se puede reabrir: la cerda ya tiene otra monta abierta.", "danger")
            return volver(monta["cerda_id"])
    ejecutar("UPDATE montas SET estado = %s WHERE id = %s", (nuevo, id))
    flash(f"Monta marcada como: {ESTADOS_MONTA[nuevo].lower()}.", "success")
    return volver(monta["cerda_id"])


@bp.route("/montas/<int:id>/eliminar", methods=["POST"])
def eliminar_monta(id):
    monta = consultar_uno("SELECT cerda_id FROM montas WHERE id = %s", (id,)) or abort(404)
    ejecutar("DELETE FROM montas WHERE id = %s", (id,))  # el parto que la usaba queda sin monta
    flash("Monta eliminada.", "success")
    return volver(monta["cerda_id"])


# ------------------------------------------------------------------ PARTOS

def validar_parto(f):
    cerda = consultar_uno("SELECT sexo FROM cerdos WHERE id = %s", (f.get("cerda_id") or 0,))
    if not cerda or cerda["sexo"] != "hembra":
        return "Elige la cerda."
    fecha = leer_fecha(f.get("fecha"))
    if not fecha:
        return "Escribe la fecha del parto."
    if fecha > date.today():
        return "La fecha del parto no puede ser en el futuro."
    vivos, muertos = leer_entero(f.get("lechones_vivos")), leer_entero(f.get("lechones_muertos"))
    if vivos is None or muertos is None or vivos < 0 or muertos < 0:
        return "Escribe cuántos lechones nacieron vivos y muertos (0 si no hubo)."
    if vivos + muertos == 0:
        return "El parto debe tener al menos un lechón."
    return validar_destete(f, fecha, vivos)


def validar_destete(f, fecha_parto, vivos):
    destete = leer_fecha(f.get("fecha_destete"))
    destetados = leer_entero(f.get("lechones_destetados"))
    if f.get("fecha_destete") and not destete:
        return "Revisa la fecha del destete."
    if destete and destete <= fecha_parto:
        return "El destete debe ser después del parto."
    if destete and destete > date.today():
        return "La fecha del destete no puede ser en el futuro."
    if destetados is not None and not 0 <= destetados <= vivos:
        return f"Los lechones destetados deben estar entre 0 y {vivos} (los que nacieron vivos)."
    if destete and destetados is None:
        return "Escribe cuántos lechones se destetaron."
    if destetados is not None and not destete:
        return "Escribe la fecha del destete."
    return None


def montas_abiertas():
    return consultar(SQL_MONTAS + " WHERE m.estado IN ('pendiente', 'confirmada') ORDER BY c.arete")


@bp.route("/partos/nuevo", methods=["GET", "POST"])
def nuevo_parto():
    if request.method == "POST":
        f = request.form
        error = validar_parto(f)
        # Si eligió una monta, debe ser de la misma cerda.
        if not error and f.get("monta_id"):
            monta = consultar_uno("SELECT cerda_id FROM montas WHERE id = %s", (f["monta_id"],))
            if not monta or str(monta["cerda_id"]) != f["cerda_id"]:
                error = "La monta elegida no es de esa cerda."
        if not error:
            ejecutar(
                """INSERT INTO partos (cerda_id, monta_id, fecha, lechones_vivos, lechones_muertos,
                       fecha_destete, lechones_destetados, observaciones, usuario_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (f["cerda_id"], f.get("monta_id") or None, f["fecha"], f["lechones_vivos"], f["lechones_muertos"],
                 f.get("fecha_destete") or None, f.get("lechones_destetados") or None,
                 f.get("observaciones", "").strip() or None, g.usuario["id"]),
            )
            if f.get("monta_id"):
                ejecutar("UPDATE montas SET estado = 'parida' WHERE id = %s", (f["monta_id"],))
            flash("Parto registrado.", "success")
            return volver(f["cerda_id"])
        flash(error, "danger")
        datos = f.to_dict()
    else:
        datos = {"fecha": date.today().isoformat(), "volver": request.args.get("volver", "")}
        # Si viene desde "Registrar parto" de una monta, llenamos la cerda y la monta.
        if request.args.get("monta"):
            monta = consultar_uno("SELECT id, cerda_id FROM montas WHERE id = %s", (request.args["monta"],))
            if monta:
                datos.update(monta_id=monta["id"], cerda_id=monta["cerda_id"])
        elif request.args.get("cerda"):
            datos["cerda_id"] = request.args["cerda"]
            abierta = consultar_uno(
                "SELECT id FROM montas WHERE cerda_id = %s AND estado IN ('pendiente', 'confirmada')",
                (datos["cerda_id"],),
            )
            if abierta:
                datos["monta_id"] = abierta["id"]
    return render_template("reproduccion/parto.html", parto=datos, cerdas=hembras_activas(),
                           montas=montas_abiertas(), hoy=date.today().isoformat())


@bp.route("/partos/<int:id>/editar", methods=["GET", "POST"])
def editar_parto(id):
    parto = consultar_uno(SQL_PARTOS + " WHERE p.id = %s", (id,)) or abort(404)
    if request.method == "POST":
        f = request.form.to_dict()
        f["cerda_id"] = str(parto["cerda_id"])  # la cerda de un parto no se cambia
        error = validar_parto(f)
        if not error:
            ejecutar(
                """UPDATE partos SET fecha = %s, lechones_vivos = %s, lechones_muertos = %s,
                       fecha_destete = %s, lechones_destetados = %s, observaciones = %s WHERE id = %s""",
                (f["fecha"], f["lechones_vivos"], f["lechones_muertos"], f.get("fecha_destete") or None,
                 f.get("lechones_destetados") or None, f.get("observaciones", "").strip() or None, id),
            )
            flash("Parto actualizado.", "success")
            return volver(parto["cerda_id"])
        flash(error, "danger")
        parto.update(f)
    parto.setdefault("volver", request.args.get("volver", ""))
    return render_template("reproduccion/parto.html", parto=parto, editando=True, hoy=date.today().isoformat())


@bp.route("/partos/<int:id>/destete", methods=["GET", "POST"])
def destete(id):
    parto = consultar_uno(SQL_PARTOS + " WHERE p.id = %s", (id,)) or abort(404)
    if request.method == "POST":
        f = request.form
        error = validar_destete(f, parto["fecha"], parto["lechones_vivos"])
        if not error and not f.get("fecha_destete"):
            error = "Escribe la fecha del destete."
        if not error:
            ejecutar(
                "UPDATE partos SET fecha_destete = %s, lechones_destetados = %s WHERE id = %s",
                (f["fecha_destete"], f["lechones_destetados"], id),
            )
            flash("Destete registrado.", "success")
            return volver(parto["cerda_id"])
        flash(error, "danger")
        parto.update(f.to_dict())
    else:
        parto.update(fecha_destete=date.today().isoformat(), lechones_destetados=parto["lechones_vivos"])
    parto.setdefault("volver", request.args.get("volver", ""))
    return render_template("reproduccion/destete.html", parto=parto, hoy=date.today().isoformat())


@bp.route("/partos/<int:id>/eliminar", methods=["POST"])
def eliminar_parto(id):
    parto = consultar_uno("SELECT cerda_id, monta_id FROM partos WHERE id = %s", (id,)) or abort(404)
    ejecutar("DELETE FROM partos WHERE id = %s", (id,))
    if parto["monta_id"]:
        # La monta vuelve a quedar como preñez confirmada, esperando su parto.
        ejecutar("UPDATE montas SET estado = 'confirmada' WHERE id = %s", (parto["monta_id"],))
    flash("Parto eliminado.", "success")
    return volver(parto["cerda_id"])


# ------------------------------------------------------------------ FICHA

def historial(cerdo):
    """Montas y partos para la ficha. Para un macho, las montas en que fue el verraco."""
    if cerdo["sexo"] == "hembra":
        montas = consultar(SQL_MONTAS + " WHERE m.cerda_id = %s ORDER BY m.fecha DESC", (cerdo["id"],))
        partos = consultar(SQL_PARTOS + " WHERE p.cerda_id = %s ORDER BY p.fecha DESC", (cerdo["id"],))
    else:
        montas = consultar(SQL_MONTAS + " WHERE m.verraco_id = %s ORDER BY m.fecha DESC", (cerdo["id"],))
        partos = []
    resumen = {
        "partos": len(partos),
        "vivos": sum(p["lechones_vivos"] for p in partos),
        "muertos": sum(p["lechones_muertos"] for p in partos),
        "destetados": sum(p["lechones_destetados"] or 0 for p in partos),
    }
    resumen["promedio"] = resumen["vivos"] / resumen["partos"] if partos else None
    return {"montas": montas, "partos": partos, "resumen": resumen}
