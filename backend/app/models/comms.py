"""Plantillas, comunicaciones, alertas, imprevistos y casos de escalamiento.

Nota sobre cascadas en SQL Server:
`pedido_item` cascadea desde `pedido`. Por eso, cualquier tabla que también
cascadee directamente desde `pedido` NO puede tener cascada adicional vía
`pedido_item` (SQL Server rechaza con error 1785). En esas tablas,
las FK a `pedido_item` e `item_hito` quedan como NO ACTION (default).
"""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    Unicode,
    UnicodeText,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base_mixins import AuditUserMixin, TimestampMixin


class Canal(str, enum.Enum):
    WHATSAPP = "WHATSAPP"
    EMAIL = "EMAIL"
    WEB = "WEB"


class DireccionComunicacion(str, enum.Enum):
    ENTRANTE = "ENTRANTE"
    SALIENTE = "SALIENTE"


class AutorComunicacion(str, enum.Enum):
    AGENTE = "AGENTE"
    HUMANO = "HUMANO"
    CLIENTE = "CLIENTE"


class Sentimiento(str, enum.Enum):
    NEUTRO = "NEUTRO"
    POSITIVO = "POSITIVO"
    NEGATIVO = "NEGATIVO"


class TipoAlerta(str, enum.Enum):
    RETRASO_LEVE = "RETRASO_LEVE"
    RETRASO_CRITICO = "RETRASO_CRITICO"
    IMPREVISTO = "IMPREVISTO"
    SILENCIO_CLIENTE = "SILENCIO_CLIENTE"
    FALTA_RESPUESTA = "FALTA_RESPUESTA"


class SeveridadAlerta(str, enum.Enum):
    BAJA = "BAJA"
    MEDIA = "MEDIA"
    ALTA = "ALTA"
    CRITICA = "CRITICA"


class EstadoAlerta(str, enum.Enum):
    ABIERTA = "ABIERTA"
    ATENDIDA = "ATENDIDA"
    CERRADA = "CERRADA"
    IGNORADA = "IGNORADA"


class TipoImprevisto(str, enum.Enum):
    OPERATIVO = "OPERATIVO"
    ADUANERO = "ADUANERO"
    DAÑO = "DAÑO"
    AGOTADO = "AGOTADO"
    OTRO = "OTRO"


class EstadoImprevisto(str, enum.Enum):
    ABIERTO = "ABIERTO"
    EN_PROCESO = "EN_PROCESO"
    RESUELTO = "RESUELTO"
    CERRADO = "CERRADO"


class MotivoEscalamiento(str, enum.Enum):
    RECLAMO = "RECLAMO"
    TONO_NEGATIVO = "TONO_NEGATIVO"
    ENTREGA_PARCIAL = "ENTREGA_PARCIAL"
    IMPREVISTO = "IMPREVISTO"
    RETRASO_CRITICO = "RETRASO_CRITICO"
    FALTA_RESPUESTA = "FALTA_RESPUESTA"
    OTRO = "OTRO"


class PrioridadCaso(str, enum.Enum):
    BAJA = "BAJA"
    MEDIA = "MEDIA"
    ALTA = "ALTA"
    CRITICA = "CRITICA"


class EstadoCaso(str, enum.Enum):
    ABIERTO = "ABIERTO"
    EN_PROCESO = "EN_PROCESO"
    RESUELTO = "RESUELTO"
    CERRADO = "CERRADO"


class PlantillaMensaje(Base, TimestampMixin, AuditUserMixin):
    __tablename__ = "plantilla_mensaje"
    __table_args__ = (UniqueConstraint("codigo", name="uq_plantilla_codigo"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(Unicode(60), nullable=False)
    nombre: Mapped[str] = mapped_column(Unicode(160), nullable=False)
    canal: Mapped[Canal] = mapped_column(SAEnum(Canal, native_enum=False, length=20), nullable=False)
    evento: Mapped[str] = mapped_column(Unicode(80), nullable=False, index=True)
    cuerpo: Mapped[str] = mapped_column(UnicodeText, nullable=False)
    whatsapp_template_id: Mapped[str | None] = mapped_column(Unicode(80), nullable=True)
    idioma: Mapped[str] = mapped_column(Unicode(10), nullable=False, default="es_PE")
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Comunicacion(Base, TimestampMixin, AuditUserMixin):
    __tablename__ = "comunicacion"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # FK a pedido: NO ACTION (evita ruta extra hacia pedido; las cascadas
    # se gestionan desde alerta/imprevisto/pedido_item)
    pedido_id: Mapped[int | None] = mapped_column(
        ForeignKey("pedido.id"), nullable=True, index=True
    )
    pedido_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("pedido_item.id"), nullable=True
    )
    direccion: Mapped[DireccionComunicacion] = mapped_column(
        SAEnum(DireccionComunicacion, native_enum=False, length=10), nullable=False, index=True
    )
    canal: Mapped[Canal] = mapped_column(
        SAEnum(Canal, native_enum=False, length=20), nullable=False, index=True
    )
    contenido: Mapped[str] = mapped_column(UnicodeText, nullable=False)
    intencion_detectada: Mapped[str | None] = mapped_column(Unicode(60), nullable=True)
    sentimiento: Mapped[Sentimiento | None] = mapped_column(
        SAEnum(Sentimiento, native_enum=False, length=20), nullable=True
    )
    autor: Mapped[AutorComunicacion] = mapped_column(
        SAEnum(AutorComunicacion, native_enum=False, length=20), nullable=False
    )
    usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuario.id"), nullable=True
    )
    plantilla_id: Mapped[int | None] = mapped_column(
        ForeignKey("plantilla_mensaje.id"), nullable=True
    )
    estado_entrega: Mapped[str | None] = mapped_column(Unicode(40), nullable=True)
    whatsapp_message_id: Mapped[str | None] = mapped_column(
        Unicode(120), nullable=True, unique=True
    )
    escalado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    # FK a caso_escalamiento: NO ACTION (rompe el ciclo con caso.comunicacion_origen_id)
    caso_id: Mapped[int | None] = mapped_column(
        ForeignKey("caso_escalamiento.id"), nullable=True
    )
    fecha: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

    # Columnas de outbox (Fase 5)
    intentos_envio: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    proximo_intento: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    error_envio: Mapped[str | None] = mapped_column(Unicode(500), nullable=True)
    enviado_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    pedido = relationship("Pedido")
    caso = relationship("CasoEscalamiento", foreign_keys=[caso_id])


