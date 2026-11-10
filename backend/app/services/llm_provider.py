"""Proveedores LLM para el agente Customers.

`MockProvider` es determinista y se usa en desarrollo/pruebas.
`OpenAIProvider` implementa Chat Completions de OpenAI (compatible con Azure,
Groq, Together, vLLM, Ollama, **Gemini** vía `generativelanguage.googleapis.com/v1beta/openai`).

**Guardrail crítico**: el provider SOLO clasifica y redacta. El motor de reglas
y los datos reales son responsabilidad de `AgentService`.

**Cortesía con la cuota del proveedor** (`RateGuard`): los planes gratuitos
limitan ~5 llamadas/minuto (RPM) y ~20/día (RPD). El provider nunca supera el
RPM (ventana deslizante), entra en reposo automático tras un 429 y en
cualquier fallo se propaga el error para que `AgentService` use el motor local
(mock): la atención al cliente nunca se corta.
"""
from __future__ import annotations

import enum
import json
import re
import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("llm_provider")


class LLMNoDisponible(RuntimeError):
    """El LLM remoto no está disponible (cuota, tiempo o error del proveedor).

    `AgentService` lo captura y responde con el motor local (mock).
    """


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
class RateGuard:
    """Cortesía con los límites del proveedor (RPM / reposo por 429).

    - Ventana deslizante de 60 s: no se hacen más de `LLM_RPM` llamadas por
      minuto (classify y compose comparten el contador).
    - Tras un 429 (cuota RPM o RPD agotada) entra en reposo durante
      `LLM_COOLDOWN_SECONDS` y NO se vuelve a llamar: no tiene sentido
      reintentar contra una cuota ya consumida.
    """

    def __init__(self, ventana_segundos: float = 60.0):
        self._lock = threading.Lock()
        self._ventana = ventana_segundos
        self._llamadas: deque[float] = deque()
        self._reposo_hasta = 0.0

    def intentar(self, rpm: int) -> str | None:
        """Reserva una llamada. Devuelve `None` si se permite o el motivo de bloqueo."""
        with self._lock:
            now = time.monotonic()
            if now < self._reposo_hasta:
                return "reposo_por_429"
            while self._llamadas and now - self._llamadas[0] > self._ventana:
                self._llamadas.popleft()
            if len(self._llamadas) >= max(1, rpm):
                return "rpm_excedido"
            self._llamadas.append(now)
            return None

    def reposo(self, segundos: float) -> None:
        """Entra en reposo (p. ej. 60 s tras un 429) y limpia la ventana."""
        with self._lock:
            self._reposo_hasta = time.monotonic() + max(0.0, segundos)
            self._llamadas.clear()

    @property
    def en_reposo(self) -> bool:
        with self._lock:
            return time.monotonic() < self._reposo_hasta


