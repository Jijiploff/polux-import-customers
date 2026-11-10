import { api } from "./client";
import type {
  Caso, EstadoCaso, MotivoEscalamiento, PrioridadCaso,
} from "../types/domain";

export const casosApi = {
  list: (params: { estado?: EstadoCaso; pedido_id?: number } = {}) => {
    const q = new URLSearchParams();
    if (params.estado) q.set("estado", params.estado);
    if (params.pedido_id) q.set("pedido_id", String(params.pedido_id));
    return api.get<Caso[]>(`/casos?${q.toString()}`);
  },
  crear: (payload: { pedido_id: number; motivo: MotivoEscalamiento;
    prioridad?: PrioridadCaso; descripcion: string }) =>
    api.post<Caso>("/casos", payload),
  actualizar: (id: number, payload: {
    estado?: EstadoCaso; responsable_id?: number; registrar_primera_accion?: boolean;
  }) => api.patch<Caso>(`/casos/${id}`, payload),
};