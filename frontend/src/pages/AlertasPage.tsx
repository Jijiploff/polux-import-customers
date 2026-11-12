import { useEffect, useState } from "react";
import { alertasApi } from "../api/alertas";
import { DataTable } from "../components/DataTable";
import { StatusBadge } from "../components/StatusBadge";
import { Loading } from "../components/Loading";
import { Modal } from "../components/Modal";
import { useAuth } from "../auth/AuthContext";
import type { Alerta, EstadoAlerta } from "../types/domain";

export function AlertasPage() {
  const { hasRole } = useAuth();
  const [rows, setRows] = useState<Alerta[] | null>(null);
  const [estado, setEstado] = useState<EstadoAlerta | "">("ABIERTA");
  const [error, setError] = useState<string | null>(null);
  const [detalle, setDetalle] = useState<Alerta | null>(null);

  async function load() {
    try {
      setRows(null);
      setRows(await alertasApi.list({ estado: estado || undefined }));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }
  useEffect(() => { load(); }, [estado]);

  async function accion(id: number, accion: "atender" | "cerrar" | "ignorar") {
    try {
      if (accion === "atender") await alertasApi.atender(id);
      else await alertasApi.actualizar(id, {
        estado: accion === "cerrar" ? "CERRADA" : "IGNORADA",
      });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const puedeOperar = hasRole("ADMIN", "OPERADOR");

  return (
    <div>
      <h1 style={{ marginTop: 0 }}>Alertas</h1>
      <label>Estado:&nbsp;
        <select value={estado} onChange={(e) => setEstado(e.target.value as any)}>
          <option value="">Todas</option>
          <option value="ABIERTA">Abierta</option>
          <option value="ATENDIDA">Atendida</option>
          <option value="CERRADA">Cerrada</option>
          <option value="IGNORADA">Ignorada</option>
        </select>
      </label>
      {error && <p style={{ color: "crimson" }}>{error}</p>}
      {!rows ? <Loading /> : (
        <DataTable
          rows={rows}
          onRowClick={setDetalle}
          columns={[
            { key: "id", header: "#", render: (a) => a.id },
            { key: "pedido", header: "Pedido",
              render: (a) => a.pedido_codigo ?? `#${a.pedido_id}` },
            { key: "tipo", header: "Tipo", render: (a) => <StatusBadge value={a.tipo} /> },
            { key: "sev", header: "Severidad", render: (a) => <StatusBadge value={a.severidad} /> },
            { key: "msg", header: "Mensaje",
              render: (a) => <span style={{ fontSize: "0.85rem" }}>{a.mensaje}</span> },
            { key: "estado", header: "Estado",
              render: (a) => <StatusBadge value={a.estado} /> },
            { key: "fecha", header: "Detección",
              render: (a) => new Date(a.fecha_deteccion).toLocaleString() },
            { key: "acc", header: "Acciones",
              render: (a) => {
                if (!puedeOperar) return "—";
                if (a.estado === "CERRADA" || a.estado === "IGNORADA") return "—";
                return (
                  <span style={{ display: "flex", gap: 4 }}>
                    {a.estado === "ABIERTA" && (
                      <button onClick={(e) => {
                        e.stopPropagation();
                        void accion(a.id, "atender");
                      }}>Atender</button>
                    )}
                    <button onClick={(e) => {
                      e.stopPropagation();
                      void accion(a.id, "cerrar");
                    }}>Cerrar</button>
                    <button onClick={(e) => {
                      e.stopPropagation();
                      void accion(a.id, "ignorar");
                    }}>Ignorar</button>
                  </span>
                );
              } },
          ]}
        />
      )}
      <Modal
        open={detalle !== null}
        title={detalle ? `Detalle de alerta #${detalle.id}` : "Detalle de alerta"}
        onClose={() => setDetalle(null)}
      >
        {detalle && (
          <div style={{ display: "grid", gap: "0.55rem", fontSize: "0.88rem" }}>
            <div><strong>Pedido:</strong> {detalle.pedido_codigo ?? `#${detalle.pedido_id}`}</div>
            <div><strong>Tipo:</strong> {detalle.tipo}</div>
            <div><strong>Severidad:</strong> <StatusBadge value={detalle.severidad} /></div>
            <div><strong>Estado:</strong> <StatusBadge value={detalle.estado} /></div>
            <div><strong>Detectada:</strong> {new Date(detalle.fecha_deteccion).toLocaleString()}</div>
            <div>
              <strong>Mensaje completo:</strong>
              <div style={{
                marginTop: 4, padding: "0.7rem", borderRadius: 6,
                background: "#f8fafc", border: "1px solid #e2e8f0",
                whiteSpace: "pre-wrap", overflowWrap: "anywhere",
              }}>
                {detalle.mensaje}
              </div>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}