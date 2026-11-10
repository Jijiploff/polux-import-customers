"""Registra todos los modelos en `Base.metadata` para Alembic y para el dominio."""
from app.models.core import (  # noqa: F401
    Cliente,
    Contrato,
    Producto,
    Rol,
    RolCodigo,
    Usuario,
    UsuarioRol,
    CategoriaProducto,
)
from app.models.orders import (  # noqa: F401
    EstadoHito,
    EstadoIngreso,
    EstadoItem,
    EstadoPedido,
    HitoCatalogo,
    ItemHito,
    ModalidadEntrega,
    OrigenItem,
    Pedido,
    PedidoItem,
    SlaHito,
)
from app.models.comms import (  # noqa: F401
    Alerta,
    AutorComunicacion,
    Canal,
    CasoEscalamiento,
    Comunicacion,
    DireccionComunicacion,
    EstadoAlerta,
    EstadoCaso,
    EstadoImprevisto,
    Imprevisto,
    MotivoEscalamiento,
    PlantillaMensaje,
    PrioridadCaso,
    Sentimiento,
    SeveridadAlerta,
    TipoAlerta,
    TipoImprevisto,
)
from app.models.delivery import (  # noqa: F401
    Conformidad,
    Entrega,
    EntregaItem,
    EstadoEntrega,
    ReglaNegocio,
    ResultadoConformidad,
    TipoEntrega,
    TipoValorRegla,
)
from app.models.analytics import (  # noqa: F401
    DimCanal,
    DimHito,
    DimKpi,
    DimProducto,
    DimTiempo,
    DimTipoImprevisto,
    FactComunicacion,
    FactEntrega,
    FactEscalamiento,
    FactHitoPedido,
    FactImprevisto,
    NivelKpi,
)

__all__ = [
    # core
    "Cliente", "Producto", "Contrato", "Rol", "RolCodigo", "Usuario", "UsuarioRol",
    "CategoriaProducto",
    # orders
    "Pedido", "PedidoItem", "HitoCatalogo", "SlaHito", "ItemHito",
    "EstadoIngreso", "EstadoPedido", "ModalidadEntrega", "OrigenItem", "EstadoItem", "EstadoHito",
    # comms
    "PlantillaMensaje", "Comunicacion", "Alerta", "Imprevisto", "CasoEscalamiento",
    "Canal", "DireccionComunicacion", "AutorComunicacion", "Sentimiento",
    "TipoAlerta", "SeveridadAlerta", "EstadoAlerta",
    "TipoImprevisto", "EstadoImprevisto", "MotivoEscalamiento", "PrioridadCaso", "EstadoCaso",
    # delivery
    "Entrega", "EntregaItem", "Conformidad", "ReglaNegocio",
    "TipoEntrega", "EstadoEntrega", "ResultadoConformidad", "TipoValorRegla",
    # analytics
    "DimTiempo", "DimCanal", "DimTipoImprevisto", "DimProducto", "DimHito", "DimKpi",
    "FactHitoPedido", "FactComunicacion", "FactEscalamiento", "FactImprevisto", "FactEntrega",
    "NivelKpi",
]