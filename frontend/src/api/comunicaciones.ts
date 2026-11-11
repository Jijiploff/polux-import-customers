import { api } from "./client";
import type {
  Comunicacion, DireccionCom, Canal, ClaseComunicacion,
} from "../types/domain";

export interface CrearComunicacionInput {
  pedido_id?: number; direccion: DireccionCom; canal: Canal;
  contenido: string; autor: string; clase?: ClaseComunicacion;
}

export const comunicacionesApi = {
  list: (params: {
    pedido_id?: number; clase?: ClaseComunicacion;
    page?: number; size?: number;
  } = {}) => {
    const q = new URLSearchParams();
    if (params.pedido_id) q.set("pedido_id", String(params.pedido_id));
    if (params.clase) q.set("clase", params.clase);
    q.set("page", String(params.page ?? 1));
    q.set("size", String(params.size ?? 50));
    return api.get<Comunicacion[]>(`/comunicaciones?${q.toString()}`);
  },
  crear: (payload: CrearComunicacionInput) => api.post<Comunicacion>("/comunicaciones", payload),
};