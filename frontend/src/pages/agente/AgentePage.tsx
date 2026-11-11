import { useEffect, useState, type FormEvent } from "react";
import {
  agentApi, type AgentMetrics, type AgentResult, type ClassifyTestResult,
} from "../../api/agent";
import { pedidosApi } from "../../api/pedidos";
import { useAuth } from "../../auth/AuthContext";
import { Loading } from "../../components/Loading";
import { FormField } from "../../components/FormField";
import type { Canal, Pedido } from "../../types/domain";

interface ChatEntry {
  contenido: string;
  pedidoId?: number;
  result: AgentResult;
}

function MetricCard({ label, value, hint }: {
  label: string; value: string | number; hint?: string;
}) {
  return (
    <div style={{
      background: "white", border: "1px solid #e2e8f0", borderRadius: 8,
      padding: "0.75rem 1rem", minWidth: 140,
    }}>
      <div style={{ fontSize: "0.75rem", color: "#64748b" }}>{label}</div>
      <div style={{ fontSize: "1.4rem", fontWeight: 700 }}>{value}</div>
      {hint && <div style={{ fontSize: "0.72rem", color: "#94a3b8" }}>{hint}</div>}
    </div>
  );
}

export function AgentePage() {
  const { hasRole } = useAuth();
  const [provider, setProvider] = useState<string>("…");
  const [metrics, setMetrics] = useState<AgentMetrics | null>(null);
  const [pedidos, setPedidos] = useState<Pedido[]>([]);

  // Formulario de prueba de conversación
  const [canal, setCanal] = useState<Canal>("WHATSAPP");
  const [pedidoId, setPedidoId] = useState<string>("");
  const [contenido, setContenido] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [chat, setChat] = useState<ChatEntry[]>([]);

  // Prueba de clasificación (solo ADMIN)
  const [testText, setTestText] = useState("");
  const [testResult, setTestResult] = useState<ClassifyTestResult | null>(null);
  const [testing, setTesting] = useState(false);

  async function loadMetrics() {
    try { setMetrics(await agentApi.metrics()); } catch { /* sin datos */ }
  }

  useEffect(() => {
    agentApi.provider().then((r) => setProvider(r.provider)).catch(() => setProvider("no disponible"));
    loadMetrics();
    pedidosApi.list({ size: 50 })
      .then((r) => setPedidos(r.items ?? []))
      .catch(() => setPedidos([]));
  }, []);

  async function enviarMensaje(e: FormEvent) {
    e.preventDefault();
    if (!contenido.trim()) return;
    setSending(true);
    setError("");
    try {
      const result = await agentApi.incoming({
        contenido: contenido.trim(),
        canal,
        pedido_id: pedidoId ? Number(pedidoId) : undefined,
      });
      setChat((prev) => [...prev, { contenido: contenido.trim(), pedidoId: pedidoId ? Number(pedidoId) : undefined, result }]);
      setContenido("");
      loadMetrics();
    } catch (err) {
      setError("No se pudo procesar el mensaje. Revisa que el pedido exista y vuelve a intentarlo.");
    } finally {
      setSending(false);
    }
  }

  async function probarClasificacion(e: FormEvent) {
    e.preventDefault();
    if (!testText.trim()) return;
    setTesting(true);
    try {
      setTestResult(await agentApi.classify(testText.trim()));
    } catch {
      setTestResult(null);
      setError("No se pudo clasificar el texto.");
    } finally {
      setTesting(false);
    }
  }

  return (
    <div>
      <div className="page-toolbar" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1 style={{ marginTop: 0 }}>Agente IA</h1>
        <span style={{
          background: "#eef2ff", color: "#4338ca", borderRadius: 999,
          padding: "0.25rem 0.75rem", fontSize: "0.8rem", fontWeight: 600,
        }}>
          Motor: {provider}
        </span>
      </div>
      <p style={{ color: "#64748b", marginTop: 0, maxWidth: 720 }}>
        Aquí puedes conversar con el agente como si fueras un cliente: él clasifica el
        mensaje, responde con una plantilla y decide si escala a una persona.
        El mensaje siempre queda en <strong>Comunicaciones</strong>; la respuesta
        también cuando asocias el mensaje a un pedido. Para responder a un caso
        escalado, usa <strong>Casos → Responder</strong>.
      </p>

      {/* Métricas del agente */}
      <section style={{ marginBottom: "1.5rem" }}>
        <h3 style={{ marginBottom: "0.5rem" }}>Resumen</h3>
        {!metrics ? <Loading /> : (
          <>
            <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
              <MetricCard label="Mensajes de clientes" value={metrics.total_entrantes} />
              <MetricCard label="Respuestas del agente" value={metrics.total_salientes} />
              <MetricCard label="Escalados a persona" value={metrics.escalados} />
              <MetricCard
                label="Tasa de escalamiento"
                value={`${metrics.tasa_escalamiento}%`}
                hint="¿Cuántas consultas necesitaron a una persona?"
              />
              <MetricCard
                label="Con plantilla / sin plantilla"
                value={`${metrics.con_plantilla} / ${metrics.sin_plantilla}`}
              />
            </div>
            <div style={{ display: "flex", gap: "1.5rem", marginTop: "0.75rem", flexWrap: "wrap", fontSize: "0.85rem" }}>
              <span><strong>Intenciones:</strong>{" "}
                {Object.entries(metrics.por_intent).map(([k, v]) => `${k} (${v})`).join(" · ") || "—"}</span>
              <span><strong>Sentimientos:</strong>{" "}
                {Object.entries(metrics.por_sentimiento).map(([k, v]) => `${k} (${v})`).join(" · ") || "—"}</span>
            </div>
          </>
        )}
      </section>

      <div style={{ display: "flex", gap: "1.5rem", flexWrap: "wrap", alignItems: "flex-start" }}>
        {/* Prueba de conversación con el agente */}
        <section style={{
          flex: "1 1 380px", background: "white", border: "1px solid #e2e8f0",
          borderRadius: 8, padding: "1rem",
        }}>
          <h3 style={{ marginTop: 0 }}>Probar conversación</h3>
          <form onSubmit={enviarMensaje}>
            <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
              <FormField label="Canal">
                <select value={canal} onChange={(e) => setCanal(e.target.value as Canal)}>
                  <option value="WHATSAPP">WhatsApp</option>
                  <option value="EMAIL">Email</option>
                  <option value="WEB">Web</option>
                  <option value="TELEGRAM">Telegram</option>
                </select>
              </FormField>
              <FormField label="Pedido (opcional)">
                <select value={pedidoId} onChange={(e) => setPedidoId(e.target.value)}>
                  <option value="">— Sin pedido —</option>
                  {pedidos.map((p) => (
                    <option key={p.id} value={p.id}>{p.codigo}</option>
                  ))}
                </select>
              </FormField>
            </div>
            <FormField label="Mensaje del cliente" required>
              <textarea
                rows={3}
                value={contenido}
                onChange={(e) => setContenido(e.target.value)}
                placeholder="Ej.: ¿Cuándo llega mi pedido PD-2025-0001?"
                style={{ width: "100%" }}
              />
            </FormField>
            {error && <p style={{ color: "crimson", fontSize: "0.85rem" }}>{error}</p>}
            <button type="submit" disabled={sending || !contenido.trim()}>
              {sending ? "Procesando…" : "Enviar mensaje"}
            </button>
          </form>

          {/* Conversación */}
          <div style={{ marginTop: "1rem", display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            {chat.length === 0 && (
              <p style={{ color: "#94a3b8", fontSize: "0.85rem" }}>
                Aún no hay mensajes. Escribe uno para ver cómo reacciona el agente.
              </p>
            )}
            {chat.map((entry, idx) => (
              <div key={idx}>
                <div style={{
                  alignSelf: "flex-start", background: "#f1f5f9", borderRadius: 8,
                  padding: "0.5rem 0.75rem", maxWidth: "90%",
                }}>
                  <div style={{ fontSize: "0.7rem", color: "#64748b" }}>
                    Cliente{entry.pedidoId ? ` · pedido #${entry.pedidoId}` : ""}
                  </div>
                  {entry.contenido}
                </div>
                <div style={{
                  alignSelf: "flex-end", background: "#dbeafe", borderRadius: 8,
                  padding: "0.5rem 0.75rem", maxWidth: "90%", marginTop: 4,
                  marginLeft: "auto",
                }}>
                  <div style={{ fontSize: "0.7rem", color: "#64748b" }}>
                    Agente · {entry.result.classification.provider_used}
                    {entry.result.fallback_used ? " (respuesta de respaldo)" : ""}
                  </div>
                  {entry.result.response_text ?? "(sin respuesta de texto)"}
                </div>
                <div style={{ fontSize: "0.75rem", color: "#475569", marginTop: 4 }}>
                  Intención: <strong>{entry.result.classification.intent}</strong> ·
                  Sentimiento: <strong>{entry.result.classification.sentiment}</strong> ·
                  Confianza: {(entry.result.classification.confidence * 100).toFixed(0)}%
                  {entry.result.escalated && (
                    <> · ⚠️ <strong>Escalado a persona</strong>
                      {entry.result.caso_id ? ` (caso #${entry.result.caso_id})` : ""}
                      {entry.result.escalation_reason ? ` — ${entry.result.escalation_reason}` : ""}
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Prueba de clasificación — solo ADMIN */}
        {hasRole("ADMIN") && (
          <section style={{
            flex: "0 1 320px", background: "white", border: "1px solid #e2e8f0",
            borderRadius: 8, padding: "1rem",
          }}>
            <h3 style={{ marginTop: 0 }}>Probar clasificación</h3>
            <p style={{ fontSize: "0.82rem", color: "#64748b", marginTop: 0 }}>
              Solo clasifica el texto (intención y sentimiento). No responde ni
              registra nada en el sistema.
            </p>
            <form onSubmit={probarClasificacion}>
              <FormField label="Texto" required>
                <textarea
                  rows={3}
                  value={testText}
                  onChange={(e) => setTestText(e.target.value)}
                  placeholder="Ej.: Me han robado el paquete, esto es una desgracia"
                  style={{ width: "100%" }}
                />
              </FormField>
              <button type="submit" disabled={testing || !testText.trim()}>
                {testing ? "Clasificando…" : "Clasificar"}
              </button>
            </form>
            {testResult && (
              <div style={{
                marginTop: "0.75rem", background: "#f8fafc", borderRadius: 6,
                padding: "0.6rem 0.75rem", fontSize: "0.85rem",
              }}>
                <div>Intención: <strong>{testResult.intent}</strong></div>
                <div>Sentimiento: <strong>{testResult.sentiment}</strong></div>
                <div>Confianza: <strong>{(testResult.confidence * 100).toFixed(0)}%</strong></div>
                <div style={{ color: "#64748b" }}>Motor: {testResult.provider_used}</div>
              </div>
            )}
          </section>
        )}
      </div>
    </div>
  );
}
