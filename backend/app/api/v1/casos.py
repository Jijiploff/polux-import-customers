"""Casos de escalamiento."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_operador
from app.db.session import get_db
from app.models import CasoEscalamiento, EstadoCaso, Pedido, Usuario
from app.schemas.comms import (
    CasoCierreRead,
    CasoCreate,
    CasoDetalleRead,
    CasoRead,
    CasoRespuestaCreate,
    CasoRespuestaRead,
    CasoUpdate,
)
from app.services.caso_service import (
    CasoError,
    actualizar_caso,
    cerrar_caso,
    crear_caso,
    responder_caso,
    serializar_comunicacion,
)

router = APIRouter(dependencies=[Depends(get_current_user)])


def _http_error(exc: CasoError) -> HTTPException:
    if exc.code == "no_encontrado":
        status_code = 404
    elif exc.code in {"asignado", "ya_cerrado"}:
        status_code = 409
    else:
        status_code = 400
    return HTTPException(status_code=status_code, detail=exc.message)


@router.get("", response_model=list[CasoRead])
def listar(
    estado: EstadoCaso | None = Query(None),
    pedido_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    stmt = select(CasoEscalamiento).order_by(CasoEscalamiento.id.desc())
    if estado:
        stmt = stmt.where(CasoEscalamiento.estado == estado)
    if pedido_id:
        stmt = stmt.where(CasoEscalamiento.pedido_id == pedido_id)
    return db.scalars(stmt).all()


@router.get("/{caso_id}", response_model=CasoDetalleRead)
def detalle(
    caso_id: int,
    db: Session = Depends(get_db),
    current=Depends(get_current_user),
):
    """Ficha del caso con el contexto necesario para responderlo."""
    caso = db.get(CasoEscalamiento, caso_id)
    if caso is None:
        raise HTTPException(status_code=404, detail="Caso no encontrado")

    pedido = db.get(Pedido, caso.pedido_id)
    cliente = pedido.cliente if pedido else None
    responsable = (
        db.get(Usuario, caso.responsable_id) if caso.responsable_id else None
    )
    puede_responder = (
        caso.estado != EstadoCaso.CERRADO
        and (caso.responsable_id is None or caso.responsable_id == current.id)
    )
    return CasoDetalleRead(
        id=caso.id,
        pedido_id=caso.pedido_id,
        motivo=caso.motivo,
        prioridad=caso.prioridad,
        descripcion=caso.descripcion,
        fecha_apertura=caso.fecha_apertura,
        fecha_primera_accion=caso.fecha_primera_accion,
        responsable_id=caso.responsable_id,
        estado=caso.estado,
        fecha_cierre=caso.fecha_cierre,
        responsable_nombre=responsable.nombre_completo if responsable else None,
        pedido_codigo=pedido.codigo if pedido else "—",
        cliente_nombre=cliente.nombre if cliente else "—",
        cliente_telegram_vinculado=bool(
            cliente and cliente.telegram_chat_id
        ),
        puede_responder=puede_responder,
    )


@router.post("", response_model=CasoRead, dependencies=[Depends(require_operador)])
def crear(payload: CasoCreate, db: Session = Depends(get_db), current=Depends(require_operador)):
    return crear_caso(db, payload, usuario_id=current.id)


@router.post(
    "/{caso_id}/responder",
    response_model=CasoRespuestaRead,
    dependencies=[Depends(require_operador)],
)
def responder(
    caso_id: int,
    payload: CasoRespuestaCreate,
    db: Session = Depends(get_db),
    current=Depends(require_operador),
):
    """Responde al cliente desde la plataforma (mismo flujo que Telegram).

    El primer operador que responde queda como responsable del caso.
    """
    try:
        caso, com, envio = responder_caso(
            db, caso_id, payload.contenido, usuario_id=current.id,
        )
    except CasoError as exc:
        raise _http_error(exc)

    aviso = None
    if not envio.ok:
        aviso = (
            "El mensaje quedó registrado pero no se pudo entregar por "
            f"Telegram: {envio.error or 'error desconocido'}."
        )
    return CasoRespuestaRead(
        message=serializar_comunicacion(com),
        caso_id=caso.id,
        caso_estado=caso.estado,
        enviado=envio.ok,
        aviso=aviso,
    )


@router.post(
    "/{caso_id}/cerrar",
    response_model=CasoCierreRead,
    dependencies=[Depends(require_operador)],
)
def cerrar(
    caso_id: int,
    db: Session = Depends(get_db),
    current=Depends(require_operador),
):
    """Cierra el caso y avisa al cliente por el canal disponible."""
    try:
        caso, com = cerrar_caso(db, caso_id, usuario_id=current.id)
    except CasoError as exc:
        raise _http_error(exc)

    aviso = None
    if com is not None and com.estado_entrega not in {"SENT", None}:
        aviso = (
            "El caso se cerró, pero el aviso al cliente no se pudo entregar "
            f"por Telegram: {com.error_envio or 'error desconocido'}."
        )
    return CasoCierreRead(caso=CasoRead.model_validate(caso), aviso=aviso)


@router.patch("/{caso_id}", response_model=CasoRead, dependencies=[Depends(require_operador)])
def actualizar(
    caso_id: int,
    payload: CasoUpdate,
    db: Session = Depends(get_db),
    current=Depends(require_operador),
):
    return actualizar_caso(db, caso_id, payload, usuario_id=current.id)