class Alerta(Base, TimestampMixin, AuditUserMixin):
    __tablename__ = "alerta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tipo: Mapped[TipoAlerta] = mapped_column(
        SAEnum(TipoAlerta, native_enum=False, length=30), nullable=False, index=True
    )
    pedido_id: Mapped[int] = mapped_column(
        ForeignKey("pedido.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # FK a pedido_item: NO ACTION (evita ruta extra pedido → pedido_item → alerta)
    pedido_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("pedido_item.id"), nullable=True
    )
    # FK a item_hito: NO ACTION (mismo motivo)
    item_hito_id: Mapped[int | None] = mapped_column(
        ForeignKey("item_hito.id"), nullable=True
    )
    severidad: Mapped[SeveridadAlerta] = mapped_column(
        SAEnum(SeveridadAlerta, native_enum=False, length=10), nullable=False
    )
    mensaje: Mapped[str] = mapped_column(Unicode(500), nullable=False)
    estado: Mapped[EstadoAlerta] = mapped_column(
        SAEnum(EstadoAlerta, native_enum=False, length=20),
        nullable=False,
        default=EstadoAlerta.ABIERTA,
        index=True,
    )
    fecha_deteccion: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    fecha_atencion: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    pedido = relationship("Pedido")


class Imprevisto(Base, TimestampMixin, AuditUserMixin):
    __tablename__ = "imprevisto"
    __table_args__ = (
        CheckConstraint(
            "(estado NOT IN ('RESUELTO','CERRADO')) OR (fecha_resolucion IS NOT NULL)",
            name="ck_imprevisto_resolucion_required",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pedido_id: Mapped[int] = mapped_column(
        ForeignKey("pedido.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # FK a pedido_item: NO ACTION (evita ruta extra pedido → pedido_item → imprevisto)
    pedido_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("pedido_item.id"), nullable=True
    )
    tipo: Mapped[TipoImprevisto] = mapped_column(
        SAEnum(TipoImprevisto, native_enum=False, length=20), nullable=False, index=True
    )
    descripcion: Mapped[str] = mapped_column(UnicodeText, nullable=False)
    fecha_deteccion: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    fecha_resolucion: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    responsable_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuario.id"), nullable=True
    )
    resolucion: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    estado: Mapped[EstadoImprevisto] = mapped_column(
        SAEnum(EstadoImprevisto, native_enum=False, length=20),
        nullable=False,
        default=EstadoImprevisto.ABIERTO,
        index=True,
    )

    pedido = relationship("Pedido")


class CasoEscalamiento(Base, TimestampMixin, AuditUserMixin):
    __tablename__ = "caso_escalamiento"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pedido_id: Mapped[int] = mapped_column(
        ForeignKey("pedido.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # FK a comunicacion: NO ACTION (rompe el ciclo con comunicacion.caso_id)
    comunicacion_origen_id: Mapped[int | None] = mapped_column(
        ForeignKey("comunicacion.id"), nullable=True
    )
    motivo: Mapped[MotivoEscalamiento] = mapped_column(
        SAEnum(MotivoEscalamiento, native_enum=False, length=30), nullable=False, index=True
    )
    prioridad: Mapped[PrioridadCaso] = mapped_column(
        SAEnum(PrioridadCaso, native_enum=False, length=10), nullable=False, default=PrioridadCaso.MEDIA
    )
    descripcion: Mapped[str] = mapped_column(UnicodeText, nullable=False)
    fecha_apertura: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    fecha_primera_accion: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    responsable_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuario.id"), nullable=True
    )
    estado: Mapped[EstadoCaso] = mapped_column(
        SAEnum(EstadoCaso, native_enum=False, length=20),
        nullable=False,
        default=EstadoCaso.ABIERTO,
        index=True,
    )
    fecha_cierre: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    pedido = relationship("Pedido")