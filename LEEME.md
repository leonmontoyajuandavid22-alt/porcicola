# Porcícola 🐷

Página web para llevar el registro de los cerdos de la granja: cerdos, pesajes, salud,
reproducción, alimentación, corrales y salidas (ventas y muertes).

Hecha en **Python con Flask** y **MySQL (XAMPP)**.

---

## Primera vez (instalación)

1. Instala **Python** y **XAMPP**.
2. Abre una terminal en esta carpeta e instala las librerías:
   ```
   pip install -r requirements.txt
   ```
3. Abre el **XAMPP Control Panel** y presiona **Start** en **MySQL**.
4. Crea la base de datos y el usuario administrador:
   ```
   python crear_base_datos.py
   ```
   Te pide un usuario, tu nombre y una contraseña (la contraseña no se ve al escribirla).

## Uso diario

1. **XAMPP Control Panel** → **Start** en **MySQL** (que quede en verde).
2. En una terminal en esta carpeta:
   ```
   python app.py
   ```
3. En el navegador abre **http://127.0.0.1:5000** y entra con tu usuario.
4. Para apagar la página: `Ctrl + C` en la terminal. Luego **Stop** en MySQL.

> Si la terminal dice que no encuentra `app.py`, escribe primero `cd C:\porcicola`.

## Abrir la página desde el celular

1. El celular y el computador deben estar en la **misma red Wi-Fi**.
2. En `app.py` cambia `ABRIR_EN_RED = False` por `ABRIR_EN_RED = True`.
3. Ejecuta `python app.py`. La terminal muestra una dirección como `http://192.168.1.20:5000`.
4. Abre esa dirección en el navegador del celular.
5. Si Windows pregunta por el **Firewall**, presiona **Permitir** en **redes privadas**.

El computador tiene que seguir encendido con la página corriendo.

## Copias de seguridad

Con MySQL encendido:
```
python respaldo.py
```
Se crea una carpeta en `respaldos/` con todos los datos y las fotos.
Cópiala a una memoria USB o a la nube **al menos una vez por semana**.

Para recuperar un respaldo (reemplaza los datos actuales):
```
C:\xampp\mysql\bin\mysql.exe -u root porcicola < respaldos\FECHA\porcicola.sql
```
y copia la carpeta `fotos` del respaldo dentro de `static\`.

## Qué hay en cada carpeta

| Archivo / carpeta | Qué hace |
|---|---|
| `app.py` | Enciende la página. Inicio de sesión obligatorio, panel de inicio y formatos (fechas, dinero, kg). |
| `db.py` | Conexión a MySQL: `consultar`, `consultar_uno` y `ejecutar`. |
| `crear_base_datos.py` | Crea la base de datos, las tablas, las razas iniciales y el administrador. |
| `respaldo.py` | Copia de seguridad de los datos y las fotos. |
| `rutas/` | Un archivo de Python por sección (`cerdos.py`, `pesajes.py`, `salud.py`, `reproduccion.py`, `alimentacion.py`, `salidas.py`, `corrales.py`, `razas.py`, `login.py`, `panel.py`). |
| `templates/` | Las páginas (HTML). `base.html` es el marco con el menú que comparten todas. |
| `static/` | Estilos (`style.css`), Bootstrap y Chart.js (`vendor/`) y las fotos de los cerdos (`fotos/`). |
| `instance/` | Clave secreta de las sesiones. Se crea sola; no la compartas. |
| `version_anterior/` | La primera versión del proyecto, guardada por si acaso. |

## Números que puedes ajustar

- `rutas/reproduccion.py`: `DIAS_GESTACION = 114` y `DIAS_DESTETE = 21`.
- `rutas/panel.py`: `DIAS_AVISO = 30` (cuántos días hacia adelante muestra vacunas y partos el panel).
