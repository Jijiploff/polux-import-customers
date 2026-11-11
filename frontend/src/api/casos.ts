import { api } from "./client";
import type {
  Caso, CasoDetalle, EstadoCaso, MotivoEscalamiento, PrioridadCaso,
} from "../types/domain";
import type { ThreadMessage } from "./agent";

export interface CasoRespuesta {
  message: ThreadMessage;
  caso_id: number;
  caso_estado: EstadoCaso;
  enviado: boolean;
  aviso?: string | null;
}

export interface CasoCierre {
  caso: Caso;
  aviso?: string | null;
}

export const casosApi = {
  list: (params: { estado?: EstadoCaso; pedido_id?: number } = {}) => {
    const q = new URLSearchParams();
    if (params.estado) q.set("estado", params.estado);
    if (params.pedido_id) q.set("pedido_id", String(params.pedido_id));
    return api.get<Caso[]>(`/casos?${q.toString()}`);
  },
  detalle: (id: number) => api.get<CasoDetalle>(`/casos/${id}`),
  crear: (payload: { pedido_id: number; motivo: MotivoEscalamiento;
    prioridad?: PrioridadCaso; descripcion: string }) =>
    api.post<Caso>("/casos", payload),
  responder: (id: number, contenido: string) =>
    api.post<CasoRespuesta>(`/casos/${id}/responder`, { contenido }),
  cerrar: (id: number) => api.post<CasoCierre>(`/casos/${id}/cerrar`),
  actualizar: (id: number, payload: {
    estado?: EstadoCaso; responsable_id?: number; registrar_primera_accion?: boolean;
  }) => api.patch<Caso>(`/casos/${id}`, payload),
};
