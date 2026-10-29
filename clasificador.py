import json
import logging
import os
from typing import Any

from openai import APIError, OpenAI


LOGGER = logging.getLogger(__name__)
URL_POR_DEFECTO = "http://localhost:1234/v1"
MODELO_POR_DEFECTO = "local-model"
CATEGORIAS = ("hardware", "software", "red", "cuenta")
PRIORIDADES = ("baja", "media", "alta")
CLASIFICACION_PENDIENTE = {
    "categoria": "revisar",
    "prioridad": "media",
    "resumen": "Pendiente de clasificación",
}

ESQUEMA_CLASIFICACION = {
    "type": "json_schema",
    "json_schema": {
        "name": "clasificacion_incidencia",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "categoria": {"type": "string", "enum": list(CATEGORIAS)},
                "prioridad": {"type": "string", "enum": list(PRIORIDADES)},
                "resumen": {"type": "string"},
            },
            "required": ["categoria", "prioridad", "resumen"],
            "additionalProperties": False,
        },
    },
}

INSTRUCCIONES = (
    "Clasifica incidencias informáticas. Elige categoria entre hardware, "
    "software, red y cuenta; prioridad entre baja, media y alta. "
    "Resume la observación en un máximo de 15 palabras. "
    "Un equipo que no arranca o no enciende es hardware. "
    "Devuelve únicamente el objeto que cumple el esquema."
)


def _validar_clasificacion(contenido: str | None) -> dict[str, str]:
    datos: Any = json.loads(contenido)
    if not isinstance(datos, dict) or set(datos) != {
        "categoria",
        "prioridad",
        "resumen",
    }:
        raise ValueError("La respuesta no contiene exactamente los campos requeridos")

    categoria = datos["categoria"]
    prioridad = datos["prioridad"]
    resumen = datos["resumen"]
    if categoria not in CATEGORIAS:
        raise ValueError("La categoría no es válida")
    if prioridad not in PRIORIDADES:
        raise ValueError("La prioridad no es válida")
    if not isinstance(resumen, str) or not resumen.strip():
        raise ValueError("El resumen debe ser texto no vacío")

    resumen = resumen.strip()
    if len(resumen.split()) > 15:
        raise ValueError("El resumen supera las 15 palabras")

    return {
        "categoria": categoria,
        "prioridad": prioridad,
        "resumen": resumen,
    }


def clasificar(observacion: str) -> dict[str, str]:
    cliente = OpenAI(
        base_url=os.getenv("LMSTUDIO_URL", URL_POR_DEFECTO),
        api_key="lm-studio",
        timeout=10.0,
    )
    modelo = os.getenv("LMSTUDIO_MODEL", MODELO_POR_DEFECTO)

    for intento in range(2):
        try:
            respuesta = cliente.chat.completions.create(
                model=modelo,
                messages=[
                    {"role": "system", "content": INSTRUCCIONES},
                    {"role": "user", "content": f"Observación: {observacion}"},
                ],
                response_format=ESQUEMA_CLASIFICACION,
                temperature=0,
            )
        except APIError as error:
            LOGGER.warning("No se pudo contactar con LM Studio: %s", error)
            break

        try:
            contenido = respuesta.choices[0].message.content
            return _validar_clasificacion(contenido)
        except (AttributeError, IndexError, TypeError, ValueError) as error:
            LOGGER.warning(
                "Respuesta de clasificación no válida (intento %d de 2): %s",
                intento + 1,
                error,
            )

    return CLASIFICACION_PENDIENTE.copy()
