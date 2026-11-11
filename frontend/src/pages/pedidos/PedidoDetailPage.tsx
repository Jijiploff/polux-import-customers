import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { pedidosApi } from "../../api/pedidos";
import { hitosApi } from "../../api/hitos";
import { entregasApi } from "../../api/entregas";
import { StatusBadge } from "../../components/StatusBadge";
import { Timeline } from "../../components/Timeline";
import { Loading } from "../../components/Loading";
import { Modal } from "../../components/Modal";
import { useAuth } from "../../auth/AuthContext";
import type { Entrega, PedidoFullDetail, ItemHito } from "../../types/domain";

export function PedidoDetailPage() {
  const { id } = useParams();
  const { hasRole } = useAuth();
  const [data, setData] = useState<PedidoFullDetail | null>(null);
  const [entregas, setEntregas] = useState<Entrega[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [completarHitoId, setCompletarHitoId] = useState<number | null>(null);
  const [fechaReal, setFechaReal] = useState<string>(new Date().toISOString().slice(0, 16));

  async function reload() {
    if (!id) return;
    try {
      const p = await pedidosApi.full(Number(id));
      setData(p);
      setEntregas(await entregasApi.listByPedido(Number(id)));
    } catch (e) { setError(String(e)); }
  }

  useEffect(() => { reload(); }, [id]);

  async function onCompletarHito() {
    if (completarHitoId == null) return;
    await hitosApi.completar(completarHitoId, new Date(fechaReal).toISOString());
    setCompletarHitoId(null);
    await reload();
  }

  if (error) return <p style={{ color: "crimson" }}>{error}</p>;
  if (!data) return <Loading />;

  const todosListos = data.items.every((i) => i.estado === "LISTO_PARA_ENTREGA");

  return (
    <div>
      <Link to="/pedidos">← Pedidos</Link>
      <h1 style={{ marginTop: "0.5rem" }}>
        {data.codigo} <StatusBadge value={data.estado_actual} />
      </h1>
      <div style={{ background: "white", borderRadius: 8, padding: "1rem", marginBottom: "1rem" }}>
        <p><strong>Cliente:</strong> {data.cliente.nombre} · {data.cliente.telefono_whatsapp}</p>
        <p><strong>Fecha prometida:</strong> {new Date(data.fecha_prometida).toLocaleDateString()}</p>
        <p><strong>Modalidad:</strong> {data.modalidad_entrega}</p>
        <p><strong>Consentimiento:</strong> {data.cliente.consentimiento_datos ? "Sí" : "No"}</p>
      </div>

      <h2>Ítems e hitos</h2>
      {data.items.map((it) => (
        <div key={it.id} style={{
          background: "white", borderRadius: 8, padding: "1rem", marginBottom: "1rem",
        }}>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <div>
              <strong>{it.descripcion_producto}</strong>
              {" "}({it.origen}) · x{it.cantidad}
            </div>
            <StatusBadge value={it.estado} />
          </div>
          <div className="data-table-wrap detail-table">
          <table className="data-table" style={{ marginTop: "0.5rem", fontSize: "0.85rem" }}>
            <thead>
              <tr style={{ background: "#f8fafc" }}>
                <th style={{ textAlign: "left" }}>Hito</th>
                <th>Previsto</th>
                <th>Real</th>
                <th>Estado</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {it.hitos.map((h: ItemHito) => (
                <tr key={h.id}>
                  <td>{h.hito_nombre}</td>
                  <td>{h.fecha_prevista ? new Date(h.fecha_prevista).toLocaleDateString() : "—"}</td>
                  <td>{h.fecha_real ? new Date(h.fecha_real).toLocaleDateString() : "—"}</td>
                  <td><StatusBadge value={h.estado} /></td>
                  <td>
                    {hasRole("ADMIN", "OPERADOR") && h.estado !== "COMPLETADO" && (
                      <button onClick={() => setCompletarHitoId(h.id)}>Completar</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </div>
      ))}

      <h2>Línea de tiempo</h2>
      <div style={{
        background: "white", borderRadius: 8, padding: "1rem", marginBottom: "1rem",
      }}>
        <Timeline key={data.id} pedidoId={data.id} />
      </div>

      <h2>Entregas</h2>
      <div style={{ background: "white", borderRadius: 8, padding: "1rem", marginBottom: "1rem" }}>
        {entregas.length === 0 && <p>Sin entregas registradas.</p>}
        {entregas.map((e) => (
          <div key={e.id} style={{ borderBottom: "1px solid #f1f5f9", paddingBottom: "0.5rem" }}>
            <strong>#{e.id}</strong> · {e.tipo} · {e.modalidad} ·{" "}
            <StatusBadge value={e.estado} /> · programada:{" "}
            {new Date(e.fecha_programada).toLocaleString()}
            {e.tipo === "PARCIAL" && (
              <> · autorizada por #{e.autorizada_por_id} · motivo: {e.motivo_parcial}</>
            )}
          </div>
        ))}
        {hasRole("ADMIN", "OPERADOR") && (
          <div style={{ marginTop: "0.75rem" }}>
            <Link to={`/entregas/nueva?pedido_id=${data.id}`}>
              <button disabled={!todosListos && data.estado_actual !== "LISTO_PARA_ENTREGA"}>
                Programar entrega
              </button>
            </Link>
            {!todosListos && (
              <span style={{ marginLeft: "0.5rem", color: "#b45309", fontSize: "0.85rem" }}>
                (Requiere que todos los ítems estén LISTO_PARA_ENTREGA)
              </span>
            )}
          </div>
        )}
      </div>

      <Modal open={completarHitoId !== null} title="Completar hito"
             onClose={() => setCompletarHitoId(null)}>
        <p>Ingresa la fecha real del hito:</p>
        <input type="datetime-local" value={fechaReal}
          onChange={(e) => setFechaReal(e.target.value)} />
        <div style={{ marginTop: "1rem" }}>
          <button onClick={onCompletarHito}>Confirmar</button>
        </div>
      </Modal>
    </div>
  );
}