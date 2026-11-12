import { useEffect, useState, type FormEvent } from "react";
import { casosApi } from "../../api/casos";
import { pedidosApi } from "../../api/pedidos";
import { adminApi } from "../../api/admin";
import { agentApi, type ThreadMessage } from "../../api/agent";
import { ApiError } from "../../api/client";
import { DataTable } from "../../components/DataTable";
import { StatusBadge } from "../../components/StatusBadge";
import { Loading } from "../../components/Loading";
import { Modal } from "../../components/Modal";
import { FormField } from "../../components/FormField";
import { Timeline } from "../../components/Timeline";
import { useAuth } from "../../auth/AuthContext";
import type {
  Caso, CasoDetalle, EstadoCaso, MotivoEscalamiento, Pedido, PrioridadCaso,
  Usuario,
} from "../../types/domain";

const MOTIVOS: MotivoEscalamiento[] = [
  "RECLAMO", "TONO_NEGATIVO", "ENTREGA_PARCIAL", "IMPREVISTO",
  "RETRASO_CRITICO", "FALTA_RESPUESTA", "OTRO",
];
const PRIORIDADES: PrioridadCaso[] = ["BAJA", "MEDIA", "ALTA", "CRITICA"];

function mensajeError(err: unknown): string {
  if (err instanceof ApiError) {
    if (typeof err.detail === "string") return err.detail;
    if (Array.isArray(err.detail)) {
      return "Revisa el contenido de la respuesta e inténtalo de nuevo.";
    }
    if (err.status === 409) {
      return "El caso ya está siendo atendido por otro operador o fue cerrado.";
    }
    if (err.status === 403) {
      return "No tienes permiso para realizar esta acción sobre este caso.";
    }
  }
  return "No se pudo completar la operación. Inténtalo de nuevo.";
}

