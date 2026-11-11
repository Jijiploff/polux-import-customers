import { useState } from "react";
import { adminApi } from "../../api/admin";

export function AdminOpsPage() {
  const [resp, setResp] = useState<{ label: string; data: unknown } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<"rules" | "facts" | null>(null);

  async function run(kind: "rules" | "facts") {
    setLoading(kind); setError(null); setResp(null);
    try {
      const data = kind === "rules"
        ? await adminApi.runRules()
        : await adminApi.syncFacts();
      setResp({
        label: kind === "rules" ? "Motor de reglas" : "Sync de hechos",
        data,
      });
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
        <button onClick={() => run("facts")} disabled={loading !== null}>
          {loading === "facts" ? "Sincronizando hechos…" : "Sincronizar modelo dimensional"}
        </button>
      </div>
      {error && <p style={{ color: "crimson" }}>{error}</p>}
      {resp && (
        <div className="panel" style={{ background: "white", borderRadius: 8, padding: "1rem" }}>
          <h3 style={{ marginTop: 0 }}>{resp.label}</h3>
          <pre style={{ fontSize: "0.85rem" }}>
            {JSON.stringify(resp.data, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}