"""Endpoints del agente IA (Customers)."""
from collections import Counter
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import (
    get_current_user,
    is_admin,
    require_admin,
    require_operador,
)
from app.core.logging import get_logger
from app.db.session import get_db
from app.models import (
    AutorComunicacion, CasoEscalamiento, ClaseComunicacion, Comunicacion,
    DireccionComunicacion, EstadoCaso, Pedido, Usuario,
)
from app.schemas.agent import (
    AgentMetrics,
    AgentResult,
    ChatResumen,
    HumanReply,
    HumanReplyResult,
    IncomingMessage,
    ThreadMessage,
)
from app.services.agent_service import AgentService
from app.services.caso_service import (
    CasoError,
    enviar_mensaje_humano,
    responder_caso,
    serializar_comunicacion,
)
from app.services.llm_provider import get_llm_provider

router = APIRouter()
logger = get_logger("agent_api")
settings = get_settings()


@router.post(
    "/messages/incoming",
    response_model=AgentResult,
    dependencies=[Depends(get_current_user)],
    summary="Procesa un mensaje entrante del cliente (simulación local)",
)
def incoming(payload: IncomingMessage, db: Session = Depends(get_db)):
    """Simula la entrada de un mensaje (webhook real: Fase 5)."""
    return AgentService(db).handle_incoming_message(payload)


# =====================================================================
# Bandeja e hilo de conversaciones (reutilizados por Casos → Responder)
# =====================================================================
def _thread_message(c: Comunicacion) -> ThreadMessage:
    return serializar_comunicacion(c)


@router.get(
    "/chats",
    response_model=list[ChatResumen],
    dependencies=[Depends(require_operador)],
    summary="Lista de conversaciones (una por pedido)",
)
def chats(
    limite: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db),
    current=Depends(require_operador),
):
    """Chats con cliente, último mensaje, caso abierto y si hay asesor reciente.

    El operador sólo ve conversaciones de casos que tenga asignados. El
    administrador ve toda la bandeja para supervisar y apoyar.
    """
    es_admin = is_admin(current)
    if es_admin:
        stmt = select(Pedido).order_by(Pedido.fecha_ingreso.desc())
    else:
        asignados = select(CasoEscalamiento.pedido_id).where(
            CasoEscalamiento.responsable_id == current.id,
            CasoEscalamiento.estado.in_(
                [EstadoCaso.ABIERTO, EstadoCaso.EN_PROCESO]
            ),
        )
        stmt = (
            select(Pedido)
            .where(Pedido.id.in_(asignados))
            .order_by(Pedido.fecha_ingreso.desc())
        )
    pedidos = db.scalars(stmt.limit(limite)).all()
    if not pedidos:
        return []
    ids = [p.id for p in pedidos]

    conteos = dict(
        db.execute(
            select(Comunicacion.pedido_id, func.count())
            .where(
                Comunicacion.pedido_id.in_(ids),
                Comunicacion.clase == ClaseComunicacion.CLIENTE,
            )
            .group_by(Comunicacion.pedido_id)
        ).all()
    )
    recientes = db.scalars(
        select(Comunicacion)
        .where(
            Comunicacion.pedido_id.in_(ids),
            Comunicacion.clase == ClaseComunicacion.CLIENTE,
        )
        .order_by(Comunicacion.fecha.desc(), Comunicacion.id.desc())
        .limit(300)
    ).all()
    ultima: dict[int, Comunicacion] = {}
    for c in recientes:
        ultima.setdefault(c.pedido_id, c)

    casos = db.scalars(
        select(CasoEscalamiento)
        .where(
            CasoEscalamiento.pedido_id.in_(ids),
            CasoEscalamiento.estado.in_([EstadoCaso.ABIERTO, EstadoCaso.EN_PROCESO]),
        )
        .order_by(CasoEscalamiento.fecha_apertura.desc())
    ).all()
    caso_por_pedido: dict[int, CasoEscalamiento] = {}
    for cs in casos:
        caso_por_pedido.setdefault(cs.pedido_id, cs)

    responsables = {
        c.responsable_id: c.responsable_nombre
        for c in casos
        if c.responsable_id is not None
    }

    limite_asesor = datetime.utcnow() - timedelta(
        minutes=settings.AGENT_RECENT_HUMAN_RESPONSE_MINUTES
    )
    con_asesor = set(
        db.scalars(
            select(Comunicacion.pedido_id).where(
                Comunicacion.pedido_id.in_(ids),
                Comunicacion.direccion == DireccionComunicacion.SALIENTE,
                Comunicacion.autor == AutorComunicacion.HUMANO,
                Comunicacion.clase == ClaseComunicacion.CLIENTE,
                Comunicacion.fecha >= limite_asesor,
            )
        ).all()
    )

    filas: list[ChatResumen] = []
    for p in pedidos:
        u = ultima.get(p.id)
        cs = caso_por_pedido.get(p.id)
        filas.append(
            ChatResumen(
                pedido_id=p.id,
                codigo=p.codigo,
                estado_pedido=p.estado_actual.value,
                cliente_id=p.cliente_id,
                cliente_nombre=p.cliente.nombre if p.cliente else "",
                total_mensajes=conteos.get(p.id, 0),
                ultima_fecha=u.fecha if u else None,
                ultima_preview=(u.contenido[:90] if u else None),
                ultima_autor=u.autor if u else None,
                caso_abierto_id=cs.id if cs else None,
                caso_abierto_motivo=cs.motivo if cs else None,
                responsable_id=cs.responsable_id if cs else None,
                responsable_nombre=(
                    responsables.get(cs.responsable_id) if cs else None
                ),
                puede_responder=bool(
                    cs
                    and cs.estado != EstadoCaso.CERRADO
                    and (
                        es_admin
                        or cs.responsable_id is None
                        or cs.responsable_id == current.id
                    )
                ),
                cliente_telegram_vinculado=bool(
                    p.cliente and p.cliente.telegram_chat_id
                ),
                asesor_reciente=p.id in con_asesor,
            )
        )
    # Con actividad primero, luego por antigüedad
    filas.sort(key=lambda f: f.ultima_fecha or datetime.min, reverse=True)
    return filas


