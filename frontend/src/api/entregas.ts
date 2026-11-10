import { api } from "./client";
import type {
  ConformidadItemIn, Entrega, Modalidad, TipoEntrega,
} from "../types/domain";

export interface CrearEntregaInput {
  pedido_id: number;
  tipo: TipoEntrega;
  modalidad: Modalidad;
  fecha_programada: string;
  pedido_item_ids?: number[];
  autorizada_por_id?: number;
  fecha_autorizacion?: string;
  motivo_parcial?: string;
}

export const entregasApi = {
  listByPedido: (pedidoId: number) =>
    api.get<Entrega[]>(`/entregas?pedido_id=${pedidoId}`),
  crear: (payload: CrearEntregaInput) => api.post<Entrega>("/entregas", payload),
  completar: (
    entregaId: number, fechaReal: string, conformidades: ConformidadItemIn[],
  ) =>
    api.post<Entrega>(`/entregas/${entregaId}/completar`, {
      fecha_real: fechaReal, conformidades,
    }),
};