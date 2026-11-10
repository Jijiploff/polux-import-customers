import { useEffect, useState } from "react";
import { comunicacionesApi } from "../../api/comunicaciones";
import { DataTable } from "../../components/DataTable";
import { StatusBadge } from "../../components/StatusBadge";
import { Loading } from "../../components/Loading";
import type { Comunicacion } from "../../types/domain";

export function ComunicacionesPage() {
  const [rows, setRows] = useState<Comunicacion[] | null>(null);
  const [page, setPage] = useState(1);
  const [pedidoId, setPedidoId] = useState<string>("");

  useEffect(() => {
    comunicacionesApi.list({ page, size: 50, pedido_id: pedidoId ? Number(pedidoId) : undefined })
      .then(setRows).catch(() => setRows([]));
  }, [page, pedidoId]);

  return (
    <div>
      <h1 style={{ marginTop: 0 }}>Comunicaciones</h1>
      <div style={{ marginBottom: "1rem" }}>
        <input placeholder="Filtrar por pedido ID" value={pedidoId}
          onChange={(e) => { setPedidoId(e.target.value); setPage(1); }} />
      </div>
      {!rows ? <Loading /> : (
        <>
          <DataTable
            rows={rows}
            columns={[
              { key: "id", header: "#", render: (c) => c.id },
              { key: "fecha", header: "Fecha",
                render: (c) => new Date(c.fecha).toLocaleString() },
              { key: "dir", header: "Dir.",
                render: (c) => <StatusBadge value={c.direccion} /> },
              { key: "canal", header: "Canal", render: (c) => c.canal },
              { key: "intent", header: "Intención",
                render: (c) => c.intencion_detectada ?? "—" },
              { key: "cont", header: "Contenido",
                render: (c) => <span style={{ fontSize: "0.8rem" }}>
                  {c.contenido.length > 100 ? c.contenido.slice(0, 100) + "…" : c.contenido}
                </span> },
              { key: "esc", header: "Escalado",
                render: (c) => c.escalado ? "Sí" : "No" },
            ]}
          />
          <div style={{ marginTop: "1rem", display: "flex", gap: "0.5rem" }}>
            <button disabled={page <= 1} onClick={() => setPage(page - 1)}>Anterior</button>
            <span>Página {page}</span>
            <button disabled={rows.length < 50} onClick={() => setPage(page + 1)}>Siguiente</button>
          </div>
        </>
      )}
    </div>
  );
}