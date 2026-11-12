"""Entregas completas y parciales + conformidad.

Regla inviolable (§2.7 y §8 del prompt / §6 del plan):
  El sistema NO permite una entrega parcial sin autorización humana
  registrada (quién, cuándo y por qué). Se valida en servicio Y en la BD
  (CHECK `ck_entrega_parcial_requiere_autorizacion`).
"""
from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Conformidad,
    Entrega,
    EntregaItem,
    EstadoEntrega,
    EstadoItem,
    EstadoPedido,
    Pedido,
    PedidoItem,
    ResultadoConformidad,
    TipoEntrega,
)
from app.schemas.entrega import ConformidadItemIn, EntregaCreate, EntregaUpdate


def _items_del_pedido(db: Session, pedido_id: int) -> list[PedidoItem]:
    return db.scalars(select(PedidoItem).where(PedidoItem.pedido_id == pedido_id)).all()


def _validar_items_listos(items: list[PedidoItem], ids: list[int]) -> None:
    mapa = {i.id: i for i in items}
    for pid in ids:
        item = mapa.get(pid)
        if item is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Ítem {pid} no pertenece al pedido")
        if item.estado != EstadoItem.LISTO_PARA_ENTREGA:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Ítem {pid} no está LISTO_PARA_ENTREGA (estado={item.estado.value})",
            )


def crear_entrega(
    db: Session, payload: EntregaCreate, *, usuario_id: int | None
) -> Entrega:
    pedido = db.get(Pedido, payload.pedido_id)
    if pedido is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pedido no encontrado")
    if pedido.estado_actual in {EstadoPedido.CERRADO, EstadoPedido.CERRADO_CON_OBSERVACIONES, EstadoPedido.CANCELADO}:
        raise HTTPException(status.HTTP_409_CONFLICT, "El pedido ya está cerrado/cancelado")

    items = _items_del_pedido(db, pedido.id)

    if payload.tipo == TipoEntrega.COMPLETA:
        no_listos = [i.id for i in items if i.estado != EstadoItem.LISTO_PARA_ENTREGA]
        if no_listos:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"No se puede programar entrega completa: ítems no listos {no_listos}",
            )
        item_ids = [i.id for i in items]

    else:  # PARCIAL — validaciones estrictas
        if not payload.autorizada_por_id or not payload.fecha_autorizacion or not payload.motivo_parcial:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "La entrega parcial exige `autorizada_por_id`, `fecha_autorizacion` y `motivo_parcial`",
            )

        # Quién autoriza solo puede ser el usuario que ejecuta la acción, o un ADMIN.
        from app.models import RolCodigo, Usuario

        autorizador = db.get(Usuario, payload.autorizada_por_id)
        if autorizador is None or not autorizador.activo:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "El usuario autorizante no existe o está inactivo",
            )
        if payload.autorizada_por_id != usuario_id:
            ejecutor = db.get(Usuario, usuario_id)
            roles_ejecutor = {r.rol.codigo for r in ejecutor.roles if r.rol} if ejecutor else set()
            if RolCodigo.ADMIN not in roles_ejecutor:
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    "Solo ADMIN puede autorizar entregas parciales en nombre de otro usuario",
                )

        if not payload.pedido_item_ids:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Debe indicar al menos un ítem a entregar")
        _validar_items_listos(items, payload.pedido_item_ids)
        item_ids = payload.pedido_item_ids
        
    entrega = Entrega(
        pedido_id=pedido.id,
        tipo=payload.tipo,
        modalidad=payload.modalidad,
        fecha_programada=payload.fecha_programada,
        estado=payload.estado_inicial,
        autorizada_por_id=payload.autorizada_por_id,
        fecha_autorizacion=payload.fecha_autorizacion,
        motivo_parcial=payload.motivo_parcial,
        created_by_id=usuario_id,
        updated_by_id=usuario_id,
        direccion=payload.direccion,
        distrito=payload.distrito,
        punto_recojo=payload.punto_recojo,
        referencia=payload.referencia,
        receptor_nombre=payload.receptor_nombre,
        receptor_dni=payload.receptor_dni,
        receptor_telefono=payload.receptor_telefono,
        franja_horaria=payload.franja_horaria,
        notas_courier=payload.notas_courier,
        creado_por_agente=payload.creado_por_agente,
    )
    db.add(entrega)
    db.flush()
    for pid in item_ids:
        db.add(EntregaItem(entrega_id=entrega.id, pedido_item_id=pid))

    pedido.estado_actual = EstadoPedido.EN_COORDINACION
    db.commit()
    db.refresh(entrega)
    return entrega