function hora(fecha: string): string {
  try {
    return new Date(fecha).toLocaleTimeString("es-PE", {
      hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return "";
  }
}

export function CasosPage() {
  const { hasRole, userId } = useAuth();
  const esAdmin = hasRole("ADMIN");
  const [rows, setRows] = useState<Caso[] | null>(null);
  const [estado, setEstado] = useState<EstadoCaso | "">("ABIERTO");
  const [accionError, setAccionError] = useState("");
  const [accionAviso, setAccionAviso] = useState("");
  const [usuarios, setUsuarios] = useState<Usuario[]>([]);

  // Formulario de nuevo caso
  const [showForm, setShowForm] = useState(false);
  const [pedidos, setPedidos] = useState<Pedido[]>([]);
  const [fPedido, setFPedido] = useState("");
  const [fMotivo, setFMotivo] = useState<MotivoEscalamiento>("RECLAMO");
  const [fPrioridad, setFPrioridad] = useState<PrioridadCaso>("MEDIA");
  const [fDesc, setFDesc] = useState("");
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");

  // Respuesta desde la plataforma
  const [replyCaso, setReplyCaso] = useState<Caso | null>(null);
  const [detalle, setDetalle] = useState<CasoDetalle | null>(null);
  const [hilo, setHilo] = useState<ThreadMessage[]>([]);
  const [cargandoDetalle, setCargandoDetalle] = useState(false);
  const [respuesta, setRespuesta] = useState("");
  const [enviandoRespuesta, setEnviandoRespuesta] = useState(false);
  const [replyError, setReplyError] = useState("");
  const [replyAviso, setReplyAviso] = useState("");
  const [responsableSel, setResponsableSel] = useState("");
  const [reasignando, setReasignando] = useState(false);

  async function load() {
    setRows(await casosApi.list({ estado: estado || undefined }));
  }
  useEffect(() => { load(); }, [estado]);

  useEffect(() => {
    if (!esAdmin) return;
    adminApi.usuarios.list()
      .then((lista) => setUsuarios(lista))
      .catch(() => setUsuarios([]));
  }, [esAdmin]);

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
    setAccionError("");
    setAccionAviso("");
    try {
      const caso = await casosApi.actualizar(id, {
        registrar_primera_accion: true,
      });
      setAccionAviso(
        caso.responsable_nombre
          ? `Primera acción registrada. Caso asignado a ${caso.responsable_nombre}.`
          : "Primera acción registrada.",
      );
      // La primera acción mueve el caso a EN_PROCESO. Si el mantenedor está
      // filtrado por ABIERTO, cambiamos el filtro para que no desaparezca.
      if (estado === "ABIERTO") {
        setEstado("EN_PROCESO");
      } else {
        await load();
      }
    } catch (err) {
      setAccionError(mensajeError(err));
    }
  }

  async function cerrar(id: number) {
    setAccionError("");
    setAccionAviso("");
    try {
      const res = await casosApi.cerrar(id);
      if (res.aviso) setAccionAviso(res.aviso);
      load();
    } catch (err) {
      setAccionError(mensajeError(err));
    }
  }

  async function reasignarCaso(id: number, nuevo: number | null) {
    if (reasignando) return;
    setReasignando(true);
    setReplyError("");
    setReplyAviso("");
    try {
      const res = await casosApi.reasignar(id, nuevo);
      setReplyAviso(res.aviso ?? "Asignación actualizada.");
      const d = await casosApi.detalle(id);
      setDetalle(d);
      setResponsableSel(d.responsable_id ? String(d.responsable_id) : "");
      await load();
    } catch (err) {
      setReplyError(mensajeError(err));
    } finally {
      setReasignando(false);
    }
  }

  async function liberarCaso(id: number) {
    setAccionError("");
    setAccionAviso("");
    try {
      const res = await casosApi.reasignar(id, null);
      setAccionAviso(res.aviso ?? "Caso liberado.");
      load();
    } catch (err) {
      setAccionError(mensajeError(err));
    }
  }

  async function abrirResponder(caso: Caso) {
    setReplyCaso(caso);
    setDetalle(null);
    setHilo([]);
    setRespuesta("");
    setReplyError("");
    setReplyAviso("");
    setResponsableSel(caso.responsable_id ? String(caso.responsable_id) : "");
    setCargandoDetalle(true);
    try {
      const [d, h] = await Promise.all([
        casosApi.detalle(caso.id),
        agentApi.thread(caso.pedido_id),
      ]);
      setDetalle(d);
      setHilo(h);
      setResponsableSel(d.responsable_id ? String(d.responsable_id) : "");
    } catch (err) {
      setReplyError(mensajeError(err));
    } finally {
      setCargandoDetalle(false);
    }
  }

  function cerrarResponder() {
    setReplyCaso(null);
    setDetalle(null);
    setHilo([]);
    setRespuesta("");
    setReplyError("");
    setReplyAviso("");
    setResponsableSel("");
  }

  async function enviarRespuesta(e: FormEvent) {
    e.preventDefault();
    if (!replyCaso || !respuesta.trim() || enviandoRespuesta) return;
    setEnviandoRespuesta(true);
    setReplyError("");
    setReplyAviso("");
    try {
      const res = await casosApi.responder(replyCaso.id, respuesta.trim());
      setReplyAviso(
        res.aviso ?? "Respuesta registrada y enviada al cliente por Telegram.",
      );
      setRespuesta("");
      const [d, h] = await Promise.all([
        casosApi.detalle(replyCaso.id),
        agentApi.thread(replyCaso.pedido_id),
      ]);
      setDetalle(d);
      setHilo(h);
      load();
    } catch (err) {
      setReplyError(mensajeError(err));
    } finally {
      setEnviandoRespuesta(false);
    }
  }

  const puedeEscribir = Boolean(
    detalle?.puede_responder && detalle?.cliente_telegram_vinculado,
  );

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

      {accionError && (
        <p style={{ color: "crimson", fontSize: "0.85rem" }}>{accionError}</p>
      )}
      {accionAviso && (
        <p style={{ color: "#166534", fontSize: "0.85rem" }}>{accionAviso}</p>
      )}

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

      {/* Responder caso desde la plataforma */}
      <Modal
        open={replyCaso !== null}
        title={replyCaso ? `Responder caso #${replyCaso.id}` : "Responder caso"}
        onClose={cerrarResponder}
      >
        {cargandoDetalle && <Loading label="Cargando caso…" />}
        {!cargandoDetalle && detalle && (
          <div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: "0.6rem" }}>
              <StatusBadge value={detalle.estado} />
              <StatusBadge value={detalle.prioridad} />
              <StatusBadge value={detalle.motivo} />
              <span style={{ fontSize: "0.78rem", color: "#475569" }}>
                Pedido <strong>{detalle.pedido_codigo}</strong> · Cliente{" "}
                <strong>{detalle.cliente_nombre}</strong>
              </span>
            </div>

            <div style={{
              background: "#f8fafc", border: "1px solid #e2e8f0",
              borderRadius: 8, padding: "0.6rem 0.75rem", marginBottom: "0.7rem",
              fontSize: "0.82rem", color: "#334155",
            }}>
              <div>
                <strong>Responsable:</strong>{" "}
                {detalle.responsable_nombre ?? "sin asignar"}
              </div>
              <div style={{ marginTop: 3 }}>
                <strong>Telegram del cliente:</strong>{" "}
                {detalle.cliente_telegram_vinculado ? "vinculado ✅" : "sin vincular ⚠️"}
              </div>
              {!detalle.cliente_telegram_vinculado && (
                <div style={{ marginTop: 5, color: "#9a3412" }}>
                  El cliente debe enviar su código de pedido y DNI al bot para
                  poder recibir respuestas. Sin eso, la plataforma no puede
                  entregar el mensaje.
                </div>
              )}
              {!detalle.puede_responder && (
                <div style={{ marginTop: 5, color: "#9a3412" }}>
                  {detalle.estado === "CERRADO"
                    ? "Este caso está cerrado."
                    : "Otro operador ya tomó este caso."}
                </div>
              )}
              {esAdmin && detalle.estado !== "CERRADO" && (
                <div style={{
                  marginTop: 8, paddingTop: 8, borderTop: "1px solid #e2e8f0",
                  display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap",
                }}>
                  <strong>Asignación:</strong>
                  <select
                    value={responsableSel}
                    onChange={(e) => setResponsableSel(e.target.value)}
                    disabled={reasignando}
                  >
                    <option value="">Sin asignar</option>
                    {usuarios
                      .filter((u) => u.activo
                        && u.roles.some((r) => r === "ADMIN" || r === "OPERADOR"))
                      .map((u) => (
                        <option key={u.id} value={u.id}>
                          {u.nombre_completo}
                        </option>
                      ))}
                  </select>
                  <button
                    type="button"
                    disabled={reasignando}
                    onClick={() => reasignarCaso(
                      detalle.id,
                      responsableSel ? Number(responsableSel) : null,
                    )}
                  >
                    {reasignando ? "Guardando…" : "Guardar asignación"}
                  </button>
                </div>
              )}
              {esAdmin && detalle.responsable_id && detalle.responsable_id !== userId
                && detalle.estado !== "CERRADO" && (
                <div style={{ marginTop: 5, color: "#1d4ed8" }}>
                  Puedes responder aunque el caso esté asignado a otro operador.
                  La asignación se mantendrá.
                </div>
              )}
              {!esAdmin && detalle.responsable_id === userId
                && detalle.estado !== "CERRADO" && (
                <button
                  type="button"
                  style={{ marginTop: 8 }}
                  onClick={() => reasignarCaso(detalle.id, null)}
                  disabled={reasignando}
                >
                  {reasignando ? "Liberando…" : "Liberar caso"}
                </button>
              )}
            </div>

            <div style={{ marginBottom: "0.7rem" }}>
              <strong style={{ fontSize: "0.85rem" }}>Conversación con el cliente</strong>
              <div style={{
                marginTop: 5, maxHeight: 220, overflowY: "auto",
                border: "1px solid #e2e8f0", borderRadius: 8,
                background: "#efeae2", padding: "0.6rem",
              }}>
                {hilo.length === 0 && (
                  <p style={{ margin: 0, color: "#64748b", fontSize: "0.82rem" }}>
                    Todavía no hay mensajes de conversación.
                  </p>
                )}
                {hilo.map((m) => {
                  const esCliente = m.autor === "CLIENTE";
                  return (
                    <div
                      key={m.id}
                      style={{
                        display: "flex",
                        justifyContent: esCliente ? "flex-start" : "flex-end",
                        marginBottom: 6,
                      }}
                    >
                      <div style={{
                        maxWidth: "82%", background: esCliente ? "white" : "#d9fdd3",
                        borderRadius: 8, padding: "0.4rem 0.55rem",
                        boxShadow: "0 1px 1px rgba(0,0,0,0.08)",
                      }}>
                        <div style={{
                          fontSize: "0.68rem", fontWeight: 700, color: "#64748b",
                        }}>
                          {esCliente
                            ? detalle.cliente_nombre
                            : m.autor === "HUMANO" ? "Operador" : "Agente IA"}
                        </div>
                        <div style={{ fontSize: "0.83rem", whiteSpace: "pre-wrap" }}>
                          {m.contenido}
                        </div>
                        <div style={{
                          fontSize: "0.65rem", color: "#64748b", textAlign: "right",
                        }}>
                          {hora(m.fecha)}
                          {!esCliente && m.estado_entrega === "SENT" ? " ✓✓" : ""}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            <details style={{ marginBottom: "0.8rem" }}>
              <summary style={{ cursor: "pointer", fontSize: "0.85rem", fontWeight: 600 }}>
                Ver línea de tiempo del pedido
              </summary>
              <div style={{ marginTop: 8 }}>
                <Timeline pedidoId={detalle.pedido_id} titulo="Historial del pedido" />
              </div>
            </details>

            <form onSubmit={enviarRespuesta}>
              <FormField label="Respuesta al cliente" required>
                <textarea
                  rows={4}
                  value={respuesta}
                  onChange={(e) => setRespuesta(e.target.value)}
                  placeholder="Escribe la respuesta que recibirá el cliente…"
                  style={{ width: "100%" }}
                  disabled={!puedeEscribir || enviandoRespuesta}
                />
              </FormField>
              {replyError && (
                <p style={{ color: "crimson", fontSize: "0.85rem" }}>{replyError}</p>
              )}
              {replyAviso && (
                <p style={{ color: "#166534", fontSize: "0.85rem" }}>{replyAviso}</p>
              )}
              <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
                <button type="button" onClick={cerrarResponder}>Cerrar ventana</button>
                <button
                  type="submit"
                  disabled={!puedeEscribir || enviandoRespuesta || !respuesta.trim()}
                >
                  {enviandoRespuesta ? "Enviando…" : "Enviar respuesta"}
                </button>
              </div>
            </form>
          </div>
        )}
        {!cargandoDetalle && !detalle && replyError && (
          <p style={{ color: "crimson", fontSize: "0.85rem" }}>{replyError}</p>
        )}
      </Modal>

      {!rows ? <Loading /> : (
        <DataTable
          rows={rows}
          columns={[
            { key: "id", header: "#", render: (c) => c.id },
            { key: "pedido", header: "Pedido",
              render: (c) => c.pedido_codigo ?? `#${c.pedido_id}` },
            { key: "motivo", header: "Motivo",
              render: (c) => <StatusBadge value={c.motivo} /> },
            { key: "prioridad", header: "Prioridad",
              render: (c) => <StatusBadge value={c.prioridad} /> },
            { key: "estado", header: "Estado",
              render: (c) => <StatusBadge value={c.estado} /> },
            { key: "resp", header: "Responsable",
              render: (c) => c.responsable_nombre
                ?? (c.responsable_id ? `#${c.responsable_id}` : "sin asignar") },
            { key: "aper", header: "Apertura",
              render: (c) => new Date(c.fecha_apertura).toLocaleString() },
            { key: "acc", header: "Acciones",
              render: (c) => hasRole("ADMIN", "OPERADOR") ? (
                <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                  <button onClick={() => abrirResponder(c)}>Ver detalle</button>
                  {c.estado !== "CERRADO" && (
                    <button onClick={() => abrirResponder(c)}>Responder</button>
                  )}
                  {c.estado !== "CERRADO" && c.responsable_id === userId && (
                    <button onClick={() => liberarCaso(c.id)}>Liberar</button>
                  )}
                  {!c.fecha_primera_accion && c.estado !== "CERRADO" && (
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
