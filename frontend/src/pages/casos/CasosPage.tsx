import { useEffect, useState } from "react";
import { casosApi } from "../../api/casos";
import { DataTable } from "../../components/DataTable";
import { StatusBadge } from "../../components/StatusBadge";
import { Loading } from "../../components/Loading";
import { useAuth } from "../../auth/AuthContext";
import type { Caso, EstadoCaso } from "../../types/domain";

export function CasosPage() {
  const { hasRole } = useAuth();
  const [rows, setRows] = useState<Caso[] | null>(null);
  const [estado, setEstado] = useState<EstadoCaso | "">("ABIERTO");

  async function load() {
    setRows(await casosApi.list({ estado: estado || undefined }));
  }
  useEffect(() => { load(); }, [estado]);

  async function registrarPrimeraAccion(id: number) {
    await casosApi.actualizar(id, { registrar_primera_accion: true });
    load();
  }
  async function cerrar(id: number) {
    await casosApi.actualizar(id, { estado: "CERRADO" });
    load();
  }

  return (
    <div>
      <h1 style={{ marginTop: 0 }}>Casos de escalamiento</h1>
      <label>Estado:&nbsp;
        <select value={estado} onChange={(e) => setEstado(e.target.value as any)}>
          <option value="">Todos</option>
          <option value="ABIERTO">Abierto</option>
          <option value="EN_PROCESO">En proceso</option>
          <option value="CERRADO">Cerrado</option>
        </select>
      </label>
      {!rows ? <Loading /> : (
        <DataTable
          rows={rows}
          columns={[
            { key: "id", header: "#", render: (c) => c.id },
            { key: "pedido", header: "Pedido", render: (c) => c.pedido_id },
            { key: "motivo", header: "Motivo",
              render: (c) => <StatusBadge value={c.motivo} /> },
            { key: "prioridad", header: "Prioridad",
              render: (c) => <StatusBadge value={c.prioridad} /> },
            { key: "estado", header: "Estado",
              render: (c) => <StatusBadge value={c.estado} /> },
            { key: "aper", header: "Apertura",
              render: (c) => new Date(c.fecha_apertura).toLocaleString() },
            { key: "acc", header: "Acciones",
              render: (c) => hasRole("ADMIN", "OPERADOR") ? (
                <div style={{ display: "flex", gap: 4 }}>
                  {!c.fecha_primera_accion && (
                    <button onClick={() => registrarPrimeraAccion(c.id)}>Primera acción</button>
                  )}
                  {c.estado !== "CERRADO" && (
                    <button onClick={() => cerrar(c.id)}>Cerrar</button>
                  )}
                </div>
              ) : "—" },
          ]}
        />
      )}
    </div>
  );
}