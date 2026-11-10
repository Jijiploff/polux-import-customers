import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import { Link } from "react-router-dom";
import {
  agentApi,
  type AgentResult,
  type ChatResumen,
  type ThreadMessage,
} from "../../api/agent";
import { Loading } from "../../components/Loading";

type Modo = "cliente" | "asesor";

const SUGERENCIAS = [
  "Hola, buenos días",
  "¿Dónde está mi pedido? ¿Cuándo llega?",
  "¿Por qué no llega? ya pasó la fecha prometida",
  "El iPhone llegó con la pantalla rota",
  "¿Puedo recibir solo los AirPods primero?",
  "¿Cómo pago las cuotas de mi contrato?",
];

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

function Chip({ children, color = "#e2e8f0", texto = "#334155" }: {
  children: React.ReactNode; color?: string; texto?: string;
}) {
  return (
    <span style={{
      background: color, color: texto, borderRadius: 999,
      padding: "0.1rem 0.5rem", fontSize: "0.7rem", fontWeight: 600,
      whiteSpace: "nowrap",
    }}>
      {children}
    </span>
  );
}

export function SimuladorPage() {
  const [provider, setProvider] = useState("…");
  const [chats, setChats] = useState<ChatResumen[]>([]);
  const [cargandoChats, setCargandoChats] = useState(true);
  const [filtro, setFiltro] = useState("");

  const [chatId, setChatId] = useState<number | null>(null);
  const [hilo, setHilo] = useState<ThreadMessage[]>([]);
  const [cargandoHilo, setCargandoHilo] = useState(false);

  const [texto, setTexto] = useState("");
  const [modo, setModo] = useState<Modo>("cliente");
  const [enviando, setEnviando] = useState(false);
  const [ultimo, setUltimo] = useState<AgentResult | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [error, setError] = useState("");

  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const chatActivo = chats.find((c) => c.pedido_id === chatId) ?? null;

  const cargarChats = useCallback(async () => {
    try {
      const lista = await agentApi.chats();
      setChats(lista);
      // Auto-selección: siempre hay un chat abierto si hay conversaciones
      setChatId((prev) => prev ?? (lista[0]?.pedido_id ?? null));
    } catch {
      setError("No se pudo cargar la lista de conversaciones.");
    } finally {
      setCargandoChats(false);
    }
  }, []);

  const cargarHilo = useCallback(async (pid: number) => {
    setCargandoHilo(true);
    try {
      setHilo(await agentApi.thread(pid));
    } catch {
      setHilo([]);
      setError("No se pudo cargar la conversación.");
    } finally {
      setCargandoHilo(false);
    }
  }, []);

  useEffect(() => {
    agentApi.provider()
      .then((r) => setProvider(r.provider))
      .catch(() => setProvider("no disponible"));
    cargarChats();
  }, [cargarChats]);

  useEffect(() => {
    if (chatId !== null) cargarHilo(chatId);
  }, [chatId, cargarHilo]);

  useEffect(() => {
    // jsdom (tests) no implementa scrollIntoView
    if (typeof bottomRef.current?.scrollIntoView === "function") {
      bottomRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [hilo, enviando]);

  function abrirChat(pid: number) {
    if (pid === chatId) return;
    setChatId(pid);
    setUltimo(null);
    setAviso(null);
    setError("");
    setTexto("");
  }

  async function enviar(e?: FormEvent) {
    e?.preventDefault();
    const contenido = texto.trim();
    if (!contenido || chatId === null || enviando) return;
    setEnviando(true);
    setError("");
    setAviso(null);
    try {
      if (modo === "cliente") {
        const res = await agentApi.incoming({
          pedido_id: chatId, canal: "WHATSAPP", contenido,
        });
        setUltimo(res);
      } else {
        const res = await agentApi.humanReply(chatId, contenido);
        // `ultimo` se conserva: sigue siendo la última decisión del agente
        setAviso(res.aviso ?? "Respuesta enviada por un asesor humano.");
      }
      setTexto("");
      await cargarHilo(chatId);
      await cargarChats();
    } catch {
      setError(
        modo === "cliente"
          ? "No se pudo procesar el mensaje. Inténtalo de nuevo."
          : "No se pudo enviar tu respuesta como asesor.",
      );
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
      c.cliente_nombre.toLowerCase().includes(q) ||
      c.codigo.toLowerCase().includes(q)
    );
  });

  return (
    <div>
      <style>{`
        @keyframes polux-parpadeo { 0%, 80%, 100% { opacity: .2 } 40% { opacity: 1 } }
        .polux-punto { animation: polux-parpadeo 1.2s infinite; }
      `}</style>

      <div style={{
        display: "flex", justifyContent: "space-between",
        alignItems: "center", flexWrap: "wrap", gap: "0.5rem",
      }}>
        <h1 style={{ marginTop: 0 }}>Simulador de WhatsApp</h1>
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <span style={{
            background: "#eef2ff", color: "#4338ca", borderRadius: 999,
            padding: "0.25rem 0.75rem", fontSize: "0.8rem", fontWeight: 600,
          }}>
            Motor: {provider}
          </span>
          <Link to="/agente" style={{ fontSize: "0.85rem" }}>Ver métricas del agente →</Link>
        </div>
      </div>

      <p style={{ color: "#64748b", marginTop: 0, maxWidth: 780 }}>
        Practica con el agente como si hablaras por WhatsApp: escribe como
        <strong> cliente</strong> y el agente clasifica, informa y decide si escala
        o responde. Si deriva el caso, cambia a modo <strong>Asesor humano</strong>
        y responde tú desde la plataforma.
      </p>

      <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", alignItems: "stretch" }}>
        {/* ---------- Lista de chats ---------- */}
        <aside style={{
          flex: "0 1 300px", background: "white", border: "1px solid #e2e8f0",
          borderRadius: 10, overflow: "hidden", display: "flex",
          flexDirection: "column", minHeight: 420, maxHeight: 680,
        }}>
          <div style={{ padding: "0.7rem 0.8rem", borderBottom: "1px solid #e2e8f0" }}>
            <input
              value={filtro}
              onChange={(e) => setFiltro(e.target.value)}
              placeholder="Buscar cliente o código…"
              style={{ width: "100%", boxSizing: "border-box" }}
              aria-label="Buscar cliente o código"
            />
          </div>
          <div style={{ overflowY: "auto", flex: 1 }}>
            {cargandoChats && <div style={{ padding: "1rem" }}><Loading /></div>}
            {!cargandoChats && visibles.length === 0 && (
              <p style={{ padding: "1rem", color: "#94a3b8", fontSize: "0.85rem" }}>
                No hay conversaciones todavía.
              </p>
            )}
            {visibles.map((c) => {
              const activo = c.pedido_id === chatId;
              return (
                <button
                  key={c.pedido_id}
                  onClick={() => abrirChat(c.pedido_id)}
                  style={{
                    display: "block", width: "100%", textAlign: "left",
                    border: "none", borderBottom: "1px solid #f1f5f9",
                    background: activo ? "#eff6ff" : "white",
                    borderLeft: activo ? "3px solid #2563eb" : "3px solid transparent",
                    padding: "0.6rem 0.8rem", cursor: "pointer",
                  }}
                >
                  <div style={{
                    display: "flex", justifyContent: "space-between",
                    gap: "0.4rem", alignItems: "baseline",
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
                    fontSize: "0.78rem", color: "#475569", marginTop: 2,
                    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                  }}>
                    {c.total_mensajes === 0
                      ? "Sin mensajes aún"
                      : `${c.ultima_autor === "CLIENTE" ? "Cliente: " : ""}${c.ultima_preview ?? ""}`}
                  </div>
                  <div style={{ display: "flex", gap: 4, marginTop: 4, flexWrap: "wrap" }}>
                    {c.caso_abierto_id && (
                      <Chip color="#fee2e2" texto="#b91c1c">Caso #{c.caso_abierto_id}</Chip>
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

        {/* ---------- Conversación ---------- */}
        <section style={{
          flex: "1 1 460px", background: "white", border: "1px solid #e2e8f0",
          borderRadius: 10, display: "flex", flexDirection: "column",
          minHeight: 420, maxHeight: 680, overflow: "hidden",
        }}>
          {/* Encabezado del chat */}
          <div style={{
            background: "#008069", color: "white", padding: "0.65rem 0.9rem",
            display: "flex", justifyContent: "space-between",
            alignItems: "center", gap: "0.5rem",
          }}>
            <div>
              <div style={{ fontWeight: 700, fontSize: "0.95rem" }}>
                {chatActivo ? chatActivo.cliente_nombre : "Selecciona un chat"}
              </div>
              <div style={{ fontSize: "0.72rem", opacity: 0.85 }}>
                {chatActivo
                  ? `${chatActivo.codigo} · ${chatActivo.estado_pedido.replace(/_/g, " ").toLowerCase()}`
                  : "Lista de conversaciones a la izquierda"}
              </div>
            </div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", justifyContent: "flex-end" }}>
              {chatActivo?.caso_abierto_id && (
                <Chip color="#fee2e2" texto="#b91c1c">
                  Caso #{chatActivo.caso_abierto_id} · {chatActivo.caso_abierto_motivo}
                </Chip>
              )}
              {chatActivo?.asesor_reciente && (
                <Chip color="#dbeafe" texto="#1d4ed8">Asesor respondiendo</Chip>
              )}
            </div>
          </div>

          {/* Mensajes */}
          <div
            style={{
              flex: 1, overflowY: "auto", padding: "0.9rem",
              background: "#efeae2",
              backgroundImage:
                "radial-gradient(rgba(0,0,0,0.045) 1px, transparent 1px)",
              backgroundSize: "18px 18px",
              minHeight: 260,
            }}
          >
            {cargandoHilo && hilo.length === 0 && (
              <div style={{ padding: "1rem" }}><Loading /></div>
            )}
            {!cargandoHilo && hilo.length === 0 && chatActivo && (
              <p style={{ color: "#6b7280", fontSize: "0.85rem", textAlign: "center" }}>
                Sin mensajes. Escribe el primero para ver cómo reacciona el agente.
              </p>
            )}

            {hilo.map((m) => {
              const esCliente = m.autor === "CLIENTE";
              const esHumano = m.autor === "HUMANO";
              return (
                <div
                  key={m.id}
                  style={{
                    display: "flex", flexDirection: "row",
                    justifyContent: esCliente ? "flex-start" : "flex-end",
                    gap: 6, marginBottom: 12,
                  }}
                >
                  <div style={{
                    width: 26, height: 26, borderRadius: "50%", flexShrink: 0,
                    background: esCliente ? "#64748b" : esHumano ? "#1d4ed8" : "#0b1221",
                    color: "white", fontSize: "0.65rem", fontWeight: 700,
                    display: "flex", alignItems: "center", justifyContent: "center",
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
                        fontSize: "0.68rem", fontWeight: 700,
                        color: esCliente ? "#64748b" : esHumano ? "#1d4ed8" : "#0f766e",
                        marginBottom: 2,
                      }}>
                        {esCliente
                          ? (chatActivo?.cliente_nombre || "Cliente")
                          : esHumano
                            ? "Asesor humano (tú)"
                            : "Agente IA"}
                      </div>
                      <div style={{ fontSize: "0.88rem", whiteSpace: "pre-wrap" }}>
                        {m.contenido}
                      </div>
                      <div style={{
                        display: "flex", justifyContent: "flex-end", gap: 4,
                        fontSize: "0.65rem", color: "#64748b", marginTop: 3,
                      }}>
                        {hora(m.fecha)}
                        {!esCliente && (
                          <span title={m.estado_entrega ?? ""}>
                            {m.estado_entrega === "SENT" ? "✓✓" : "⏳"}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Clasificación registrada en este mensaje */}
                    {m.intencion_detectada && (
                      <div style={{
                        display: "flex", gap: 4, marginTop: 4, flexWrap: "wrap",
                        justifyContent: esCliente ? "flex-start" : "flex-end",
                      }}>
                        <Chip color="#ede9fe" texto="#5b21b6">
                          {m.intencion_detectada}
                        </Chip>
                        {m.sentimiento && (
                          <Chip color="#e0f2fe" texto="#075985">{m.sentimiento}</Chip>
                        )}
                        {m.plantilla_id && (
                          <Chip color="#dcfce7" texto="#166534">plantilla aprobada</Chip>
                        )}
                      </div>
                    )}

                    {/* Acción tomada por el agente: escalamiento */}
                    {m.escalado && esCliente && (
                      <div style={{
                        marginTop: 5, background: "#fff7ed",
                        border: "1px solid #fdba74", borderRadius: 8,
                        padding: "0.35rem 0.55rem", fontSize: "0.75rem",
                        color: "#9a3412",
                      }}>
                        ⚠️ El agente derivó este caso a una persona
                        {m.caso_id && <> · <strong>Caso #{m.caso_id}</strong></>}
                        {m.caso_motivo && <> · motivo {m.caso_motivo}</>}
                        {m.caso_prioridad && <> · prioridad {m.caso_prioridad}</>}
                        {m.caso_estado && <> · estado {m.caso_estado}</>}
                        {" · "}
                        <Link to="/casos">ver casos</Link>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}

            {enviando && (
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <div style={{
                  background: "white", borderRadius: "0 10px 10px 10px",
                  padding: "0.5rem 0.7rem", boxShadow: "0 1px 1px rgba(0,0,0,0.08)",
                }}>
                  <span style={{ fontSize: "0.85rem", color: "#64748b" }}>
                    {modo === "cliente" ? "El agente está escribiendo" : "Enviando"}…
                  </span>
                </div>
                <span className="polux-punto" style={{ width: 6, height: 6, borderRadius: "50%", background: "#64748b" }} />
                <span className="polux-punto" style={{ width: 6, height: 6, borderRadius: "50%", background: "#64748b", animationDelay: "0.2s" }} />
                <span className="polux-punto" style={{ width: 6, height: 6, borderRadius: "50%", background: "#64748b", animationDelay: "0.4s" }} />
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Última decisión del agente */}
          {(ultimo || aviso) && (
            <div style={{
              borderTop: "1px solid #e2e8f0", background: "#f8fafc",
              padding: "0.55rem 0.8rem", fontSize: "0.8rem",
            }}>
              {aviso && (
                <div style={{ color: "#166534", marginBottom: 4 }}>✅ {aviso}</div>
              )}
              {ultimo && (
                <>
                  <div style={{ display: "flex", gap: 5, flexWrap: "wrap", alignItems: "center" }}>
                    <strong>Decisión del agente:</strong>
                    <Chip color="#ede9fe" texto="#5b21b6">
                      {ultimo.classification.intent}
                    </Chip>
                    <Chip color="#e0f2fe" texto="#075985">
                      {ultimo.classification.sentiment}
                    </Chip>
                    <Chip color="#f1f5f9" texto="#334155">
                      confianza {(ultimo.classification.confidence * 100).toFixed(0)}%
                    </Chip>
                    <Chip color="#eef2ff" texto="#4338ca">
                      {ultimo.classification.provider_used}
                      {ultimo.fallback_used ? " (motor local)" : ""}
                    </Chip>
                    {ultimo.escalated
                      ? <Chip color="#fee2e2" texto="#b91c1c">derivado a persona</Chip>
                      : <Chip color="#dcfce7" texto="#166534">respondió solo</Chip>}
                  </div>
                  <div style={{ marginTop: 5, display: "flex", gap: 8, flexWrap: "wrap" }}>
                    {ultimo.escalated && (
                      <button
                        type="button"
                        onClick={() => { setModo("asesor"); inputRef.current?.focus(); }}
                        style={{
                          background: "#1d4ed8", color: "white", border: "none",
                          borderRadius: 6, padding: "0.3rem 0.7rem",
                          fontSize: "0.8rem", cursor: "pointer",
                        }}
                      >
                        Responder como asesor
                      </button>
                    )}
                    {ultimo.escalated && ultimo.caso_id && (
                      <Link
                        to="/casos"
                        style={{ fontSize: "0.8rem", alignSelf: "center" }}
                      >
                        Ver caso #{ultimo.caso_id}
                      </Link>
                    )}
                    {ultimo.human_in_progress && (
                      <span style={{ color: "#9a3412" }}>
                        El agente no interviene: una persona respondió hace poco.
                      </span>
                    )}
                  </div>
                </>
              )}
            </div>
          )}

          {/* Redacción */}
          <div style={{ borderTop: "1px solid #e2e8f0", padding: "0.6rem 0.8rem" }}>
            <div style={{
              display: "flex", gap: 6, overflowX: "auto",
              paddingBottom: 5, alignItems: "center",
            }}>
              <span style={{ fontSize: "0.7rem", color: "#94a3b8", whiteSpace: "nowrap" }}>
                Ideas:
              </span>
              {SUGERENCIAS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => { setTexto(s); inputRef.current?.focus(); }}
                  disabled={enviando}
                  style={{
                    border: "1px solid #cbd5e1", background: "white",
                    borderRadius: 999, padding: "0.15rem 0.6rem",
                    fontSize: "0.73rem", cursor: "pointer", whiteSpace: "nowrap",
                  }}
                >
                  {s}
                </button>
              ))}
            </div>

            <form onSubmit={enviar} style={{ display: "flex", gap: 8, alignItems: "flex-end" }}>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <span style={{ fontSize: "0.7rem", color: "#64748b" }}>
                  Responder como:
                </span>
                <div style={{ display: "flex", borderRadius: 7, overflow: "hidden", border: "1px solid #cbd5e1" }}>
                  <button
                    type="button"
                    onClick={() => setModo("cliente")}
                    aria-pressed={modo === "cliente"}
                    style={{
                      border: "none", padding: "0.35rem 0.6rem", fontSize: "0.78rem",
                      cursor: "pointer", background: modo === "cliente" ? "#2563eb" : "white",
                      color: modo === "cliente" ? "white" : "#475569",
                    }}
                  >
                    Cliente
                  </button>
                  <button
                    type="button"
                    onClick={() => setModo("asesor")}
                    aria-pressed={modo === "asesor"}
                    style={{
                      border: "none", borderLeft: "1px solid #cbd5e1",
                      padding: "0.35rem 0.6rem", fontSize: "0.78rem", cursor: "pointer",
                      background: modo === "asesor" ? "#1d4ed8" : "white",
                      color: modo === "asesor" ? "white" : "#475569",
                    }}
                  >
                    Asesor humano
                  </button>
                </div>
              </div>

              <textarea
                ref={inputRef}
                rows={2}
                value={texto}
                onChange={(e) => setTexto(e.target.value)}
                onKeyDown={onTecla}
                disabled={enviando || chatId === null}
                placeholder={
                  modo === "cliente"
                    ? "Escribe como si fueras el cliente…"
                    : "Escribe la respuesta del asesor…"
                }
                aria-label={modo === "cliente"
                  ? "Mensaje del cliente"
                  : "Respuesta del asesor"}
                style={{ flex: 1, resize: "vertical", minWidth: 200 }}
              />

              <button
                type="submit"
                disabled={enviando || !texto.trim() || chatId === null}
                style={{
                  background: modo === "cliente" ? "#2563eb" : "#1d4ed8",
                  color: "white", border: "none", borderRadius: 7,
                  padding: "0.5rem 1rem", cursor: "pointer", fontSize: "0.85rem",
                }}
              >
                {enviando ? "Enviando…" : "Enviar"}
              </button>
            </form>

            <p style={{ margin: "0.4rem 0 0", fontSize: "0.72rem", color: "#64748b" }}>
              {modo === "cliente"
                ? "Modo cliente: el agente recibe, clasifica el mensaje y responde o escala."
                : "Modo asesor: tu respuesta queda como HUMANO (auditoría) y el agente no responderá en los próximos minutos."}
            </p>
            {error && <p style={{ color: "crimson", fontSize: "0.8rem", margin: "0.3rem 0 0" }}>{error}</p>}
          </div>
        </section>
      </div>
    </div>
  );
}
