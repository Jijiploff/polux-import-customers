import { useEffect, useState } from "react";
import { alertasApi } from "../api/alertas";
import { DataTable } from "../components/DataTable";
import { StatusBadge } from "../components/StatusBadge";
import { Loading } from "../components/Loading";
import { useAuth } from "../auth/AuthContext";
import type { Alerta, EstadoAlerta } from "../types/domain";

export function AlertasPage() {
  const { hasRole } = useAuth();
  const [rows, setRows] = useState<Alerta[] | null>(null);
  const [estado, setEstado] = useState<EstadoAlerta | "">("ABIERTA");
  const [error, setError] = useState<string | null>(null);

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
          columns={[
            { key: "id", header: "#", render: (a) => a.id },
            { key: "pedido", header: "Pedido", render: (a) => a.pedido_id },
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
                      <button onClick={() => accion(a.id, "atender")}>Atender</button>
                    )}
                    <button onClick={() => accion(a.id, "cerrar")}>Cerrar</button>
                    <button onClick={() => accion(a.id, "ignorar")}>Ignorar</button>
                  </span>
                );
              } },
          ]}
        />
      )}
    </div>
  );
}