import { useEffect, useState, type FormEvent } from "react";
import { imprevistosApi } from "../../api/imprevistos";
import { pedidosApi } from "../../api/pedidos";
import { DataTable } from "../../components/DataTable";
import { StatusBadge } from "../../components/StatusBadge";
import { Loading } from "../../components/Loading";
import { Modal } from "../../components/Modal";
import { FormField } from "../../components/FormField";
import { useAuth } from "../../auth/AuthContext";
import type {
  Imprevisto, EstadoImprevisto, Pedido, TipoImprevisto,
} from "../../types/domain";

const TIPOS: TipoImprevisto[] = ["OPERATIVO", "ADUANERO", "DAÑO", "AGOTADO", "OTRO"];

function ahoraLocal(): string {
  // datetime-local espera "YYYY-MM-DDTHH:MM" en hora local
  const d = new Date(Date.now() - new Date().getTimezoneOffset() * 60000);
  return d.toISOString().slice(0, 16);
}

export function ImprevistosPage() {
  const { hasRole } = useAuth();
  const [rows, setRows] = useState<Imprevisto[] | null>(null);
  const [estado, setEstado] = useState<EstadoImprevisto | "">("ABIERTO");

  // Formulario de nuevo imprevisto
  const [showForm, setShowForm] = useState(false);
  const [pedidos, setPedidos] = useState<Pedido[]>([]);
  const [fPedido, setFPedido] = useState("");
  const [fTipo, setFTipo] = useState<TipoImprevisto>("OPERATIVO");
  const [fDesc, setFDesc] = useState("");
  const [fFecha, setFFecha] = useState(ahoraLocal());
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");

  async function load() {
    setRows(await imprevistosApi.list({ estado: estado || undefined }));
  }
  useEffect(() => { load(); }, [estado]);

  async function openForm() {
    setShowForm(true);
    setFormError("");
    setFFecha(ahoraLocal());
    if (pedidos.length === 0) {
      try {
        const res = await pedidosApi.list({ size: 50 });
        setPedidos(res.items ?? []);
      } catch { setPedidos([]); }
    }
  }

  async function crearImprevisto(e: FormEvent) {
    e.preventDefault();
    if (!fPedido || !fDesc.trim()) {
      setFormError("Elige un pedido y describe el imprevisto.");
      return;
    }
    setSaving(true);
    setFormError("");
    try {
      await imprevistosApi.crear({
        pedido_id: Number(fPedido),
        tipo: fTipo,
        descripcion: fDesc.trim(),
        fecha_deteccion: new Date(fFecha).toISOString(),
      });
      setShowForm(false);
      setFDesc("");
      load();
    } catch {
      setFormError("No se pudo registrar el imprevisto. Verifica los datos e inténtalo de nuevo.");
    } finally {
      setSaving(false);
    }
  }

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
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1 style={{ marginTop: 0 }}>Imprevistos</h1>
        {hasRole("ADMIN", "OPERADOR") && (
          <button onClick={openForm}>+ Nuevo imprevisto</button>
        )}
      </div>
      <label>Estado:&nbsp;
        <select value={estado} onChange={(e) => setEstado(e.target.value as any)}>
          <option value="">Todos</option>
          <option value="ABIERTO">Abierto</option>
          <option value="EN_PROCESO">En proceso</option>
          <option value="RESUELTO">Resuelto</option>
          <option value="CERRADO">Cerrado</option>
        </select>
      </label>
      <Modal open={showForm} title="Registrar imprevisto" onClose={() => setShowForm(false)}>
        <form onSubmit={crearImprevisto}>
          <FormField label="Pedido" required>
            <select value={fPedido} onChange={(e) => setFPedido(e.target.value)} style={{ width: "100%" }}>
              <option value="">— Elige un pedido —</option>
              {pedidos.map((p) => (
                <option key={p.id} value={p.id}>{p.codigo}</option>
              ))}
            </select>
          </FormField>
          <FormField label="Tipo" required>
            <select value={fTipo} onChange={(e) => setFTipo(e.target.value as TipoImprevisto)}>
              {TIPOS.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </FormField>
          <FormField label="Fecha de detección" required>
            <input
              type="datetime-local"
              value={fFecha}
              onChange={(e) => setFFecha(e.target.value)}
            />
          </FormField>
          <FormField label="Descripción" required>
            <textarea
              rows={3}
              value={fDesc}
              onChange={(e) => setFDesc(e.target.value)}
              placeholder="Qué ocurrió (aduana, transporte, daño…)"
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