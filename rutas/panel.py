"""Datos del panel de inicio: el resumen de toda la granja en una sola página."""
from datetime import date, timedelta

from db import consultar, consultar_uno
from rutas import reproduccion, salud

DIAS_AVISO = 30  # se muestran las vacunas y los partos de los próximos 30 días


def resumen():
    hoy = date.today()
    inicio_mes = hoy.replace(day=1)

    por_sexo = {f["sexo"]: f["n"] for f in consultar(
        "SELECT sexo, COUNT(*) AS n FROM cerdos WHERE estado = 'activo' GROUP BY sexo"
    )}

    corrales = consultar(
        """SELECT co.id, co.nombre, co.capacidad, COUNT(c.id) AS n
           FROM corrales co LEFT JOIN cerdos c ON c.corral_id = co.id AND c.estado = 'activo'
           GROUP BY co.id ORDER BY co.nombre"""
    )
    sin_corral = consultar_uno(
        "SELECT COUNT(*) AS n FROM cerdos WHERE estado = 'activo' AND corral_id IS NULL"
    )["n"]

    # Cerdos activos que no se pesan hace más de 30 días (o que nunca se han pesado).
    sin_pesar = consultar_uno(
        """SELECT COUNT(*) AS n FROM cerdos c
           WHERE c.estado = 'activo' AND NOT EXISTS (
               SELECT 1 FROM pesajes p WHERE p.cerdo_id = c.id AND p.fecha >= %s)""",
        (hoy - timedelta(days=30),),
    )["n"]

    # Dinero y salidas del mes actual.
    def suma(sql):
        return consultar_uno(sql, (inicio_mes, hoy))["total"] or 0

    mes = {
        "alimentacion": suma("SELECT SUM(costo) AS total FROM alimentacion WHERE fecha BETWEEN %s AND %s"),
        "salud": suma("SELECT SUM(costo) AS total FROM salud WHERE fecha BETWEEN %s AND %s"),
        "ventas": suma("SELECT SUM(precio) AS total FROM salidas WHERE tipo = 'venta' AND fecha BETWEEN %s AND %s"),
        "vendidos": suma("SELECT COUNT(*) AS total FROM salidas WHERE tipo = 'venta' AND fecha BETWEEN %s AND %s"),
        "muertes": suma("SELECT COUNT(*) AS total FROM salidas WHERE tipo = 'muerte' AND fecha BETWEEN %s AND %s"),
        "nacidos": suma("SELECT SUM(lechones_vivos) AS total FROM partos WHERE fecha BETWEEN %s AND %s"),
    }
    mes["gastos"] = mes["alimentacion"] + mes["salud"]

    return {
        "hembras": por_sexo.get("hembra", 0),
        "machos": por_sexo.get("macho", 0),
        "total": sum(por_sexo.values()),
        "corrales": corrales,
        "sin_corral": sin_corral,
        "sin_pesar": sin_pesar,
        "vacunas": salud.pendientes(dias=DIAS_AVISO),
        "partos": reproduccion.proximos_partos(dias=DIAS_AVISO),
        "destetes": reproduccion.destetes_pendientes(),
        "mes": mes,
        "dias_aviso": DIAS_AVISO,
        "dias_destete": reproduccion.DIAS_DESTETE,
        "hoy": hoy,
    }
