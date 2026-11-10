import { api } from "./client";
import type { Canal } from "../types/domain";

export interface AgentClassification {
  intent: string;
  sentiment: string;
  confidence: number;
  provider_used: string;
}

export interface AgentResult {
  incoming_comunicacion_id: number;
  outgoing_comunicacion_id?: number | null;
  classification: AgentClassification;
  escalated: boolean;
  escalation_reason?: string | null;
  caso_id?: number | null;
  response_text?: string | null;
  fallback_used: boolean;
  human_in_progress: boolean;
  fecha_procesamiento: string;
}

export interface AgentMetrics {
  total_entrantes: number;
  total_salientes: number;
  escalados: number;
  no_escalados: number;
  tasa_escalamiento: number;
  por_intent: Record<string, number>;
  por_sentimiento: Record<string, number>;
  con_plantilla: number;
  sin_plantilla: number;
}

export interface ClassifyTestResult {
  intent: string;
  sentiment: string;
  confidence: number;
  provider_used: string;
}

export const agentApi = {
  provider: () => api.get<{ provider: string }>("/agent/provider"),
  metrics: (pedido_id?: number) =>
    api.get<AgentMetrics>(
      pedido_id ? `/agent/metrics?pedido_id=${pedido_id}` : "/agent/metrics",
    ),
  incoming: (payload: { pedido_id?: number; canal: Canal; contenido: string }) =>
    api.post<AgentResult>("/agent/messages/incoming", payload),
  classify: (contenido: string) =>
    api.post<ClassifyTestResult>("/agent/test/classify", { contenido }),
};
