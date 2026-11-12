"""Flujo conversacional de coordinación de entregas por Telegram."""
from __future__ import annotations

import json
import re
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    CasoEscalamiento, CoordinacionEntrega, Entrega, EstadoEntrega,
    EstadoCaso, MotivoEscalamiento, Pedido, PrioridadCaso,
    EstadoItem, PedidoItem,
)
from app.schemas.entrega import EntregaCreate
from app.services.entrega_service import crear_entrega


def _datos(row: CoordinacionEntrega) -> dict:
    return json.loads(row.datos or "{}")


def _guardar(row: CoordinacionEntrega, datos: dict, fase: str) -> None:
    row.datos = json.dumps(datos, ensure_ascii=False)
    row.fase = fase


def pedido_listo_para_coordinar(db: Session, pedido: Pedido) -> bool:
    """Solo permite coordinar cuando todos los ítems ya están disponibles."""
    items = db.scalars(
        select(PedidoItem).where(PedidoItem.pedido_id == pedido.id)
    ).all()
    return bool(items) and all(item.estado == EstadoItem.LISTO_PARA_ENTREGA for item in items)


def cancelar(db: Session, chat_id: int) -> bool:
    row = db.scalar(
        select(CoordinacionEntrega).where(CoordinacionEntrega.chat_id == str(chat_id))
    )
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


def _normal(text: str) -> str:
    return " ".join(text.strip().split())


