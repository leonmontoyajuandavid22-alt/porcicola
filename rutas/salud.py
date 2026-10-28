"""Salud: vacunas, desparasitaciones, enfermedades y tratamientos."""
from datetime import date, timedelta

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from db import consultar, consultar_uno, ejecutar

bp = Blueprint("salud", __name__, url_prefix="/salud")

TIPOS = {
    "vacuna": "Vacuna",
    "desparasitacion": "Desparasitación",
    "enfermedad": "Enfermedad",
    "tratamiento": "Tratamiento",
}

# Las columnas que se llenan desde el formulario, en el mismo orden que valores().
COLUMNAS = "tipo, fecha, descripcion, medicamento, dosis, proxima_fecha, costo, responsable, observaciones"


@bp.route("/")
def lista():
    filtros = {
        "buscar": request.args.get("buscar", "").strip(),
        "corral": request.args.get("corral", ""),
        "tipo": request.args.get("tipo", ""),
    }
    condiciones, params = [], []
    if filtros["buscar"]:
        condiciones.append("(c.arete LIKE %s OR c.nombre LIKE %s OR s.descripcion LIKE %s OR s.medicamento LIKE %s)")
        params += [f"%{filtros['buscar']}%"] * 4
    if filtros["corral"]:
        condiciones.append("c.corral_id = %s")
        params.append(filtros["corral"])
    if filtros["tipo"]:
        condiciones.append("s.tipo = %s")
        params.append(filtros["tipo"])
    where = "WHERE " + " AND ".join(condiciones) if condiciones else ""

    registros = consultar(
        f"""SELECT s.*, c.arete, c.nombre
            FROM salud s JOIN cerdos c ON c.id = s.cerdo_id
            {where}
            ORDER BY s.fecha DESC, s.id DESC
            LIMIT 200""",
        params,
    )
    return render_template(
        "salud/lista.html",
        registros=registros,
        pendientes=pendientes(),
        filtros=filtros,
        tipos=TIPOS,
        corrales=consultar("SELECT id, nombre FROM corrales ORDER BY nombre"),
        hoy=date.today(),
    )


def pendientes(cerdo_id=None, dias=None):
    """Próximas dosis que todavía no se han aplicado (de cerdos activos).
    Si se da 'dias', solo trae las que vencen dentro de ese número de días."""
    condiciones, params = ["s.proxima_fecha IS NOT NULL", "c.estado = 'activo'"], []
    if cerdo_id:
        condiciones.append("s.cerdo_id = %s")
        params.append(cerdo_id)
    if dias is not None:
        condiciones.append("s.proxima_fecha <= %s")
        params.append(date.today() + timedelta(days=dias))
    return consultar(
        f"""SELECT s.*, c.arete, c.nombre
            FROM salud s JOIN cerdos c ON c.id = s.cerdo_id
            WHERE {" AND ".join(condiciones)}
            ORDER BY s.proxima_fecha""",
        params,
    )


def validar(f):
    if f.get("tipo") not in TIPOS:
        return "Elige el tipo de registro."
    if not f.get("descripcion", "").strip():
        return "Escribe la descripción (por ejemplo, el nombre de la vacuna o la enfermedad)."
    try:
        fecha = date.fromisoformat(f.get("fecha", ""))
        proxima = date.fromisoformat(f["proxima_fecha"]) if f.get("proxima_fecha") else None
        costo = float(f["costo"]) if f.get("costo") else 0
    except ValueError:
        return "Revisa las fechas y el costo."
    if fecha > date.today():
        return "La fecha no puede ser en el futuro. Si es algo pendiente, ponlo como 'próxima dosis'."
    if proxima and proxima <= fecha:
        return "La próxima dosis debe ser después de la fecha de aplicación."
    if costo < 0:
        return "El costo no puede ser negativo."
    return None


def valores(f):
    return (
        f["tipo"],
        f["fecha"],
        f["descripcion"].strip(),
        f.get("medicamento", "").strip() or None,
        f.get("dosis", "").strip() or None,
        f.get("proxima_fecha") or None,
        f.get("costo") or None,
        f.get("responsable", "").strip() or None,
        f.get("observaciones", "").strip() or None,
    )


def volver(cerdo_id):
    if request.form.get("volver") == "ficha" and cerdo_id:
        return redirect(url_for("cerdos.ficha", id=cerdo_id) + "#salud")
    return redirect(url_for("salud.lista"))


