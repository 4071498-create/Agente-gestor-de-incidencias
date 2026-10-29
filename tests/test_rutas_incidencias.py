from unittest.mock import Mock

from werkzeug.security import generate_password_hash

from app import create_app
from db import conectar_db


def crear_cliente(tmp_path, monkeypatch):
    monkeypatch.setenv("INCIDENCIAS_USUARIO_PASSWORD", "clave-usuario")
    monkeypatch.setenv("INCIDENCIAS_TECNICO_PASSWORD", "clave-tecnico")
    app = create_app(
        {
            "TESTING": True,
            "DATABASE": tmp_path / "incidencias.db",
            "SECRET_KEY": "clave-de-prueba",
        }
    )
    return app.test_client(), app.config["DATABASE"]


def iniciar_sesion(cliente, nombre_usuario="usuario", contrasena="clave-usuario"):
    return cliente.post(
        "/login",
        data={"nombre_usuario": nombre_usuario, "contrasena": contrasena},
        follow_redirects=True,
    )


def test_login_rechaza_contrasena_incorrecta(tmp_path, monkeypatch):
    cliente, _ = crear_cliente(tmp_path, monkeypatch)

    respuesta = cliente.post(
        "/login",
        data={"nombre_usuario": "usuario", "contrasena": "incorrecta"},
    )

    assert respuesta.status_code == 200
    assert "Usuario o contraseña incorrectos" in respuesta.get_data(as_text=True)


def test_login_correcto_muestra_solo_las_incidencias_del_usuario(
    tmp_path, monkeypatch
):
    cliente, ruta_db = crear_cliente(tmp_path, monkeypatch)
    with conectar_db(ruta_db) as conexion:
        otro_usuario = conexion.execute(
            """
            INSERT INTO usuarios (nombre_usuario, password_hash, rol)
            VALUES (?, ?, ?)
            """,
            ("otro", generate_password_hash("clave-otro"), "usuario"),
        ).lastrowid
        usuario = conexion.execute(
            "SELECT id FROM usuarios WHERE nombre_usuario = 'usuario'"
        ).fetchone()
        conexion.execute(
            """
            INSERT INTO incidencias (usuario_id, observacion, prioridad)
            VALUES (?, ?, ?)
            """,
            (otro_usuario, "Incidencia privada de otra persona", "baja"),
        )
        conexion.execute(
            """
            INSERT INTO incidencias (usuario_id, observacion, prioridad)
            VALUES (?, ?, ?)
            """,
            (usuario["id"], "Incidencia propia", "media"),
        )

    respuesta = iniciar_sesion(cliente)
    contenido = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert "Incidencia propia" in contenido
    assert "Incidencia privada de otra persona" not in contenido


def test_no_autenticado_no_puede_abrir_formulario(tmp_path, monkeypatch):
    cliente, _ = crear_cliente(tmp_path, monkeypatch)

    respuesta = cliente.get("/incidencias/nueva")

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/login")


def test_usuario_registra_incidencia_clasificada_y_se_guarda(
    tmp_path, monkeypatch
):
    cliente, ruta_db = crear_cliente(tmp_path, monkeypatch)
    clasificador_simulado = Mock(
        return_value={
            "categoria": "hardware",
            "prioridad": "alta",
            "resumen": "El portátil no enciende",
        }
    )
    monkeypatch.setattr(
        "app.clasificar",
        clasificador_simulado,
    )
    iniciar_sesion(cliente)

    observacion = "No arranca el portátil, no enciende ni el led"
    respuesta = cliente.post(
        "/incidencias/nueva",
        data={"observacion": observacion},
        follow_redirects=True,
    )

    clasificador_simulado.assert_called_once_with(observacion)
    assert respuesta.status_code == 200
    assert "La incidencia se ha registrado" in respuesta.get_data(as_text=True)
    assert "No arranca el portátil, no enciende ni el led" in respuesta.get_data(
        as_text=True
    )
    with conectar_db(ruta_db) as conexion:
        incidencia = conexion.execute(
            """
            SELECT observacion, categoria, prioridad, resumen, estado, usuario_id
            FROM incidencias
            """
        ).fetchone()

    assert dict(incidencia) == {
        "observacion": "No arranca el portátil, no enciende ni el led",
        "categoria": "hardware",
        "prioridad": "alta",
        "resumen": "El portátil no enciende",
        "estado": "abierta",
        "usuario_id": 1,
    }


