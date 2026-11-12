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
  direccion?: string; distrito?: string; punto_recojo?: string; referencia?: string;
  receptor_nombre?: string; receptor_dni?: string; receptor_telefono?: string;
  franja_horaria?: string; notas_courier?: string;
  estado_inicial?: "BORRADOR" | "PROGRAMADA";
  creado_por_agente?: boolean;
}

export const entregasApi = {
  listByPedido: (pedidoId?: number) =>
    api.get<Entrega[]>(pedidoId ? `/entregas?pedido_id=${pedidoId}` : "/entregas"),
  detail: (id: number) => api.get<Entrega>(`/entregas/${id}`),
  crear: (payload: CrearEntregaInput) => api.post<Entrega>("/entregas", payload),
  actualizar: (id: number, payload: Partial<CrearEntregaInput>) =>
    api.patch<Entrega>(`/entregas/${id}`, payload),
  confirmar: (id: number) => api.post<Entrega>(`/entregas/${id}/confirmar`, {}),
  rechazar: (id: number, motivo: string) =>
    api.post<Entrega>(`/entregas/${id}/rechazar`, { motivo }),
  cambiarEstado: (id: number, estado: string) =>
    api.post<Entrega>(`/entregas/${id}/estado/${estado}`, {}),
  completar: (
    entregaId: number, fechaReal: string, conformidades: ConformidadItemIn[],
    receptorVerificado = false, recibidoPor = "",
  ) =>
    api.post<Entrega>(`/entregas/${entregaId}/completar`, {
      fecha_real: fechaReal, conformidades,
      receptor_verificado: receptorVerificado, recibido_por: recibidoPor,
    }),
};