"""Datos demo para poblar el dashboard (Fase A).

Historia demo (coherente con los pedidos de `scripts.test_data`):

- **PD-2025-0001** (AirPods, stock): hitos completados a tiempo → ítem listo →
  entrega COMPLETA entregada antes de la fecha prometida, todo conforme →
  pedido CERRADO. Alimenta *entregas a tiempo* y *entregas sin observaciones*.
- **PD-2025-0002** (mixto): el AirPods queda listo → entrega PARCIAL autorizada
  por el ADMIN (quién, cuándo, por qué) con una observación; el iPhone sigue
  en importación (4 hitos completados, 3 pendientes/atrados). Alimenta
  *% entregas parciales*.
- **PD-2025-0003** (importación): en curso; 2 hitos completados muy recientes
  (el motor de reglas los notifica) + hitos atrasados que generan alertas.
- **Comunicaciones entrantes**: 3 consultas (no escaladas) + 1 reclamo
  escalado a caso → alimenta *tasa de resolución automática*.
- **Caso RECLAMO** resuelto con primera acción humana a las 3.5 h →
  alimenta *tiempo de respuesta de escalados*.
- **Imprevistos**: aduanero resuelto en 3 días + operativo abierto →
  alimenta *resolución de imprevistos*.
- Al final se ejecuta el **motor de reglas** (comunicaciones/alertas/casos
  reales), el **outbox** (dry-run) y el **sync dimensional** (`fact_*`).

Ejecutar: `python -m scripts.demo_dashboard_data` (solo si APP_ENV != 'production').
Idempotente: si ya hay entregas registradas, no hace nada.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import (
    Alerta,
    AutorComunicacion,
    Canal,
    CasoEscalamiento,
    Comunicacion,
    DireccionComunicacion,
    Entrega,
    EstadoAlerta,
    EstadoCaso,
    EstadoHito,
    EstadoImprevisto,
    EstadoItem,
    HitoCatalogo,
    Imprevisto,
    ItemHito,
    MotivoEscalamiento,
    Pedido,
    PedidoItem,
    PrioridadCaso,
    ResultadoConformidad,
    Sentimiento,
    TipoAlerta,
    TipoEntrega,
    TipoImprevisto,
    Usuario,
)
from app.schemas.entrega import ConformidadItemIn, EntregaCreate
from app.services.entrega_service import completar_entrega, crear_entrega
from app.services.fact_sync_service import FactSyncService
from app.services.outbox_worker import OutboxWorker
from app.services.pedido_service import recompute_pedido_estado
from app.services.rule_engine import RuleEngine


def _now() -> datetime:
    return datetime.utcnow()


def _hitos_del_item(db: Session, pedido_item_id: int) -> list[ItemHito]:
    return db.scalars(
        select(ItemHito)
        .join(HitoCatalogo, HitoCatalogo.id == ItemHito.hito_id)
        .where(ItemHito.pedido_item_id == pedido_item_id)
        .order_by(HitoCatalogo.orden)
    ).all()


def _completar(ih: ItemHito, fecha_real: datetime, *, horas_notif: float | None) -> None:
    """Marca un hito COMPLETADO con fecha notificación controlada (KPI oportuno)."""
    if ih.estado == EstadoHito.COMPLETADO:
        return
    ih.fecha_real = fecha_real
    ih.estado = EstadoHito.COMPLETADO
    if horas_notif is not None:
        ih.notificado_cliente = True
        ih.fecha_notificacion = fecha_real + timedelta(hours=horas_notif)
    # `horas_notif=None` → queda sin notificar: el motor de reglas enviará
    # el AVISO_HITO consolidado en el paso de reglas.


def _recalcular_estado_item(db: Session, item: PedidoItem) -> None:
    pendientes = db.scalar(
        select(ItemHito).where(
            ItemHito.pedido_item_id == item.id,
            ItemHito.estado != EstadoHito.COMPLETADO,
        )
    )
    item.estado = (
        EstadoItem.LISTO_PARA_ENTREGA if pendientes is None else EstadoItem.EN_PROCESO
    )


def _comm_entrante(
    db: Session,
    pedido: Pedido,
    contenido: str,
    *,
    intencion: str,
    sentimiento: Sentimiento,
    fecha: datetime,
    caso_id: int | None = None,
) -> Comunicacion | None:
    existe = db.scalar(
        select(Comunicacion.id).where(
            Comunicacion.pedido_id == pedido.id,
            Comunicacion.direccion == DireccionComunicacion.ENTRANTE,
            Comunicacion.contenido == contenido,
        )
    )
    if existe is not None:
        return None
    com = Comunicacion(
        pedido_id=pedido.id,
        direccion=DireccionComunicacion.ENTRANTE,
        canal=Canal.WHATSAPP,
        contenido=contenido,
        intencion_detectada=intencion,
        sentimiento=sentimiento,
        autor=AutorComunicacion.CLIENTE,
        fecha=fecha,
        escalado=caso_id is not None,
        caso_id=caso_id,
    )
    db.add(com)
    db.flush()
    return com


def run() -> None:
    settings = get_settings()
    if settings.APP_ENV.lower() == "production":
        raise SystemExit("demo_dashboard_data no corre en producción.")

    db = SessionLocal()
    try:
        if db.scalar(select(Entrega.id).limit(1)) is not None:
            print("[demo] Ya hay entregas registradas — nada que hacer (idempotente).")
            return

        now = _now()
        admin = db.scalar(select(Usuario).where(Usuario.email == "admin@poluximport.pe"))
        admin_id = admin.id if admin else None

        def pedido(codigo: str) -> Pedido:
            p = db.scalar(select(Pedido).where(Pedido.codigo == codigo))
            if p is None:
                raise SystemExit(f"[demo] Falta el pedido {codigo} — ejecuta scripts.test_data antes.")
            return p

        def items(p: Pedido) -> list[PedidoItem]:
            return db.scalars(
                select(PedidoItem).where(PedidoItem.pedido_id == p.id).order_by(PedidoItem.id)
            ).all()

        p1, p2, p3 = pedido("PD-2025-0001"), pedido("PD-2025-0002"), pedido("PD-2025-0003")

        # ------------------------------------------------------------------
        # 1. Hitos completados (con fecha de notificación controlada para el
        #    KPI FREQ_ACTUALIZACION_CLIENTE: 9 de 10 oportunas ≈ 90%)
        # ------------------------------------------------------------------
        it1 = items(p1)[0]                      # AirPods (stock, 2 hitos)
        it2a, it2b = items(p2)                  # iPhone (import, 7) + AirPods (stock, 2)
        it3a, it3b = items(p3)                  # MacBook (import, 7) + iPhone (import, 9)

        h = _hitos_del_item(db, it1.id)
        _completar(h[0], p1.fecha_ingreso + timedelta(days=1), horas_notif=1.0)
        _completar(h[1], p1.fecha_ingreso + timedelta(days=1, hours=6), horas_notif=1.5)

        h = _hitos_del_item(db, it2b.id)
        _completar(h[0], p2.fecha_ingreso + timedelta(days=2), horas_notif=0.5)
        _completar(h[1], p2.fecha_ingreso + timedelta(days=3), horas_notif=1.0)

        h = _hitos_del_item(db, it2a.id)
        _completar(h[0], p2.fecha_ingreso + timedelta(days=2), horas_notif=1.0)
        _completar(h[1], p2.fecha_ingreso + timedelta(days=3), horas_notif=1.0)
        _completar(h[2], p2.fecha_ingreso + timedelta(days=4), horas_notif=8.0)  # tardía
        _completar(h[3], p2.fecha_ingreso + timedelta(days=5), horas_notif=1.0)
        # h[4..6] quedan PENDIENTE/atrados → alimentan alertas de retraso

        h = _hitos_del_item(db, it3a.id)
        # Sin notificación manual: el motor de reglas enviará AVISO_HITO
        _completar(h[0], now - timedelta(hours=1), horas_notif=None)
        _completar(h[1], now - timedelta(minutes=45), horas_notif=None)

        for item in (it1, it2a, it2b, it3a, it3b):
            _recalcular_estado_item(db, item)
        for p in (p1, p2, p3):
            recompute_pedido_estado(db, p)
        db.commit()

        # ------------------------------------------------------------------
        # 2. Comunicaciones entrantes (cliente) — 3 consultas + 1 reclamo
        # ------------------------------------------------------------------
        _comm_entrante(
            db, p1,
            "Buenas, ¿ya está listo mi pedido? ¿Cuándo llega a mi domicilio?",
            intencion="ESTADO_PEDIDO", sentimiento=Sentimiento.NEUTRO,
            fecha=now - timedelta(days=1),
        )
        _comm_entrante(
            db, p2,
            "Hola, ¿cuánto falta para que llegue el MacBook? Necesito una fecha precisa.",
            intencion="CONSULTA_GENERAL", sentimiento=Sentimiento.NEUTRO,
            fecha=now - timedelta(days=2),
        )
        _comm_entrante(
            db, p3,
            "¿Ya pasó por la aduana? Llevo esperando bastante y nadie me escribe.",
            intencion="RETRASO", sentimiento=Sentimiento.NEUTRO,
            fecha=now - timedelta(days=2, hours=3),
        )
        db.commit()

        # ------------------------------------------------------------------
        # 3. Caso RECLAMO resuelto con primera acción humana (3.5 h)
        #    + reclamo entrante vinculado (escala, no resuelve)
        # ------------------------------------------------------------------
        caso_existente = db.scalar(
            select(CasoEscalamiento).where(
                CasoEscalamiento.pedido_id == p2.id,
                CasoEscalamiento.motivo == MotivoEscalamiento.RECLAMO,
            )
        )
        if caso_existente is None:
            apertura = now - timedelta(days=4)
            caso = CasoEscalamiento(
                pedido_id=p2.id,
                motivo=MotivoEscalamiento.RECLAMO,
                prioridad=PrioridadCaso.ALTA,
                descripcion=(
                    "Cliente molesto por la demora en la importación del MacBook. "
                    "Se contactó al proveedor y se actualizó la fecha estimada."
                ),
                fecha_apertura=apertura,
                fecha_primera_accion=apertura + timedelta(hours=3, minutes=30),
                responsable_id=admin_id,
                estado=EstadoCaso.RESUELTO,
                fecha_cierre=apertura + timedelta(days=1),
                created_by_id=admin_id,
                updated_by_id=admin_id,
            )
            db.add(caso)
            db.flush()
            _comm_entrante(
                db, p2,
                "Estoy muy molesto, el pedido lleva demasiado tiempo y nadie me contesta.",
                intencion="RECLAMO", sentimiento=Sentimiento.NEGATIVO,
                fecha=now - timedelta(days=4), caso_id=caso.id,
            )
            db.commit()

        # ------------------------------------------------------------------
        # 4. Imprevistos: 1 resuelto (3 días) + 1 abierto
        # ------------------------------------------------------------------
        if db.scalar(select(Imprevisto.id).limit(1)) is None:
            db.add_all([
                Imprevisto(
                    pedido_id=p3.id,
                    tipo=TipoImprevisto.ADUANERO,
                    descripcion="Retraso en revisión aduanera: selección de archivo para documentación adicional.",
                    fecha_deteccion=now - timedelta(days=6),
                    fecha_resolucion=now - timedelta(days=3),
                    responsable_id=admin_id,
                    resolucion="Se presentó la documentación solicitada y la carga fue liberada.",
                    estado=EstadoImprevisto.RESUELTO,
                    created_by_id=admin_id,
                    updated_by_id=admin_id,
                ),
                Imprevisto(
                    pedido_id=p2.id,
                    tipo=TipoImprevisto.OPERATIVO,
                    descripcion="Retraso en la consolidación de carga aérea en el almacén de origen.",
                    fecha_deteccion=now - timedelta(days=2),
                    estado=EstadoImprevisto.EN_PROCESO,
                    created_by_id=admin_id,
                    updated_by_id=admin_id,
                ),
            ])
            db.commit()

        # ------------------------------------------------------------------
        # 5. Motor de reglas: bienvenida, avisos de hito, retrasos, imprevisto,
        #    entrega lista → comunicaciones PENDING + alertas + casos reales
        # ------------------------------------------------------------------
        counts = RuleEngine(db).run_all()
        print(f"[demo] motor_de_reglas: {counts}")

        # ------------------------------------------------------------------
        # 6. Outbox (dry-run): PENDING → SENT con wamid sintético
        # ------------------------------------------------------------------
        ob = OutboxWorker(db).process_batch()
        print(f"[demo] outbox: {ob}")

        # ------------------------------------------------------------------
        # 7. Entregas (reutiliza los servicios: valida las reglas de negocio)
        # ------------------------------------------------------------------
        # 7a. Pedido 1: entrega COMPLETA, a tiempo, todo conforme
        e1 = crear_entrega(
            db,
            EntregaCreate(
                pedido_id=p1.id,
                tipo=TipoEntrega.COMPLETA,
                modalidad=p1.modalidad_entrega,
                fecha_programada=now - timedelta(days=1),
            ),
            usuario_id=admin_id,
        )
        completar_entrega(
            db,
            e1.id,
            fecha_real=now - timedelta(days=1, hours=4),
            conformidades=[
                ConformidadItemIn(
                    pedido_item_id=it1.id,
                    checklist_caja_sellada=True,
                    checklist_modelo_ok=True,
                    checklist_color_ok=True,
                    checklist_capacidad_ok=True,
                    checklist_imei_ok=True,
                    checklist_accesorios_ok=True,
                    resultado=ResultadoConformidad.CONFORME,
                ),
            ],
            usuario_id=admin_id,
        )
        print("[demo] entrega COMPLETA registrada (PD-2025-0001)")

        # 7b. Pedido 2: entrega PARCIAL autorizada por ADMIN, con observación
        e2 = crear_entrega(
            db,
            EntregaCreate(
                pedido_id=p2.id,
                tipo=TipoEntrega.PARCIAL,
                modalidad=p2.modalidad_entrega,
                fecha_programada=now - timedelta(hours=20),
                pedido_item_ids=[it2b.id],
                autorizada_por_id=admin_id,
                fecha_autorizacion=now - timedelta(days=1),
                motivo_parcial=(
                    "Cliente necesita los AirPods para un evento; el iPhone "
                    "sigue en importación. Parcial autorizada por ADMIN."
                ),
            ),
            usuario_id=admin_id,
        )
        completar_entrega(
            db,
            e2.id,
            fecha_real=now - timedelta(hours=20),
            conformidades=[
                ConformidadItemIn(
                    pedido_item_id=it2b.id,
                    checklist_caja_sellada=True,
                    checklist_modelo_ok=True,
                    checklist_color_ok=True,
                    checklist_capacidad_ok=False,
                    checklist_imei_ok=False,
                    checklist_accesorios_ok=True,
                    resultado=ResultadoConformidad.CON_OBSERVACIONES,
                    observaciones="Rayón leve en la tapa del estuche (evidencia fotográfica adjunta).",
                ),
            ],
            usuario_id=admin_id,
        )
        print("[demo] entrega PARCIAL autorizada registrada (PD-2025-0002)")

        # ------------------------------------------------------------------
        # 8. Atender 1 alerta de retraso (demo de bandeja con alertas atendidas)
        # ------------------------------------------------------------------
        alerta = db.scalar(
            select(Alerta).where(Alerta.tipo == TipoAlerta.RETRASO_LEVE).limit(1)
        )
        if alerta is not None and alerta.estado == EstadoAlerta.ABIERTA:
            alerta.estado = EstadoAlerta.ATENDIDA
            alerta.fecha_atencion = now - timedelta(hours=12)
            db.commit()

        # ------------------------------------------------------------------
        # 9. Sync dimensional: llena fact_* para las vistas KPI
        # ------------------------------------------------------------------
        facts = FactSyncService(db).sync_all()
        print(f"[demo] fact_sync: {facts}")

        # ------------------------------------------------------------------
        # 10. Resumen
        # ------------------------------------------------------------------
        resumen = {
            "comunicaciones": db.scalar(select(Comunicacion.id).limit(1)) is not None,
            "alertas": db.scalar(select(Alerta.id).limit(1)) is not None,
            "casos": db.scalar(select(CasoEscalamiento.id).limit(1)) is not None,
            "imprevistos": db.scalar(select(Imprevisto.id).limit(1)) is not None,
            "entregas": db.scalar(select(Entrega.id).limit(1)) is not None,
        }
        print(f"[demo] OK — datos presentes: {resumen}")
        print("[demo] Verifica: GET /api/v1/dashboard/resumen (semáforos con valores)")
    finally:
        db.close()


if __name__ == "__main__":
    run()