def test_observacion_vacia_no_se_envia_al_clasificador(tmp_path, monkeypatch):
    cliente, ruta_db = crear_cliente(tmp_path, monkeypatch)
    clasificador_simulado = Mock()
    monkeypatch.setattr("app.clasificar", clasificador_simulado)
    iniciar_sesion(cliente)

    respuesta = cliente.post("/incidencias/nueva", data={"observacion": "  "})

    clasificador_simulado.assert_not_called()
    assert respuesta.status_code == 400
    assert "Escribe una observación" in respuesta.get_data(as_text=True)
    with conectar_db(ruta_db) as conexion:
        total = conexion.execute("SELECT COUNT(*) FROM incidencias").fetchone()[0]
    assert total == 0


def test_incidencia_se_guarda_con_categoria_revisar_si_falla_clasificacion(
    tmp_path, monkeypatch
):
    cliente, ruta_db = crear_cliente(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "app.clasificar",
        Mock(
            return_value={
                "categoria": "revisar",
                "prioridad": "media",
                "resumen": "Pendiente de clasificación",
            }
        ),
    )
    iniciar_sesion(cliente)

    respuesta = cliente.post(
        "/incidencias/nueva",
        data={"observacion": "No hay conexión con el servidor"},
        follow_redirects=True,
    )

    assert respuesta.status_code == 200
    with conectar_db(ruta_db) as conexion:
        incidencia = conexion.execute(
            "SELECT categoria, estado FROM incidencias"
        ).fetchone()
    assert dict(incidencia) == {"categoria": "revisar", "estado": "abierta"}


def test_tecnico_no_puede_usar_formulario_de_usuario(tmp_path, monkeypatch):
    cliente, _ = crear_cliente(tmp_path, monkeypatch)
    iniciar_sesion(cliente, "tecnico", "clave-tecnico")

    respuesta = cliente.get("/incidencias/nueva")

    assert respuesta.status_code == 403


def test_solo_tecnico_puede_abrir_el_panel(tmp_path, monkeypatch):
    cliente, _ = crear_cliente(tmp_path, monkeypatch)

    assert cliente.get("/tecnico").status_code == 302
    iniciar_sesion(cliente)
    assert cliente.get("/tecnico").status_code == 403

    cliente.post("/logout")
    iniciar_sesion(cliente, "tecnico", "clave-tecnico")
    respuesta = cliente.get("/tecnico")
    assert respuesta.status_code == 200
    assert "Panel del técnico" in respuesta.get_data(as_text=True)


