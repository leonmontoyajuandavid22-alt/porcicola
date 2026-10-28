"""Funciones para hablar con la base de datos MySQL de XAMPP.

Todo el resto del proyecto usa estas funciones en vez de conectarse
directamente, así la configuración está en un solo lugar.
"""
import mysql.connector

CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "",
    "database": "porcicola",
}


def conectar():
    return mysql.connector.connect(**CONFIG)


def consultar(sql, params=()):
    """Para SELECT: devuelve una lista de filas (cada fila es un diccionario)."""
    con = conectar()
    cur = con.cursor(dictionary=True)
    cur.execute(sql, params)
    filas = cur.fetchall()
    cur.close()
    con.close()
    return filas


def consultar_uno(sql, params=()):
    """Para SELECT de una sola fila: devuelve un diccionario o None."""
    filas = consultar(sql, params)
    return filas[0] if filas else None


def ejecutar(sql, params=()):
    """Para INSERT, UPDATE y DELETE. Devuelve el id de la fila insertada."""
    con = conectar()
    cur = con.cursor()
    cur.execute(sql, params)
    con.commit()
    nuevo_id = cur.lastrowid
    cur.close()
    con.close()
    return nuevo_id
