"""Proveedores LLM para el agente Customers.

`MockProvider` es determinista y se usa en desarrollo/pruebas.
`OpenAIProvider` implementa Chat Completions de OpenAI (compatible con Azure,
Groq, Together, vLLM, Ollama, etc.).

**Guardrail crítico**: el provider SOLO clasifica y redacta. El motor de reglas
y los datos reales son responsabilidad de `AgentService`.
"""
from __future__ import annotations

import enum
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("llm_provider")


class Intent(str, enum.Enum):
    SALUDO = "SALUDO"
    ESTADO_PEDIDO = "ESTADO_PEDIDO"
    RETRASO = "RETRASO"
    CONSULTA_GENERAL = "CONSULTA_GENERAL"
    ENTREGA_PARCIAL = "ENTREGA_PARCIAL"
    RECLAMO = "RECLAMO"
    DAÑO = "DAÑO"
    PRODUCTO_INCORRECTO = "PRODUCTO_INCORRECTO"
    PAGOS = "PAGOS"
    OTRO = "OTRO"


class Sentiment(str, enum.Enum):
    NEUTRO = "NEUTRO"
    POSITIVO = "POSITIVO"
    NEGATIVO = "NEGATIVO"


class TipoMensajeEntrante(str, enum.Enum):
    TEXT = "TEXT"
    MULTIMEDIA = "MULTIMEDIA"
    UNKNOWN = "UNKNOWN"


@dataclass
class ClassificationResult:
    intent: Intent
    sentiment: Sentiment
    confidence: float
    raw: dict | None = None
    provider_used: str = "mock"


class LLMProvider(ABC):
    name: str = "abstract"

    @abstractmethod
    def classify(self, message: str, context: dict | None = None) -> ClassificationResult:
        ...

    @abstractmethod
    def compose_response(self, intent: Intent, facts: dict) -> str:
        ...


# =========================================================================
# Mock (deterministic)
# =========================================================================
_MOCK_KEYWORDS: list[tuple[Intent, tuple[str, ...]]] = [
    (Intent.ENTREGA_PARCIAL, (
        "entrega parcial", "recibir antes", "solo una parte", "solo el primero",
        "solo los airpods", "solo el iphone", "puedo recibir por partes",
        "antes de todo", "por partes",
    )),
    (Intent.DAÑO, (
        "roto", "rota", "dañado", "dañada", "quebrado", "quebrada",
        "golpeado", "golpeada", "no funciona", "defectuoso", "defectuosa",
        "pantalla rota", "llego mal", "llegó mal",
    )),
    (Intent.PRODUCTO_INCORRECTO, (
        "no es lo que pedí", "no es lo que pedi", "producto equivocado",
        "modelo equivocado", "color equivocado", "no corresponde",
        "me enviaron otro", "me mandaron otro", "no es el correcto",
    )),
    (Intent.RECLAMO, (
        "reclamo", "queja", "pésimo", "pesimo", "estafa", "robo", "indignado",
        "molesto", "harto", "reembolso", "devolución", "devolucion",
        "quiero mi dinero", "pésimo servicio", "no me han", "nunca llegó",
    )),
    (Intent.PAGOS, (
        "pago", "pagar", "cuota", "cuotas", "factura", "cobro", "contrato",
        "financiamiento", "crédito", "credito", "yape", "plin", "transferencia",
    )),
    (Intent.RETRASO, (
        "retraso", "retrasado", "retrasada", "demora", "demorado",
        "por qué no llega", "por que no llega", "se ha pasado la fecha",
        "ya pasó la fecha", "ya paso la fecha", "tarde",
    )),
    (Intent.ESTADO_PEDIDO, (
        "dónde está", "donde esta", "estado de mi pedido", "cómo va", "como va",
        "cuándo llega", "cuando llega", "mi pedido", "mi compra",
        "tracking", "sigue mi pedido", "avance",
    )),
    (Intent.SALUDO, ("hola", "buenos días", "buenos dias", "buenas tardes",
                     "buenas noches", "qué tal", "que tal", "hi", "hello")),
]

_MOCK_NEGATIVE = (
    "pésimo", "pesimo", "estafa", "molesto", "indignado", "harto",
    "reembolso", "devolución", "devolucion", "nunca", "horrible", "asco",
    # Daño/defecto siempre implica malestar del cliente (coherente con el
    # prompt: "Producto dañado, roto, no funciona → DAÑO (sentiment NEGATIVO)")
    "roto", "rota", "dañado", "dañada", "quebrado", "quebrada",
    "golpeado", "golpeada", "no funciona", "defectuoso", "defectuosa",
)


