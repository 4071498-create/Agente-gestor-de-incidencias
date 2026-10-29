from flask import Flask

from app import create_app
from db import conectar_db


def test_arranque_prepara_base_de_datos_y_muestra_inicio(tmp_path, monkeypatch):
    monkeypatch.setenv("INCIDENCIAS_USUARIO_PASSWORD", "clave-usuario")
    monkeypatch.setenv("INCIDENCIAS_TECNICO_PASSWORD", "clave-tecnico")
    ruta_db = tmp_path / "incidencias.db"

    app = create_app({"TESTING": True, "DATABASE": ruta_db})

    assert isinstance(app, Flask)
    cliente = app.test_client()
    assert cliente.get("/").status_code == 302
    respuesta = cliente.get("/login")
    assert respuesta.status_code == 200
    assert "Iniciar sesión" in respuesta.get_data(as_text=True)

    with conectar_db(ruta_db) as conexion:
        usuarios = conexion.execute(
            "SELECT nombre_usuario FROM usuarios ORDER BY nombre_usuario"
        ).fetchall()

    assert [usuario["nombre_usuario"] for usuario in usuarios] == [
        "tecnico",
        "usuario",
    ]