@router.get(
    "/thread",
    response_model=list[ThreadMessage],
    dependencies=[Depends(require_operador)],
    summary="Mensajes del hilo de conversación de un pedido",
)
def thread(
    pedido_id: int = Query(..., ge=1),
    incluir_operativos: bool = Query(
        False, description="Incluye comandos y avisos internos (auditoría)"
    ),
    db: Session = Depends(get_db),
    current=Depends(require_operador),
):
    pedido = db.get(Pedido, pedido_id)
    if pedido is None:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")

    if not is_admin(current):
        caso_activo = db.scalar(
            select(CasoEscalamiento)
            .where(
                CasoEscalamiento.pedido_id == pedido.id,
                CasoEscalamiento.estado.in_(
                    [EstadoCaso.ABIERTO, EstadoCaso.EN_PROCESO]
                ),
            )
            .order_by(CasoEscalamiento.fecha_apertura.desc())
            .limit(1)
        )
        if caso_activo is None:
            raise HTTPException(
                status_code=403,
                detail="Sólo puedes ver conversaciones de casos asignados a ti.",
            )
        if (
            caso_activo.responsable_id is not None
            and caso_activo.responsable_id != current.id
        ):
            raise HTTPException(
                status_code=403,
                detail="Esta conversación está asignada a otro operador.",
            )
    stmt = select(Comunicacion).where(Comunicacion.pedido_id == pedido_id)
    if not incluir_operativos:
        stmt = stmt.where(Comunicacion.clase == ClaseComunicacion.CLIENTE)
    rows = db.scalars(
        stmt.order_by(Comunicacion.fecha.asc(), Comunicacion.id.asc()).limit(300)
    ).all()
    return [_thread_message(c) for c in rows]


