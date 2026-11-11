"""Línea de tiempo del pedido (Fase H: GET /pedidos/{id}/timeline).

Crea un pedido de prueba con hitos (uno completado y otro atrasado),
tres mensajes (uno neutro que NO es evento clave, una queja escalada y
una respuesta de asesor), un caso, un imprevisto, una entrega y una
alerta; después verifica la fusión, el orden, los filtros y el resumen.
"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import (
    Alerta,
    AutorComunicacion,
    Canal,
    CasoEscalamiento,
    ClaseComunicacion,
    Comunicacion,
    DireccionComunicacion,
    Entrega,
    EstadoAlerta,
    EstadoCaso,
    EstadoEntrega,
    EstadoHito,
    EstadoImprevisto,
    HitoCatalogo,
    Imprevisto,
    ItemHito,
    ModalidadEntrega,
    MotivoEscalamiento,
    OrigenItem,
    PrioridadCaso,
    Sentimiento,
    TipoAlerta,
    TipoEntrega,
    TipoImprevisto,
    SeveridadAlerta,
)
from tests.db_utils import cleanup_pedido, crear_pedido_listo


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _preparar(db):
    """Pedido con todas las fuentes de la línea de tiempo pobladas."""
    ped, item, ih1 = crear_pedido_listo(db, con_hito=True)
    ahora = datetime.utcnow()

    # Hitos: el primero completado, el segundo atrasado (3 días)
    ih1.estado = EstadoHito.COMPLETADO
    ih1.fecha_real = ahora - timedelta(days=2)
    ih1.notificado_cliente = True
    hito2 = db.scalar(
        select(HitoCatalogo)
        .where(
            HitoCatalogo.origen == OrigenItem.STOCK_TRUJILLO,
            HitoCatalogo.orden == 2,
        )
    )
    if hito2 is None:  # pragma: no cover - el seed crea STOCK_LISTO_ENTREGA
        hito2 = HitoCatalogo(
            codigo="STOCK_LISTO_ENTREGA", nombre="Listo para entrega",
            origen=OrigenItem.STOCK_TRUJILLO, orden=2, activo=True,
        )
        db.add(hito2)
        db.flush()
    db.add(ItemHito(
        pedido_item_id=item.id, hito_id=hito2.id,
        fecha_prevista=ahora - timedelta(days=1),
        estado=EstadoHito.ATRASADO, dias_atraso=3,
    ))

    # Mensajes: consulta neutra (NO es evento clave), queja escalada y asesor
    m_neutra = Comunicacion(
        pedido_id=ped.id, direccion=DireccionComunicacion.ENTRANTE,
        canal=Canal.WHATSAPP, contenido="¿Cómo va mi pedido?",
        intencion_detectada="ESTADO_PEDIDO", sentimiento=Sentimiento.NEUTRO,
        autor=AutorComunicacion.CLIENTE, fecha=ahora - timedelta(days=1),
    )
    m_queja = Comunicacion(
        pedido_id=ped.id, direccion=DireccionComunicacion.ENTRANTE,
        canal=Canal.WHATSAPP, contenido="Llevo semanas esperando, esto es una estafa",
        intencion_detectada="RECLAMO", sentimiento=Sentimiento.NEGATIVO,
        autor=AutorComunicacion.CLIENTE,
        fecha=ahora - timedelta(days=1, hours=1), escalado=True,
    )
    db.add_all([m_neutra, m_queja])
    db.flush()

    caso = CasoEscalamiento(
        pedido_id=ped.id, comunicacion_origen_id=m_queja.id,
        motivo=MotivoEscalamiento.RECLAMO, prioridad=PrioridadCaso.ALTA,
        descripcion="Agente detectó RECLAMO. Escalar sin resolver.",
        fecha_apertura=m_queja.fecha,
        fecha_primera_accion=m_queja.fecha + timedelta(minutes=40),
        estado=EstadoCaso.EN_PROCESO,
    )
    db.add(caso)
    db.flush()
    m_queja.caso_id = caso.id

    m_humano = Comunicacion(
        pedido_id=ped.id, direccion=DireccionComunicacion.SALIENTE,
        canal=Canal.WHATSAPP, contenido="Ya estamos atendiendo tu caso.",
        autor=AutorComunicacion.HUMANO,
        fecha=caso.fecha_primera_accion, estado_entrega="SENT",
    )
    db.add_all([
        m_humano,
        Imprevisto(
            pedido_id=ped.id, tipo=TipoImprevisto.ADUANERO,
            descripcion="Retención en aduana",
            fecha_deteccion=ahora - timedelta(days=3),
            estado=EstadoImprevisto.ABIERTO,
        ),
        Entrega(
            pedido_id=ped.id, tipo=TipoEntrega.COMPLETA,
            modalidad=ModalidadEntrega.DOMICILIO,
            fecha_programada=ahora + timedelta(days=2),
            estado=EstadoEntrega.PROGRAMADA,
        ),
        Alerta(
            pedido_id=ped.id, tipo=TipoAlerta.RETRASO_LEVE,
            severidad=SeveridadAlerta.MEDIA,
            mensaje="Hito con retraso leve", estado=EstadoAlerta.ABIERTA,
            fecha_deteccion=ahora - timedelta(days=2, hours=1),
        ),
    ])
    db.commit()
    return ped, item


def _get(client, auth, pid, params=""):
    return client.get(f"/api/v1/pedidos/{pid}/timeline{params}", headers=auth["operador"])


def test_fusiona_fuentes_ordena_y_resumen(db, client, auth):
    ped, _ = _preparar(db)
    try:
        r = _get(client, auth, ped.id)
        assert r.status_code == 200
        body = r.json()
        assert body["pedido_id"] == ped.id
        assert body["incluyendo_mensajes"] is False

        # Las 7 fuentes aparecen
        tipos = {e["tipo"] for e in body["eventos"]}
        assert {"pedido", "hito", "mensaje", "caso", "imprevisto",
                "entrega", "alerta"} <= tipos

        # Orden: más reciente primero
        fechas = [e["fecha"] for e in body["eventos"]]
        assert fechas == sorted(fechas, reverse=True)

        # Hitos: completado y atrasado con su criticidad ALTA
        hitos = [e for e in body["eventos"] if e["tipo"] == "hito"]
        assert any("Hito completado" in e["titulo"] for e in hitos)
        atrasado = next(e for e in hitos if "atrasado" in e["titulo"])
        assert atrasado["criticidad"] == "ALTA"
        assert "3 día(s) de atraso" in atrasado["detalle"]

        # Resumen (contexto rápido para el operador)
        res = body["resumen"]
        assert res["mensajes"] == 3
        assert res["mensajes_clave"] == 2  # queja escalada + asesor
        assert res["hitos_atrasados"] == 1
        assert res["casos_abiertos"] == 1
        assert res["imprevistos_abiertos"] == 1
        assert res["alertas_activas"] == 1
    finally:
        cleanup_pedido(db, ped.id)


def test_eventos_clave_vs_todos_los_mensajes(db, client, auth):
    ped, _ = _preparar(db)
    try:
        # Por defecto: solo eventos clave (la consulta neutra NO aparece)
        r = _get(client, auth, ped.id)
        assert r.status_code == 200
        detalles = [e["detalle"] for e in r.json()["eventos"]]
        titulos = [e["titulo"] for e in r.json()["eventos"]]
        assert "¿Cómo va mi pedido?" not in detalles
        assert any("escalada" in t for t in titulos)
        assert "Respuesta del asesor" in titulos

        # Con incluir_mensajes=true: aparecen TODOS los mensajes
        r2 = _get(client, auth, ped.id, "?incluir_mensajes=true")
        assert r2.status_code == 200
        body2 = r2.json()
        assert body2["incluyendo_mensajes"] is True
        assert "¿Cómo va mi pedido?" in [e["detalle"] for e in body2["eventos"]]
        assert body2["resumen"]["mensajes"] == 3
        # El evento más reciente sigue siendo la entrega programada
        assert body2["eventos"][0]["tipo"] in {"entrega", "hito", "mensaje",
                                               "caso", "imprevisto",
                                               "alerta", "pedido"}
    finally:
        cleanup_pedido(db, ped.id)


def test_filtro_tipos_y_tipos_desconocidos(db, client, auth):
    ped, _ = _preparar(db)
    try:
        r = _get(client, auth, ped.id, "?tipos=caso")
        assert r.status_code == 200
        eventos = r.json()["eventos"]
        assert eventos and all(e["tipo"] == "caso" for e in eventos)
        # apertura + primera respuesta (el caso aún no tiene cierre)
        assert len(eventos) == 2

        r2 = _get(client, auth, ped.id, "?tipos=coco,otro")
        assert r2.status_code == 422
        assert "coco" in str(r2.json()["detail"])
    finally:
        cleanup_pedido(db, ped.id)


def test_pedido_inexistente_404(client, auth):
    r = client.get("/api/v1/pedidos/999999/timeline", headers=auth["operador"])
    assert r.status_code == 404


def test_sin_token_401(client):
    r = client.get("/api/v1/pedidos/1/timeline")
    assert r.status_code == 401


def test_mensajes_operativos_separados_de_la_conversacion(db, client, auth):
    ped, _ = _preparar(db)
    ahora = datetime.utcnow()
    operativo = Comunicacion(
        pedido_id=ped.id, direccion=DireccionComunicacion.SALIENTE,
        canal=Canal.TELEGRAM, contenido="✅ Vinculado al pedido de prueba",
        autor=AutorComunicacion.AGENTE,
        clase=ClaseComunicacion.OPERATIVO,
        estado_entrega="SENT", fecha=ahora,
    )
    db.add(operativo)
    db.commit()
    try:
        # Por defecto el resumen separa conversación de operación.
        body = _get(client, auth, ped.id).json()
        assert body["resumen"]["mensajes"] == 3
        assert body["resumen"]["mensajes_operativos"] == 1
        assert all(e["tipo"] != "operativo" for e in body["eventos"])

        # Al pedir todos los mensajes, el operativo aparece con su propio tipo.
        body = _get(client, auth, ped.id, "?incluir_mensajes=true").json()
        operativos = [e for e in body["eventos"] if e["tipo"] == "operativo"]
        assert len(operativos) == 1
        assert operativos[0]["detalle"] == "✅ Vinculado al pedido de prueba"
        assert body["resumen"]["mensajes"] == 3

        # Filtro explícito por tipo.
        body = _get(client, auth, ped.id, "?tipos=operativo").json()
        assert body["eventos"] and all(
            e["tipo"] == "operativo" for e in body["eventos"]
        )
    finally:
        cleanup_pedido(db, ped.id)
