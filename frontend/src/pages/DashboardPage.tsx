import { useEffect, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import {
  DashboardResumen, FiltrosOpciones, SerieResponse,
  kpisApi,
} from "../api/kpis";
import { FilterBar, Filters, defaultFilters } from "../components/FilterBar";
import { KpiChart } from "../components/KpiChart";
import { Loading } from "../components/Loading";

const KPI_META: { codigo: string; titulo: string; key: keyof DashboardResumen; sufijo: string }[] = [
  { codigo: "FREQ_ACTUALIZACION_CLIENTE", titulo: "Actualización al cliente",
    key: "actualizacion_cliente", sufijo: "%" },
  { codigo: "TASA_RESOLUCION_AUTOMATICA", titulo: "Resolución automática",
    key: "resolucion_automatica", sufijo: "%" },
  { codigo: "TIEMPO_RESPUESTA_ESCALADOS", titulo: "Tiempo respuesta escalados",
    key: "tiempo_respuesta_escalados", sufijo: " h" },
  { codigo: "TIEMPO_RESOLUCION_IMPREVISTOS", titulo: "Resolución de imprevistos (global)",
    key: "resolucion_imprevistos", sufijo: " d" },
  { codigo: "ENTREGAS_A_TIEMPO", titulo: "Entregas a tiempo",
    key: "entregas_a_tiempo", sufijo: "%" },
  { codigo: "ENTREGAS_SIN_OBSERVACIONES", titulo: "Entregas sin observaciones",
    key: "entregas_sin_observaciones", sufijo: "%" },
  { codigo: "PCT_ENTREGAS_PARCIALES", titulo: "% entregas parciales",
    key: "entregas_parciales", sufijo: "%" },
];

function KpiCard({ titulo, valor, semaforo, sufijo }: {
  titulo: string; valor?: number | null; semaforo: string; sufijo?: string;
}) {
  const color = semaforo === "OPTIMO" ? "#16a34a"
    : semaforo === "ALERTA" ? "#f59e0b"
    : semaforo === "CRITICO" ? "#dc2626" : "#94a3b8";
  return (
    <div style={{
      background: "white", borderRadius: 8, padding: "1rem",
      borderLeft: `4px solid ${color}`, boxShadow: "0 1px 4px rgba(0,0,0,0.05)",
    }}>
      <p style={{ margin: 0, fontSize: "0.8rem", color: "#64748b" }}>{titulo}</p>
      <p style={{ margin: "0.3rem 0 0", fontSize: "1.6rem", fontWeight: 700 }}>
        {valor != null ? valor.toFixed(2) : "—"}{sufijo ?? ""}
      </p>
      <p style={{ margin: 0, fontSize: "0.75rem", color }}>{semaforo}</p>
    </div>
  );
}

export function DashboardPage() {
  const { hasRole } = useAuth();
  const [resumen, setResumen] = useState<DashboardResumen | null>(null);
  const [opciones, setOpciones] = useState<FiltrosOpciones | null>(null);
  const [filters, setFilters] = useState<Filters>(defaultFilters());
  const [kpiSel, setKpiSel] = useState<string>(KPI_META[0].codigo);
  const [serie, setSerie] = useState<SerieResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadingSerie, setLoadingSerie] = useState(false);

  useEffect(() => {
    if (!hasRole("ADMIN", "GERENTE")) return;
    kpisApi.resumen().then(setResumen).catch((e) => setError(String(e)));
    kpisApi.filtros().then(setOpciones).catch(() => {});
  }, [hasRole]);

  useEffect(() => {
    if (!hasRole("ADMIN", "GERENTE") || !filters.desde || !filters.hasta) return;
    setLoadingSerie(true);
    kpisApi.serie(kpiSel, filters)
      .then(setSerie)
      .catch((e) => setError(String(e)))
      .finally(() => setLoadingSerie(false));
  }, [hasRole, kpiSel, filters]);

  if (!hasRole("ADMIN", "GERENTE")) {
    return (
      <div>
        <h1>Bienvenido</h1>
        <p>Usa el menú lateral para gestionar pedidos, casos y entregas.</p>
      </div>
    );
  }
  if (error) return <p style={{ color: "crimson" }}>{error}</p>;
  if (!resumen) return <Loading />;

  return (
    <div>
      <h1 style={{ marginTop: 0 }}>Dashboard de KPIs</h1>
      <p style={{ color: "#64748b", fontSize: "0.9rem" }}>
        Cifras calculadas por SQL sobre <code>fact_*</code> / <code>vw_kpi_*</code>.
        La IA no interviene.
      </p>

      <FilterBar filters={filters} opciones={opciones} onChange={setFilters} />

      <h2>Snapshot actual</h2>
      <div style={{
        display: "grid", gap: "1rem", marginBottom: "1.5rem",
        gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
      }}>
        {KPI_META.map((m) => {
          const snap = resumen[m.key] as any;
          const valor = snap.kpi_porcentaje ?? snap.kpi_horas_promedio
            ?? snap.kpi_dias_promedio;
          return (
            <KpiCard key={m.codigo} titulo={m.titulo} valor={valor}
                     semaforo={snap.semaforo} sufijo={m.sufijo} />
          );
        })}
      </div>

      <h2>Evolución del KPI seleccionado</h2>
      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.75rem",
                    flexWrap: "wrap" }}>
        {KPI_META.map((m) => (
          <button key={m.codigo} onClick={() => setKpiSel(m.codigo)}
            style={{
              background: kpiSel === m.codigo ? "#0b57d0" : "white",
              color: kpiSel === m.codigo ? "white" : "#0f172a",
              border: "1px solid #cbd5e1",
            }}>
            {m.titulo}
          </button>
        ))}
      </div>
      <div style={{ background: "white", padding: "1rem", borderRadius: 8 }}>
        {loadingSerie ? <Loading label="Cargando serie…" /> :
          serie ? <KpiChart data={serie} /> : null}
      </div>
    </div>
  );
}