class MockProvider(LLMProvider):
    name = "mock"

    def classify(self, message: str, context: dict | None = None) -> ClassificationResult:
        low = message.lower().strip()
        intent = Intent.CONSULTA_GENERAL
        for candidate, kws in _MOCK_KEYWORDS:
            if any(k in low for k in kws):
                intent = candidate
                break
        sentiment = (
            Sentiment.NEGATIVO
            if any(k in low for k in _MOCK_NEGATIVE)
            else Sentiment.NEUTRO
        )
        return ClassificationResult(
            intent=intent, sentiment=sentiment, confidence=0.95,
            raw={"provider": "mock"}, provider_used="mock",
        )

    def compose_response(self, intent: Intent, facts: dict) -> str:
        nombre = facts.get("cliente_nombre", "")
        if intent == Intent.SALUDO:
            return (
                f"Hola {nombre}, soy el asistente de Polux Import. "
                "Puedo consultarte el estado de tu pedido, ¿me indicas tu código?"
            )
        if intent in (Intent.ESTADO_PEDIDO, Intent.RETRASO):
            items = facts.get("items", [])
            if not items:
                return "No encontré ítems en tu pedido. ¿Podrías confirmarme tu código?"
            resumen = "; ".join(
                f"{it['descripcion']} — {it['estado']} "
                f"(próximo hito: {it['proximo_hito']}"
                + (f" el {it['fecha_prevista_proximo']}" if it.get('fecha_prevista_proximo') else "")
                + ")"
                for it in items
            )
            extra = ""
            if facts.get("imprevisto_activo"):
                extra = " Estamos atendiendo un imprevisto que puede afectar la entrega."
            if facts.get("retraso_critico"):
                extra += " Un asesor te contactará en breve con una actualización."
            return (
                f"Hola {nombre}, tu pedido {facts['pedido_codigo']} "
                f"está {facts['estado_pedido']}. Fecha prometida: {facts['fecha_prometida']}. "
                f"Avance: {resumen}.{extra}"
            )
        if intent == Intent.PAGOS:
            return (
                f"Hola {nombre}, las consultas sobre pagos, cuotas o contrato "
                "se atienden por otro canal. Un asesor te contactará."
            )
        return (
            f"Hola {nombre}, ¿en qué puedo ayudarte? "
            "Puedo consultarte el estado de tu pedido o pasarte con un asesor."
        )


