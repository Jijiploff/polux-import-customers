"""Línea de tiempo del pedido (Fase H).

Fusiona —solo lectura— las fuentes existentes del pedido en una única
lista ordenada por fecha (más reciente primero):

- **pedido**: ingreso del pedido (ancla de la historia);
- **hito**: hitos COMPLETADOS (fecha real) y ATRASADOS/vencidos (fecha
  prevista, con los días de atraso);
- **mensaje**: por defecto solo *eventos clave* — quejas/escalamientos,
  respuestas de asesor (`autor=HUMANO`) y avisos con plantilla; con
  ``incluir_mensajes=True`` se añaden **todos** los mensajes;
- **caso**: apertura, primera respuesta humana y cierre;
- **imprevisto**: detección y resolución;
- **entrega**: programación y registro final;
- **alerta**: detección (con severidad) y atención.

No escribe en la BD ni dispara el motor de reglas: es una consulta
fusionada de las tablas que ya existen.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    Alerta,
    AutorComunicacion,
    CasoEscalamiento,
    ClaseComunicacion,
    Comunicacion,
    Entrega,
    EstadoAlerta,
    EstadoCaso,
    EstadoEntrega,
    EstadoHito,
    EstadoImprevisto,
    Imprevisto,
    ItemHito,
    Pedido,
    PedidoItem,
    PrioridadCaso,
    Sentimiento,
)
from app.schemas.timeline import TimelineEvent, TimelineRead, TimelineResumen

_MAX_DETALLE = 240

# Severidad/prioridad → criticidad del evento (para el color del badge).
_CRIT_POR_VALOR = {
    "CRITICA": "ALTA",
    "ALTA": "ALTA",
    "MEDIA": "MEDIA",
    "BAJA": "INFO",
}


def _corto(texto: str | None, max_: int = _MAX_DETALLE) -> str | None:
    """Colapsa espacios y trunca para que el detalle sea legible."""
    if not texto:
        return None
    t = " ".join(str(texto).split())
    if len(t) <= max_:
        return t
    return t[: max_ - 1].rstrip() + "…"


def _ev(
    fecha: datetime,
    tipo: str,
    titulo: str,
    *,
    detalle: str | None = None,
    criticidad: str = "INFO",
    ref_tipo: str | None = None,
    ref_id: int | None = None,
    autor: str | None = None,
) -> TimelineEvent:
    return TimelineEvent(
        fecha=fecha,
        tipo=tipo,
        titulo=titulo,
        detalle=detalle,
        criticidad=criticidad,
        ref_tipo=ref_tipo,
        ref_id=ref_id,
        autor=autor,
    )


def _eventos_pedido(pedido: Pedido) -> list[TimelineEvent]:
    return [
        _ev(
            pedido.fecha_ingreso,
            "pedido",
            "Pedido ingresado",
            detalle=(
                pedido.estado_ingreso.replace("_", " ").lower()
                + f" · fecha prometida {pedido.fecha_prometida:%d/%m/%Y}"
            ),
            ref_tipo="pedido",
            ref_id=pedido.id,
        )
    ]


def _eventos_hitos(db: Session, pedido_id: int) -> list[TimelineEvent]:
    ahora = datetime.utcnow()
    rows = db.scalars(
        select(ItemHito)
        .join(PedidoItem, PedidoItem.id == ItemHito.pedido_item_id)
        .options(joinedload(ItemHito.hito), joinedload(ItemHito.item))
        .where(PedidoItem.pedido_id == pedido_id)
    ).unique().all()
    eventos: list[TimelineEvent] = []
    for ih in rows:
        nombre = ih.hito.nombre if ih.hito else "Hito"
        item = ih.item.descripcion_producto if ih.item else ""
        if ih.estado == EstadoHito.COMPLETADO and ih.fecha_real:
            eventos.append(_ev(
                ih.fecha_real, "hito", f"Hito completado: {nombre}",
                detalle=_corto(item)
                + (" · cliente notificado" if ih.notificado_cliente else ""),
                ref_tipo="item_hito", ref_id=ih.id,
            ))
        elif ih.estado == EstadoHito.ATRASADO and ih.fecha_prevista:
            dias = (
                f"{ih.dias_atraso} día(s) de atraso"
                if ih.dias_atraso > 0
                else "fecha prevista vencida"
            )
            eventos.append(_ev(
                ih.fecha_prevista, "hito", f"Hito atrasado: {nombre}",
                detalle=_corto(f"{item} · {dias}"),
                criticidad="ALTA", ref_tipo="item_hito", ref_id=ih.id,
            ))
        elif (
            ih.estado in (EstadoHito.PENDIENTE, EstadoHito.EN_PROCESO)
            and ih.fecha_prevista
            and ih.fecha_prevista < ahora
        ):
            # Aún no recalculado por `registrar_atrasos` (ciclo de 5 min).
            eventos.append(_ev(
                ih.fecha_prevista, "hito", f"Hito vencido: {nombre}",
                detalle=_corto(item),
                criticidad="MEDIA", ref_tipo="item_hito", ref_id=ih.id,
            ))
    return eventos


def _eventos_mensajes(
    db: Session, pedido_id: int, *, incluir_todos: bool
) -> list[TimelineEvent]:
    stmt = select(Comunicacion).where(Comunicacion.pedido_id == pedido_id)
    if not incluir_todos:
        # Eventos clave: solo conversación real con el cliente. Los mensajes
        # operativos quedan en la auditoría y aparecen con `incluir_mensajes`.
        stmt = stmt.where(
            Comunicacion.clase == ClaseComunicacion.CLIENTE,
            (Comunicacion.autor == AutorComunicacion.HUMANO)
            # NOTA: en SQL Server `IS 1` no es válido; `== True` → `= 1`.
            | (Comunicacion.escalado == True)  # noqa: E712
            | (Comunicacion.plantilla_id.is_not(None))
            | (Comunicacion.sentimiento == Sentimiento.NEGATIVO),
        )
    msgs = db.scalars(
        stmt.options(joinedload(Comunicacion.plantilla)).order_by(Comunicacion.fecha)
    ).all()
    eventos: list[TimelineEvent] = []
    for m in msgs:
        if m.clase == ClaseComunicacion.OPERATIVO:
            eventos.append(_ev(
                m.fecha, "operativo", "Mensaje operativo",
                detalle=_corto(m.contenido),
                ref_tipo="comunicacion", ref_id=m.id,
                autor=m.autor.value if m.autor else None,
            ))
            continue

        criticidad = "INFO"
        if m.autor == AutorComunicacion.HUMANO:
            titulo = "Respuesta del asesor"
        elif m.autor == AutorComunicacion.AGENTE:
            if m.plantilla is not None:
                titulo = f"Aviso automático: {m.plantilla.nombre}"
            elif m.escalado:
                titulo = "Agente derivó el caso a una persona"
                criticidad = "ALTA"
            else:
                titulo = "Respuesta del agente"
        else:  # CLIENTE
            if m.escalado or m.sentimiento == Sentimiento.NEGATIVO:
                intencion = f" ({m.intencion_detectada})" if m.intencion_detectada else ""
                titulo = f"Consulta del cliente escalada{intencion}"
                criticidad = "ALTA"
            else:
                titulo = "Mensaje del cliente"
        eventos.append(_ev(
            m.fecha, "mensaje", titulo,
            detalle=_corto(m.contenido),
            criticidad=criticidad,
            ref_tipo="comunicacion", ref_id=m.id,
            autor=m.autor.value if m.autor else None,
        ))
    return eventos


def _eventos_casos(db: Session, pedido_id: int) -> list[TimelineEvent]:
    casos = db.scalars(
        select(CasoEscalamiento).where(CasoEscalamiento.pedido_id == pedido_id)
    ).all()
    eventos: list[TimelineEvent] = []
    for c in casos:
        motivo = c.motivo.value if c.motivo else ""
        criticidad = _CRIT_POR_VALOR.get(
            c.prioridad.value if c.prioridad else "MEDIA", "MEDIA"
        )
        eventos.append(_ev(
            c.fecha_apertura, "caso", f"Caso #{c.id}: {motivo}",
            detalle=_corto(
                f"{c.descripcion or ''} · prioridad "
                f"{c.prioridad.value if c.prioridad else '—'} · "
                f"estado {c.estado.value if c.estado else '—'}"
            ),
            criticidad=criticidad,
            ref_tipo="caso", ref_id=c.id,
        ))
        if c.fecha_primera_accion:
            eventos.append(_ev(
                c.fecha_primera_accion, "caso",
                f"Caso #{c.id}: primera respuesta de asesor",
                ref_tipo="caso", ref_id=c.id,
            ))
        if c.fecha_cierre:
            eventos.append(_ev(
                c.fecha_cierre, "caso", f"Caso #{c.id} resuelto",
                ref_tipo="caso", ref_id=c.id,
            ))
    return eventos


def _eventos_imprevistos(db: Session, pedido_id: int) -> list[TimelineEvent]:
    rows = db.scalars(
        select(Imprevisto).where(Imprevisto.pedido_id == pedido_id)
    ).all()
    eventos: list[TimelineEvent] = []
    for i in rows:
        tipo = i.tipo.value if i.tipo else "Imprevisto"
        abierto = i.estado in (EstadoImprevisto.ABIERTO, EstadoImprevisto.EN_PROCESO)
        eventos.append(_ev(
            i.fecha_deteccion, "imprevisto", f"Imprevisto: {tipo}",
            detalle=_corto(
                f"{i.descripcion or ''} · estado {i.estado.value if i.estado else '—'}"
            ),
            criticidad="ALTA" if abierto else "MEDIA",
            ref_tipo="imprevisto", ref_id=i.id,
        ))
        if i.fecha_resolucion:
            eventos.append(_ev(
                i.fecha_resolucion, "imprevisto", f"Imprevisto resuelto: {tipo}",
                detalle=_corto(i.resolucion),
                ref_tipo="imprevisto", ref_id=i.id,
            ))
    return eventos


def _eventos_entregas(db: Session, pedido_id: int) -> list[TimelineEvent]:
    rows = db.scalars(
        select(Entrega).where(Entrega.pedido_id == pedido_id)
    ).all()
    eventos: list[TimelineEvent] = []
    for e in rows:
        tipo = e.tipo.value if e.tipo else "ENTREGA"
        modalidad = e.modalidad.value if e.modalidad else ""
        eventos.append(_ev(
            e.fecha_programada, "entrega", f"Entrega #{e.id} programada · {tipo}",
            detalle=_corto(
                f"{modalidad.lower()} · estado actual "
                f"{e.estado.value if e.estado else '—'}"
            ),
            ref_tipo="entrega", ref_id=e.id,
        ))
        if e.fecha_real:
            fallida = e.estado == EstadoEntrega.FALLIDA
            estado_txt = e.estado.value.lower() if e.estado else "registrada"
            titulo = (
                f"Entrega #{e.id} fallida"
                if fallida
                else f"Entrega #{e.id}: {estado_txt}"
            )
            eventos.append(_ev(
                e.fecha_real, "entrega", titulo,
                criticidad="ALTA" if fallida else "INFO",
                ref_tipo="entrega", ref_id=e.id,
            ))
    return eventos


def _eventos_alertas(db: Session, pedido_id: int) -> list[TimelineEvent]:
    rows = db.scalars(select(Alerta).where(Alerta.pedido_id == pedido_id)).all()
    eventos: list[TimelineEvent] = []
    for a in rows:
        tipo = a.tipo.value if a.tipo else "ALERTA"
        criticidad = _CRIT_POR_VALOR.get(
            a.severidad.value if a.severidad else "MEDIA", "MEDIA"
        )
        eventos.append(_ev(
            a.fecha_deteccion, "alerta", f"Alerta: {tipo}",
            detalle=_corto(a.mensaje),
            criticidad=criticidad,
            ref_tipo="alerta", ref_id=a.id,
        ))
        if a.fecha_atencion:
            eventos.append(_ev(
                a.fecha_atencion, "alerta", f"Alerta atendida: {tipo}",
                ref_tipo="alerta", ref_id=a.id,
            ))
    return eventos


def _resumen(db: Session, pedido_id: int) -> TimelineResumen:
    """Contadores para la cabecera (contexto rápido al responder)."""
    mensajes = db.scalar(
        select(func.count()).select_from(Comunicacion).where(
            Comunicacion.pedido_id == pedido_id,
            Comunicacion.clase == ClaseComunicacion.CLIENTE,
        )
    ) or 0
    mensajes_operativos = db.scalar(
        select(func.count()).select_from(Comunicacion).where(
            Comunicacion.pedido_id == pedido_id,
            Comunicacion.clase == ClaseComunicacion.OPERATIVO,
        )
    ) or 0
    mensajes_clave = db.scalar(
        select(func.count()).select_from(Comunicacion).where(
            Comunicacion.pedido_id == pedido_id,
            Comunicacion.clase == ClaseComunicacion.CLIENTE,
            (
                (Comunicacion.autor == AutorComunicacion.HUMANO)
                # NOTA: en SQL Server `IS 1` no es válido; `== True` → `= 1`.
            | (Comunicacion.escalado == True)  # noqa: E712
                | (Comunicacion.plantilla_id.is_not(None))
                | (Comunicacion.sentimiento == Sentimiento.NEGATIVO)
            ),
        )
    ) or 0
    hitos_atrasados = db.scalar(
        select(func.count()).select_from(ItemHito)
        .join(PedidoItem, PedidoItem.id == ItemHito.pedido_item_id)
        .where(
            PedidoItem.pedido_id == pedido_id,
            ItemHito.estado == EstadoHito.ATRASADO,
        )
    ) or 0
    casos_abiertos = db.scalar(
        select(func.count()).select_from(CasoEscalamiento).where(
            CasoEscalamiento.pedido_id == pedido_id,
            CasoEscalamiento.estado.in_([EstadoCaso.ABIERTO, EstadoCaso.EN_PROCESO]),
        )
    ) or 0
    imprevistos_abiertos = db.scalar(
        select(func.count()).select_from(Imprevisto).where(
            Imprevisto.pedido_id == pedido_id,
            Imprevisto.estado.in_([EstadoImprevisto.ABIERTO, EstadoImprevisto.EN_PROCESO]),
        )
    ) or 0
    alertas_activas = db.scalar(
        select(func.count()).select_from(Alerta).where(
            Alerta.pedido_id == pedido_id,
            Alerta.estado == EstadoAlerta.ABIERTA,
        )
    ) or 0
    return TimelineResumen(
        mensajes=mensajes,
        mensajes_clave=mensajes_clave,
        mensajes_operativos=mensajes_operativos,
        hitos_atrasados=hitos_atrasados,
        casos_abiertos=casos_abiertos,
        imprevistos_abiertos=imprevistos_abiertos,
        alertas_activas=alertas_activas,
    )


def build_timeline(
    db: Session,
    pedido: Pedido,
    *,
    incluir_mensajes: bool = False,
    tipos: set[str] | None = None,
    desde: datetime | None = None,
    hasta: datetime | None = None,
    limit: int = 200,
) -> TimelineRead:
    """Construye la línea de tiempo fusionada y ordenada (fecha desc)."""
    # Si el operador pide explícitamente el tipo `operativo`, hay que leer
    # todos los mensajes: por defecto solo se listan los eventos clave.
    incluir_todos = incluir_mensajes or bool(tipos and "operativo" in tipos)
    eventos: list[TimelineEvent] = []
    eventos.extend(_eventos_pedido(pedido))
    eventos.extend(_eventos_hitos(db, pedido.id))
    eventos.extend(_eventos_mensajes(db, pedido.id, incluir_todos=incluir_todos))
    eventos.extend(_eventos_casos(db, pedido.id))
    eventos.extend(_eventos_imprevistos(db, pedido.id))
    eventos.extend(_eventos_entregas(db, pedido.id))
    eventos.extend(_eventos_alertas(db, pedido.id))

    if tipos is not None:
        eventos = [e for e in eventos if e.tipo in tipos]
    if desde is not None:
        eventos = [e for e in eventos if e.fecha >= desde]
    if hasta is not None:
        eventos = [e for e in eventos if e.fecha <= hasta]

    eventos.sort(key=lambda e: e.fecha, reverse=True)
    eventos = eventos[:limit]

    return TimelineRead(
        pedido_id=pedido.id,
        resumen=_resumen(db, pedido.id),
        eventos=eventos,
        incluyendo_mensajes=incluir_mensajes,
    )
