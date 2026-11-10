"""Endpoints del agente IA (Customers)."""
from collections import Counter
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_admin
from app.db.session import get_db
from app.models import (
    AutorComunicacion, Comunicacion, DireccionComunicacion, Pedido,
)
from app.schemas.agent import AgentMetrics, AgentResult, IncomingMessage
from app.services.agent_service import AgentService
from app.services.llm_provider import get_llm_provider

router = APIRouter()


@router.post(
    "/messages/incoming",
    response_model=AgentResult,
    dependencies=[Depends(get_current_user)],
    summary="Procesa un mensaje entrante del cliente (simulación local)",
)
def incoming(payload: IncomingMessage, db: Session = Depends(get_db)):
    """Simula la entrada de un mensaje (webhook real: Fase 5)."""
    return AgentService(db).handle_incoming_message(payload)


@router.get(
    "/provider",
    dependencies=[Depends(get_current_user)],
    summary="Información del proveedor LLM activo",
)
def provider_info():
    p = get_llm_provider()
    return {"provider": p.name}


@router.get(
    "/metrics",
    response_model=AgentMetrics,
    dependencies=[Depends(get_current_user)],
    summary="Métricas del agente (agregados)",
)
def metrics(
    pedido_id: int | None = Query(None),
    db: Session = Depends(get_db),
) -> AgentMetrics:
    stmt_in = select(Comunicacion).where(
        Comunicacion.direccion == DireccionComunicacion.ENTRANTE,
        Comunicacion.autor == AutorComunicacion.CLIENTE,
    )
    stmt_out = select(Comunicacion).where(
        Comunicacion.direccion == DireccionComunicacion.SALIENTE,
        Comunicacion.autor == AutorComunicacion.AGENTE,
    )
    if pedido_id:
        stmt_in = stmt_in.where(Comunicacion.pedido_id == pedido_id)
        stmt_out = stmt_out.where(Comunicacion.pedido_id == pedido_id)

    entrantes = db.scalars(stmt_in).all()
    salientes = db.scalars(stmt_out).all()

    intent_counts = Counter(c.intencion_detectada or "—" for c in entrantes)
    sent_counts = Counter(
        c.sentimiento.value if c.sentimiento else "—" for c in entrantes
    )
    escalados = sum(1 for c in entrantes if c.escalado)
    no_escalados = len(entrantes) - escalados
    tasa = round(100.0 * escalados / len(entrantes), 2) if entrantes else 0.0
    con_plantilla = sum(1 for c in salientes if c.plantilla_id is not None)
    sin_plantilla = len(salientes) - con_plantilla

    return AgentMetrics(
        total_entrantes=len(entrantes),
        total_salientes=len(salientes),
        escalados=escalados,
        no_escalados=no_escalados,
        tasa_escalamiento=tasa,
        por_intent=dict(intent_counts),
        por_sentimiento=dict(sent_counts),
        con_plantilla=con_plantilla,
        sin_plantilla=sin_plantilla,
    )


@router.post(
    "/test/classify",
    dependencies=[Depends(require_admin)],
    summary="Clasifica un texto sin ejecutar el flujo (solo ADMIN)",
)
def test_classify(payload: IncomingMessage):
    provider = get_llm_provider()
    result = provider.classify(payload.contenido)
    return {
        "intent": result.intent.value,
        "sentiment": result.sentiment.value,
        "confidence": result.confidence,
        "provider_used": result.provider_used,
    }