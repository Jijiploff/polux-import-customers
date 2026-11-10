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

// ----- Simulador de chat WhatsApp (Fase G2) -----
export type AutorCom = "CLIENTE" | "AGENTE" | "HUMANO";

export interface ThreadMessage {
  id: number;
  direccion: "ENTRANTE" | "SALIENTE";
  autor: AutorCom;
  canal: Canal;
  contenido: string;
  fecha: string;
  intencion_detectada?: string | null;
  sentimiento?: string | null;
  escalado: boolean;
  caso_id?: number | null;
  caso_motivo?: string | null;
  caso_prioridad?: string | null;
  caso_estado?: string | null;
  plantilla_id?: number | null;
  estado_entrega?: string | null;
}

export interface ChatResumen {
  pedido_id: number;
  codigo: string;
  estado_pedido: string;
  cliente_id: number;
  cliente_nombre: string;
  total_mensajes: number;
  ultima_fecha?: string | null;
  ultima_preview?: string | null;
  ultima_autor?: AutorCom | null;
  caso_abierto_id?: number | null;
  caso_abierto_motivo?: string | null;
  asesor_reciente: boolean;
}

export interface HumanReplyResult {
  message: ThreadMessage;
  caso_id?: number | null;
  caso_estado?: string | null;
  aviso?: string | null;
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
  chats: () => api.get<ChatResumen[]>("/agent/chats"),
  thread: (pedidoId: number) =>
    api.get<ThreadMessage[]>(`/agent/thread?pedido_id=${pedidoId}`),
  humanReply: (pedido_id: number, contenido: string) =>
    api.post<HumanReplyResult>("/agent/human-reply", { pedido_id, contenido }),
};
