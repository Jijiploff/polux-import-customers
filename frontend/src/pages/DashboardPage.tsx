import { useEffect, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import {
  DashboardResumen, FiltrosOpciones, SerieResponse,
  kpisApi,
} from "../api/kpis";
import { FilterBar, Filters, defaultFilters } from "../components/FilterBar";
import { KpiChart } from "../components/KpiChart";
import { Loading } from "../components/Loading";
import { StatusBadge } from "../components/StatusBadge";
import { alertasApi } from "../api/alertas";
import type { Alerta, SeveridadAlerta } from "../types/domain";

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

const SEVERIDAD_ORDEN: Record<SeveridadAlerta, number> = {
  CRITICA: 0, ALTA: 1, MEDIA: 2, BAJA: 3,
};

const SEVERIDAD_COLOR: Record<SeveridadAlerta, { bg: string; border: string }> = {
  CRITICA: { bg: "#fee2e2", border: "#dc2626" },
  ALTA: { bg: "#ffedd5", border: "#f97316" },
  MEDIA: { bg: "#fef3c7", border: "#eab308" },
  BAJA: { bg: "#dcfce7", border: "#16a34a" },
};

function KpiCard({ titulo, valor, semaforo, sufijo }: {
  titulo: string; valor?: number | null; semaforo: string; sufijo?: string;
}) {
  const color = semaforo === "OPTIMO" ? "#16a34a"
    : semaforo === "ALERTA" ? "#f59e0b"
    : semaforo === "CRITICO" ? "#dc2626" : "#94a3b8";
  return (
    <div className={`kpi-card kpi-${semaforo.toLowerCase()}`}>
      <p className="kpi-title">{titulo}</p>
      <p className="kpi-value">
        {valor != null ? valor.toFixed(2) : "—"}{sufijo ?? ""}
      </p>
      <p className="kpi-state" style={{ color }}>{semaforo}</p>
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
  const [alertas, setAlertas] = useState<Alerta[]>([]);

  useEffect(() => {
    if (!hasRole("ADMIN", "GERENTE")) return;
    kpisApi.resumen().then(setResumen).catch((e) => setError(String(e)));
    kpisApi.filtros().then(setOpciones).catch(() => {});
    alertasApi.list({ estado: "ABIERTA" })
      .then((items) => setAlertas(items.sort(
        (a, b) => SEVERIDAD_ORDEN[a.severidad] - SEVERIDAD_ORDEN[b.severidad],
      )))
      .catch(() => setAlertas([]));
  }, [hasRole]);

  useEffect(() => {
    if (!hasRole("ADMIN", "GERENTE") || !filters.desde || !filters.hasta) return;
    let active = true;
    setLoadingSerie(true);
    kpisApi.serie(kpiSel, filters)
      .then((nextSerie) => {
        if (active) setSerie(nextSerie);
      })
      .catch((e) => {
        if (active) setError(String(e));
      })
      .finally(() => {
        if (active) setLoadingSerie(false);
      });
    return () => {
      active = false;
    };
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
      <h1 className="page-heading">Dashboard de KPIs</h1>
      <p className="page-subtitle">
        Cifras calculadas por SQL sobre <code>fact_*</code> / <code>vw_kpi_*</code>.
        La IA no interviene.
      </p>

      <FilterBar filters={filters} opciones={opciones} onChange={setFilters} />

      <h2>Alertas activas</h2>
      {alertas.length === 0 ? (
        <div className="surface-card" style={{ padding: "1rem", color: "#166534" }}>
          No hay alertas activas.
        </div>
      ) : (
        <div style={{ display: "grid", gap: "0.6rem", marginBottom: "1.5rem" }}>
          {alertas.map((alerta) => {
            const colors = SEVERIDAD_COLOR[alerta.severidad];
            return (
              <div
                key={alerta.id}
                className="surface-card"
                style={{
                  padding: "0.75rem 1rem", background: colors.bg,
                  borderLeft: `5px solid ${colors.border}`,
                }}
              >
                <div style={{
                  display: "flex", justifyContent: "space-between",
                  gap: "0.75rem", alignItems: "center",
                }}>
                  <strong>{alerta.pedido_codigo ?? `#${alerta.pedido_id}`}</strong>
                  <StatusBadge value={alerta.severidad} />
                </div>
                <div style={{ marginTop: 4 }}>{alerta.mensaje}</div>
                <small style={{ color: "#475569" }}>
                  {alerta.tipo.replace(/_/g, " ")} · {new Date(alerta.fecha_deteccion).toLocaleString()}
                </small>
              </div>
            );
          })}
        </div>
      )}

      <h2>Snapshot actual</h2>
      <div style={{
        display: "grid", gap: "1rem", marginBottom: "1.5rem",
        gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 190px), 1fr))",
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
      <div className="kpi-tabs">
        {KPI_META.map((m) => (
          <button
            type="button"
            key={m.codigo}
            onClick={(event) => {
              event.preventDefault();
              setKpiSel(m.codigo);
            }}
            className={kpiSel === m.codigo ? "kpi-tab-active" : undefined}>
            {m.titulo}
          </button>
        ))}
      </div>
      <div className="surface-card chart-panel">
        {serie ? (
          <div className={loadingSerie ? "chart-content chart-content-loading" : "chart-content"}>
            <KpiChart data={serie} />
            {loadingSerie ? <div className="chart-loading-overlay">Actualizando serie…</div> : null}
          </div>
        ) : loadingSerie ? <Loading label="Cargando serie…" /> : null}
      </div>
    </div>
  );
}