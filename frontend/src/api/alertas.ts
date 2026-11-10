import { api } from "./client";
import type { Alerta, EstadoAlerta } from "../types/domain";

export const alertasApi = {
  list: (params: { estado?: EstadoAlerta; pedido_id?: number } = {}) => {
    const q = new URLSearchParams();
    if (params.estado) q.set("estado", params.estado);
    if (params.pedido_id) q.set("pedido_id", String(params.pedido_id));
    return api.get<Alerta[]>(`/alertas?${q.toString()}`);
  },
  atender: (id: number) => api.patch<Alerta>(`/alertas/${id}/atender`),
  actualizar: (id: number, payload: { estado: EstadoAlerta }) =>
    api.patch<Alerta>(`/alertas/${id}`, payload),
};