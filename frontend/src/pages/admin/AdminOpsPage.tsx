import { useState } from "react";
import { adminApi } from "../../api/admin";

type RuleSummary = Record<string, number>;
type RulesResponse = {
  before: RuleSummary;
  counts: RuleSummary;
  after: RuleSummary;
};
type OperationResponse =
  | { kind: "rules"; label: string; data: RulesResponse }
  | { kind: "facts"; label: string; data: unknown };

const SUMMARY_LABELS: Record<string, string> = {
  pedidos_total: "Pedidos totales",
  hitos_atrasados: "Hitos atrasados",
  alertas_abiertas: "Alertas abiertas",
  alertas_retraso_critico: "Alertas críticas por retraso",
  casos_retraso_critico: "Casos críticos por retraso",
};

export function AdminOpsPage() {
  const [resp, setResp] = useState<OperationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<"rules" | "facts" | null>(null);

  async function run(kind: "rules" | "facts") {
    setLoading(kind); setError(null); setResp(null);
    try {
      if (kind === "rules") {
        setResp({
          kind: "rules",
          label: "Motor de reglas",
          data: await adminApi.runRules(),
        });
      } else {
        setResp({
          kind: "facts",
          label: "Sync de hechos",
          data: await adminApi.syncFacts(),
        });
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(null);
    }
  }

  return (
    <div>
      <h1 style={{ marginTop: 0 }}>Operaciones administrativas</h1>
      <p style={{ color: "#64748b", fontSize: "0.9rem" }}>
        Acciones idempotentes que normalmente corre el worker programado. Úsalas
        para forzar la ejecución inmediata.
      </p>
      <div style={{ display: "flex", gap: "0.75rem", marginBottom: "1rem" }}>
        <button onClick={() => run("rules")} disabled={loading !== null}>
          {loading === "rules" ? "Ejecutando motor…" : "Ejecutar motor de reglas"}
        </button>
      </div>
      {error && <p style={{ color: "crimson" }}>{error}</p>}
      {resp && (
        <div className="panel" style={{ background: "white", borderRadius: 8, padding: "1rem" }}>
          <h3 style={{ marginTop: 0 }}>{resp.label}</h3>
          {resp.kind === "rules" ? (
            <>
              <p style={{ color: "#64748b", marginTop: 0 }}>
                Los valores de “Antes” y “Después” son el estado total del sistema.
                “Ejecución” muestra solo lo nuevo detectado en esta corrida.
              </p>
              <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap" }}>
                {(["before", "counts", "after"] as const).map((section) => (
                  <div
                    key={section}
                    style={{
                      flex: "1 1 220px",
                      border: "1px solid #e2e8f0",
                      borderRadius: 6,
                      padding: "0.75rem",
                    }}
                  >
                    <strong>
                      {section === "before"
                        ? "Antes de ejecutar"
                        : section === "counts"
                          ? "Encontrado en esta ejecución"
                          : "Después de ejecutar"}
                    </strong>
                    <dl style={{ margin: "0.5rem 0 0" }}>
                      {Object.entries(resp.data[section]).map(([key, value]) => (
                        <div
                          key={key}
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            gap: "1rem",
                          }}
                        >
                          <dt>{SUMMARY_LABELS[key] ?? key}</dt>
                          <dd style={{ margin: 0, fontWeight: 600 }}>{value}</dd>
                        </div>
                      ))}
                    </dl>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <pre style={{ fontSize: "0.85rem" }}>
              {JSON.stringify(resp.data, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}