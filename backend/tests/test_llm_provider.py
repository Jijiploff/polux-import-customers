"""Tests del provider LLM: cero cuota en la suite, cortesía con RPM y parsing.

Ningún test de este archivo hace peticiones de red: si algo intentara llamar
a Gemini desde la suite, el test correspondiente fallaría en lugar de gastar
cuota.
"""
import os
import time

import pytest

from app.core.config import get_settings
from app.services.llm_provider import (
    LLMNoDisponible,
    MockProvider,
    OpenAIProvider,
    RateGuard,
    _safe_confidence,
    get_llm_provider,
)


@pytest.fixture(autouse=True)
def _reset_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# --------- La suite nunca toca el LLM real ---------
def test_suite_fuerza_motor_local():
    """conftest.py fija LLM_PROVIDER=mock: la suite no gasta cuota de Gemini."""
    assert os.environ.get("LLM_PROVIDER") == "mock"
    assert isinstance(get_llm_provider(), MockProvider)


def test_provider_gemini_se_identifica_correctamente(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_API_KEY", "clave-de-prueba")
    monkeypatch.setenv(
        "LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai"
    )
    monkeypatch.setenv("LLM_MODEL", "gemini-3.1-flash-lite")
    monkeypatch.setenv("LLM_MODEL_FALLBACK", "gemini-3.5-flash")
    get_settings.cache_clear()
    p = get_llm_provider()
    assert isinstance(p, OpenAIProvider)
    assert p.name == "gemini"
    assert p.fallback_model == "gemini-3.5-flash"


def test_llm_sin_api_key_no_hace_ninguna_llamada(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_API_KEY", "")
    get_settings.cache_clear()
    p = OpenAIProvider()
    # Falla ANTES de abrir conexión: ni RPM ni RPD se tocan.
    with pytest.raises(LLMNoDisponible):
        p.classify("Hola, ¿dónde está mi pedido?")


# --------- RateGuard: no saturar el RPM ni reintentar contra cuota agotada ---------
def test_rate_guard_respeta_rpm():
    g = RateGuard(ventana_segundos=60)
    assert g.intentar(rpm=2) is None
    assert g.intentar(rpm=2) is None
    assert g.intentar(rpm=2) == "rpm_excedido"


def test_rate_guard_reposo_tras_429():
    g = RateGuard()
    g.reposo(0.2)
    assert g.intentar(rpm=1000) == "reposo_por_429"
    time.sleep(0.25)
    assert g.intentar(rpm=1000) is None


def test_rate_guard_ventana_deslizante_se_libera():
    g = RateGuard(ventana_segundos=0.15)
    assert g.intentar(rpm=1) is None
    assert g.intentar(rpm=1) == "rpm_excedido"
    time.sleep(0.2)
    assert g.intentar(rpm=1) is None


def test_rate_guard_en_reposo_expuesto():
    g = RateGuard()
    assert g.en_reposo is False
    g.reposo(30)
    assert g.en_reposo is True


# --------- Robustez del parsing (modelos que devuelven cosas raras) ---------
def test_confianza_normalizada_a_rango_0_1():
    assert _safe_confidence("0.7") == 0.7
    assert _safe_confidence(95) == 0.95        # devuelve 95 en vez de 0.95
    assert _safe_confidence(150) == 1.0        # fuera de rango → tope
    assert _safe_confidence(2) == 0.02         # basura → confianza baja → escala a humano
    assert _safe_confidence(-3) == 0.0         # negativo → 0
    assert _safe_confidence("muy seguro") == 0.5  # no numérico → default
    assert _safe_confidence(None) == 0.5
