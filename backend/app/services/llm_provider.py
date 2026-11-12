"""Proveedores LLM para el agente Customers.

`MockProvider` es determinista y se usa en desarrollo/pruebas.
`OpenAIProvider` implementa Chat Completions de OpenAI (compatible con Azure,
Groq, Together, vLLM, Ollama, **Gemini** vía `generativelanguage.googleapis.com/v1beta/openai`).

**Guardrail crítico**: el provider SOLO clasifica y redacta. El motor de reglas
y los datos reales son responsabilidad de `AgentService`.

**Cortesía con la cuota del proveedor** (`RateGuard`): Gemini free tier limita
por modelo las llamadas por minuto (RPM), los tokens por minuto (TPM) y las
llamadas por día (RPD). El provider reserva cuota por modelo en una ventana
deslizante, entra en reposo tras un 429 y prueba el modelo de respaldo antes de
caer al motor local. Cualquier fallo se propaga como `LLMNoDisponible` para que
`AgentService` use el motor local (mock): la atención al cliente nunca se corta.
"""
from __future__ import annotations

import enum
import json
import re
import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

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
    model_used: str = ""


class LLMProvider(ABC):
    name: str = "abstract"

    @abstractmethod
    def classify(self, message: str, context: dict | None = None) -> ClassificationResult:
        ...

    @abstractmethod
    def compose_response(self, intent: Intent, facts: dict) -> str:
        ...

    def status(self) -> dict:
        """Estado mínimo del motor (las implementaciones reales lo amplían)."""
        return {"provider": self.name, "model": self.name, "limits": {}, "usage": {}}


def get_telegram_llm_provider() -> LLMProvider:
    """Selecciona el motor conversacional de Telegram sin afectar WhatsApp."""
    settings = get_settings()
    if settings.TELEGRAM_MODE.lower() != "ai":
        return MockProvider()
    return get_llm_provider("gemini")


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
            raw={"provider": "mock"}, provider_used="mock", model_used="mock",
        )

    def compose_response(self, intent: Intent, facts: dict) -> str:
        if facts.get("knowledge_answer"):
            return str(facts["knowledge_answer"])
        nombre = facts.get("cliente_nombre", "")
        if facts.get("sin_pedido"):
            return (
                f"¡Hola{f' {nombre}' if nombre else ''}! 👋 Soy el asistente de Polux Import. "
                "Envíame tu código de pedido junto con tu DNI para vincularlo, "
                "o dime en qué necesitas ayuda."
            )
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
@dataclass
class _EstadoCuotaModelo:
    """Consumo de un modelo concreto (la cuota de Gemini es por modelo)."""

    dia: date
    llamadas_minuto: deque[float] = field(default_factory=deque)
    tokens_minuto: deque[tuple[float, int]] = field(default_factory=deque)
    llamadas_dia: int = 0
    tokens_dia: int = 0
    reposo_hasta: float = 0.0


