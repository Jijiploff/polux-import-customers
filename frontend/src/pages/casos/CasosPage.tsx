import { useEffect, useState, type FormEvent } from "react";
import { casosApi } from "../../api/casos";
import { pedidosApi } from "../../api/pedidos";
import { DataTable } from "../../components/DataTable";
import { StatusBadge } from "../../components/StatusBadge";
import { Loading } from "../../components/Loading";
import { Modal } from "../../components/Modal";
import { FormField } from "../../components/FormField";
import { useAuth } from "../../auth/AuthContext";
import type {
  Caso, EstadoCaso, MotivoEscalamiento, Pedido, PrioridadCaso,
} from "../../types/domain";

const MOTIVOS: MotivoEscalamiento[] = [
  "RECLAMO", "TONO_NEGATIVO", "ENTREGA_PARCIAL", "IMPREVISTO",
  "RETRASO_CRITICO", "FALTA_RESPUESTA", "OTRO",
];
const PRIORIDADES: PrioridadCaso[] = ["BAJA", "MEDIA", "ALTA", "CRITICA"];

export function CasosPage() {
  const { hasRole } = useAuth();
  const [rows, setRows] = useState<Caso[] | null>(null);
  const [estado, setEstado] = useState<EstadoCaso | "">("ABIERTO");

  // Formulario de nuevo caso
  const [showForm, setShowForm] = useState(false);
  const [pedidos, setPedidos] = useState<Pedido[]>([]);
  const [fPedido, setFPedido] = useState("");
  const [fMotivo, setFMotivo] = useState<MotivoEscalamiento>("RECLAMO");
  const [fPrioridad, setFPrioridad] = useState<PrioridadCaso>("MEDIA");
  const [fDesc, setFDesc] = useState("");
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");

  async function load() {
    setRows(await casosApi.list({ estado: estado || undefined }));
  }
  useEffect(() => { load(); }, [estado]);

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

  async function crearCaso(e: FormEvent) {
    e.preventDefault();
    if (!fPedido || !fDesc.trim()) {
      setFormError("Elige un pedido y describe el motivo.");
      return;
    }
    setSaving(true);
    setFormError("");
    try {
      await casosApi.crear({
        pedido_id: Number(fPedido),
        motivo: fMotivo,
        prioridad: fPrioridad,
        descripcion: fDesc.trim(),
      });
      setShowForm(false);
      setFDesc("");
      load();
    } catch {
      setFormError("No se pudo crear el caso. Verifica los datos e inténtalo de nuevo.");
    } finally {
      setSaving(false);
    }
  }

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
      <div className="page-toolbar" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1 style={{ marginTop: 0 }}>Casos de escalamiento</h1>
        {hasRole("ADMIN", "OPERADOR") && (
          <button onClick={openForm}>+ Nuevo caso</button>
        )}
      </div>
      <label>Estado:&nbsp;
        <select value={estado} onChange={(e) => setEstado(e.target.value as any)}>
          <option value="">Todos</option>
          <option value="ABIERTO">Abierto</option>
          <option value="EN_PROCESO">En proceso</option>
          <option value="CERRADO">Cerrado</option>
        </select>
      </label>
      <Modal open={showForm} title="Nuevo caso de escalamiento" onClose={() => setShowForm(false)}>
        <form onSubmit={crearCaso}>
          <FormField label="Pedido" required>
            <select value={fPedido} onChange={(e) => setFPedido(e.target.value)} style={{ width: "100%" }}>
              <option value="">— Elige un pedido —</option>
              {pedidos.map((p) => (
                <option key={p.id} value={p.id}>{p.codigo}</option>
              ))}
            </select>
          </FormField>
          <FormField label="Motivo" required>
            <select value={fMotivo} onChange={(e) => setFMotivo(e.target.value as MotivoEscalamiento)} style={{ width: "100%" }}>
              {MOTIVOS.map((m) => <option key={m} value={m}>{m.replace(/_/g, " ")}</option>)}
            </select>
          </FormField>
          <FormField label="Prioridad">
            <select value={fPrioridad} onChange={(e) => setFPrioridad(e.target.value as PrioridadCaso)}>
              {PRIORIDADES.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </FormField>
          <FormField label="Descripción" required>
            <textarea
              rows={3}
              value={fDesc}
              onChange={(e) => setFDesc(e.target.value)}
              placeholder="Qué pasó y por qué requiere a una persona"
              style={{ width: "100%" }}
            />
          </FormField>
          {formError && <p style={{ color: "crimson", fontSize: "0.85rem" }}>{formError}</p>}
          <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
            <button type="button" onClick={() => setShowForm(false)}>Cancelar</button>
            <button type="submit" disabled={saving}>{saving ? "Guardando…" : "Crear caso"}</button>
          </div>
        </form>
      </Modal>
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