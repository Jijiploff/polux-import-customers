import { api } from "./client";
import type { Comunicacion, DireccionCom, Canal } from "../types/domain";

export interface CrearComunicacionInput {
  pedido_id?: number; direccion: DireccionCom; canal: Canal;
  contenido: string; autor: string;
}

export const comunicacionesApi = {
  list: (params: { pedido_id?: number; page?: number; size?: number } = {}) => {
    const q = new URLSearchParams();
    if (params.pedido_id) q.set("pedido_id", String(params.pedido_id));
    q.set("page", String(params.page ?? 1));
    q.set("size", String(params.size ?? 50));
    return api.get<Comunicacion[]>(`/comunicaciones?${q.toString()}`);
  },
  crear: (payload: CrearComunicacionInput) => api.post<Comunicacion>("/comunicaciones", payload),
};