import sqlite3

import pytest
from werkzeug.security import check_password_hash

from db import conectar_db, inicializar_db


def test_inicializar_db_crea_usuarios_con_password_hash(tmp_path):
    ruta = tmp_path / "test.db"
    entorno = {
        "INCIDENCIAS_USUARIO_PASSWORD": "clave-usuario",
        "INCIDENCIAS_TECNICO_PASSWORD": "clave-tecnico",
    }

    inicializar_db(ruta, entorno)

    with conectar_db(ruta) as conexion:
        usuarios = conexion.execute(
            "SELECT nombre_usuario, password_hash, rol FROM usuarios ORDER BY id"
        ).fetchall()

    assert [(usuario["nombre_usuario"], usuario["rol"]) for usuario in usuarios] == [
        ("usuario", "usuario"),
        ("tecnico", "tecnico"),
    ]
    assert all(
        check_password_hash(usuario["password_hash"], entorno[
            f"INCIDENCIAS_{usuario['rol'].upper()}_PASSWORD"
        ])
        for usuario in usuarios
    )
    assert all(
        usuario["password_hash"] != entorno[
            f"INCIDENCIAS_{usuario['rol'].upper()}_PASSWORD"
        ]
        for usuario in usuarios
    )


def test_inicializar_db_es_idempotente_y_crea_esquema_de_incidencias(tmp_path):
    ruta = tmp_path / "test.db"
    entorno = {
        "INCIDENCIAS_USUARIO_PASSWORD": "clave-usuario",
        "INCIDENCIAS_TECNICO_PASSWORD": "clave-tecnico",
    }

    inicializar_db(ruta, entorno)
    with conectar_db(ruta) as conexion:
        usuario_id = conexion.execute(
            "SELECT id FROM usuarios WHERE nombre_usuario = 'usuario'"
        ).fetchone()["id"]
        hash_original = conexion.execute(
            "SELECT password_hash FROM usuarios WHERE nombre_usuario = 'usuario'"
        ).fetchone()["password_hash"]
        conexion.execute(
            """
            INSERT INTO incidencias (usuario_id, observacion, prioridad)
            VALUES (?, ?, ?)
            """,
            (usuario_id, "El equipo no arranca", "alta"),
        )

    inicializar_db(
        ruta,
        {
            "INCIDENCIAS_USUARIO_PASSWORD": "nueva-clave",
            "INCIDENCIAS_TECNICO_PASSWORD": "clave-tecnico",
        },
    )

    with conectar_db(ruta) as conexion:
        usuarios = conexion.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
        incidencia = conexion.execute(
            "SELECT categoria, estado FROM incidencias"
        ).fetchone()
        hash_persistido = conexion.execute(
            "SELECT password_hash FROM usuarios WHERE nombre_usuario = 'usuario'"
        ).fetchone()["password_hash"]

    assert usuarios == 2
    assert dict(incidencia) == {"categoria": "revisar", "estado": "abierta"}
    assert hash_persistido == hash_original


def test_inicializar_db_rechaza_claves_ausentes_sin_crear_archivo(tmp_path):
    ruta = tmp_path / "test.db"

    with pytest.raises(RuntimeError, match="INCIDENCIAS_USUARIO_PASSWORD"):
        inicializar_db(ruta, {})

    assert not ruta.exists()


def test_esquema_rechaza_roles_invalidos(tmp_path):
    ruta = tmp_path / "test.db"
    inicializar_db(
        ruta,
        {
            "INCIDENCIAS_USUARIO_PASSWORD": "clave-usuario",
            "INCIDENCIAS_TECNICO_PASSWORD": "clave-tecnico",
        },
    )

    with pytest.raises(sqlite3.IntegrityError):
        with conectar_db(ruta) as conexion:
            conexion.execute(
                "INSERT INTO usuarios (nombre_usuario, password_hash, rol) "
                "VALUES ('otro', 'hash', 'administrador')"
            )