@bp.route("/nuevo", methods=["GET", "POST"])
def nuevo():
    if request.method == "POST":
        f = request.form
        # "destino" puede ser "cerdo-5" (un cerdo) o "corral-2" (todos los cerdos activos del corral).
        tipo_destino, _, destino_id = f.get("destino", "").partition("-")
        if tipo_destino == "corral":
            cerdos = consultar(
                "SELECT id FROM cerdos WHERE corral_id = %s AND estado = 'activo'", (destino_id,)
            )
        elif tipo_destino == "cerdo":
            cerdos = consultar("SELECT id FROM cerdos WHERE id = %s", (destino_id,))
        else:
            cerdos = []

        error = validar(f) or ("" if cerdos else "Elige un cerdo o un corral con cerdos activos.")
        if not error:
            for cerdo in cerdos:
                ejecutar(
                    f"INSERT INTO salud (cerdo_id, {COLUMNAS}, usuario_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (cerdo["id"],) + valores(f) + (g.usuario["id"],),
                )
            # Si este registro es la dosis que estaba pendiente, la quitamos de pendientes.
            if f.get("pendiente_id"):
                ejecutar("UPDATE salud SET proxima_fecha = NULL WHERE id = %s", (f["pendiente_id"],))
            flash(f"Registro de salud guardado{f' para {len(cerdos)} cerdos' if len(cerdos) > 1 else ''}.", "success")
            return volver(cerdos[0]["id"] if tipo_destino == "cerdo" else None)
        flash(error, "danger")
        datos = f.to_dict()
    else:
        # Los datos pueden venir en la dirección para llenar el formulario,
        # por ejemplo al presionar "Aplicar" en una dosis pendiente.
        datos = request.args.to_dict()
        datos.setdefault("fecha", date.today().isoformat())
        datos.setdefault("responsable", g.usuario["nombre"])
        if "cerdo" in datos:
            datos["destino"] = f"cerdo-{datos['cerdo']}"
    return render_template("salud/formulario.html", registro=datos, **opciones())


def opciones():
    return {
        "tipos": TIPOS,
        "cerdos": consultar("SELECT id, arete, nombre FROM cerdos WHERE estado = 'activo' ORDER BY arete"),
        "corrales": consultar(
            """SELECT co.id, co.nombre, COUNT(c.id) AS n FROM corrales co
               JOIN cerdos c ON c.corral_id = co.id AND c.estado = 'activo'
               GROUP BY co.id ORDER BY co.nombre"""
        ),
        # Sugerencias para escribir más rápido (lo que ya se ha usado antes).
        "usuarios": consultar("SELECT nombre FROM usuarios ORDER BY nombre"),
        "descripciones": consultar("SELECT DISTINCT descripcion FROM salud ORDER BY descripcion"),
        "medicamentos": consultar(
            "SELECT DISTINCT medicamento FROM salud WHERE medicamento IS NOT NULL ORDER BY medicamento"
        ),
        "hoy": date.today().isoformat(),
    }


@bp.route("/<int:id>/editar", methods=["GET", "POST"])
def editar(id):
    registro = consultar_uno(
        "SELECT s.*, c.arete, c.nombre FROM salud s JOIN cerdos c ON c.id = s.cerdo_id WHERE s.id = %s", (id,)
    ) or abort(404)
    if request.method == "POST":
        f = request.form
        error = validar(f)
        if not error:
            asignaciones = ", ".join(f"{col.strip()} = %s" for col in COLUMNAS.split(","))
            ejecutar(f"UPDATE salud SET {asignaciones} WHERE id = %s", valores(f) + (id,))
            flash("Registro de salud actualizado.", "success")
            return volver(registro["cerdo_id"])
        flash(error, "danger")
        registro.update(f.to_dict())
    registro["volver"] = request.values.get("volver", "")
    return render_template("salud/formulario.html", registro=registro, editando=True, **opciones())


@bp.route("/<int:id>/descartar", methods=["POST"])
def descartar(id):
    """Quita una dosis de la lista de pendientes sin registrar nada nuevo."""
    registro = consultar_uno("SELECT cerdo_id FROM salud WHERE id = %s", (id,)) or abort(404)
    ejecutar("UPDATE salud SET proxima_fecha = NULL WHERE id = %s", (id,))
    flash("Dosis pendiente descartada.", "success")
    return volver(registro["cerdo_id"])


@bp.route("/<int:id>/eliminar", methods=["POST"])
def eliminar(id):
    registro = consultar_uno("SELECT cerdo_id FROM salud WHERE id = %s", (id,)) or abort(404)
    ejecutar("DELETE FROM salud WHERE id = %s", (id,))
    flash("Registro de salud eliminado.", "success")
    return volver(registro["cerdo_id"])


def historial(cerdo_id):
    return consultar(
        "SELECT * FROM salud WHERE cerdo_id = %s ORDER BY fecha DESC, id DESC", (cerdo_id,)
    )