def _fecha(value: str) -> str | None:
    match = re.search(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b|\b(\d{1,2})/(\d{1,2})/(\d{4})\b", value)
    if not match:
        return None
    if match.group(1):
        year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
    else:
        day, month, year = int(match.group(4)), int(match.group(5)), int(match.group(6))
    try:
        parsed = datetime(year, month, day)
    except ValueError:
        return None
    if parsed.date() < datetime.utcnow().date():
        return None
    return parsed.strftime("%Y-%m-%d")


def _hora(value: str) -> str | None:
    match = re.search(
        r"(?:entre\s+la?\s*)?(\d{1,2})(?::(\d{2}))?\s*"
        r"(?:-|a|y|hasta)\s*(\d{1,2})(?::(\d{2}))?",
        value.lower(),
    )
    if not match:
        return None
    start, end = int(match.group(1)), int(match.group(3))
    suffix = value.lower()
    if ("tarde" in suffix or "p.m" in suffix or "pm" in suffix) and start < 12:
        start += 12
    if ("tarde" in suffix or "p.m" in suffix or "pm" in suffix) and end < 12:
        end += 12
    if start > 23 or end > 23 or start >= end:
        return None
    return f"{start:02d}:{match.group(2) or '00'}-{end:02d}:{match.group(4) or '00'}"


def _receptor(value: str) -> dict[str, str] | None:
    """Acepta líneas, comas y texto natural sin pedir repetir los datos."""
    dni = re.search(r"\b\d{8}\b", value)
    if not dni:
        return None
    telefonos = [
        match for match in re.findall(r"\b\d{9,15}\b", value)
        if match != dni.group(0)
    ]
    fecha = _fecha(value)
    franja = _hora(value)
    if not telefonos or not fecha or not franja:
        return None
    before_dni = value[:dni.start()].strip(" ,;\n")
    nombre = before_dni.split(",")[0].strip()
    nombre = re.sub(
        r"^(?:nombre(?:\s+completo)?|receptor)\s*:\s*",
        "",
        nombre,
        flags=re.IGNORECASE,
    )
    if not nombre:
        lines = [line.strip() for line in value.splitlines() if line.strip()]
        nombre = lines[0] if lines else ""
    if not nombre:
        return None
    return {
        "receptor_nombre": nombre,
        "receptor_dni": dni.group(0),
        "receptor_telefono": telefonos[0],
        "fecha": fecha,
        "franja_horaria": franja,
    }


def _ubicacion(value: str, modalidad: str) -> dict[str, str]:
    limpio = _normal(value)
    limpio = re.sub(r"^(?:la\s+)?direcci[oó]n\s*(?:es)?\s*:?\s*", "", limpio, flags=re.IGNORECASE)
    if modalidad != "DOMICILIO":
        return {"punto_recojo": limpio}
    lineas = [linea.strip() for linea in value.splitlines() if linea.strip()]
    primera = lineas[0] if lineas else value
    partes = [parte.strip(" .") for parte in primera.split(",") if parte.strip()]
    if len(partes) >= 2:
        referencias = partes[2:] + [linea.strip(" .") for linea in lineas[1:]]
        return {
            "direccion": re.sub(
                r"^(?:la\s+)?direcci[oó]n\s*(?:es)?\s*:?\s*",
                "",
                partes[0],
                flags=re.IGNORECASE,
            ),
            "distrito": partes[1],
            **({"referencia": " ".join(referencias)} if referencias else {}),
        }
    return {"direccion": limpio}


def iniciar(db: Session, pedido: Pedido, chat_id: int) -> str:
    row = db.scalar(select(CoordinacionEntrega).where(CoordinacionEntrega.chat_id == str(chat_id)))
    datos = {"pedido_codigo": pedido.codigo}
    if row is None:
        row = CoordinacionEntrega(
            chat_id=str(chat_id), pedido_id=pedido.id, fase="MODALIDAD",
            datos=json.dumps(datos, ensure_ascii=False),
        )
        db.add(row)
    else:
        row.pedido_id = pedido.id
        _guardar(row, datos, "MODALIDAD")
    db.commit()
    return (
        "📦 Vamos a coordinar tu entrega. Empecemos:\n\n"
        "¿Prefieres delivery a domicilio (costo según zona) o recojo coordinado (sin costo)?"
    )


def _resumen(datos: dict) -> str:
    ubicacion = datos.get("direccion") or datos.get("punto_recojo") or "—"
    distrito = datos.get("distrito") or datos.get("referencia") or ""
    return (
        "✅ Perfecto. Revisa el resumen:\n\n"
        "📦 RESUMEN DE ENTREGA\n"
        f"🚚 Modalidad: {datos.get('modalidad', '—')}\n"
        f"📍 Ubicación: {ubicacion} · {distrito}\n"
        f"👤 Receptor: {datos.get('receptor_nombre', '—')} · DNI {datos.get('receptor_dni', '—')}\n"
        f"📱 Tel: {datos.get('receptor_telefono', '—')}\n"
        f"📅 Fecha: {datos.get('fecha', '—')} · {datos.get('franja_horaria', '—')}\n"
        f"📝 Notas: {datos.get('notas') or '—'}\n\n"
        "¿Todo correcto?"
    )


def procesar(db: Session, pedido: Pedido, chat_id: int, text: str) -> tuple[str, dict | None]:
    row = db.scalar(select(CoordinacionEntrega).where(CoordinacionEntrega.chat_id == str(chat_id)))
    if row is None or row.pedido_id != pedido.id:
        return iniciar(db, pedido, chat_id), None
    datos = _datos(row)
    value = _normal(text)
    low = value.lower()
    if row.fase == "MODALIDAD":
        if "recojo" in low:
            datos["modalidad"] = "RECOJO"
        elif "delivery" in low or "domicilio" in low:
            datos["modalidad"] = "DOMICILIO"
        else:
            return "Responde con Delivery o Recojo, por favor.", None
        _guardar(row, datos, "UBICACION")
        db.commit()
        return (
            "Perfecto. Ahora envíame en un solo mensaje:\n"
            "📍 Dirección completa y distrito (si es delivery), o punto de recojo (si es recojo).\n"
            "🧭 Referencia opcional.",
            None,
        )
    if row.fase == "UBICACION":
        datos.update(_ubicacion(text, datos["modalidad"]))
        _guardar(row, datos, "RECEPTOR")
        db.commit()
        return (
            "✅ Ubicación recibida. Ahora envíame en un solo mensaje:\n"
            "👤 Nombre completo, DNI, teléfono, fecha (AAAA-MM-DD) y franja (ej. 15:00-18:00).",
            None,
        )
    if row.fase == "RECEPTOR":
        receptor = _receptor(text)
        if receptor is None:
            return (
                "No pude identificar todos los datos. Envíame nombre completo, DNI de 8 dígitos, "
                "teléfono, fecha futura (DD/MM/AAAA o AAAA-MM-DD) y horario, por ejemplo: "
                "María Rodriguez, 70000001, 923027824, 16/11/2026, entre la 1 y 3 de la tarde.",
                None,
            )
        datos.update(receptor)
        _guardar(row, datos, "NOTAS")
        db.commit()
        return "✅ Datos recibidos. Envía notas para el courier o escribe /saltar.", None
    if row.fase == "NOTAS":
        datos["notas"] = "" if low == "/saltar" else value
        _guardar(row, datos, "CONFIRMACION")
        db.commit()
        return _resumen(datos), {
            "inline_keyboard": [[
                {"text": "✅ Confirmar", "callback_data": f"entrega:confirmar:{row.id}"},
                {"text": "✏️ Corregir", "callback_data": f"entrega:corregir:{row.id}"},
            ]],
        }
    return "Revisa el resumen y pulsa Confirmar o Corregir.", {
        "inline_keyboard": [[
            {"text": "✅ Confirmar", "callback_data": f"entrega:confirmar:{row.id}"},
            {"text": "✏️ Corregir", "callback_data": f"entrega:corregir:{row.id}"},
        ]],
    }


def confirmar(db: Session, row_id: int, usuario_id: int | None = None) -> Entrega:
    row = db.get(CoordinacionEntrega, row_id)
    if row is None:
        raise HTTPException(404, "Coordinación no encontrada")
    datos = _datos(row)
    fecha = datetime.fromisoformat(datos["fecha"])
    entrega = crear_entrega(db, EntregaCreate(
        pedido_id=row.pedido_id, tipo="COMPLETA", modalidad=datos["modalidad"],
        fecha_programada=fecha, estado_inicial=EstadoEntrega.BORRADOR,
        creado_por_agente=True, direccion=datos.get("direccion"),
        punto_recojo=datos.get("punto_recojo"), referencia=datos.get("referencia"),
        receptor_nombre=datos.get("receptor_nombre"), receptor_dni=datos.get("receptor_dni"),
        receptor_telefono=datos.get("receptor_telefono"),
        franja_horaria=datos.get("franja_horaria"), notas_courier=datos.get("notas"),
    ), usuario_id=usuario_id)
    db.delete(row)
    db.commit()
    return entrega


def escalar_modificacion(db: Session, pedido: Pedido, texto: str, entrega: Entrega) -> CasoEscalamiento:
    caso = CasoEscalamiento(
        pedido_id=pedido.id, motivo=MotivoEscalamiento.MODIFICAR_ENTREGA,
        prioridad=PrioridadCaso.ALTA,
        descripcion=f"Cliente solicita modificar la entrega #{entrega.id}: {texto}",
        fecha_apertura=datetime.utcnow(), estado=EstadoCaso.ABIERTO,
    )
    db.add(caso)
    db.commit()
    db.refresh(caso)
    return caso