class RateGuard:
    """Cortesía con los límites del proveedor por modelo.

    Gemini free tier limita RPM, TPM y RPD **por modelo**. Este guard:
    - usa una ventana deslizante de 60 s para RPM y TPM;
    - lleva un contador diario UTC para RPD;
    - entra en reposo solo para el modelo que devolvió 429, de modo que el
      modelo de respaldo puede seguir atendiendo;
    - opcionalmente persiste el consumo diario en JSON para sobrevivir a
      reinicios del proceso (``LLM_QUOTA_STATE_PATH``).
    """

    def __init__(self, ventana_segundos: float = 60.0,
                 state_path: str | None = None):
        self._lock = threading.Lock()
        self._ventana = max(0.001, ventana_segundos)
        self._modelos: dict[str, _EstadoCuotaModelo] = {}
        self._state_path = Path(state_path) if state_path else None
        self._cargar()

    @staticmethod
    def _hoy() -> date:
        return datetime.now(timezone.utc).date()

    def _estado(self, modelo: str) -> _EstadoCuotaModelo:
        hoy = self._hoy()
        estado = self._modelos.get(modelo)
        if estado is None or estado.dia != hoy:
            estado = _EstadoCuotaModelo(dia=hoy)
            self._modelos[modelo] = estado
        return estado

    @staticmethod
    def _limpiar_ventana(estado: _EstadoCuotaModelo, ahora: float,
                         ventana: float) -> None:
        while estado.llamadas_minuto and ahora - estado.llamadas_minuto[0] > ventana:
            estado.llamadas_minuto.popleft()
        while estado.tokens_minuto and ahora - estado.tokens_minuto[0][0] > ventana:
            estado.tokens_minuto.popleft()

    def intentar(
        self,
        rpm: int,
        tpm: int | None = None,
        rpd: int | None = None,
        tokens: int = 0,
        modelo: str = "default",
        ahora: float | None = None,
    ) -> str | None:
        """Reserva una llamada en el modelo indicado.

        Devuelve ``None`` si se permite o el motivo de bloqueo
        (``rpm_excedido``, ``tpm_excedido``, ``rpd_excedido`` o
        ``reposo_por_429``). No muta el contador cuando bloquea.
        """
        with self._lock:
            now = time.monotonic() if ahora is None else ahora
            estado = self._estado(modelo)
            if now < estado.reposo_hasta:
                return "reposo_por_429"
            self._limpiar_ventana(estado, now, self._ventana)

            if len(estado.llamadas_minuto) >= max(1, rpm):
                return "rpm_excedido"

            tokens = max(0, int(tokens))
            tokens_ventana = sum(t for _, t in estado.tokens_minuto)
            if tpm and tokens_ventana + tokens > tpm:
                return "tpm_excedido"
            if rpd and estado.llamadas_dia >= rpd:
                return "rpd_excedido"

            estado.llamadas_minuto.append(now)
            estado.tokens_minuto.append((now, tokens))
            estado.llamadas_dia += 1
            estado.tokens_dia += tokens
            self._guardar()
            return None

    def reposo(self, segundos: float, modelo: str = "default") -> None:
        """Marca un modelo en reposo (p. ej. 60 s tras un 429)."""
        with self._lock:
            estado = self._estado(modelo)
            estado.reposo_hasta = time.monotonic() + max(0.0, segundos)

    @property
    def en_reposo(self) -> bool:
        with self._lock:
            now = time.monotonic()
            return any(now < e.reposo_hasta for e in self._modelos.values())

    def uso_modelo(self, modelo: str = "default") -> dict:
        """Consumo actual de un modelo (para diagnóstico/``/agent/provider``)."""
        with self._lock:
            estado = self._estado(modelo)
            now = time.monotonic()
            self._limpiar_ventana(estado, now, self._ventana)
            return {
                "llamadas_minuto": len(estado.llamadas_minuto),
                "tokens_minuto": sum(t for _, t in estado.tokens_minuto),
                "llamadas_dia": estado.llamadas_dia,
                "tokens_dia": estado.tokens_dia,
                "en_reposo": now < estado.reposo_hasta,
                "reposo_restante_segundos": round(
                    max(0.0, estado.reposo_hasta - now), 1
                ),
            }

    def uso(self) -> dict[str, dict]:
        with self._lock:
            modelos = sorted(self._modelos)
        return {modelo: self.uso_modelo(modelo) for modelo in modelos}

    # ------------------------------------------------------------------
    # Persistencia opcional del contador diario (RPD)
    # ------------------------------------------------------------------
    def _cargar(self) -> None:
        if not self._state_path or not self._state_path.exists():
            return
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
            if data.get("fecha") != str(self._hoy()):
                return
            for modelo, item in (data.get("modelos") or {}).items():
                self._modelos[str(modelo)] = _EstadoCuotaModelo(
                    dia=self._hoy(),
                    llamadas_dia=max(0, int(item.get("llamadas_dia", 0))),
                    tokens_dia=max(0, int(item.get("tokens_dia", 0))),
                )
        except (OSError, ValueError, TypeError) as exc:
            logger.warning("llm_quota_state_no_leido err=%s", exc)

    def _guardar(self) -> None:
        if not self._state_path:
            return
        hoy = self._hoy()
        data = {
            "fecha": str(hoy),
            "modelos": {
                modelo: {
                    "llamadas_dia": estado.llamadas_dia,
                    "tokens_dia": estado.tokens_dia,
                }
                for modelo, estado in self._modelos.items()
                if estado.dia == hoy
            },
        }
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._state_path.with_suffix(self._state_path.suffix + ".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self._state_path)
        except OSError as exc:
            logger.warning("llm_quota_state_no_guardado err=%s", exc)


# Estado compartido entre instancias del provider (se crea uno por mensaje).
_guard = RateGuard(
    state_path=(get_settings().LLM_QUOTA_STATE_PATH or "").strip() or None
)

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


def _estimar_tokens(messages: list[dict], max_tokens: int) -> int:
    """Estimación conservadora para TPM sin gastar una llamada extra.

    Gemini ronda 4 caracteres por token, pero el español y el JSON pueden
    consumir más. Usamos 3 caracteres/token, sumamos el máximo de salida y un
    margen por mensaje. Sobreestimar es preferible a superar el TPM real.
    """
    texto = "".join(str(m.get("content") or "") for m in messages)
    entrada = max(1, (len(texto) + 2) // 3)
    return entrada + max(0, int(max_tokens)) + 32 * len(messages) + 64


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self):
        s = get_settings()
        self.api_key = s.LLM_API_KEY
        self.base_url = s.LLM_BASE_URL.rstrip("/")
        self.model = (s.LLM_MODEL or "").strip()
        self.timeout = s.LLM_TIMEOUT_SECONDS        # presupuesto TOTAL (reintentos incluidos)
        self.max_tokens = s.LLM_MAX_TOKENS
        self.retries = max(0, s.LLM_MAX_RETRIES)
        self.rpm = max(1, s.LLM_RPM)
        self.tpm = max(0, s.LLM_TPM)
        self.rpd = max(0, s.LLM_RPD)
        self.cooldown = s.LLM_COOLDOWN_SECONDS
        # El respaldo admite una lista separada por comas; se prueba en orden.
        fallbacks = [m.strip() for m in (s.LLM_MODEL_FALLBACK or "").split(",")]
        if "generativelanguage.googleapis.com" in self.base_url:
            self.name = "gemini"
            # Garantiza por lo menos 3 alternativas probadas antes del fallback determinista
            for cand in ("gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-flash-lite-latest", "gemini-3.6-flash"):
                if cand != self.model and cand not in fallbacks:
                    fallbacks.append(cand)
                if len(fallbacks) >= 3:
                    break

        self.fallback_models = [m for m in fallbacks if m and m != self.model]




        self.fallback_model = self.fallback_models[0] if self.fallback_models else ""
        self.model_chain = list(dict.fromkeys([self.model, *self.fallback_models]))
        self.last_model = self.model
        if "generativelanguage.googleapis.com" in self.base_url:
            self.name = "gemini"

    def status(self) -> dict:
        return {
            "provider": self.name,
            "model": self.model,
            "fallback_models": list(self.fallback_models),
            "limits": {
                "rpm": self.rpm,
                "tpm": self.tpm,
                "rpd": self.rpd,
                "cooldown_seconds": self.cooldown,
            },
            "usage": {
                modelo: _guard.uso_modelo(modelo) for modelo in self.model_chain
            },
        }

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
            raw=data, provider_used=self.name, model_used=self.last_model,
        )

    def compose_response(self, intent: Intent, facts: dict) -> str:
        system = (
            "Eres un asesor conversacional de Polux Import para Telegram. "
            "Escribe en español, tono cálido, humano y semi-formal, en 2 a 4 líneas. "
            "Usa solo el nombre de pila del cliente, nunca una firma. "
            "REGLAS ESTRICTAS:\n"
            "- Usa EXCLUSIVAMENTE los datos del bloque DATOS.\n"
            "- NO inventes fechas. Solo menciona fechas del bloque DATOS.\n"
            "- NO prometas fechas de entrega que no estén en DATOS.\n"
            "- Si falta un dato, dilo con honestidad y ofrece escalarlo.\n"
            "- Nunca decidas excepciones, descuentos, cambios, reembolsos o entregas parciales.\n"
            "- Ante molestia, daño o reclamo, reconoce la emoción antes del siguiente paso.\n"
            "- Siempre termina con una pregunta o siguiente paso concreto.\n"
            "- Nunca uses frases como 'según el sistema', 'le informamos' o 'saludos cordiales'.\n"
            "- Si DATOS indica sin_pedido=true, pide el código de pedido y el DNI para vincularlo.\n"
        )
        user = (
            f"INTENCIÓN: {intent.value}\n"
            f"DATOS:\n{json.dumps(facts, ensure_ascii=False, indent=2)}\n\n"
            f"CONOCIMIENTO_EMPRESA:\n{facts.get('knowledge_context', '')}\n\n"
            "Redacta el mensaje:"
        )
        return self._chat(
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            max_tokens=self.max_tokens,
        ).strip()

    def _chat(self, *, messages: list[dict], response_format: dict | None = None,
              max_tokens: int = 400) -> str:
        """Llama a Chat Completions con cuota por modelo y respaldo ordenado.

        Protecciones, en orden:
        1. reserva RPM/TPM/RPD **del modelo** antes de cada intento;
        2. 429 → reposo de ese modelo y se prueba el siguiente;
        3. 404 / 400 / 5xx → se prueba el siguiente modelo de la cadena;
        4. 401/403 → error de credenciales (no se insiste);
        5. cualquier fallo final lanza `LLMNoDisponible` para que
           `AgentService` responda con el motor local.
        """
        if not self.api_key:
            raise LLMNoDisponible("LLM_API_KEY no configurada")
        if not self.model_chain:
            raise LLMNoDisponible("LLM_MODEL no configurado")

        tokens_estimados = _estimar_tokens(messages, max_tokens)
        headers = {"Authorization": f"Bearer {self.api_key}",
                   "Content-Type": "application/json"}
        url = f"{self.base_url}/chat/completions"
        deadline = time.monotonic() + self.timeout
        ultimo_error: Exception | None = None

        for model in self.model_chain:
            if time.monotonic() >= deadline:
                break
            # Un intento normal + reintentos transitorios. Si el modelo no
            # acepta response_format, se añade un intento sin él.
            intentos = self.retries + 1 + (1 if response_format else 0)
            formato_actual = response_format

            for intento in range(intentos):
                restante = deadline - time.monotonic()
                if restante < 1.0:
                    break

                motivo = _guard.intentar(
                    rpm=self.rpm, tpm=self.tpm, rpd=self.rpd,
                    tokens=tokens_estimados, modelo=model,
                )
                if motivo:
                    ultimo_error = LLMNoDisponible(
                        f"llm_limitado model={model} motivo={motivo} "
                        f"rpm={self.rpm} tpm={self.tpm} rpd={self.rpd}"
                    )
                    logger.warning(
                        "llm_limitado model=%s motivo=%s rpm=%s tpm=%s rpd=%s",
                        model, motivo, self.rpm, self.tpm, self.rpd,
                    )
                    break  # modelo sin cuota: se prueba el respaldo

                body = {
                    "model": model,
                    "messages": messages,
                    "temperature": 0.2,
                    "max_tokens": max_tokens,
                }
                if formato_actual:
                    body["response_format"] = formato_actual

                try:
                    tiempo_llamada = min(7.0, max(restante, 2.0))
                    with httpx.Client(timeout=tiempo_llamada) as client:
                        r = client.post(url, headers=headers, json=body)
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    ultimo_error = exc
                    logger.warning(
                        "llm_transport_error model=%s intento=%s/%s err=%s",
                        model, intento + 1, intentos, exc,
                    )
                    if len(self.model_chain) > 1:
                        logger.warning("llm_fallo_modelo model=%s -> saltando a siguiente modelo de respaldo", model)
                        break
                    if intento + 1 < intentos:
                        time.sleep(min(1.0, max(restante, 0.0)))
                    continue

                if r.status_code == 429:
                    # Cuota de ESTE modelo agotada: reposo y siguiente modelo.
                    _guard.reposo(self.cooldown, modelo=model)
                    ultimo_error = LLMNoDisponible(
                        f"429 del proveedor model={model} (cuota RPM/TPM/RPD)"
                    )
                    logger.warning(
                        "llm_429_reposo model=%s segundos=%s",
                        model, self.cooldown,
                    )
                    break

                if r.status_code in (401, 403):
                    raise LLMNoDisponible(
                        f"HTTP {r.status_code}: credenciales del proveedor rechazadas"
                    )

                if r.status_code == 404:
                    ultimo_error = LLMNoDisponible(
                        f"HTTP 404: modelo {model} no disponible"
                    )
                    logger.warning("llm_modelo_no_disponible model=%s", model)
                    break

                if r.status_code == 400 and formato_actual is not None:
                    # Algunos modelos no admiten response_format. Se reintenta
                    # sin él y el JSON se extrae con _parse_json_robust.
                    logger.info("llm_sin_response_format model=%s", model)
                    formato_actual = None
                    continue

                if r.status_code >= 500:
                    ultimo_error = LLMNoDisponible(
                        f"HTTP {r.status_code} del proveedor LLM model={model}"
                    )
                    logger.warning(
                        "llm_5xx model=%s intento=%s/%s status=%s",
                        model, intento + 1, intentos, r.status_code,
                    )
                    if len(self.model_chain) > 1:
                        logger.warning("llm_fallo_modelo model=%s -> saltando a siguiente modelo de respaldo", model)
                        break
                    if intento + 1 < intentos:
                        time.sleep(min(1.0, max(restante, 0.0)))
                    continue

                if r.status_code >= 400:
                    ultimo_error = LLMNoDisponible(
                        f"HTTP {r.status_code} del proveedor LLM model={model}"
                    )
                    logger.warning(
                        "llm_4xx model=%s status=%s body=%r",
                        model, r.status_code, r.text[:200],
                    )
                    break

                try:
                    data = r.json()
                except ValueError:
                    ultimo_error = LLMNoDisponible("Respuesta LLM no es JSON")
                    logger.warning("llm_respuesta_no_json model=%s", model)
                    break
                try:
                    content = data["choices"][0]["message"]["content"]
                except (KeyError, IndexError, TypeError):
                    ultimo_error = LLMNoDisponible("Respuesta LLM sin contenido")
                    logger.warning("llm_respuesta_sin_contenido model=%s", model)
                    break

                self.last_model = model
                return content

        raise ultimo_error or LLMNoDisponible(
            "El LLM no respondió dentro del tiempo o sin cuota disponible"
        )


# =========================================================================
# Factory
# =========================================================================
def get_llm_provider(provider_override: str | None = None) -> LLMProvider:
    settings = get_settings()
    provider = (provider_override or settings.LLM_PROVIDER).lower()
    if provider in ("openai", "gemini"):
        if not settings.LLM_API_KEY:
            logger.warning("LLM_API_KEY vacío; se usará MockProvider")
            return MockProvider()
        p = OpenAIProvider()
        logger.info(
            "llm_provider_activo name=%s model=%s fallback=%s rpm=%s tpm=%s rpd=%s",
            p.name, p.model, ",".join(p.fallback_models), p.rpm, p.tpm, p.rpd,
        )
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