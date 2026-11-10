import { api } from "./client";
import type { EstadoImprevisto, Imprevisto, TipoImprevisto } from "../types/domain";

export const imprevistosApi = {
  list: (params: { estado?: EstadoImprevisto; pedido_id?: number } = {}) => {
    const q = new URLSearchParams();
    if (params.estado) q.set("estado", params.estado);
    if (params.pedido_id) q.set("pedido_id", String(params.pedido_id));
    return api.get<Imprevisto[]>(`/imprevistos?${q.toString()}`);
  },
  crear: (payload: {
    pedido_id: number; pedido_item_id?: number; tipo: TipoImprevisto;
    descripcion: string; fecha_deteccion: string;
  }) => api.post<Imprevisto>("/imprevistos", payload),
  actualizar: (id: number, payload: {
    estado: EstadoImprevisto; resolucion?: string; fecha_resolucion?: string;
  }) => api.patch<Imprevisto>(`/imprevistos/${id}`, payload),
};