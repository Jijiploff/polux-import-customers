import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { pedidosApi } from "../../api/pedidos";
import { DataTable } from "../../components/DataTable";
import { Pagination } from "../../components/Pagination";
import { StatusBadge } from "../../components/StatusBadge";
import { Loading } from "../../components/Loading";
import type { Page, Pedido, EstadoPedido } from "../../types/domain";

export function PedidosListPage() {
  const [data, setData] = useState<Page<Pedido> | null>(null);
  const [page, setPage] = useState(1);
  const [estado, setEstado] = useState<EstadoPedido | "">("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    pedidosApi.list({ page, size: 20, estado: estado || undefined })
      .then(setData)
      .catch((e) => setError(String(e)));
  }, [page, estado]);

  return (
    <div>
      <h1 style={{ marginTop: 0 }}>Pedidos</h1>
      <div style={{ marginBottom: "1rem", display: "flex", gap: "0.5rem" }}>
        <label>Estado:&nbsp;
          <select value={estado} onChange={(e) => { setEstado(e.target.value as any); setPage(1); }}>
            <option value="">Todos</option>
            <option value="RECIBIDO">Recibido</option>
            <option value="EN_PROCESO">En proceso</option>
            <option value="LISTO_PARA_ENTREGA">Listo p/ entrega</option>
            <option value="EN_COORDINACION">En coordinación</option>
            <option value="CERRADO">Cerrado</option>
          </select>
        </label>
      </div>
      {error && <p style={{ color: "crimson" }}>{error}</p>}
      {!data ? <Loading /> : (
        <>
          <DataTable
            rows={data.items}
            columns={[
              { key: "codigo", header: "Código",
                render: (p) => <Link to={`/pedidos/${p.id}`}>{p.codigo}</Link> },
              { key: "estado", header: "Estado",
                render: (p) => <StatusBadge value={p.estado_actual} /> },
              { key: "ingreso", header: "Ingreso",
                render: (p) => new Date(p.fecha_ingreso).toLocaleDateString() },
              { key: "prometida", header: "Prometida",
                render: (p) => new Date(p.fecha_prometida).toLocaleDateString() },
              { key: "modalidad", header: "Modalidad",
                render: (p) => p.modalidad_entrega },
            ]}
          />
          <Pagination page={page} size={20} total={data.total} onChange={setPage} />
        </>
      )}
    </div>
  );
}