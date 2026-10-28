import mysql.connector
from mysql.connector import errors
from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "",
    "database": "porcicola",
}


def conectar():
    return mysql.connector.connect(**CONFIG)


def consultar(sql, params=()):
    """Para SELECT: devuelve una lista de filas."""
    con = conectar()
    cur = con.cursor(dictionary=True)
    cur.execute(sql, params)
    filas = cur.fetchall()
    cur.close()
    con.close()
    return filas


def ejecutar(sql, params=()):
    """Para INSERT, UPDATE y DELETE."""
    con = conectar()
    cur = con.cursor()
    cur.execute(sql, params)
    con.commit()
    cur.close()
    con.close()


@app.route("/")
def inicio():
    buscar = request.args.get("buscar", "").strip()
    cerdos = consultar(
        "SELECT * FROM cerdos WHERE arete LIKE %s ORDER BY arete",
        (f"%{buscar}%",),
    )
    return render_template(
        "cerdos.html",
        cerdos=cerdos,
        buscar=buscar,
        error=request.args.get("error"),
    )


@app.route("/agregar", methods=["POST"])
def agregar():
    f = request.form
    try:
        ejecutar(
            """INSERT INTO cerdos (arete, sexo, nacimiento, estado, corral, peso)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (
                f["arete"].strip(),
                f["sexo"],
                f["nacimiento"],
                f["estado"],
                f["corral"].strip(),
                f["peso"] or None,
            ),
        )
    except errors.IntegrityError:
        return redirect(url_for("inicio", error="Ya existe un cerdo con ese arete"))
    return redirect(url_for("inicio"))


@app.route("/borrar/<int:id>", methods=["POST"])
def borrar(id):
    ejecutar("DELETE FROM cerdos WHERE id = %s", (id,))
    return redirect(url_for("inicio"))


if __name__ == "__main__":
    app.run(debug=True)