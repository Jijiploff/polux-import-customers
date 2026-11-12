import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { Link } from "react-router-dom";
import { agentApi, type ChatResumen, type ThreadMessage } from "../../api/agent";
import { casosApi } from "../../api/casos";
import { ApiError } from "../../api/client";
import { Loading } from "../../components/Loading";
import { Timeline } from "../../components/Timeline";
import { useAuth } from "../../auth/AuthContext";

function hora(fecha: string): string {
  try {
    return new Date(fecha).toLocaleTimeString("es-PE", {
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

function errorTexto(err: unknown): string {
  if (err instanceof ApiError) {
    if (typeof err.detail === "string") return err.detail;
    if (err.status === 409) {
      return "El caso ya está siendo atendido por otro operador.";
    }
    if (err.status === 403) {
      return "No tienes permiso para atender esta conversación.";
    }
  }
  return "No se pudo completar la acción. Inténtalo de nuevo.";
}

function Chip({
  children,
  color = "#e2e8f0",
  texto = "#334155",
}: {
  children: ReactNode;
  color?: string;
  texto?: string;
}) {
  return (
    <span
      style={{
        background: color,
        color: texto,
        borderRadius: 999,
        padding: "0.1rem 0.5rem",
        fontSize: "0.7rem",
        fontWeight: 600,
        whiteSpace: "nowrap",
      }}
    >
      {children}
    </span>
  );
}

export function ContestadorPage() {
  const { hasRole, userId } = useAuth();
  const esAdmin = hasRole("ADMIN");

  const [chats, setChats] = useState<ChatResumen[]>([]);
  const [cargandoChats, setCargandoChats] = useState(true);
  const [filtro, setFiltro] = useState("");

  const [chatId, setChatId] = useState<number | null>(null);
  const [hilo, setHilo] = useState<ThreadMessage[]>([]);
  const [cargandoHilo, setCargandoHilo] = useState(false);

  const [texto, setTexto] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [aviso, setAviso] = useState("");
  const [error, setError] = useState("");
  const [verHistorial, setVerHistorial] = useState(false);

  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const chatActivo = useMemo(
    () => chats.find((c) => c.pedido_id === chatId) ?? null,
    [chats, chatId],
  );

  const puedeEscribir = Boolean(
    chatActivo
      && chatActivo.cliente_telegram_vinculado
      && (
        chatActivo.puede_responder
        || (esAdmin && !chatActivo.caso_abierto_id)
      ),
  );

  const cargarChats = useCallback(async () => {
    try {
      const lista = await agentApi.chats();
      setChats(lista);
      setChatId((prev) => {
        if (prev !== null && lista.some((c) => c.pedido_id === prev)) {
          return prev;
        }
        return lista[0]?.pedido_id ?? null;
      });
    } catch (err) {
      setError(errorTexto(err));
    } finally {
      setCargandoChats(false);
    }
  }, []);

  const cargarHilo = useCallback(async (pid: number) => {
    setCargandoHilo(true);
    try {
      setHilo(await agentApi.thread(pid));
    } catch (err) {
      setHilo([]);
      setError(errorTexto(err));
    } finally {
      setCargandoHilo(false);
    }
  }, []);

  useEffect(() => {
    cargarChats();
  }, [cargarChats]);

  useEffect(() => {
    if (chatId !== null) cargarHilo(chatId);
  }, [chatId, cargarHilo]);

  useEffect(() => {
    if (typeof bottomRef.current?.scrollIntoView === "function") {
      bottomRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [hilo, enviando]);

  function abrirChat(pid: number) {
    if (pid === chatId) return;
    setChatId(pid);
    setTexto("");
    setAviso("");
    setError("");
    setVerHistorial(false);
  }

  async function enviar(e?: FormEvent) {
    e?.preventDefault();
    const contenido = texto.trim();
    if (!contenido || !chatActivo || enviando) return;
    if (!puedeEscribir) {
      setError(
        !chatActivo.cliente_telegram_vinculado
          ? "El cliente no tiene Telegram vinculado."
          : "Esta conversación no está disponible para responder.",
      );
      return;
    }

    setEnviando(true);
    setError("");
    setAviso("");
    try {
      if (chatActivo.caso_abierto_id) {
        const res = await casosApi.responder(
          chatActivo.caso_abierto_id,
          contenido,
        );
        setAviso(
          res.aviso ?? "Respuesta registrada y enviada al cliente por Telegram.",
        );
      } else {
        const res = await agentApi.humanReply(chatActivo.pedido_id, contenido);
        setAviso(res.aviso ?? "Respuesta registrada y enviada al cliente.");
      }
      setTexto("");
      await cargarHilo(chatActivo.pedido_id);
      await cargarChats();
    } catch (err) {
      setError(errorTexto(err));
    } finally {
      setEnviando(false);
    }
  }

  function onTecla(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      enviar();
    }
  }

  const visibles = chats.filter((c) => {
    const q = filtro.trim().toLowerCase();
    if (!q) return true;
    return (
      c.cliente_nombre.toLowerCase().includes(q)
      || c.codigo.toLowerCase().includes(q)
    );
  });

  return (
    <div>
      <style>{`
        .con-fila { display: flex; gap: 1rem; flex-wrap: wrap; align-items: stretch; }
        .con-panel {
          display: flex; flex-direction: column; min-width: 0; overflow: hidden;
          background: white; border: 1px solid #e2e8f0; border-radius: 10px;
          height: clamp(430px, calc(100vh - 245px), 700px);
        }
        .con-lista { flex: 0 1 280px; }
        .con-chat { flex: 1 1 420px; }
        .con-cab { display: flex; align-items: center; justify-content: space-between;
          gap: .5rem; min-width: 0; }
        .con-nombre { font-weight: 700; font-size: .95rem; min-width: 0;
          overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .con-mens {
          flex: 1; min-width: 0; overflow-y: auto; overflow-x: hidden; padding: .9rem;
          background: #efeae2;
          background-image: radial-gradient(rgba(0,0,0,0.045) 1px, transparent 1px);
          background-size: 18px 18px;
        }
        .con-texto { overflow-wrap: anywhere; word-break: break-word; }
        .con-form { display: flex; gap: 8px; align-items: flex-end; flex-wrap: wrap;
          min-width: 0; }
        .con-ta { flex: 1 1 220px; min-width: 0; resize: vertical; }
        .con-bloque { min-width: 0; }
        @media (max-width: 980px) {
          .con-lista { flex: 1 1 100%; height: 200px; }
          .con-chat { flex: 1 1 100%;
            height: clamp(500px, calc(100vh - 400px), 700px); }
        }
      `}</style>

      <div style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        flexWrap: "wrap",
        gap: "0.5rem",
      }}>
        <div>
          <h1 style={{ marginTop: 0, marginBottom: 2 }}>Contestador</h1>
          <p style={{ margin: 0, color: "#64748b", fontSize: "0.88rem" }}>
            {esAdmin
              ? "Bandeja completa. Puedes responder casos asignados a cualquier operador."
              : "Solo ves conversaciones de casos asignados a ti. Los casos libres se reclaman desde Casos."}
          </p>
        </div>
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <Link to="/casos" style={{ fontSize: "0.85rem" }}>
            Ir a Casos →
          </Link>
          {!esAdmin && (
            <Chip color="#eef2ff" texto="#4338ca">
              Operador {userId ?? ""}
            </Chip>
          )}
        </div>
      </div>

      <div className="con-fila" style={{ marginTop: "0.9rem" }}>
        <aside className="con-panel con-lista">
          <div style={{ padding: "0.7rem 0.8rem", borderBottom: "1px solid #e2e8f0" }}>
            <input
              value={filtro}
              onChange={(e) => setFiltro(e.target.value)}
              placeholder="Buscar cliente o código…"
              style={{ width: "100%", boxSizing: "border-box" }}
              aria-label="Buscar cliente o código"
            />
          </div>
          <div style={{ overflowY: "auto", overflowX: "hidden", flex: 1, minWidth: 0 }}>
            {cargandoChats && <div style={{ padding: "1rem" }}><Loading /></div>}
            {!cargandoChats && visibles.length === 0 && (
              <p style={{ padding: "1rem", color: "#94a3b8", fontSize: "0.85rem" }}>
                {esAdmin
                  ? "No hay conversaciones todavía."
                  : "No tienes conversaciones asignadas. Reclama un caso libre desde Casos."}
              </p>
            )}
            {visibles.map((c) => {
              const activo = c.pedido_id === chatId;
              return (
                <button
                  key={c.pedido_id}
                  onClick={() => abrirChat(c.pedido_id)}
                  style={{
                    display: "block",
                    width: "100%",
                    textAlign: "left",
                    border: "none",
                    borderBottom: "1px solid #f1f5f9",
                    background: activo ? "#eff6ff" : "white",
                    borderLeft: activo ? "3px solid #2563eb" : "3px solid transparent",
                    padding: "0.6rem 0.8rem",
                    cursor: "pointer",
                  }}
                >
                  <div style={{
                    display: "flex",
                    justifyContent: "space-between",
                    gap: "0.4rem",
                    alignItems: "baseline",
                  }}>
                    <strong style={{ fontSize: "0.9rem" }}>
                      {c.cliente_nombre || "(sin nombre)"}
                    </strong>
                    <span style={{ fontSize: "0.7rem", color: "#94a3b8" }}>
                      {c.ultima_fecha ? hora(c.ultima_fecha) : ""}
                    </span>
                  </div>
                  <div style={{ fontSize: "0.72rem", color: "#64748b" }}>
                    {c.codigo} · {c.estado_pedido.replace(/_/g, " ").toLowerCase()}
                  </div>
                  <div style={{
                    fontSize: "0.78rem",
                    color: "#475569",
                    marginTop: 2,
                    display: "-webkit-box",
                    WebkitBoxOrient: "vertical",
                    WebkitLineClamp: 1,
                    overflow: "hidden",
                  }}>
                    {c.total_mensajes === 0
                      ? "Sin mensajes aún"
                      : `${c.ultima_autor === "CLIENTE" ? "Cliente: " : ""}${c.ultima_preview ?? ""}`}
                  </div>
                  <div style={{ display: "flex", gap: 4, marginTop: 4, flexWrap: "wrap" }}>
                    {c.responsable_nombre && (
                      <Chip color="#dcfce7" texto="#166534">
                        {c.responsable_nombre}
                      </Chip>
                    )}
                    {c.caso_abierto_id && (
                      <Chip color="#fee2e2" texto="#b91c1c">
                        Caso #{c.caso_abierto_id}
                      </Chip>
                    )}
                    {c.asesor_reciente && (
                      <Chip color="#dbeafe" texto="#1d4ed8">Asesor activo</Chip>
                    )}
                  </div>
                </button>
              );
            })}
          </div>
        </aside>

        <section className="con-panel con-chat">
          <div style={{
            background: "#008069",
            color: "white",
            padding: "0.65rem 0.9rem",
            flexShrink: 0,
          }}>
            <div className="con-cab">
              <div style={{ minWidth: 0 }}>
                <div className="con-nombre">
                  {chatActivo ? chatActivo.cliente_nombre : "Selecciona una conversación"}
                </div>
                <div style={{
                  fontSize: "0.72rem",
                  opacity: 0.85,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}>
                  {chatActivo
                    ? `${chatActivo.codigo} · ${chatActivo.estado_pedido.replace(/_/g, " ").toLowerCase()}`
                    : "Lista de conversaciones a la izquierda"}
                </div>
              </div>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap", justifyContent: "flex-end" }}>
                {chatActivo && (
                  <button
                    type="button"
                    onClick={() => setVerHistorial((v) => !v)}
                    aria-label="Ver historial del pedido"
                    aria-expanded={verHistorial}
                    style={{
                      background: verHistorial ? "#ffffff" : "rgba(255,255,255,0.15)",
                      color: verHistorial ? "#008069" : "#ffffff",
                      border: "1px solid rgba(255,255,255,0.6)",
                      borderRadius: 999,
                      padding: "2px 10px",
                      fontSize: "0.72rem",
                      fontWeight: 700,
                      cursor: "pointer",
                    }}
                  >
                    📋 Historial
                  </button>
                )}
                {chatActivo?.caso_abierto_id && (
                  <Chip color="#fee2e2" texto="#b91c1c">
                    Caso #{chatActivo.caso_abierto_id} · {chatActivo.caso_abierto_motivo}
                  </Chip>
                )}
                {chatActivo?.responsable_nombre && (
                  <Chip color="#dcfce7" texto="#166534">
                    {chatActivo.responsable_nombre}
                  </Chip>
                )}
              </div>
            </div>
          </div>

          {chatActivo && !chatActivo.cliente_telegram_vinculado && (
            <div style={{
              background: "#fff7ed",
              borderBottom: "1px solid #fdba74",
              color: "#9a3412",
              padding: "0.45rem 0.8rem",
              fontSize: "0.78rem",
            }}>
              El cliente no tiene Telegram vinculado. Pídele que envíe su código
              de pedido y DNI al bot para poder responderle.
            </div>
          )}

          {verHistorial && chatId !== null && (
            <div style={{
              flex: "0 1 auto",
              maxHeight: "45%",
              overflowY: "auto",
              background: "#fff",
              borderBottom: "1px solid #e2e8f0",
              padding: "0.75rem 0.9rem",
            }}>
              <Timeline key={chatId} pedidoId={chatId} titulo="Historial del pedido" />
            </div>
          )}

          <div className="con-mens">
            {cargandoHilo && hilo.length === 0 && (
              <div style={{ padding: "1rem" }}><Loading /></div>
            )}
            {!cargandoHilo && hilo.length === 0 && chatActivo && (
              <p style={{ color: "#6b7280", fontSize: "0.85rem", textAlign: "center" }}>
                Sin mensajes de conversación todavía.
              </p>
            )}

            {hilo.map((m) => {
              const esCliente = m.autor === "CLIENTE";
              const esHumano = m.autor === "HUMANO";
              return (
                <div
                  key={m.id}
                  style={{
                    display: "flex",
                    justifyContent: esCliente ? "flex-start" : "flex-end",
                    gap: 6,
                    marginBottom: 12,
                  }}
                >
                  <div style={{
                    width: 26,
                    height: 26,
                    borderRadius: "50%",
                    flexShrink: 0,
                    background: esCliente ? "#64748b" : esHumano ? "#1d4ed8" : "#0b1221",
                    color: "white",
                    fontSize: "0.65rem",
                    fontWeight: 700,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}>
                    {esCliente ? "C" : esHumano ? "TÚ" : "IA"}
                  </div>
                  <div style={{ maxWidth: "74%" }}>
                    <div style={{
                      background: esCliente ? "#ffffff" : "#d9fdd3",
                      border: esHumano ? "1px solid #93c5fd" : "1px solid transparent",
                      borderRadius: esCliente ? "0 10px 10px 10px" : "10px 0 10px 10px",
                      padding: "0.45rem 0.65rem",
                      boxShadow: "0 1px 1px rgba(0,0,0,0.08)",
                    }}>
                      <div style={{
                        fontSize: "0.68rem",
                        fontWeight: 700,
                        color: esCliente ? "#64748b" : esHumano ? "#1d4ed8" : "#0f766e",
                        marginBottom: 2,
                      }}>
                        {esCliente
                          ? (chatActivo?.cliente_nombre || "Cliente")
                          : esHumano ? "Operador" : "Agente IA"}
                      </div>
                      <div className="con-texto" style={{ fontSize: "0.88rem", whiteSpace: "pre-wrap" }}>
                        {m.contenido}
                      </div>
                      <div style={{
                        display: "flex",
                        justifyContent: "flex-end",
                        gap: 4,
                        fontSize: "0.65rem",
                        color: "#64748b",
                        marginTop: 3,
                      }}>
                        {hora(m.fecha)}
                        {!esCliente && (
                          <span title={m.estado_entrega ?? ""}>
                            {m.estado_entrega === "SENT" ? "✓✓" : "⏳"}
                          </span>
                        )}
                      </div>
                    </div>
                    {m.escalado && esCliente && (
                      <div style={{
                        marginTop: 5,
                        background: "#fff7ed",
                        border: "1px solid #fdba74",
                        borderRadius: 8,
                        padding: "0.35rem 0.55rem",
                        fontSize: "0.75rem",
                        color: "#9a3412",
                      }}>
                        ⚠️ Derivado a una persona
                        {m.caso_id && <> · <strong>Caso #{m.caso_id}</strong></>}
                        {m.caso_motivo && <> · {m.caso_motivo}</>}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
            <div ref={bottomRef} />
          </div>

          <div className="con-bloque" style={{
            borderTop: "1px solid #e2e8f0",
            padding: "0.6rem 0.8rem",
            flexShrink: 0,
          }}>
            {error && <p style={{ color: "crimson", fontSize: "0.8rem", margin: "0 0 0.35rem" }}>{error}</p>}
            {aviso && <p style={{ color: "#166534", fontSize: "0.8rem", margin: "0 0 0.35rem" }}>✅ {aviso}</p>}
            {chatActivo && !puedeEscribir && (
              <p style={{ color: "#9a3412", fontSize: "0.8rem", margin: "0 0 0.35rem" }}>
                {!chatActivo.cliente_telegram_vinculado
                  ? "No se puede responder: falta vincular el Telegram del cliente."
                  : chatActivo.caso_abierto_id
                    ? "No puedes responder este caso porque está asignado a otro operador."
                    : "Selecciona una conversación disponible para responder."}
              </p>
            )}
            <form onSubmit={enviar} className="con-form">
              <textarea
                ref={inputRef}
                rows={2}
                value={texto}
                onChange={(e) => setTexto(e.target.value)}
                onKeyDown={onTecla}
                disabled={enviando || !puedeEscribir}
                placeholder={
                  chatActivo?.caso_abierto_id
                    ? "Escribe la respuesta al cliente…"
                    : "Escribe la respuesta al cliente…"
                }
                className="con-ta"
                aria-label="Respuesta al cliente"
              />
              <button
                type="submit"
                disabled={enviando || !texto.trim() || !puedeEscribir}
                style={{
                  background: "#1d4ed8",
                  color: "white",
                  border: "none",
                  borderRadius: 7,
                  padding: "0.5rem 1rem",
                  cursor: "pointer",
                  fontSize: "0.85rem",
                }}
              >
                {enviando ? "Enviando…" : "Enviar"}
              </button>
            </form>
            <p style={{ margin: "0.4rem 0 0", fontSize: "0.72rem", color: "#64748b" }}>
              La respuesta queda registrada como HUMANO y el agente no interviene
              durante los próximos minutos. Si el cliente no tiene Telegram, se
              bloqueará y quedará constancia operativa.
            </p>
          </div>
        </section>
      </div>
    </div>
  );
}
