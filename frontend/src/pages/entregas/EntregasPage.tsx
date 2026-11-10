import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { pedidosApi } from "../../api/pedidos";
import { entregasApi } from "../../api/entregas";
import { DataTable } from "../../components/DataTable";
import { StatusBadge } from "../../components/StatusBadge";
import { Modal } from "../../components/Modal";
import { Loading } from "../../components/Loading";
import { useAuth } from "../../auth/AuthContext";
import type {
  ConformidadItemIn, Entrega, Pedido, PedidoFullDetail, PedidoItem,
  ResultadoConformidad,
} from "../../types/domain";

type ConfForm = ConformidadItemIn;

function initConf(pedidoItemId: number): ConfForm {
  return {
    pedido_item_id: pedidoItemId,
    checklist_caja_sellada: false, checklist_modelo_ok: false,
    checklist_color_ok: false, checklist_capacidad_ok: false,
    checklist_imei_ok: false, checklist_accesorios_ok: false,
    resultado: "CONFORME",
    observaciones: "",
    evidencias_urls: "",
  };
}

export function EntregasPage() {
  const [sp] = useSearchParams();
  const initialPedido = sp.get("pedido_id");
  const [pedidoId, setPedidoId] = useState(initialPedido ?? "");
  const [entregas, setEntregas] = useState<Entrega[]>([]);
  const [pedidos, setPedidos] = useState<Pedido[]>([]);
  const { hasRole } = useAuth();

  // Modal completar
  const [completar, setCompletar] = useState<Entrega | null>(null);
  const [pedidoFull, setPedidoFull] = useState<PedidoFullDetail | null>(null);
  const [fechaReal, setFechaReal] = useState(new Date().toISOString().slice(0, 16));
  const [confs, setConfs] = useState<Record<number, ConfForm>>({});
  const [modalError, setModalError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    pedidosApi.list({ size: 100 }).then((p) => setPedidos(p.items));
  }, []);

  async function reload() {
    if (!pedidoId) { setEntregas([]); return; }
    setEntregas(await entregasApi.listByPedido(Number(pedidoId)));
  }
  useEffect(() => { reload(); }, [pedidoId]);

  async function openCompletar(e: Entrega) {
    setCompletar(e);
    setModalError(null);
    setFechaReal(new Date().toISOString().slice(0, 16));
    try {
      const p = await pedidosApi.full(e.pedido_id);
      setPedidoFull(p);
      const itemIds = new Set(e.items.map((ei) => ei.pedido_item_id));
      const init: Record<number, ConfForm> = {};
      for (const it of p.items) {
        if (itemIds.has(it.id)) init[it.id] = initConf(it.id);
      }
      setConfs(init);
    } catch (err) {
      setModalError(err instanceof Error ? err.message : String(err));
    }
  }

  function updateConf(itemId: number, patch: Partial<ConfForm>) {
    setConfs((prev) => ({ ...prev, [itemId]: { ...prev[itemId], ...patch } }));
  }

  async function submitCompletar() {
    if (!completar) return;
    setModalError(null);
    const list = Object.values(confs);
    for (const c of list) {
      if (c.resultado === "CON_OBSERVACIONES" && !(c.observaciones ?? "").trim()) {
        setModalError(
          `Ítem ${c.pedido_item_id}: las observaciones son obligatorias si el resultado es CON_OBSERVACIONES.`,
        );
        return;
      }
    }
    setSubmitting(true);
    try {
      await entregasApi.completar(completar.id, new Date(fechaReal).toISOString(), list);
      setCompletar(null);
      setPedidoFull(null);
      await reload();
    } catch (err) {
      setModalError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  const canOperate = hasRole("ADMIN", "OPERADOR");

  return (
    <div>
      <h1 style={{ marginTop: 0 }}>Entregas</h1>
      <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", marginBottom: "1rem" }}>
        <select value={pedidoId} onChange={(e) => setPedidoId(e.target.value)}>
          <option value="">Selecciona un pedido</option>
          {pedidos.map((p) => (
            <option key={p.id} value={p.id}>{p.codigo} · {p.estado_actual}</option>
          ))}
        </select>
        {canOperate && (
          <Link to={`/entregas/nueva${pedidoId ? `?pedido_id=${pedidoId}` : ""}`}>
            <button disabled={!pedidoId}>Programar nueva entrega</button>
          </Link>
        )}
      </div>
      <DataTable
        rows={entregas}
        columns={[
          { key: "id", header: "#", render: (e) => e.id },
          { key: "tipo", header: "Tipo", render: (e) => <StatusBadge value={e.tipo} /> },
          { key: "mod", header: "Modalidad", render: (e) => e.modalidad },
          { key: "est", header: "Estado", render: (e) => <StatusBadge value={e.estado} /> },
          { key: "fecha", header: "Programada",
            render: (e) => new Date(e.fecha_programada).toLocaleString() },
          { key: "items", header: "Ítems", render: (e) => e.items?.length ?? 0 },
          { key: "autoriza", header: "Autorización",
            render: (e) => e.tipo === "PARCIAL" ? (
              <span style={{ fontSize: "0.8rem" }}>
                por #{e.autorizada_por_id}<br />{e.motivo_parcial}
              </span>
            ) : "—" },
          { key: "acc", header: "Acciones",
            render: (e) => canOperate && (e.estado === "PROGRAMADA" || e.estado === "EN_RUTA") ? (
              <button onClick={() => openCompletar(e)}>Completar</button>
            ) : e.estado === "ENTREGADA" ? (
              <span style={{ color: "#16a34a", fontSize: "0.8rem" }}>
                entregada {e.fecha_real ? new Date(e.fecha_real).toLocaleDateString() : ""}
              </span>
            ) : "—" },
        ]}
      />

      <Modal
        open={completar !== null}
        title={`Completar entrega #${completar?.id ?? ""} · conformidad por ítem`}
        onClose={() => { setCompletar(null); setPedidoFull(null); }}
      >
        {!pedidoFull ? <Loading label="Cargando ítems…" /> : (
          <div>
            <p style={{ fontSize: "0.85rem", color: "#64748b" }}>
              Verifica cada ítem. Si algo no coincide con lo pactado, marca
              <strong> CON_OBSERVACIONES</strong> y documenta el detalle.
            </p>
            <label style={{ display: "block", marginBottom: "1rem" }}>
              Fecha real de entrega:&nbsp;
              <input type="datetime-local" value={fechaReal}
                onChange={(e) => setFechaReal(e.target.value)} />
            </label>
            {Object.values(confs).map((c) => {
              const item: PedidoItem | undefined = pedidoFull.items.find((i) => i.id === c.pedido_item_id);
              if (!item) return null;
              return (
                <div key={c.pedido_item_id} style={{
                  border: "1px solid #e2e8f0", borderRadius: 6,
                  padding: "0.75rem", marginBottom: "0.75rem",
                }}>
                  <p style={{ margin: 0, fontWeight: 600 }}>
                    {item.descripcion_producto} · {item.modelo} · {item.color} · {item.capacidad}
                  </p>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 4, marginTop: 6 }}>
                    {[
                      ["checklist_caja_sellada", "Caja sellada"],
                      ["checklist_modelo_ok", "Modelo OK"],
                      ["checklist_color_ok", "Color OK"],
                      ["checklist_capacidad_ok", "Capacidad OK"],
                      ["checklist_imei_ok", "IMEI/Serie OK"],
                      ["checklist_accesorios_ok", "Accesorios completos"],
                    ].map(([key, label]) => (
                      <label key={key} style={{ fontSize: "0.85rem" }}>
                        <input type="checkbox"
                          checked={(c as any)[key] as boolean}
                          onChange={(e) => updateConf(c.pedido_item_id, { [key]: e.target.checked } as any)} />
                        {" "}{label}
                      </label>
                    ))}
                  </div>
                  <label style={{ display: "block", marginTop: 6, fontSize: "0.85rem" }}>
                    Resultado:&nbsp;
                    <select value={c.resultado}
                      onChange={(e) => updateConf(c.pedido_item_id, {
                        resultado: e.target.value as ResultadoConformidad,
                      })}>
                      <option value="CONFORME">Conforme</option>
                      <option value="CON_OBSERVACIONES">Con observaciones</option>
                    </select>
                  </label>
                  {c.resultado === "CON_OBSERVACIONES" && (
                    <label style={{ display: "block", marginTop: 6, fontSize: "0.85rem" }}>
                      Observaciones*:&nbsp;
                      <input value={c.observaciones ?? ""}
                        onChange={(e) => updateConf(c.pedido_item_id, { observaciones: e.target.value })}
                        style={{ width: "100%" }} />
                    </label>
                  )}
                  <label style={{ display: "block", marginTop: 6, fontSize: "0.85rem" }}>
                    Evidencias (URLs, separadas por coma):&nbsp;
                    <input value={c.evidencias_urls ?? ""}
                      onChange={(e) => updateConf(c.pedido_item_id, { evidencias_urls: e.target.value })}
                      style={{ width: "100%" }} />
                  </label>
                </div>
              );
            })}
            {modalError && <p style={{ color: "crimson" }}>{modalError}</p>}
            <button onClick={submitCompletar} disabled={submitting}>
              {submitting ? "Guardando…" : "Registrar conformidad y completar entrega"}
            </button>
          </div>
        )}
      </Modal>
    </div>
  );
}