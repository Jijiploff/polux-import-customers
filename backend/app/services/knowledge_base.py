"""Base de conocimiento pequeña y verificable para consultas generales."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re
import unicodedata


_DOCUMENT_PATH = Path(__file__).resolve().parents[1] / "knowledge" / "empresa.md"


def _normalizar(texto: str) -> str:
    normalizado = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in normalizado if not unicodedata.combining(c))


@lru_cache(maxsize=1)
def _documento() -> str:
    try:
        return _DOCUMENT_PATH.read_text(encoding="utf-8")
    except OSError:
        return ""


_RESPUESTAS: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        ("que puedes hacer", "que cosas puedes hacer", "funciones", "ayuda"),
        "Puedo consultar el estado y avance de tu pedido, informarte sobre sus próximos hitos y detectar si necesita atención. También puedo responder dudas generales sobre Polux Import. Para pagos, reclamos, daños o cambios, te comunico con un asesor.",
    ),
    (
        ("donde puedo recoger", "recoger mi pedido", "punto de recojo", "recoger"),
        "La modalidad de entrega y el punto de recojo dependen de tu pedido. Envíame tu código de pedido para revisar la información disponible; si necesitas coordinar un cambio, un asesor te ayudará.",
    ),
    (
        ("horario", "atienden", "atencion al cliente", "contactar un asesor"),
        "Puedo orientarte sobre tu pedido y registrar tu consulta. Si necesitas una gestión que requiere validación humana, la derivaré a un asesor de Polux Import.",
    ),
    (
        ("hola", "buenas", "buenos dias", "buenas tardes", "buenas noches"),
        "Hola, soy el asistente de Polux Import. Puedo consultar el estado de tu pedido y responder dudas generales. ¿Qué necesitas saber?",
    ),
)


def respuesta(texto: str) -> str | None:
    """Devuelve una respuesta aprobada para una pregunta general conocida."""
    consulta = _normalizar(texto)
    for claves, respuesta_texto in _RESPUESTAS:
        if any(re.search(rf"\b{re.escape(_normalizar(clave))}\b", consulta) for clave in claves):
            return respuesta_texto
    return None


def contexto() -> str:
    """Contenido documental que puede consultar un proveedor LLM."""
    return _documento()


def es_consulta_conocida(texto: str) -> bool:
    return respuesta(texto) is not None
