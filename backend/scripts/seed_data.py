"""Datos semilla: catálogos, RBAC, KPIs, reglas, plantillas.

Ejecutar: `python -m scripts.seed_data` (idempotente — inserta si no existe).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.db.session import SessionLocal
from app.core.security import hash_password
from app.models import (
    Canal,
    CategoriaProducto,
    Cliente,
    DimCanal,
    DimHito,
    DimKpi,
    DimProducto,
    DimTiempo,
    DimTipoImprevisto,
    EstadoItem,
    EstadoPedido,
    HitoCatalogo,
    ModalidadEntrega,
    OrigenItem,
    Pedido,
    PedidoItem,
    PlantillaMensaje,
    Producto,
    ReglaNegocio,
    Rol,
    RolCodigo,
    SlaHito,
    TipoValorRegla,
    Usuario,
    UsuarioRol,
)


def _get_or_create(db, model, filter_kwargs, **values):
    obj = db.scalar(select(model).filter_by(**filter_kwargs))
    if obj is None:
        obj = model(**filter_kwargs, **values)
        db.add(obj)
        db.flush()
    return obj


def seed_rbac(db) -> None:
    rol_admin = _get_or_create(
        db, Rol, {"codigo": RolCodigo.ADMIN},
        nombre="Administrador", descripcion="Configura reglas, SLA, plantillas e integraciones.",
    )
    rol_op = _get_or_create(
        db, Rol, {"codigo": RolCodigo.OPERADOR},
        nombre="Operador", descripcion="Gestiona hitos, casos, entregas y conformidad.",
    )
    rol_ger = _get_or_create(
        db, Rol, {"codigo": RolCodigo.GERENTE},
        nombre="Gerente", descripcion="Solo lectura de dashboard y KPIs.",
    )

    admin = _get_or_create(
        db, Usuario, {"email": "admin@poluximport.pe"},
        nombre_completo="Admin Demo",
        password_hash=hash_password("Admin123!"),
        activo=True,
    )
    operador = _get_or_create(
        db, Usuario, {"email": "operador@poluximport.pe"},
        nombre_completo="Operador Demo",
        password_hash=hash_password("Oper123!"),
        activo=True,
    )
    gerente = _get_or_create(
        db, Usuario, {"email": "gerente@poluximport.pe"},
        nombre_completo="Gerente Demo",
        password_hash=hash_password("Ger123!"),
        activo=True,
    )

    for u, r in [(admin, rol_admin), (operador, rol_op), (gerente, rol_ger)]:
        if not db.scalar(select(UsuarioRol).filter_by(usuario_id=u.id, rol_id=r.id)):
            db.add(UsuarioRol(usuario_id=u.id, rol_id=r.id))


def seed_hitos(db) -> None:
    hitos = [
        # Stock
        ("STOCK_PREPARACION", "Preparación", OrigenItem.STOCK_TRUJILLO, 1, 1),
        ("STOCK_LISTO_ENTREGA", "Listo para entrega", OrigenItem.STOCK_TRUJILLO, 2, 0),
        # Importación
        ("IMP_COMPRA_EEUU", "Compra en EE. UU.", OrigenItem.IMPORTACION, 1, 2),
        ("IMP_RECIBIDO_EEUU", "Recibido en EE. UU.", OrigenItem.IMPORTACION, 2, 5),
        ("IMP_ENVIADO_PERU", "Enviado a Perú", OrigenItem.IMPORTACION, 3, 2),
        ("IMP_LLEGADA_PERU", "Llegada a Perú / aduana", OrigenItem.IMPORTACION, 4, 10),
        ("IMP_LIBERADO", "Liberado", OrigenItem.IMPORTACION, 5, 7),
        ("IMP_RECIBIDO_TRUJILLO", "Recibido en Trujillo", OrigenItem.IMPORTACION, 6, 5),
        ("IMP_LISTO_ENTREGA", "Listo para entrega", OrigenItem.IMPORTACION, 7, 1),
    ]
    for codigo, nombre, origen, orden, dias in hitos:
        hito = _get_or_create(
            db, HitoCatalogo, {"codigo": codigo},
            nombre=nombre, origen=origen, orden=orden, activo=True,
        )
        if not db.scalar(select(SlaHito).filter_by(hito_id=hito.id, origen=origen)):
            db.add(SlaHito(hito_id=hito.id, origen=origen, dias_maximos=dias, activo=True))


def seed_plantillas(db) -> None:
    plantillas = [
        ("BIENVENIDA", "Bienvenida al pedido verificado", "BIENVENIDA", Canal.WHATSAPP,
         "Hola {{cliente_nombre}}, te damos la bienvenida a Polux Import. "
         "Tu pedido {{pedido_codigo}} fue verificado. Ítems: {{items_resumen}}. "
         "Fecha prometida: {{fecha_prometida}}. Te mantendremos informado."),
        ("AVISO_HITO", "Aviso de hito completado", "AVISO_HITO", Canal.WHATSAPP,
         "Hola {{cliente_nombre}}, tu pedido {{pedido_codigo}} avanzó: "
         "{{hito_nombre}} — {{items_afectados}}. Fecha prometida: {{fecha_prometida}}."),
        ("RETRASO_LEVE", "Aviso de retraso leve", "RETRASO_LEVE", Canal.WHATSAPP,
         "Hola {{cliente_nombre}}, tu pedido {{pedido_codigo}} presenta un retraso leve "
         "en {{hito_nombre}}. Nueva fecha estimada: {{fecha_estimada}}. Gracias por la paciencia."),
        ("RETRASO_CRITICO", "Aviso de retraso crítico", "RETRASO_CRITICO", Canal.WHATSAPP,
         "Hola {{cliente_nombre}}, estamos atendiendo un imprevisto con tu pedido {{pedido_codigo}}. "
         "Un asesor te contactará en breve con una actualización."),
        ("ENTREGA_LISTA", "Coordinación de entrega", "ENTREGA_LISTA", Canal.WHATSAPP,
         "Hola {{cliente_nombre}}, tu pedido {{pedido_codigo}} está listo. "
         "¿Prefieres recojo o envío a domicilio? Indícanos modalidad, fecha y horario."),
        ("REINTENTO_24H", "Reintento a las 24 h", "REINTENTO_CONTACTO", Canal.WHATSAPP,
         "Hola {{cliente_nombre}}, seguimos a la espera de tu confirmación para coordinar la entrega "
         "de tu pedido {{pedido_codigo}}."),
        ("REINTENTO_48H", "Reintento a las 48 h", "REINTENTO_CONTACTO", Canal.WHATSAPP,
         "Hola {{cliente_nombre}}, es nuestro segundo recordatorio sobre la coordinación del pedido "
         "{{pedido_codigo}}. Si necesitas ayuda, escríbenos."),
        ("ESCALAMIENTO_CLIENTE", "Aviso de derivación a asesor", "ESCALAMIENTO", Canal.WHATSAPP,
         "Hola {{cliente_nombre}}, hemos derivado tu caso con un asesor. Te contactaremos en breve."),
                ("ACTUALIZACION_PERIODICA", "Actualización periódica sin novedades",
         "ACTUALIZACION_PERIODICA", Canal.WHATSAPP,
         "Hola {{cliente_nombre}}, seguimos avanzando con tu pedido {{pedido_codigo}}. "
         "Sin novedades por ahora; fecha prometida: {{fecha_prometida}}."),
        ("IMPREVISTO", "Aviso de imprevisto", "IMPREVISTO", Canal.WHATSAPP,
         "Hola {{cliente_nombre}}, hemos detectado un imprevisto con tu pedido "
         "{{pedido_codigo}}. Un asesor te contactará en breve para darte detalles "
         "y coordinar la solución."),
                # --- Plantillas del agente IA ---
        ("AGENTE_SALUDO", "Saludo inicial del agente", "AGENTE", Canal.WHATSAPP,
         "Hola {{cliente_nombre}}, soy el asistente de Polux Import. "
         "Puedo consultarte el estado de tu pedido; indícame tu código."),
        ("AGENTE_ESTADO_PEDIDO", "Respuesta de estado de pedido", "AGENTE",
         Canal.WHATSAPP,
         "Hola {{cliente_nombre}}, tu pedido {{pedido_codigo}} está {{estado_pedido}}. "
         "Fecha prometida: {{fecha_prometida}}. {{items_resumen}}"),
        ("AGENTE_PAGOS_REDIRECT", "Redirección de consultas de pagos", "AGENTE",
         Canal.WHATSAPP,
         "Hola {{cliente_nombre}}, las consultas sobre pagos, cuotas o contrato "
         "se atienden por otro canal. Un asesor te contactará."),
        ("AGENTE_HOLDING_ESCALAMIENTO", "Mensaje de holding al escalar", "AGENTE",
         Canal.WHATSAPP,
         "Hola {{cliente_nombre}}, hemos derivado tu caso con un asesor que te "
         "contactará en breve."),
    ]
    for codigo, nombre, evento, canal, cuerpo in plantillas:
        _get_or_create(
            db, PlantillaMensaje, {"codigo": codigo},
            nombre=nombre, evento=evento, canal=canal, cuerpo=cuerpo,
            idioma="es_PE", activo=True,
        )


def seed_reglas(db) -> None:
    reglas = [
        ("RETRASO_LEVE_DIAS", "Umbral de retraso leve (días)", "SLA",
         "2", TipoValorRegla.INT, "Hito con retraso ≤ N días genera aviso leve."),
        ("RETRASO_CRITICO_DIAS", "Umbral de retraso crítico (días)", "SLA",
         "5", TipoValorRegla.INT, "Hito con retraso > N días genera alerta crítica y escalamiento."),
        ("SILENCIO_CLIENTE_HORAS", "Umbral de silencio del cliente (horas)", "COMUNICACION",
         "48", TipoValorRegla.INT, "Reintentos a las 24 y 48 h; luego escalar."),
        ("ACTUALIZACION_PERIODICA_DIAS", "Periodicidad de actualización proactiva (días)", "COMUNICACION",
         "3", TipoValorRegla.INT, "Sin novedades durante N días en pedido activo → enviar actualización."),
        ("VENTANA_NOTIFICACION_HORAS", "Ventana de notificación oportuna (horas)", "COMUNICACION",
         "2", TipoValorRegla.INT, "KPI 1: notificación ≤ N horas tras hito completado."),
        ("MAX_REINTENTOS_CONTACTO", "Máximo de reintentos de contacto", "COMUNICACION",
         "2", TipoValorRegla.INT, "Reintentos de 24 y 48 h antes de escalar."),
        ("RESOLUCION_AUTOMATICA_VENTANA_HORAS", "Ventana de resolución automática (horas)", "KPI",
         "48", TipoValorRegla.INT, "KPI 2: consulta resuelta sin escalar ni reabrirse en N horas."),
        ("CHECKLIST_CONFORMIDAD", "Checklist de conformidad por ítem", "ENTREGA",
         '["caja_sellada","modelo_ok","color_ok","capacidad_ok","imei_ok","accesorios_ok"]',
         TipoValorRegla.JSON, "Ítems a verificar al momento de la entrega."),
        ("ENTREGA_PARCIAL_PERMITIDA", "Permitir entrega parcial con autorización", "ENTREGA",
         "true", TipoValorRegla.BOOL, "Solo si un humano registra quién, cuándo y por qué."),
        ("CONSENTIMIENTO_OBLIGATORIO", "Consentimiento obligatorio para mensajes proactivos", "PRIVACIDAD",
         "true", TipoValorRegla.BOOL, "Ley 29733 — sin consentimiento, sin mensajes proactivos."),
                ("REINTENTO_1_HORAS", "Reintento de contacto #1 (horas)", "COMUNICACION",
         "24", TipoValorRegla.INT, "Enviar primer reintento tras N horas sin respuesta."),
        ("REINTENTO_2_HORAS", "Reintento de contacto #2 (horas)", "COMUNICACION",
         "48", TipoValorRegla.INT, "Enviar segundo reintento tras N horas sin respuesta."),
        ("CASO_FALTA_RESPUESTA_HORAS", "Umbral para abrir caso por falta de respuesta (horas)",
         "COMUNICACION", "72", TipoValorRegla.INT,
         "Tras N horas sin respuesta (después de 2 reintentos) abrir caso."),
        ("RIESGO_FECHA_PROMETIDA_DIAS", "Ventana de riesgo de fecha prometida (días)",
         "SLA", "2", TipoValorRegla.INT,
         "Si la fecha prometida está dentro de N días y quedan hitos pendientes, marcar como riesgo."),
    ]
    for codigo, nombre, categoria, valor, tipo, descripcion in reglas:
        _get_or_create(
            db, ReglaNegocio, {"codigo": codigo},
            nombre=nombre, categoria=categoria, valor=valor,
            tipo_valor=tipo, descripcion=descripcion, activo=True,
        )


def seed_dimensiones(db) -> None:
    # dim_canal
    for codigo, nombre in [("WHATSAPP", "WhatsApp"), ("EMAIL", "Correo electrónico"), ("WEB", "Web")]:
        _get_or_create(db, DimCanal, {"codigo": codigo}, nombre=nombre)

    # dim_tipo_imprevisto
    for codigo, nombre, categoria in [
        ("OPERATIVO", "Operativo", "OPERATIVO"),
        ("ADUANERO", "Aduanero", "ADUANERO"),
        ("DAÑO", "Daño", "OPERATIVO"),
        ("AGOTADO", "Agotado en origen", "OPERATIVO"),
        ("OTRO", "Otro", "OPERATIVO"),
    ]:
        _get_or_create(db, DimTipoImprevisto, {"codigo": codigo}, nombre=nombre, categoria=categoria)

    # dim_kpi (6 KPIs + 1 complementario)
    kpis = [
        ("FREQ_ACTUALIZACION_CLIENTE", "Frecuencia de actualización al cliente",
         "Hitos notificados dentro de ≤2 h / hitos completados ×100", "%",
         Decimal("95.00"), Decimal("85.00"), Decimal("0.00"), "mayor_mejor", False),
        ("TASA_RESOLUCION_AUTOMATICA", "Tasa de resolución automática",
         "Consultas resueltas por el agente sin escalar en 48 h / total consultas ×100", "%",
         Decimal("80.00"), Decimal("60.00"), Decimal("0.00"), "mayor_mejor", False),
        ("TIEMPO_RESPUESTA_ESCALADOS", "Tiempo de respuesta a escalados",
         "Promedio de horas entre apertura del caso y primera acción humana", "horas",
         Decimal("4.00"), Decimal("8.00"), Decimal("9999.00"), "menor_mejor", False),
        ("TIEMPO_RESOLUCION_IMPREVISTOS", "Tiempo de resolución de imprevistos",
         "Promedio de días entre detección y cierre del imprevisto (por tipo)", "días",
         Decimal("2.00"), Decimal("5.00"), Decimal("9999.00"), "menor_mejor", False),
        ("ENTREGAS_A_TIEMPO", "Entregas a tiempo",
         "Entregas completas con fecha_real ≤ fecha_prometida / entregas ×100", "%",
         Decimal("90.00"), Decimal("75.00"), Decimal("0.00"), "mayor_mejor", False),
        ("ENTREGAS_SIN_OBSERVACIONES", "Entregas confirmadas sin observaciones",
         "Pedidos con todos sus ítems conformes sin observación / pedidos entregados ×100", "%",
         Decimal("97.00"), Decimal("90.00"), Decimal("0.00"), "mayor_mejor", False),
        ("PCT_ENTREGAS_PARCIALES", "Porcentaje de pedidos con entrega parcial",
         "Complementario: pedidos con al menos una entrega parcial / pedidos entregados ×100", "%",
         Decimal("5.00"), Decimal("10.00"), Decimal("9999.00"), "menor_mejor", True),
    ]
    for codigo, nombre, definicion, unidad, opt, alerta, critico, sentido, complementario in kpis:
        _get_or_create(
            db, DimKpi, {"codigo": codigo},
            nombre=nombre, definicion=definicion, unidad=unidad,
            umbral_optimo=opt, umbral_alerta=alerta, umbral_critico=critico,
            sentido=sentido, es_complementario=complementario,
        )


def seed_dim_tiempo(db, desde: date, hasta: date) -> None:
    from datetime import timedelta as td
    d = desde
    dias_semana = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    meses = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
             "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    while d <= hasta:
        pk = d.year * 10000 + d.month * 100 + d.day
        if not db.scalar(select(DimTiempo).filter_by(id=pk)):
            db.add(DimTiempo(
                id=pk, fecha=d, anio=d.year, mes=d.month, dia=d.day,
                trimestre=(d.month - 1) // 3 + 1, dia_semana=d.weekday(),
                nombre_mes=meses[d.month - 1], es_fin_semana=d.weekday() >= 5,
            ))
        d += td(days=1)


def run() -> None:
    db = SessionLocal()
    try:
        seed_rbac(db)
        seed_hitos(db)
        seed_plantillas(db)
        seed_reglas(db)
        seed_dimensiones(db)
        seed_dim_tiempo(db, date(2024, 1, 1), date(2030, 12, 31))

        # Sincronizar dim_hito con hito_catalogo
        for h in db.scalars(select(HitoCatalogo)).all():
            _get_or_create(db, DimHito, {"codigo": h.codigo},
                           hito_id=h.id, nombre=h.nombre, origen=h.origen.value)

        # Sincronizar dim_producto desde catálogo (idempotente)
        from app.services.fact_sync_service import FactSyncService
        sync_counts = FactSyncService(db).sync_all()
        print(f"[seed] fact_sync: {sync_counts}")

        db.commit()
        print("[seed] OK")
    finally:
        db.close()


if __name__ == "__main__":
    run()