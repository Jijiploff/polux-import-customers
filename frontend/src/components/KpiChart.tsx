import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import { SerieResponse } from "../api/kpis";

export function KpiChart({ data, tipo }: { data: SerieResponse; tipo?: "porcentaje" | "promedio" }) {
  const isPct = tipo === "porcentaje" || data.tipo === "porcentaje";
  if (!data.serie.length) {
    return     <p className="loading-state">
      Sin datos en el periodo seleccionado.
    </p>;
  }
  return (
    <div style={{ width: "100%", height: 280 }}>
      <ResponsiveContainer>
        <LineChart data={data.serie}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="etiqueta" fontSize={11} />
          <YAxis fontSize={11}
                 tickFormatter={(v) => isPct ? `${v}%` : v}
                 domain={isPct ? [0, 100] : ["auto", "auto"]} />
          <Tooltip formatter={(v: number) => isPct ? `${v.toFixed(2)}%` : v} />
          <Line type="monotone" dataKey="valor" stroke="#6366f1" strokeWidth={2}
                dot={{ r: 3 }} connectNulls />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}