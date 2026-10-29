import os
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

from werkzeug.security import generate_password_hash


DB_PATH = Path(__file__).resolve().with_name("incidencias.db")


@contextmanager
def conectar_db(ruta: Path = DB_PATH) -> Iterator[sqlite3.Connection]:
    conexion = sqlite3.connect(ruta)
    conexion.row_factory = sqlite3.Row
    conexion.execute("PRAGMA foreign_keys = ON")
    try:
        yield conexion
        conexion.commit()
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def inicializar_db(
    ruta: Path = DB_PATH,
    entorno: Mapping[str, str] | None = None,
) -> None:
    variables = os.environ if entorno is None else entorno
    claves = {
        "usuario": variables.get("INCIDENCIAS_USUARIO_PASSWORD", ""),
        "tecnico": variables.get("INCIDENCIAS_TECNICO_PASSWORD", ""),
    }
    faltantes = [rol for rol, clave in claves.items() if not clave]
    if faltantes:
        nombres = ", ".join(
            f"INCIDENCIAS_{rol.upper()}_PASSWORD" for rol in faltantes
        )
        raise RuntimeError(
            f"Configura las variables de entorno requeridas: {nombres}"
        )

    with conectar_db(ruta) as conexion:
        conexion.executescript(
            """
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY,
                nombre_usuario TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                rol TEXT NOT NULL CHECK (rol IN ('usuario', 'tecnico'))
            );

            CREATE TABLE IF NOT EXISTS incidencias (
                id INTEGER PRIMARY KEY,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario_id INTEGER NOT NULL REFERENCES usuarios (id),
                observacion TEXT NOT NULL,
                categoria TEXT NOT NULL DEFAULT 'revisar'
                    CHECK (categoria IN ('hardware', 'software', 'red', 'cuenta', 'revisar')),
                prioridad TEXT NOT NULL
                    CHECK (prioridad IN ('baja', 'media', 'alta')),
                resumen TEXT NOT NULL DEFAULT '',
                estado TEXT NOT NULL DEFAULT 'abierta'
                    CHECK (estado IN ('abierta', 'en curso', 'resuelta'))
            );

            CREATE INDEX IF NOT EXISTS idx_incidencias_usuario_id
                ON incidencias (usuario_id);
            """
        )
        for nombre_usuario, clave in claves.items():
            conexion.execute(
                """
                INSERT INTO usuarios (nombre_usuario, password_hash, rol)
                VALUES (?, ?, ?)
                ON CONFLICT (nombre_usuario) DO NOTHING
                """,
                (nombre_usuario, generate_password_hash(clave), nombre_usuario),
            )