# Estado compartido entre instancias del provider (se crea uno por mensaje).
_guard = RateGuard()

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
        self.timeout = s.LLM_TIMEOUT_SECONDS        # presupuesto TOTAL (reintentos incluidos)
        self.max_tokens = s.LLM_MAX_TOKENS
        self.retries = max(0, s.LLM_MAX_RETRIES)
        self.rpm = max(1, s.LLM_RPM)
        self.cooldown = s.LLM_COOLDOWN_SECONDS
        self.fallback_model = (s.LLM_MODEL_FALLBACK or "").strip()
        if "generativelanguage.googleapis.com" in self.base_url:
            self.name = "gemini"

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
            max_tokens=500,
        )
        data = _parse_json_robust(content)
        intent = _safe_intent(data.get("intent", "CONSULTA_GENERAL"))
        sentiment = _safe_sentiment(data.get("sentiment", "NEUTRO"))
        confidence = _safe_confidence(data.get("confidence"))
        return ClassificationResult(
            intent=intent, sentiment=sentiment, confidence=confidence,
            raw=data, provider_used=self.name,
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
        """Una llamada a Chat Completions, frugal con la cuota del proveedor.

        Orden de protección: reposo por 429 → ventana RPM → 1 reintento ante
        5xx → presupuesto total de tiempo. Cualquier fallo lanza
        `LLMNoDisponible` (o el error de HTTP) para que el caller use el motor
        local: nunca se reintenta contra una cuota agotada.
        """
        if not self.api_key:
            raise LLMNoDisponible("LLM_API_KEY no configurada")

        motivo = _guard.intentar(self.rpm)
        if motivo:
            # No se gasta ni una llamada más: el motor local responde.
            raise LLMNoDisponible(f"llm_limitado motivo={motivo} rpm={self.rpm}")

        body = {"model": self.model, "messages": messages,
                "temperature": 0.2, "max_tokens": max_tokens}
        if response_format:
            body["response_format"] = response_format
        headers = {"Authorization": f"Bearer {self.api_key}",
                   "Content-Type": "application/json"}
        url = f"{self.base_url}/chat/completions"

        deadline = time.monotonic() + self.timeout
        # intentos = reintento transitorio + 1 intento extra si hay modelo respaldo
        intentos = self.retries + 1 + (1 if self.fallback_model else 0)
        ultimo_error: Exception | None = None
        sin_response_format = False
        en_modelo_respaldo = False

        for intento in range(1, intentos + 1):
            restante = deadline - time.monotonic()
            if restante < 1.0:
                break
            try:
                with httpx.Client(timeout=restante) as client:
                    r = client.post(url, headers=headers, json=body)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                logger.warning("llm_transport_error intento=%s/%s err=%s",
                               intento, intentos, exc)
                ultimo_error = exc
                continue

            if r.status_code == 429:
                # Cuota RPM/RPD agotada: reposo, sin reintentos (no gastar más).
                _guard.reposo(self.cooldown)
                logger.warning("llm_429_reposo segundos=%s", self.cooldown)
                raise LLMNoDisponible("429 del proveedor (cuota RPM/RPD); reposo activo")

            if r.status_code >= 500:
                # Alta demanda en el modelo principal → se prueba el modelo
                # respaldo una vez antes de caer al motor local.
                if (not en_modelo_respaldo and self.fallback_model
                        and self.fallback_model != body.get("model")):
                    en_modelo_respaldo = True
                    body["model"] = self.fallback_model
                    logger.info("llm_modelo_respaldo primary=%s fallback=%s status=%s",
                                self.model, self.fallback_model, r.status_code)
                else:
                    ultimo_error = RuntimeError(f"HTTP {r.status_code} del proveedor LLM")
                    logger.warning("llm_5xx intento=%s/%s status=%s model=%s",
                                   intento, intentos, r.status_code, body.get("model"))
                if intento < intentos:
                    time.sleep(min(1.0 * intento, max(restante, 0.0)))
                continue

            if r.status_code == 400 and response_format is not None and not sin_response_format:
                # Algún modelo no admite response_format: se reintenta sin él
                # y el JSON se extrae con _parse_json_robust.
                logger.info("llm_sin_response_format model=%s", self.model)
                sin_response_format = True
                body.pop("response_format", None)
                continue

            try:
                r.raise_for_status()
            except httpx.HTTPStatusError as exc:
                # 4xx definitivos (auth, petición inválida): al motor local.
                raise LLMNoDisponible(f"HTTP {r.status_code}: {exc}") from exc

            try:
                data = r.json()
            except ValueError as exc:
                raise LLMNoDisponible("Respuesta LLM no es JSON") from exc
            try:
                return data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as exc:
                raise LLMNoDisponible("Respuesta LLM sin contenido") from exc

        raise ultimo_error or LLMNoDisponible("El LLM no respondió dentro del tiempo")


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
        p = OpenAIProvider()
        logger.info("llm_provider_activo name=%s model=%s rpm=%s",
                    p.name, p.model, p.rpm)
        return p
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


def _safe_confidence(value: object, default: float = 0.5) -> float:
    """Confianza 0..1 aunque el modelo devuelva texto, porcentaje o algo raro."""
    try:
        conf = float(value)
    except (TypeError, ValueError):
        return default
    if conf > 1.0:            # a veces devuelve 95 en vez de 0.95
        conf = conf / 100.0
    return min(max(conf, 0.0), 1.0)


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