@router.post(
    "/human-reply",
    response_model=HumanReplyResult,
    dependencies=[Depends(require_operador)],
    summary="Responde como persona (asesor) desde la plataforma",
)
def human_reply(
    payload: HumanReply,
    db: Session = Depends(get_db),
    current=Depends(require_operador),
):
    """Escribe una respuesta humana en el hilo.

    - Queda registrada como `HUMANO`/saliente por Telegram (auditoría completa).
    - El agente **no interviene** en los próximos
      `AGENT_RECENT_HUMAN_RESPONSE_MINUTES` (tiene prioridad la persona).
    - Si hay un caso abierto, se marca su primera acción humana, pasa a
      `EN_PROCESO` y el primero que responde queda como responsable.
    """
    pedido = db.get(Pedido, payload.pedido_id)
    if pedido is None:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")

    es_admin = is_admin(current)
    caso = db.scalar(
        select(CasoEscalamiento)
        .where(
            CasoEscalamiento.pedido_id == pedido.id,
            CasoEscalamiento.estado.in_([EstadoCaso.ABIERTO, EstadoCaso.EN_PROCESO]),
        )
        .order_by(CasoEscalamiento.fecha_apertura.desc())
        .limit(1)
    )

    try:
        if caso is not None:
            caso, com, envio = responder_caso(
                db,
                caso.id,
                payload.contenido,
                usuario_id=current.id,
                es_admin=es_admin,
            )
            aviso = (
                f"Caso #{caso.id} en proceso (registrada la primera respuesta humana)."
            )
            if not envio.ok:
                aviso += (
                    " El mensaje quedó registrado pero no se pudo entregar por "
                    f"Telegram: {envio.error or 'error desconocido'}."
                )
        else:
            if not es_admin:
                raise HTTPException(
                    status_code=403,
                    detail=(
                        "Sólo puedes responder conversaciones con un caso "
                        "asignado a ti."
                    ),
                )
            com, envio = enviar_mensaje_humano(
                db, pedido, payload.contenido, usuario_id=current.id,
            )
            aviso = None
            if not envio.ok:
                aviso = (
                    "El mensaje quedó registrado pero no se pudo entregar por "
                    f"Telegram: {envio.error or 'error desconocido'}."
                )
    except CasoError as exc:
        status_code = 409 if exc.code in {"asignado", "ya_cerrado"} else 400
        raise HTTPException(status_code=status_code, detail=exc.message)

    logger.info(
        "respuesta_humana pedido_id=%s com_id=%s caso_id=%s usuario=%s",
        pedido.id, com.id, caso.id if caso else None, current.email,
    )
    return HumanReplyResult(
        message=_thread_message(com),
        caso_id=caso.id if caso else None,
        caso_estado=caso.estado if caso else None,
        aviso=aviso,
    )


@router.get(
    "/provider",
    dependencies=[Depends(get_current_user)],
    summary="Información del proveedor LLM activo",
)
def provider_info():
    p = get_llm_provider()
    return p.status()


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
@router.post(
    "/clasificar",
    dependencies=[Depends(require_admin)],
    summary="Alias de /test/classify para clasificar un texto con IA",
)
def test_classify(payload: IncomingMessage):
    """Solo clasifica. Si el LLM remoto no está disponible (cuota, demanda),
    responde con el motor local en lugar de fallar: nunca corta la demo."""
    try:
        result = get_llm_provider().classify(payload.contenido)
        return {
            "intent": result.intent.value,
            "sentiment": result.sentiment.value,
            "confidence": result.confidence,
            "provider_used": result.provider_used,
            "model_used": result.model_used,
        }
    except Exception as exc:  # noqa: BLE001 — degradar es el comportamiento deseado
        logger.warning("test_classify_fallback err=%s", exc)
        from app.services.llm_provider import MockProvider
        result = MockProvider().classify(payload.contenido)
        return {
            "intent": result.intent.value,
            "sentiment": result.sentiment.value,
            "confidence": result.confidence,
            "provider_used": "mock_fallback",
            "aviso": "El LLM remoto no está disponible; se usó el motor local.",
        }