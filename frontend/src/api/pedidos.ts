import { api } from "./client";
import type { Page, Pedido, PedidoDetail, PedidoFullDetail, Origen, EstadoPedido } from "../types/domain";

export interface ListPedidosParams {
  estado?: EstadoPedido; cliente_id?: number; origen?: Origen;
  page?: number; size?: number;
}

export const pedidosApi = {
  list: (params: ListPedidosParams = {}) => {
    const q = new URLSearchParams();
    if (params.estado) q.set("estado", params.estado);
    if (params.cliente_id) q.set("cliente_id", String(params.cliente_id));
    if (params.origen) q.set("origen", params.origen);
    q.set("page", String(params.page ?? 1));
    q.set("size", String(params.size ?? 20));
    return api.get<Page<Pedido>>(`/pedidos?${q.toString()}`);
  },
  detail: (id: number) => api.get<PedidoDetail>(`/pedidos/${id}`),
  full: (id: number) => api.get<PedidoFullDetail>(`/pedidos/${id}/full`),
};