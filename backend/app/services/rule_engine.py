"""Motor de reglas Customers: evaluación periódica de §6 del plan.

Cada método `_rule_*` es idempotente: revisar dos veces seguidas no duplica
alertas, casos ni comunicaciones. `run_all()` agrupa la ejecución completa.
Las comunicaciones se encolan con estado_entrega="PENDING" (Fase 5 las envía).

Cuando una regla crea un `CasoEscalamiento`, se notifica al operador por
Telegram (si `TELEGRAM_OPERATOR_CHAT_ID` está configurado). La importación de
`notify_operator_new_caso` es **local** para evitar un ciclo de imports:
    rule_engine → telegram_handler → agent_service → rule_engine
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models import (
    Alerta,
    AutorComunicacion,
    CasoEscalamiento,
    Comunicacion,
    DireccionComunicacion,
    EstadoAlerta,
    EstadoCaso,
    EstadoHito,
    EstadoImprevisto,
    EstadoItem,
    EstadoPedido,
    Imprevisto,
    ItemHito,
    MotivoEscalamiento,
    Pedido,
    PedidoItem,
    PrioridadCaso,
    ReglaNegocio,
    SeveridadAlerta,
    TipoAlerta,
)
from app.services.notification_service import NotificationService

logger = get_logger("rule_engine")


def _notify_operator(caso: CasoEscalamiento, pedido: Pedido) -> None:
    """Notifica al operador por Telegram sobre un caso recién creado.

    Import local para romper el ciclo:
        rule_engine ← agent_service ← telegram_handler ← rule_engine

    Nunca lanza excepción: si Telegram está deshabilitado o falla, sólo
    se registra un log. El flujo del motor de reglas continúa.
    """
    try:
        from app.services.telegram_handler import notify_operator_new_caso

        notify_operator_new_caso(caso, pedido)
    except Exception:
        logger.exception(
            "notify_operator_failed caso_id=%s pedido_id=%s",
            caso.id if caso else None,
            pedido.id if pedido else None,
        )


class RuleEngine:
    """Motor de reglas parametrizable. Una instancia por ejecución."""

    def __init__(self, db: Session, *, now: datetime | None = None):
        self.db = db
        self.now = now or datetime.utcnow()
        self.notifier = NotificationService(db)
        self._counts: dict[str, int] = {}
        self._rules: list[tuple[str, Callable[[], None]]] = [
            ("bienvenida", self._rule_bienvenida),
            ("aviso_hito", self._rule_aviso_hito),
            ("actualizacion_periodica", self._rule_actualizacion_periodica),
            ("retraso_leve", self._rule_retraso_leve),
            ("retraso_critico", self._rule_retraso_critico),
            ("imprevisto", self._rule_imprevisto),
            ("silencio_cliente", self._rule_silencio_cliente),
            ("reclamo_tono_negativo", self._rule_reclamo_tono_negativo),
            ("entrega_lista", self._rule_entrega_lista),
        ]

    # --------- API ---------
    def run_all(self) -> dict[str, int]:
        """Paso 1: recalcular atrasos. Paso 2: ejecutar reglas.

        `registrar_atrasos` es indispensable: sin él, ningún `ItemHito` pasaría
        a estado ATRASADO y las reglas `_rule_retraso_leve/_rule_retraso_critico`
        nunca dispararían.
        """
        from app.services.hito_service import registrar_atrasos

        self._counts = {}
        try:
            n = registrar_atrasos(self.db, ahora=self.now)
            self._counts["atrasos_detectados"] = n
        except Exception:
            logger.exception("registrar_atrasos_failed")
            self._counts["atrasos_detectados"] = -1

        for name, fn in self._rules:
            try:
                fn()
            except Exception as exc:
                logger.exception("rule_failed name=%s err=%s", name, exc)
                self._counts[name] = -1
        self.db.commit()
        logger.info("rule_engine_run counts=%s", self._counts)
        return dict(self._counts)

    def handle_partial_delivery_request(
        self, *, pedido_id: int, comunicacion_id: int | None = None
    ) -> CasoEscalamiento:
        """Regla 10: el agente NO decide entregas parciales. Solo informa y escala.

        Se invoca desde la Fase 4 (agente IA) al detectar `intencion=entrega_parcial`.
        Notifica al operador por Telegram.
        """
        pedido = self.db.get(Pedido, pedido_id)
        if pedido is None:
            raise ValueError(f"Pedido {pedido_id} no existe")

        self.notifier.send_from_template(
            codigo_plantilla="ESCALAMIENTO_CLIENTE",
            pedido=pedido,
            variables={"cliente_nombre": pedido.cliente.nombre},
        )
        caso = CasoEscalamiento(
            pedido_id=pedido.id,
            comunicacion_origen_id=comunicacion_id,
            motivo=MotivoEscalamiento.ENTREGA_PARCIAL,
            prioridad=PrioridadCaso.ALTA,
            descripcion=(
                "Cliente solicita entrega parcial. Requiere autorización humana "
                "expresa (quién, cuándo y por qué) antes de coordinar."
            ),
            fecha_apertura=self.now,
            estado=EstadoCaso.ABIERTO,
        )
        self.db.add(caso)
        self.db.commit()
        self.db.refresh(caso)
        _notify_operator(caso, pedido)
        return caso

    # --------- helpers ---------
    def _inc(self, name: str, n: int = 1) -> None:
        self._counts[name] = self._counts.get(name, 0) + n

    def _regla_int(self, codigo: str, default: int) -> int:
        regla = self.db.scalar(
            select(ReglaNegocio).where(
                ReglaNegocio.codigo == codigo, ReglaNegocio.activo == True
            )
        )
        if regla is None:
            return default
        try:
            return int(regla.valor)
        except (TypeError, ValueError):
            return default

    # =====================================================================
    # Reglas
    # =====================================================================

    def _rule_bienvenida(self) -> None:
        """Bienvenida al pedido verificado (idempotente)."""
        pedidos = self.db.scalars(
            select(Pedido).where(
                Pedido.estado_actual.not_in(
                    [
                        EstadoPedido.CERRADO,
                        EstadoPedido.CERRADO_CON_OBSERVACIONES,
                        EstadoPedido.CANCELADO,
                    ]
                )
            )
        ).all()

        for pedido in pedidos:
            if self.notifier.has_plantilla_for_pedido(pedido.id, "BIENVENIDA"):
                continue
            items = self.db.scalars(
                select(PedidoItem).where(PedidoItem.pedido_id == pedido.id)
            ).all()
            resumen = (
                ", ".join(f"{i.cantidad}x {i.descripcion_producto}" for i in items)
                or "(sin ítems)"
            )
            com = self.notifier.send_from_template(
                codigo_plantilla="BIENVENIDA",
                pedido=pedido,
                variables={
                    "cliente_nombre": pedido.cliente.nombre,
                    "pedido_codigo": pedido.codigo,
                    "items_resumen": resumen,
                    "fecha_prometida": pedido.fecha_prometida.strftime("%d/%m/%Y"),
                },
            )
            if com:
                self._inc("bienvenida")

    def _rule_aviso_hito(self) -> None:
        """Aviso de hitos completados, consolidado por pedido (idempotente)."""
        hitos_pendientes = self.db.scalars(
            select(ItemHito).where(
                ItemHito.estado == EstadoHito.COMPLETADO,
                ItemHito.notificado_cliente == False,
            )
        ).all()
        if not hitos_pendientes:
            return

        por_pedido: dict[int, list[ItemHito]] = {}
        for ih in hitos_pendientes:
            pedido_id = ih.item.pedido_id
            por_pedido.setdefault(pedido_id, []).append(ih)

        for pedido_id, hitos in por_pedido.items():
            pedido = self.db.get(Pedido, pedido_id)
            if pedido is None:
                continue
            hitos_txt = ", ".join(sorted({ih.hito.nombre for ih in hitos}))
            items_txt = ", ".join(sorted({ih.item.descripcion_producto for ih in hitos}))
            com = self.notifier.send_from_template(
                codigo_plantilla="AVISO_HITO",
                pedido=pedido,
                variables={
                    "cliente_nombre": pedido.cliente.nombre,
                    "pedido_codigo": pedido.codigo,
                    "hito_nombre": hitos_txt,
                    "items_afectados": items_txt,
                    "fecha_prometida": pedido.fecha_prometida.strftime("%d/%m/%Y"),
                },
            )
            if com is None:
                continue
            for ih in hitos:
                ih.notificado_cliente = True
                ih.fecha_notificacion = self.now
            self._inc("aviso_hito", len(hitos))

    def _rule_actualizacion_periodica(self) -> None:
        """Actualización proactiva si N días sin comunicación en pedido activo."""
        dias = self._regla_int("ACTUALIZACION_PERIODICA_DIAS", 3)
        umbral = self.now - timedelta(days=dias)
        pedidos = self.db.scalars(
            select(Pedido).where(
                Pedido.estado_actual.in_(
                    [
                        EstadoPedido.RECIBIDO,
                        EstadoPedido.EN_PROCESO,
                        EstadoPedido.EN_COORDINACION,
                    ]
                )
            )
        ).all()

        for pedido in pedidos:
            ultima = self.db.scalar(
                select(Comunicacion.fecha)
                .where(Comunicacion.pedido_id == pedido.id)
                .order_by(Comunicacion.fecha.desc())
                .limit(1)
            )
            referencia = ultima if ultima is not None else pedido.fecha_ingreso
            if referencia > umbral:
                continue

            com = self.notifier.send_from_template(
                codigo_plantilla="ACTUALIZACION_PERIODICA",
                pedido=pedido,
                variables={
                    "cliente_nombre": pedido.cliente.nombre,
                    "pedido_codigo": pedido.codigo,
                    "fecha_prometida": pedido.fecha_prometida.strftime("%d/%m/%Y"),
                },
            )
            if com:
                self._inc("actualizacion_periodica")

    def _rule_retraso_leve(self) -> None:
        """Retraso leve: `dias_atraso > 0` y ≤ umbral → aviso + alerta MEDIA."""
        umbral = self._regla_int("RETRASO_LEVE_DIAS", 2)
        hitos = self.db.scalars(
            select(ItemHito).where(
                ItemHito.estado == EstadoHito.ATRASADO,
                ItemHito.dias_atraso > 0,
                ItemHito.dias_atraso <= umbral,
                ItemHito.notificado_cliente == False,
            )
        ).all()

        for ih in hitos:
            if self._alerta_abierta_para_hito(ih.id, TipoAlerta.RETRASO_LEVE):
                continue
            pedido = ih.item.pedido
            com = self.notifier.send_from_template(
                codigo_plantilla="RETRASO_LEVE",
                pedido=pedido,
                variables={
                    "cliente_nombre": pedido.cliente.nombre,
                    "pedido_codigo": pedido.codigo,
                    "hito_nombre": ih.hito.nombre,
                    "fecha_estimada": (
                        ih.fecha_prevista + timedelta(days=2)
                    ).strftime("%d/%m/%Y")
                    if ih.fecha_prevista
                    else "",
                },
            )
            if com:
                ih.notificado_cliente = True
                ih.fecha_notificacion = self.now
                self.db.add(
                    Alerta(
                        tipo=TipoAlerta.RETRASO_LEVE,
                        pedido_id=pedido.id,
                        pedido_item_id=ih.pedido_item_id,
                        item_hito_id=ih.id,
                        severidad=SeveridadAlerta.MEDIA,
                        mensaje=f"Hito '{ih.hito.nombre}' con retraso leve ({ih.dias_atraso}d)",
                        estado=EstadoAlerta.ABIERTA,
                        fecha_deteccion=self.now,
                    )
                )
                self._inc("retraso_leve")

    def _rule_retraso_critico(self) -> None:
        """Retraso crítico: `> umbral` o fecha prometida en riesgo → alerta CRÍTICA + caso."""
        umbral = self._regla_int("RETRASO_CRITICO_DIAS", 5)
        dias_riesgo = self._regla_int("RIESGO_FECHA_PROMETIDA_DIAS", 2)

        # 1) Hitos con dias_atraso > umbral
        hitos = self.db.scalars(
            select(ItemHito).where(
                ItemHito.estado == EstadoHito.ATRASADO,
                ItemHito.dias_atraso > umbral,
            )
        ).all()
        pedidos_criticos: set[int] = {ih.item.pedido_id for ih in hitos}

        # 2) Pedidos cuya fecha prometida está en riesgo
        limite = self.now + timedelta(days=dias_riesgo)
        pedidos_riesgo = self.db.scalars(
            select(Pedido).where(
                Pedido.estado_actual.in_(
                    [EstadoPedido.RECIBIDO, EstadoPedido.EN_PROCESO]
                ),
                Pedido.fecha_prometida <= limite,
            )
        ).all()
        pedidos_criticos.update(p.id for p in pedidos_riesgo)

        for pedido_id in pedidos_criticos:
            if self._caso_abierto_para_pedido(
                pedido_id, MotivoEscalamiento.RETRASO_CRITICO
            ):
                continue
            pedido = self.db.get(Pedido, pedido_id)
            if pedido is None:
                continue

            self.notifier.send_from_template(
                codigo_plantilla="RETRASO_CRITICO",
                pedido=pedido,
                variables={
                    "cliente_nombre": pedido.cliente.nombre,
                    "pedido_codigo": pedido.codigo,
                },
            )
            self.db.add(
                Alerta(
                    tipo=TipoAlerta.RETRASO_CRITICO,
                    pedido_id=pedido_id,
                    severidad=SeveridadAlerta.CRITICA,
                    mensaje="Retraso crítico o fecha prometida en riesgo",
                    estado=EstadoAlerta.ABIERTA,
                    fecha_deteccion=self.now,
                )
            )
            caso = CasoEscalamiento(
                pedido_id=pedido_id,
                motivo=MotivoEscalamiento.RETRASO_CRITICO,
                prioridad=PrioridadCaso.CRITICA,
                descripcion=(
                    "Hito superó el SLA crítico o la fecha prometida está en riesgo."
                ),
                fecha_apertura=self.now,
                estado=EstadoCaso.ABIERTO,
            )
            self.db.add(caso)
            self.db.flush()
            _notify_operator(caso, pedido)
            self._inc("retraso_critico")

    def _rule_imprevisto(self) -> None:
        """Imprevisto abierto sin caso asociado → notificar y escalar."""
        imprevistos = self.db.scalars(
            select(Imprevisto).where(
                Imprevisto.estado.in_(
                    [EstadoImprevisto.ABIERTO, EstadoImprevisto.EN_PROCESO]
                )
            )
        ).all()
        for imp in imprevistos:
            if self._caso_abierto_para_pedido(
                imp.pedido_id, MotivoEscalamiento.IMPREVISTO
            ):
                continue
            pedido = self.db.get(Pedido, imp.pedido_id)
            if pedido is None:
                continue

            self.notifier.send_from_template(
                codigo_plantilla="IMPREVISTO",
                pedido=pedido,
                variables={
                    "cliente_nombre": pedido.cliente.nombre,
                    "pedido_codigo": pedido.codigo,
                },
            )
            self.db.add(
                Alerta(
                    tipo=TipoAlerta.IMPREVISTO,
                    pedido_id=pedido.id,
                    pedido_item_id=imp.pedido_item_id,
                    severidad=SeveridadAlerta.ALTA,
                    mensaje=f"Imprevisto {imp.tipo.value}: {imp.descripcion[:120]}",
                    estado=EstadoAlerta.ABIERTA,
                    fecha_deteccion=self.now,
                )
            )
            caso = CasoEscalamiento(
                pedido_id=pedido.id,
                motivo=MotivoEscalamiento.IMPREVISTO,
                prioridad=PrioridadCaso.ALTA,
                descripcion=f"Imprevisto registrado: {imp.descripcion}",
                fecha_apertura=self.now,
                estado=EstadoCaso.ABIERTO,
            )
            self.db.add(caso)
            self.db.flush()
            _notify_operator(caso, pedido)
            self._inc("imprevisto")

    def _rule_silencio_cliente(self) -> None:
        """Reintentos 24h y 48h; caso a las 72h sin respuesta."""
        h1 = self._regla_int("REINTENTO_1_HORAS", 24)
        h2 = self._regla_int("REINTENTO_2_HORAS", 48)
        h3 = self._regla_int("CASO_FALTA_RESPUESTA_HORAS", 72)

        pedidos = self.db.scalars(
            select(Pedido).where(
                Pedido.estado_actual == EstadoPedido.EN_COORDINACION
            )
        ).all()

        for pedido in pedidos:
            ultima_saliente = self.db.scalar(
                select(Comunicacion)
                .where(
                    Comunicacion.pedido_id == pedido.id,
                    Comunicacion.direccion == DireccionComunicacion.SALIENTE,
                )
                .order_by(Comunicacion.fecha.desc())
                .limit(1)
            )
            if ultima_saliente is None:
                continue

            ultima_entrante = self.db.scalar(
                select(Comunicacion.fecha)
                .where(
                    Comunicacion.pedido_id == pedido.id,
                    Comunicacion.direccion == DireccionComunicacion.ENTRANTE,
                    Comunicacion.autor == AutorComunicacion.CLIENTE,
                )
                .order_by(Comunicacion.fecha.desc())
                .limit(1)
            )
            if ultima_entrante and ultima_entrante > ultima_saliente.fecha:
                continue

            horas = (self.now - ultima_saliente.fecha).total_seconds() / 3600
            reintentos = self._contar_reintentos(pedido.id)

            if reintentos == 0 and horas >= h1:
                self.notifier.send_from_template(
                    codigo_plantilla="REINTENTO_24H",
                    pedido=pedido,
                    variables={
                        "cliente_nombre": pedido.cliente.nombre,
                        "pedido_codigo": pedido.codigo,
                    },
                )
                self._inc("reintento_24h")
            elif reintentos == 1 and horas >= h2:
                self.notifier.send_from_template(
                    codigo_plantilla="REINTENTO_48H",
                    pedido=pedido,
                    variables={
                        "cliente_nombre": pedido.cliente.nombre,
                        "pedido_codigo": pedido.codigo,
                    },
                )
                self._inc("reintento_48h")
            elif reintentos >= 2 and horas >= h3:
                if not self._caso_abierto_para_pedido(
                    pedido.id, MotivoEscalamiento.FALTA_RESPUESTA
                ):
                    caso = CasoEscalamiento(
                        pedido_id=pedido.id,
                        motivo=MotivoEscalamiento.FALTA_RESPUESTA,
                        prioridad=PrioridadCaso.ALTA,
                        descripcion="Cliente sin respuesta tras 2 reintentos.",
                        fecha_apertura=self.now,
                        estado=EstadoCaso.ABIERTO,
                    )
                    self.db.add(caso)
                    self.db.flush()
                    _notify_operator(caso, pedido)
                    self._inc("caso_falta_respuesta")

    def _rule_reclamo_tono_negativo(self) -> None:
        """Reclamos y tono negativo se escalan, no se intentan resolver."""
        comunicaciones = self.db.scalars(
            select(Comunicacion).where(
                Comunicacion.direccion == DireccionComunicacion.ENTRANTE,
                Comunicacion.autor == AutorComunicacion.CLIENTE,
                (
                    (Comunicacion.sentimiento == "NEGATIVO")
                    | (Comunicacion.intencion_detectada == "RECLAMO")
                ),
                Comunicacion.caso_id.is_(None),
            )
        ).all()

        for c in comunicaciones:
            if c.pedido_id is None:
                continue
            if self._caso_abierto_para_pedido(
                c.pedido_id, MotivoEscalamiento.RECLAMO
            ):
                continue
            motivo = (
                MotivoEscalamiento.RECLAMO
                if c.intencion_detectada == "RECLAMO"
                else MotivoEscalamiento.TONO_NEGATIVO
            )
            caso = CasoEscalamiento(
                pedido_id=c.pedido_id,
                comunicacion_origen_id=c.id,
                motivo=motivo,
                prioridad=PrioridadCaso.ALTA,
                descripcion=(
                    f"Comunicación entrante detectada como {motivo.value}. "
                    "Escalar sin resolver."
                ),
                fecha_apertura=self.now,
                estado=EstadoCaso.ABIERTO,
            )
            self.db.add(caso)
            self.db.flush()
            c.escalado = True
            c.caso_id = caso.id

            pedido = self.db.get(Pedido, c.pedido_id)
            if pedido is not None:
                _notify_operator(caso, pedido)
            self._inc("reclamo_escalado")

    def _rule_entrega_lista(self) -> None:
        """Cuando todos los ítems están LISTO_PARA_ENTREGA → coordinación."""
        candidatos = self.db.scalars(
            select(Pedido).where(
                Pedido.estado_actual.in_(
                    [EstadoPedido.RECIBIDO, EstadoPedido.EN_PROCESO]
                )
            )
        ).all()

        for pedido in candidatos:
            items = self.db.scalars(
                select(PedidoItem).where(PedidoItem.pedido_id == pedido.id)
            ).all()
            if not items:
                continue
            if not all(
                i.estado == EstadoItem.LISTO_PARA_ENTREGA for i in items
            ):
                continue
            pedido.estado_actual = EstadoPedido.LISTO_PARA_ENTREGA
            if self.notifier.has_plantilla_for_pedido(pedido.id, "ENTREGA_LISTA"):
                continue
            com = self.notifier.send_from_template(
                codigo_plantilla="ENTREGA_LISTA",
                pedido=pedido,
                variables={
                    "cliente_nombre": pedido.cliente.nombre,
                    "pedido_codigo": pedido.codigo,
                },
            )
            if com:
                pedido.estado_actual = EstadoPedido.EN_COORDINACION
                self._inc("entrega_lista")

    # --------- helpers de idempotencia ---------
    def _alerta_abierta_para_hito(
        self, item_hito_id: int, tipo: TipoAlerta
    ) -> bool:
        return (
            self.db.scalar(
                select(Alerta.id).where(
                    Alerta.item_hito_id == item_hito_id,
                    Alerta.tipo == tipo,
                    Alerta.estado == EstadoAlerta.ABIERTA,
                )
            )
            is not None
        )

    def _caso_abierto_para_pedido(
        self, pedido_id: int, motivo: MotivoEscalamiento
    ) -> bool:
        return (
            self.db.scalar(
                select(CasoEscalamiento.id).where(
                    CasoEscalamiento.pedido_id == pedido_id,
                    CasoEscalamiento.motivo == motivo,
                    CasoEscalamiento.estado.in_(
                        [EstadoCaso.ABIERTO, EstadoCaso.EN_PROCESO]
                    ),
                )
            )
            is not None
        )

    def _contar_reintentos(self, pedido_id: int) -> int:
        from app.models import PlantillaMensaje

        return (
            self.db.scalar(
                select(func.count(Comunicacion.id))
                .join(
                    PlantillaMensaje,
                    PlantillaMensaje.id == Comunicacion.plantilla_id,
                )
                .where(
                    Comunicacion.pedido_id == pedido_id,
                    PlantillaMensaje.evento == "REINTENTO_CONTACTO",
                )
            )
            or 0
        )