def test_panel_muestra_todas_las_incidencias_y_filtra_por_campos(
    tmp_path, monkeypatch
):
    cliente, ruta_db = crear_cliente(tmp_path, monkeypatch)
    with conectar_db(ruta_db) as conexion:
        usuario_id = conexion.execute(
            "SELECT id FROM usuarios WHERE nombre_usuario = 'usuario'"
        ).fetchone()["id"]
        tecnico_id = conexion.execute(
            "SELECT id FROM usuarios WHERE nombre_usuario = 'tecnico'"
        ).fetchone()["id"]
        conexion.executemany(
            """
            INSERT INTO incidencias (
                usuario_id, observacion, categoria, prioridad, estado
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (usuario_id, "Portátil averiado", "hardware", "alta", "abierta"),
                (tecnico_id, "Aplicación se cierra", "software", "media", "en curso"),
                (usuario_id, "Red intermitente", "red", "alta", "resuelta"),
            ],
        )
    iniciar_sesion(cliente, "tecnico", "clave-tecnico")

    todas = cliente.get("/tecnico")
    filtradas = cliente.get(
        "/tecnico?categoria=hardware&prioridad=alta&estado=abierta"
    )

    assert todas.status_code == 200
    assert "Portátil averiado" in todas.get_data(as_text=True)
    assert "Aplicación se cierra" in todas.get_data(as_text=True)
    assert "Red intermitente" in todas.get_data(as_text=True)
    assert filtradas.status_code == 200
    contenido = filtradas.get_data(as_text=True)
    assert "Portátil averiado" in contenido
    assert "Aplicación se cierra" not in contenido
    assert "Red intermitente" not in contenido


def test_panel_rechaza_filtros_invalidos(tmp_path, monkeypatch):
    cliente, _ = crear_cliente(tmp_path, monkeypatch)
    iniciar_sesion(cliente, "tecnico", "clave-tecnico")

    respuesta = cliente.get("/tecnico?categoria=desconocida")

    assert respuesta.status_code == 400


def test_tecnico_puede_actualizar_categoria_prioridad_y_estado(
    tmp_path, monkeypatch
):
    cliente, ruta_db = crear_cliente(tmp_path, monkeypatch)
    with conectar_db(ruta_db) as conexion:
        usuario_id = conexion.execute(
            "SELECT id FROM usuarios WHERE nombre_usuario = 'usuario'"
        ).fetchone()["id"]
        incidencia_id = conexion.execute(
            """
            INSERT INTO incidencias (
                usuario_id, observacion, prioridad, categoria
            )
            VALUES (?, ?, ?, ?)
            """,
            (usuario_id, "Equipo sin conexión", "baja", "revisar"),
        ).lastrowid
    iniciar_sesion(cliente, "tecnico", "clave-tecnico")

    respuesta = cliente.post(
        f"/tecnico/incidencias/{incidencia_id}",
        data={"categoria": "red", "prioridad": "alta", "estado": "en curso"},
    )

    assert respuesta.status_code == 302
    with conectar_db(ruta_db) as conexion:
        incidencia = conexion.execute(
            "SELECT categoria, prioridad, estado FROM incidencias WHERE id = ?",
            (incidencia_id,),
        ).fetchone()
    assert dict(incidencia) == {
        "categoria": "red",
        "prioridad": "alta",
        "estado": "en curso",
    }


def test_actualizacion_tecnica_rechaza_datos_invalidos_y_ids_inexistentes(
    tmp_path, monkeypatch
):
    cliente, ruta_db = crear_cliente(tmp_path, monkeypatch)
    with conectar_db(ruta_db) as conexion:
        usuario_id = conexion.execute(
            "SELECT id FROM usuarios WHERE nombre_usuario = 'usuario'"
        ).fetchone()["id"]
        incidencia_id = conexion.execute(
            """
            INSERT INTO incidencias (usuario_id, observacion, prioridad)
            VALUES (?, ?, ?)
            """,
            (usuario_id, "Equipo averiado", "media"),
        ).lastrowid
    iniciar_sesion(cliente, "tecnico", "clave-tecnico")

    invalida = cliente.post(
        f"/tecnico/incidencias/{incidencia_id}",
        data={"categoria": "desconocida", "prioridad": "alta", "estado": "abierta"},
    )
    inexistente = cliente.post(
        "/tecnico/incidencias/99999",
        data={"categoria": "hardware", "prioridad": "alta", "estado": "abierta"},
    )

    assert invalida.status_code == 400
    assert inexistente.status_code == 404
    with conectar_db(ruta_db) as conexion:
        incidencia = conexion.execute(
            "SELECT categoria, prioridad, estado FROM incidencias WHERE id = ?",
            (incidencia_id,),
        ).fetchone()
    assert dict(incidencia) == {
        "categoria": "revisar",
        "prioridad": "media",
        "estado": "abierta",
    }
