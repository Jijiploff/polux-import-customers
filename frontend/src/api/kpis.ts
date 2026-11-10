import { api } from "./client";
import type { KpiSnapshot } from "../types/domain";

export interface DashboardResumen {
  actualizacion_cliente: KpiSnapshot;
  resolucion_automatica: KpiSnapshot;
  tiempo_respuesta_escalados: KpiSnapshot;
  resolucion_imprevistos: KpiSnapshot & { por_tipo?: KpiSnapshot[] };
  entregas_a_tiempo: KpiSnapshot;
  entregas_sin_observaciones: KpiSnapshot;
  entregas_parciales: KpiSnapshot;
}

export interface FiltrosOpciones {
  productos: { id: number; sku: string; nombre: string }[];
  origenes: { codigo: string; nombre: string }[];
  operadores: { id: number; nombre: string }[];
}

export interface SeriePunto {
  periodo: string; etiqueta: string; valor: number | null;
  total: number; numerador: number;
}
export interface SerieResponse {
  granularidad: "dia" | "semana" | "mes";
  tipo: "porcentaje" | "promedio";
  serie: SeriePunto[];
}

export interface ValidacionKpi {
  definicion: string; formula: string; sql: string;
}
export type ValidacionResponse = Record<string, ValidacionKpi>;

export interface SerieFiltros {
  desde: string; hasta: string;
  granularidad?: "dia" | "semana" | "mes";
  producto_id?: number;
  origen?: string;
  operador_id?: number;
}

export const kpisApi = {
  resumen: () => api.get<DashboardResumen>("/dashboard/resumen"),
  filtros: () => api.get<FiltrosOpciones>("/kpis/filtros/opciones"),
  validacion: () => api.get<ValidacionResponse>("/kpis/validacion"),
  serie: (codigo: string, f: SerieFiltros) => {
    const q = new URLSearchParams();
    q.set("desde", f.desde);
    q.set("hasta", f.hasta);
    q.set("granularidad", f.granularidad ?? "mes");
    if (f.producto_id) q.set("producto_id", String(f.producto_id));
    if (f.origen) q.set("origen", f.origen);
    if (f.operador_id) q.set("operador_id", String(f.operador_id));
    return api.get<SerieResponse>(`/kpis/${codigo}/serie?${q.toString()}`);
  },
};