def completar_entrega(
    db: Session,
    entrega_id: int,
    *,
    fecha_real: datetime,
    conformidades: list[ConformidadItemIn],
    receptor_verificado: bool = False,
    recibido_por: str = "",
    usuario_id: int,
) -> Entrega:
    entrega = db.scalar(
        select(Entrega)
        .options(selectinload(Entrega.items))
        .where(Entrega.id == entrega_id)
    )
    if entrega is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entrega no encontrada")
    if entrega.estado == EstadoEntrega.ENTREGADA:
        raise HTTPException(status.HTTP_409_CONFLICT, "La entrega ya fue registrada como ENTREGADA")

    item_ids_entrega = {ei.pedido_item_id for ei in entrega.items}
    conformidades_por_item = {c.pedido_item_id: c for c in conformidades}
    if set(conformidades_por_item) != item_ids_entrega:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Debe registrar conformidad para exactamente los ítems de la entrega",
        )

    # Registrar conformidad por ítem
    for ei in entrega.items:
        c = conformidades_por_item[ei.pedido_item_id]
        if c.resultado == ResultadoConformidad.CON_OBSERVACIONES and not c.observaciones:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Ítem {c.pedido_item_id}: `observaciones` es obligatorio si el resultado es CON_OBSERVACIONES",
            )
        conf = Conformidad(
            entrega_item_id=ei.id,
            checklist_caja_sellada=c.checklist_caja_sellada,
            checklist_modelo_ok=c.checklist_modelo_ok,
            checklist_color_ok=c.checklist_color_ok,
            checklist_capacidad_ok=c.checklist_capacidad_ok,
            checklist_imei_ok=c.checklist_imei_ok,
            checklist_accesorios_ok=c.checklist_accesorios_ok,
            resultado=c.resultado,
            observaciones=c.observaciones,
            evidencias_urls=c.evidencias_urls,
            fecha_registro=datetime.utcnow(),
            registrado_por_id=usuario_id,
            created_by_id=usuario_id,
            updated_by_id=usuario_id,
        )
        db.add(conf)

        item = db.get(PedidoItem, ei.pedido_item_id)
        if c.resultado == ResultadoConformidad.CONFORME:
            item.estado = EstadoItem.ENTREGADO
        else:
            item.estado = EstadoItem.CON_OBSERVACIONES
        item.updated_by_id = usuario_id

    entrega.fecha_real = fecha_real
    entrega.estado = EstadoEntrega.ENTREGADA
    entrega.receptor_verificado = receptor_verificado
    entrega.recibido_por = recibido_por or entrega.receptor_nombre
    entrega.updated_by_id = usuario_id
    db.flush()

    _cerrar_o_actualizar_pedido(db, entrega.pedido_id, usuario_id)
    db.commit()
    db.refresh(entrega)
    return entrega


def actualizar_entrega(
    db: Session, entrega_id: int, payload: EntregaUpdate, *, usuario_id: int
) -> Entrega:
    entrega = db.get(Entrega, entrega_id)
    if entrega is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entrega no encontrada")
    if entrega.estado in {EstadoEntrega.ENTREGADA, EstadoEntrega.FALLIDA}:
        raise HTTPException(status.HTTP_409_CONFLICT, "La entrega es inmutable en su estado actual")
    for campo, valor in payload.model_dump(exclude_unset=True).items():
        setattr(entrega, campo, valor)
    entrega.updated_by_id = usuario_id
    db.commit()
    db.refresh(entrega)
    return entrega


def confirmar_entrega(db: Session, entrega_id: int, *, usuario_id: int) -> Entrega:
    entrega = db.get(Entrega, entrega_id)
    if entrega is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entrega no encontrada")
    if entrega.estado not in {EstadoEntrega.BORRADOR, EstadoEntrega.RECHAZADA}:
        raise HTTPException(status.HTTP_409_CONFLICT, "Solo se pueden confirmar borradores")
    entrega.estado = EstadoEntrega.PROGRAMADA
    entrega.confirmada_por_id = usuario_id
    entrega.fecha_confirmacion = datetime.utcnow()
    entrega.motivo_rechazo = None
    entrega.updated_by_id = usuario_id
    db.commit()
    db.refresh(entrega)
    return entrega


def rechazar_entrega(
    db: Session, entrega_id: int, motivo: str, *, usuario_id: int
) -> Entrega:
    entrega = db.get(Entrega, entrega_id)
    if entrega is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entrega no encontrada")
    if entrega.estado != EstadoEntrega.BORRADOR:
        raise HTTPException(status.HTTP_409_CONFLICT, "Solo se pueden rechazar borradores")
    entrega.estado = EstadoEntrega.RECHAZADA
    entrega.motivo_rechazo = motivo
    entrega.updated_by_id = usuario_id
    db.commit()
    db.refresh(entrega)
    return entrega


def cambiar_estado_entrega(
    db: Session, entrega_id: int, estado: EstadoEntrega, *, usuario_id: int
) -> Entrega:
    entrega = db.get(Entrega, entrega_id)
    if entrega is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entrega no encontrada")
    permitidas = {
        EstadoEntrega.PROGRAMADA: {EstadoEntrega.EN_RUTA, EstadoEntrega.REPROGRAMADA},
        EstadoEntrega.EN_RUTA: {EstadoEntrega.ENTREGADA, EstadoEntrega.FALLIDA},
        EstadoEntrega.FALLIDA: {EstadoEntrega.REPROGRAMADA},
        EstadoEntrega.REPROGRAMADA: {EstadoEntrega.PROGRAMADA},
    }
    if estado not in permitidas.get(entrega.estado, set()):
        raise HTTPException(status.HTTP_409_CONFLICT, "Transición de estado no permitida")
    entrega.estado = estado
    entrega.updated_by_id = usuario_id
    db.commit()
    db.refresh(entrega)
    return entrega


def _cerrar_o_actualizar_pedido(db: Session, pedido_id: int, usuario_id: int) -> None:
    pedido = db.get(Pedido, pedido_id)
    items = _items_del_pedido(db, pedido.id)
    todos_entregados = all(
        i.estado in {EstadoItem.ENTREGADO, EstadoItem.CON_OBSERVACIONES} for i in items
    )
    if not todos_entregados:
        pedido.estado_actual = EstadoPedido.EN_PROCESO
        return
    hay_observaciones = any(i.estado == EstadoItem.CON_OBSERVACIONES for i in items)
    pedido.estado_actual = (
        EstadoPedido.CERRADO_CON_OBSERVACIONES if hay_observaciones else EstadoPedido.CERRADO
    )
    pedido.updated_by_id = usuario_id