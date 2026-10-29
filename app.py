import os
import secrets
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from flask import (
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash

from clasificador import clasificar
from db import DB_PATH, conectar_db, inicializar_db


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_mapping(
        DATABASE=DB_PATH,
        SECRET_KEY=os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32),
    )
    if config is not None:
        app.config.update(config)

    inicializar_db(Path(app.config["DATABASE"]))

    @app.before_request
    def cargar_usuario() -> None:
        usuario_id = session.get("usuario_id")
        g.usuario = None
        if usuario_id is not None:
            with conectar_db(Path(app.config["DATABASE"])) as conexion:
                g.usuario = conexion.execute(
                    """
                    SELECT id, nombre_usuario, rol
                    FROM usuarios
                    WHERE id = ?
                    """,
                    (usuario_id,),
                ).fetchone()
            if g.usuario is None:
                session.clear()

    def requiere_usuario(funcion: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(funcion)
        def protegida(*args: Any, **kwargs: Any) -> Any:
            if g.usuario is None:
                return redirect(url_for("login"))
            return funcion(*args, **kwargs)

        return protegida

    @app.get("/")
    @requiere_usuario
    def inicio() -> str:
        if g.usuario["rol"] == "tecnico":
            return render_template("tecnico_pendiente.html")

        with conectar_db(Path(app.config["DATABASE"])) as conexion:
            incidencias = conexion.execute(
                """
                SELECT id, fecha, observacion, categoria, prioridad, resumen, estado
                FROM incidencias
                WHERE usuario_id = ?
                ORDER BY id DESC
                """,
                (g.usuario["id"],),
            ).fetchall()
        return render_template("incidencias.html", incidencias=incidencias)

    @app.route("/login", methods=["GET", "POST"])
    def login() -> str:
        if g.usuario is not None:
            return redirect(url_for("inicio"))

        if request.method == "POST":
            nombre_usuario = request.form.get("nombre_usuario", "").strip()
            contrasena = request.form.get("contrasena", "")
            with conectar_db(Path(app.config["DATABASE"])) as conexion:
                usuario = conexion.execute(
                    """
                    SELECT id, nombre_usuario, password_hash, rol
                    FROM usuarios
                    WHERE nombre_usuario = ?
                    """,
                    (nombre_usuario,),
                ).fetchone()

            if usuario is None or not check_password_hash(
                usuario["password_hash"], contrasena
            ):
                flash("Usuario o contraseña incorrectos.", "error")
            else:
                session.clear()
                session["usuario_id"] = usuario["id"]
                return redirect(url_for("inicio"))

        return render_template("login.html")

    @app.post("/logout")
    @requiere_usuario
    def logout() -> Any:
        session.clear()
        return redirect(url_for("login"))

    @app.route("/incidencias/nueva", methods=["GET", "POST"])
    @requiere_usuario
    def nueva_incidencia() -> Any:
        if g.usuario["rol"] != "usuario":
            abort(403)

        if request.method == "POST":
            observacion = request.form.get("observacion", "").strip()
            if not observacion:
                flash("Escribe una observación antes de enviar.", "error")
                return render_template("nueva_incidencia.html"), 400

            resultado = clasificar(observacion)
            with conectar_db(Path(app.config["DATABASE"])) as conexion:
                conexion.execute(
                    """
                    INSERT INTO incidencias (
                        usuario_id, observacion, categoria, prioridad, resumen
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        g.usuario["id"],
                        observacion,
                        resultado["categoria"],
                        resultado["prioridad"],
                        resultado["resumen"],
                    ),
                )
            flash("La incidencia se ha registrado.", "success")
            return redirect(url_for("inicio"))

        return render_template("nueva_incidencia.html")

    return app
