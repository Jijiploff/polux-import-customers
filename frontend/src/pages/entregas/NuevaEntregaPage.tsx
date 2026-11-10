import { FormEvent, useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { pedidosApi } from "../../api/pedidos";
import { entregasApi } from "../../api/entregas";
import { FormField } from "../../components/FormField";
import { Loading } from "../../components/Loading";
import { StatusBadge } from "../../components/StatusBadge";
import { useAuth } from "../../auth/AuthContext";
import type { Modalidad, PedidoFullDetail, TipoEntrega } from "../../types/domain";

export function NuevaEntregaPage() {
  const nav = useNavigate();
  const [sp] = useSearchParams();
  const { userId } = useAuth();
  const [pedidoId] = useState<number | null>(
    sp.get("pedido_id") ? Number(sp.get("pedido_id")) : null,
  );
  const [pedido, setPedido] = useState<PedidoFullDetail | null>(null);
  const [tipo, setTipo] = useState<TipoEntrega>("COMPLETA");
  const [modalidad, setModalidad] = useState<Modalidad>("DOMICILIO");
  const [fecha, setFecha] = useState(
    new Date(Date.now() + 24 * 3600 * 1000).toISOString().slice(0, 16),
  );
  const [motivo, setMotivo] = useState("");
  const [autorizaConfirm, setAutorizaConfirm] = useState(false);
  const [itemIds, setItemIds] = useState<number[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!pedidoId) return;
    pedidosApi.full(pedidoId).then(setPedido).catch((e) => setError(String(e)));
  }, [pedidoId]);

  useEffect(() => {
    if (!pedido) return;
    setItemIds(pedido.items
      .filter((i) => i.estado === "LISTO_PARA_ENTREGA")
      .map((i) => i.id));
  }, [pedido, tipo]);

  if (!pedidoId) {
    return <p>Debes elegir un pedido primero. <a href="/entregas">Volver</a></p>;
  }
  if (error) return <p style={{ color: "crimson" }}>{error}</p>;
  if (!pedido) return <Loading />;

  const todosListos = pedido.items.length > 0 &&
    pedido.items.every((i) => i.estado === "LISTO_PARA_ENTREGA");

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (tipo === "COMPLETA" && !todosListos) {
      setError("No se puede programar una entrega completa si hay ítems no listos.");
      return;
    }
    if (tipo === "PARCIAL") {
      if (!userId) { setError("Falta identificación de usuario."); return; }
      if (!motivo.trim()) { setError("Debes indicar el motivo de la entrega parcial."); return; }
      if (!autorizaConfirm) { setError("Debes confirmar la autorización humana."); return; }
      if (itemIds.length === 0) { setError("Debes seleccionar al menos un ítem."); return; }
    }
    setSubmitting(true);
    try {
      await entregasApi.crear({
        pedido_id: pedido.id,
        tipo, modalidad,
        fecha_programada: new Date(fecha).toISOString(),
        pedido_item_ids: tipo === "PARCIAL" ? itemIds : undefined,
        autorizada_por_id: tipo === "PARCIAL" ? userId ?? undefined : undefined,
        fecha_autorizacion: tipo === "PARCIAL" ? new Date().toISOString() : undefined,
        motivo_parcial: tipo === "PARCIAL" ? motivo : undefined,
      });
      // La entrega queda PROGRAMADA; se completará en el flujo de conformidad
      // cuando el cliente reciba el producto.
      nav(`/pedidos/${pedido.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <h1 style={{ marginTop: 0 }}>Programar entrega · {pedido.codigo}</h1>
      <form onSubmit={onSubmit} style={{ background: "white", padding: "1.25rem", borderRadius: 8 }}>
        <FormField label="Tipo">
          <select value={tipo} onChange={(e) => setTipo(e.target.value as TipoEntrega)}>
            <option value="COMPLETA">Completa</option>
            <option value="PARCIAL">Parcial (excepción)</option>
          </select>
        </FormField>
        <FormField label="Modalidad">
          <select value={modalidad} onChange={(e) => setModalidad(e.target.value as Modalidad)}>
            <option value="DOMICILIO">Domicilio</option>
            <option value="RECOJO">Recojo</option>
          </select>
        </FormField>
        <FormField label="Fecha programada" required>
          <input type="datetime-local" required value={fecha}
            onChange={(e) => setFecha(e.target.value)} />
        </FormField>

        {tipo === "PARCIAL" && (
          <>
            <div style={{
              background: "#fef3c7", border: "1px solid #fde68a",
              borderRadius: 6, padding: "0.75rem", marginBottom: "0.75rem",
              fontSize: "0.85rem",
            }}>
              <strong>Regla inviolable:</strong> la entrega parcial exige autorización humana.
              Se registrará tu usuario (<strong>#{userId}</strong>), la fecha y el motivo.
            </div>
            <FormField label="Motivo de la entrega parcial" required>
              <textarea required value={motivo}
                onChange={(e) => setMotivo(e.target.value)}
                style={{ width: "100%", minHeight: 60 }} />
            </FormField>
            <FormField label="Ítems a entregar" required>
              {pedido.items.map((it) => (
                <label key={it.id} style={{ display: "block" }}>
                  <input type="checkbox"
                    checked={itemIds.includes(it.id)}
                    disabled={it.estado !== "LISTO_PARA_ENTREGA"}
                    onChange={(e) => setItemIds((prev) =>
                      e.target.checked ? [...prev, it.id] : prev.filter((x) => x !== it.id),
                    )} />
                  {" "}{it.descripcion_producto} <StatusBadge value={it.estado} />
                </label>
              ))}
            </FormField>
            <label style={{ display: "block", marginBottom: "1rem" }}>
              <input type="checkbox" checked={autorizaConfirm}
                onChange={(e) => setAutorizaConfirm(e.target.checked)} />
              {" "}Confirmo que la entrega parcial está autorizada por un humano.
            </label>
          </>
        )}

        {error && <p style={{ color: "crimson" }}>{error}</p>}
        <button type="submit" disabled={submitting}>
          {submitting ? "Guardando…" : "Programar entrega"}
        </button>
      </form>
      <p style={{ color: "#64748b", fontSize: "0.85rem", marginTop: "1rem" }}>
        La entrega quedará <strong>PROGRAMADA</strong>. Cuando se realice, se
        completará con el checklist de conformidad por ítem desde{" "}
        <a href={`/entregas?pedido_id=${pedido.id}`}>Entregas</a>.
      </p>
    </div>
  );
}