# =========================================================================
# OpenAI-compatible
# =========================================================================
_CLASSIFY_SYSTEM = (
    "Eres un clasificador de mensajes de clientes de Polux Import "
    "(importador peruano de productos Apple).\n"
    "Devuelve SOLO un objeto JSON sin texto adicional, con este esquema:\n"
    '{"intent": "SALUDO|ESTADO_PEDIDO|RETRASO|CONSULTA_GENERAL|ENTREGA_PARCIAL|'
    'RECLAMO|DAÑO|PRODUCTO_INCORRECTO|PAGOS|OTRO", '
    '"sentiment": "NEUTRO|POSITIVO|NEGATIVO", "confidence": <float 0..1>}\n'
    "Reglas:\n"
    "- 'entrega parcial' o pedidos de recibir solo parte del pedido → ENTREGA_PARCIAL.\n"
    "- Producto dañado, roto, no funciona → DAÑO (sentiment NEGATIVO).\n"
    "- Producto equivocado, modelo/color incorrecto → PRODUCTO_INCORRECTO.\n"
    "- Queja explícita, insulto, amenaza, frustración → RECLAMO con sentiment NEGATIVO.\n"
    "- Preguntas sobre retrasos, demoras, 'por qué no llega' → RETRASO.\n"
    "- Consultas sobre pagos, cuotas, contrato → PAGOS.\n"
    "- Consultas sobre el estado/avance del pedido → ESTADO_PEDIDO.\n"
    "- Saludos sin otra consulta → SALUDO.\n"
    "- Cualquier otra consulta → CONSULTA_GENERAL u OTRO."
)


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self):
        s = get_settings()
        self.api_key = s.LLM_API_KEY
        self.base_url = s.LLM_BASE_URL.rstrip("/")
        self.model = s.LLM_MODEL
        self.timeout = s.AGENT_MAX_RESPONSE_SECONDS
        self.max_tokens = s.LLM_MAX_TOKENS

    def classify(self, message: str, context: dict | None = None) -> ClassificationResult:
        user = message
        if context:
            user = f"CONTEXTO:\n{json.dumps(context, ensure_ascii=False)}\n\nMENSAJE:\n{message}"
        content = self._chat(
            messages=[
                {"role": "system", "content": _CLASSIFY_SYSTEM},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            max_tokens=200,
        )
        data = _parse_json_robust(content)
        intent = _safe_intent(data.get("intent", "CONSULTA_GENERAL"))
        sentiment = _safe_sentiment(data.get("sentiment", "NEUTRO"))
        confidence = float(data.get("confidence", 0.5))
        return ClassificationResult(
            intent=intent, sentiment=sentiment, confidence=confidence,
            raw=data, provider_used="openai",
        )

    def compose_response(self, intent: Intent, facts: dict) -> str:
        system = (
            "Eres un redactor de mensajes de atención al cliente de Polux Import. "
            "Escribe en español, tono cordial y profesional, máximo 4 líneas. "
            "REGLAS ESTRICTAS:\n"
            "- Usa EXCLUSIVAMENTE los datos del bloque DATOS.\n"
            "- NO inventes fechas. Solo menciona fechas del bloque DATOS.\n"
            "- NO prometas fechas de entrega que no estén en DATOS.\n"
            "- NO menciones pagos, cuotas ni contratos.\n"
            "- NO ofrezcas entregas parciales.\n"
            "- NO repitas el teléfono ni el correo del cliente.\n"
            "- Si el cliente pide entrega parcial, reclama o reporta un daño, indica "
            "que un asesor lo contactará.\n"
        )
        user = (
            f"INTENCIÓN: {intent.value}\n"
            f"DATOS:\n{json.dumps(facts, ensure_ascii=False, indent=2)}\n\n"
            "Redacta el mensaje:"
        )
        return self._chat(
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            max_tokens=self.max_tokens,
        ).strip()

    def _chat(self, *, messages: list[dict], response_format: dict | None = None,
              max_tokens: int = 400) -> str:
        if not self.api_key:
            raise RuntimeError("LLM_API_KEY no configurada")
        body = {"model": self.model, "messages": messages,
                "temperature": 0.2, "max_tokens": max_tokens}
        if response_format:
            body["response_format"] = response_format
        with httpx.Client(timeout=self.timeout) as client:
            r = client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}",
                         "Content-Type": "application/json"},
                json=body,
            )
            r.raise_for_status()
            data = r.json()
        return data["choices"][0]["message"]["content"]


# =========================================================================
# Factory
# =========================================================================
def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    provider = settings.LLM_PROVIDER.lower()
    if provider == "openai":
        if not settings.LLM_API_KEY:
            logger.warning("LLM_API_KEY vacío; se usará MockProvider")
            return MockProvider()
        return OpenAIProvider()
    return MockProvider()


# =========================================================================
# Helpers robustos (parsing, normalización)
# =========================================================================
_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def _parse_json_robust(content: str) -> dict:
    """Intenta `json.loads` directo; si falla, extrae el primer objeto {...}."""
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        m = _JSON_OBJECT.search(content)
        if not m:
            logger.warning("llm_json_unparseable content=%r", content[:200])
            return {}
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            logger.warning("llm_json_unparseable_after_extract content=%r", content[:200])
            return {}


def _safe_intent(value: object) -> Intent:
    try:
        return Intent(str(value))
    except ValueError:
        return Intent.OTRO


def _safe_sentiment(value: object) -> Sentiment:
    try:
        return Sentiment(str(value))
    except ValueError:
        return Sentiment.NEUTRO


_DATE_DDMMYYYY = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
_DATE_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_PHONE = re.compile(r"\+?\d{9,15}")


def extract_dates(text: str) -> list[str]:
    """Fechas normalizadas a dd/mm/yyyy para comparar contra `valid_dates`."""
    found: list[str] = []
    for m in _DATE_DDMMYYYY.finditer(text):
        found.append(f"{int(m.group(1)):02d}/{int(m.group(2)):02d}/{m.group(3)}")
    for m in _DATE_ISO.finditer(text):
        found.append(f"{int(m.group(3)):02d}/{int(m.group(2)):02d}/{m.group(1)}")
    return found


def contains_pii(text: str, *, phone: str | None = None, email: str | None = None) -> bool:
    """Detecta si la respuesta expone el teléfono o email del cliente."""
    if email and email.lower() in text.lower():
        return True
    if phone:
        digits = "".join(c for c in phone if c.isdigit())
        if digits and digits in "".join(c for c in text if c.isdigit()):
            return True
    for m in _PHONE.finditer(text):
        # solo consideramos PII si parece teléfono de contacto (evita años, precios)
        if len(m.group(0).lstrip("+")) >= 10:
            return True
    return False