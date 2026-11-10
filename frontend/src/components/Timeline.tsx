import { useCallback, useEffect, useState } from "react";
import { pedidosApi } from "../api/pedidos";
import { StatusBadge } from "./StatusBadge";
import { Loading } from "./Loading";
import type { Timeline, TimelineEvento } from "../types/domain";

/** Icono y color de fondo por tipo de evento. */
const TIPO_UI: Record<string, { icono: string; bg: string; label: string }> = {
  pedido: { icono: "🛒", bg: "#f1f5f9", label: "Pedido" },
  hito: { icono: "🏁", bg: "#e0e7ff", label: "Hito" },
  mensaje: { icono: "💬", bg: "#dcfce7", label: "Mensaje" },
  caso: { icono: "⚖️", bg: "#fee2e2", label: "Caso" },
  imprevisto: { icono: "⚠️", bg: "#fef3c7", label: "Imprevisto" },
  entrega: { icono: "📦", bg: "#ede9fe", label: "Entrega" },
  alerta: { icono: "🔔", bg: "#ffedd5", label: "Alerta" },
};

function fechaHora(fecha: string): string {
  try {
    return new Date(fecha).toLocaleString("es-PE", {
      day: "2-digit", month: "2-digit", year: "2-digit",
      hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return fecha;
  }
}

/** Contador del resumen (chip) solo si tiene algo que mostrar. */
function ChipResumen({ valor, texto }: { valor: number; texto: string }) {
  if (valor <= 0) return null;
  return (
    <span style={{
      background: "#f1f5f9", border: "1px solid #e2e8f0", borderRadius: 999,
      padding: "1px 8px", fontSize: "0.72rem", color: "#334155",
      whiteSpace: "nowrap",
    }}>
      <strong>{valor}</strong> {texto}
    </span>
  );
}

function Evento({ e, ultimo }: { e: TimelineEvento; ultimo: boolean }) {
  const ui = TIPO_UI[e.tipo] ?? TIPO_UI.pedido;
  return (
    <div style={{ display: "flex", gap: "0.6rem" }}>
      {/* Eje vertical: icono + línea conectora */}
      <div style={{
        display: "flex", flexDirection: "column", alignItems: "center",
        width: 28, flexShrink: 0,
      }}>
        <div title={ui.label} style={{
          width: 26, height: 26, borderRadius: "50%", background: ui.bg,
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: "0.8rem", flexShrink: 0,
        }}>
          {ui.icono}
        </div>
        {!ultimo && (
          <div style={{ width: 2, flex: 1, minHeight: 10, background: "#e2e8f0" }} />
        )}
      </div>

      {/* Contenido del evento */}
      <div style={{ minWidth: 0, flex: 1, paddingBottom: ultimo ? 0 : "0.85rem" }}>
        <div style={{
          display: "flex", gap: "0.45rem", alignItems: "baseline",
          flexWrap: "wrap",
        }}>
          <strong style={{ fontSize: "0.88rem" }}>{e.titulo}</strong>
          {e.criticidad !== "INFO" && <StatusBadge value={e.criticidad} />}
          <span style={{ fontSize: "0.72rem", color: "#64748b" }}>
            {fechaHora(e.fecha)}
          </span>
        </div>
        {e.detalle && (
          <div style={{
            fontSize: "0.8rem", color: "#475569", overflowWrap: "anywhere",
          }}>
            {e.detalle}
          </div>
        )}
        <div style={{ fontSize: "0.7rem", color: "#94a3b8" }}>
          {ui.label}
          {e.autor ? ` · ${e.autor}` : ""}
          {e.ref_id != null ? ` · #${e.ref_id}` : ""}
        </div>
      </div>
    </div>
  );
}

/**
 * Línea de tiempo del pedido (Fase H): hitos, mensajes (clave o todos),
 * casos, imprevistos, entregas y alertas en una sola lista ordenada.
 * Se auto-carga al montarse; el toggle recarga con `incluir_mensajes`.
 */
export function Timeline({
  pedidoId,
  titulo,
}: {
  pedidoId: number;
  titulo?: string;
}) {
  const [datos, setDatos] = useState<Timeline | null>(null);
  const [todos, setTodos] = useState(false);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState("");

  const cargar = useCallback(async (incluirMensajes: boolean) => {
    setCargando(true);
    try {
      setDatos(await pedidosApi.timeline(pedidoId, {
        incluir_mensajes: incluirMensajes,
      }));
      setError("");
    } catch {
      setError("No se pudo cargar la línea de tiempo.");
    } finally {
      setCargando(false);
    }
  }, [pedidoId]);

  // Recarga al cambiar de pedido y arranca en modo "eventos clave".
  useEffect(() => {
    setTodos(false);
    cargar(false);
  }, [pedidoId, cargar]);

  function alternarMensajes() {
    const nuevo = !todos;
    setTodos(nuevo);
    cargar(nuevo);
  }

  const r = datos?.resumen;

  return (
    <div>
      {/* Cabecera: título + chips de resumen + toggle de mensajes */}
      <div style={{
        display: "flex", flexWrap: "wrap", gap: "0.5rem",
        alignItems: "center", justifyContent: "space-between",
        marginBottom: "0.6rem",
      }}>
        <div style={{
          display: "flex", flexWrap: "wrap", gap: "0.35rem",
          alignItems: "center", minWidth: 0,
        }}>
          {titulo && (
            <strong style={{ fontSize: "0.9rem", marginRight: "0.25rem" }}>
              {titulo}
            </strong>
          )}
          {r && (
            <>
              <ChipResumen valor={r.mensajes} texto="mensajes" />
              <ChipResumen valor={r.casos_abiertos} texto="caso(s) abierto(s)" />
              <ChipResumen valor={r.hitos_atrasados} texto="hito(s) atrasado(s)" />
              <ChipResumen valor={r.imprevistos_abiertos} texto="imprevisto(s)" />
              <ChipResumen valor={r.alertas_activas} texto="alerta(s)" />
            </>
          )}
        </div>
        <label style={{
          display: "flex", gap: "0.4rem", alignItems: "center",
          fontSize: "0.78rem", color: "#475569", cursor: "pointer",
          whiteSpace: "nowrap",
        }}>
          <input
            type="checkbox"
            checked={todos}
            onChange={alternarMensajes}
            disabled={cargando}
          />
          Ver todos los mensajes e interacciones
        </label>
      </div>

      {/* Lista */}
      {cargando && !datos && <Loading label="Cargando línea de tiempo…" />}
      {error && <p style={{ color: "crimson", fontSize: "0.85rem" }}>{error}</p>}
      {datos && datos.eventos.length === 0 && !error && (
        <p style={{ color: "#64748b", fontSize: "0.85rem" }}>
          Sin eventos registrados todavía.
        </p>
      )}
      {datos && datos.eventos.length > 0 && (
        <div aria-busy={cargando} style={{ opacity: cargando ? 0.6 : 1 }}>
          {datos.eventos.map((e, i) => (
            <Evento
              key={`${e.tipo}-${e.ref_tipo ?? ""}-${e.ref_id ?? i}-${e.fecha}`}
              e={e}
              ultimo={i === datos.eventos.length - 1}
            />
          ))}
        </div>
      )}
    </div>
  );
}
