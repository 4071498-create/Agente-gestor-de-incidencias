from pathlib import Path

from flask import Flask

from db import DB_PATH, inicializar_db


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_mapping(DATABASE=DB_PATH)
    if config is not None:
        app.config.update(config)

    inicializar_db(Path(app.config["DATABASE"]))

    @app.get("/")
    def inicio() -> str:
        return (
            "<!doctype html><html lang='es'><meta charset='utf-8'>"
            "<title>Gestor de incidencias</title>"
            "<h1>Gestor de incidencias</h1>"
            "<p>La aplicación está en marcha y la base de datos está preparada.</p>"
            "</html>"
        )

    return app
