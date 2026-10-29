import json
from types import SimpleNamespace

from openai import APIError

import clasificador


class ClienteSimulado:
    def __init__(self, respuestas):
        self.respuestas = iter(respuestas)
        self.llamadas = []
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self.crear_completado)
        )

    def crear_completado(self, **argumentos):
        self.llamadas.append(argumentos)
        respuesta = next(self.respuestas)
        if isinstance(respuesta, Exception):
            raise respuesta
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=respuesta),
                )
            ]
        )


def instalar_cliente(monkeypatch, cliente, **entorno):
    opciones_cliente = {}

    def crear_cliente(**opciones):
        opciones_cliente.update(opciones)
        return cliente

    monkeypatch.setattr(clasificador, "OpenAI", crear_cliente)
    for nombre, valor in entorno.items():
        monkeypatch.setenv(nombre, valor)
    return opciones_cliente


def test_clasificar_observacion_de_portatil_como_hardware(monkeypatch):
    cliente = ClienteSimulado(
        [
            json.dumps(
                {
                    "categoria": "hardware",
                    "prioridad": "alta",
                    "resumen": "El portátil no enciende",
                }
            )
        ]
    )
    opciones_cliente = instalar_cliente(
        monkeypatch,
        cliente,
        LMSTUDIO_URL="http://localhost:1234/v1",
        LMSTUDIO_MODEL="modelo-prueba",
    )

    resultado = clasificador.clasificar(
        "No arranca el portátil, no enciende ni el led"
    )

    assert resultado == {
        "categoria": "hardware",
        "prioridad": "alta",
        "resumen": "El portátil no enciende",
    }
    assert len(cliente.llamadas) == 1
    llamada = cliente.llamadas[0]
    assert llamada["model"] == "modelo-prueba"
    assert llamada["temperature"] == 0
    assert llamada["response_format"]["type"] == "json_schema"
    assert opciones_cliente == {
        "base_url": "http://localhost:1234/v1",
        "api_key": "lm-studio",
        "timeout": 10.0,
    }
    assert llamada["messages"][1]["content"].endswith(
        "No arranca el portátil, no enciende ni el led"
    )


def test_clasificar_reintenta_una_vez_ante_respuesta_invalida(monkeypatch):
    monkeypatch.delenv("LMSTUDIO_URL", raising=False)
    monkeypatch.delenv("LMSTUDIO_MODEL", raising=False)
    cliente = ClienteSimulado(
        [
            '{"categoria": "desconocida"}',
            json.dumps(
                {
                    "categoria": "software",
                    "prioridad": "media",
                    "resumen": "La aplicación se cierra al abrir",
                }
            ),
        ]
    )
    opciones_cliente = instalar_cliente(monkeypatch, cliente)

    resultado = clasificador.clasificar("La aplicación se cierra")

    assert resultado["categoria"] == "software"
    assert len(cliente.llamadas) == 2
    assert opciones_cliente["base_url"] == "http://localhost:1234/v1"
    assert cliente.llamadas[0]["model"] == "local-model"


def test_clasificar_devuelve_respaldo_tras_dos_respuestas_invalidas(monkeypatch):
    cliente = ClienteSimulado(["no es json", '{"categoria": "hardware"}'])
    instalar_cliente(monkeypatch, cliente)

    resultado = clasificador.clasificar("El equipo no funciona")

    assert resultado == clasificador.CLASIFICACION_PENDIENTE
    assert len(cliente.llamadas) == 2


def test_clasificar_devuelve_respaldo_si_lm_studio_no_responde(monkeypatch):
    cliente = ClienteSimulado(
        [APIError("servidor no disponible", request=None, body=None)]
    )
    instalar_cliente(monkeypatch, cliente)

    resultado = clasificador.clasificar("No hay conexión")

    assert resultado == clasificador.CLASIFICACION_PENDIENTE
    assert len(cliente.llamadas) == 1


def test_clasificar_rechaza_resumen_de_mas_de_quince_palabras(monkeypatch):
    resumen = " ".join(f"palabra{numero}" for numero in range(16))
    cliente = ClienteSimulado(
        [
            json.dumps(
                {
                    "categoria": "red",
                    "prioridad": "baja",
                    "resumen": resumen,
                }
            ),
            json.dumps(
                {
                    "categoria": "red",
                    "prioridad": "baja",
                    "resumen": "Falla intermitente de conexión",
                }
            ),
        ]
    )
    instalar_cliente(monkeypatch, cliente)

    resultado = clasificador.clasificar("La conexión falla a veces")

    assert resultado["resumen"] == "Falla intermitente de conexión"
    assert len(resultado["resumen"].split()) <= 15
    assert len(cliente.llamadas) == 2
