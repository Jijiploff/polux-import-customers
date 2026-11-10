import { useEffect, useState } from "react";
import { imprevistosApi } from "../../api/imprevistos";
import { DataTable } from "../../components/DataTable";
import { StatusBadge } from "../../components/StatusBadge";
import { Loading } from "../../components/Loading";
import { useAuth } from "../../auth/AuthContext";
import type { Imprevisto, EstadoImprevisto } from "../../types/domain";

export function ImprevistosPage() {
  const { hasRole } = useAuth();
  const [rows, setRows] = useState<Imprevisto[] | null>(null);
  const [estado, setEstado] = useState<EstadoImprevisto | "">("ABIERTO");

  async function load() {
    setRows(await imprevistosApi.list({ estado: estado || undefined }));
  }
  useEffect(() => { load(); }, [estado]);

  async function resolver(id: number) {
    const resolucion = window.prompt("Resolución:");
    if (!resolucion) return;
    await imprevistosApi.actualizar(id, {
      estado: "RESUELTO", resolucion,
      fecha_resolucion: new Date().toISOString(),
    });
    load();
  }

  return (
    <div>
      <h1 style={{ marginTop: 0 }}>Imprevistos</h1>
      <label>Estado:&nbsp;
        <select value={estado} onChange={(e) => setEstado(e.target.value as any)}>
          <option value="">Todos</option>
          <option value="ABIERTO">Abierto</option>
          <option value="EN_PROCESO">En proceso</option>
          <option value="RESUELTO">Resuelto</option>
          <option value="CERRADO">Cerrado</option>
        </select>
      </label>
      {!rows ? <Loading /> : (
        <DataTable
          rows={rows}
          columns={[
            { key: "id", header: "#", render: (i) => i.id },
            { key: "pedido", header: "Pedido", render: (i) => i.pedido_id },
            { key: "tipo", header: "Tipo", render: (i) => <StatusBadge value={i.tipo} /> },
            { key: "desc", header: "Descripción", render: (i) => i.descripcion },
            { key: "estado", header: "Estado", render: (i) => <StatusBadge value={i.estado} /> },
            { key: "acc", header: "Acciones",
              render: (i) => hasRole("ADMIN", "OPERADOR") && i.estado !== "RESUELTO" ? (
                <button onClick={() => resolver(i.id)}>Resolver</button>
              ) : "—" },
          ]}
        />
      )}
    </div>
  );
}