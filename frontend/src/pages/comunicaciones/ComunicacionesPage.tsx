import { useEffect, useState, type FormEvent } from "react";
import { comunicacionesApi } from "../../api/comunicaciones";
import { pedidosApi } from "../../api/pedidos";
import { DataTable } from "../../components/DataTable";
import { StatusBadge } from "../../components/StatusBadge";
import { Loading } from "../../components/Loading";
import { Modal } from "../../components/Modal";
import { FormField } from "../../components/FormField";
import { useAuth } from "../../auth/AuthContext";
import type {
  Canal, ClaseComunicacion, Comunicacion, DireccionCom, Pedido,
} from "../../types/domain";

export function ComunicacionesPage() {
  const { hasRole } = useAuth();
  const [rows, setRows] = useState<Comunicacion[] | null>(null);
  const [page, setPage] = useState(1);
  const [pedidoId, setPedidoId] = useState<string>("");
  const [clase, setClase] = useState<ClaseComunicacion | "">("");

  // Formulario de nuevo mensaje
  const [showForm, setShowForm] = useState(false);
  const [pedidos, setPedidos] = useState<Pedido[]>([]);
  const [fPedido, setFPedido] = useState("");
  const [fDir, setFDir] = useState<DireccionCom>("SALIENTE");
  const [fCanal, setFCanal] = useState<Canal>("WHATSAPP");
  const [fAutor, setFAutor] = useState("HUMANO");
  const [fClase, setFClase] = useState<ClaseComunicacion>("CLIENTE");
  const [fContenido, setFContenido] = useState("");
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");

  useEffect(() => {
    comunicacionesApi.list({
      page, size: 50,
      pedido_id: pedidoId ? Number(pedidoId) : undefined,
      clase: clase || undefined,
    })
      .then(setRows).catch(() => setRows([]));
  }, [page, pedidoId, clase]);

  async function openForm() {
    setShowForm(true);
    setFormError("");
    if (pedidos.length === 0) {
      try {
        const res = await pedidosApi.list({ size: 50 });
        setPedidos(res.items ?? []);
      } catch { setPedidos([]); }
    }
  }

  async function enviar(e: FormEvent) {
    e.preventDefault();
    if (!fContenido.trim()) {
      setFormError("Escribe el contenido del mensaje.");
      return;
    }
    setSaving(true);
    setFormError("");
    try {
      await comunicacionesApi.crear({
        pedido_id: fPedido ? Number(fPedido) : undefined,
        direccion: fDir,
        canal: fCanal,
        autor: fAutor,
        clase: fClase,
        contenido: fContenido.trim(),
      });
      setShowForm(false);
      setFContenido("");
      setPage(1);
      setRows(await comunicacionesApi.list({ page: 1, size: 50 }));
    } catch {
      setFormError("No se pudo registrar el mensaje. Verifica los datos e inténtalo de nuevo.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <div className="page-toolbar" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1 style={{ marginTop: 0 }}>Comunicaciones</h1>
        {hasRole("ADMIN", "OPERADOR") && (
          <button onClick={openForm}>+ Nuevo mensaje</button>
        )}
      </div>
      <div style={{ marginBottom: "1rem", display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
        <input placeholder="Filtrar por pedido ID" value={pedidoId}
          onChange={(e) => { setPedidoId(e.target.value); setPage(1); }} />
        <label>Clase:&nbsp;
          <select
            value={clase}
            onChange={(e) => { setClase(e.target.value as ClaseComunicacion | ""); setPage(1); }}
          >
            <option value="">Todas</option>
            <option value="CLIENTE">Cliente</option>
            <option value="OPERATIVO">Operativo</option>
          </select>
        </label>
      </div>
      <Modal open={showForm} title="Registrar comunicación" onClose={() => setShowForm(false)}>
        <form onSubmit={enviar}>
          <FormField label="Pedido (opcional)">
            <select value={fPedido} onChange={(e) => setFPedido(e.target.value)} style={{ width: "100%" }}>
              <option value="">— Sin pedido —</option>
              {pedidos.map((p) => (
                <option key={p.id} value={p.id}>{p.codigo}</option>
              ))}
            </select>
          </FormField>
          <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
            <FormField label="Dirección">
              <select value={fDir} onChange={(e) => setFDir(e.target.value as DireccionCom)}>
                <option value="SALIENTE">Saliente (hacia el cliente)</option>
                <option value="ENTRANTE">Entrante (del cliente)</option>
              </select>
            </FormField>
            <FormField label="Canal">
              <select value={fCanal} onChange={(e) => setFCanal(e.target.value as Canal)}>
                <option value="WHATSAPP">WhatsApp</option>
                <option value="EMAIL">Email</option>
                <option value="WEB">Web</option>
                <option value="TELEGRAM">Telegram</option>
              </select>
            </FormField>
            <FormField label="Quién escribe">
              <select value={fAutor} onChange={(e) => setFAutor(e.target.value)}>
                <option value="HUMANO">Persona (operador)</option>
                <option value="CLIENTE">Cliente</option>
                <option value="AGENTE">Agente IA</option>
              </select>
            </FormField>
            <FormField label="Clase">
              <select
                value={fClase}
                onChange={(e) => setFClase(e.target.value as ClaseComunicacion)}
              >
                <option value="CLIENTE">Cliente (conversación)</option>
                <option value="OPERATIVO">Operativo (interno)</option>
              </select>
            </FormField>
          </div>
          <FormField label="Contenido" required>
            <textarea
              rows={3}
              value={fContenido}
              onChange={(e) => setFContenido(e.target.value)}
              placeholder="Texto del mensaje"
              style={{ width: "100%" }}
            />
          </FormField>
          {formError && <p style={{ color: "crimson", fontSize: "0.85rem" }}>{formError}</p>}
          <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
            <button type="button" onClick={() => setShowForm(false)}>Cancelar</button>
            <button type="submit" disabled={saving}>{saving ? "Guardando…" : "Registrar"}</button>
          </div>
        </form>
      </Modal>
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
              { key: "clase", header: "Clase",
                render: (c) => <StatusBadge value={c.clase} /> },
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