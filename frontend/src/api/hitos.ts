import { api } from "./client";
import type { ItemHito } from "../types/domain";

export const hitosApi = {
  porItem: (itemId: number) => api.get<ItemHito[]>(`/hitos/por-item/${itemId}`),
  completar: (hitoId: number, fechaReal: string) =>
    api.post<ItemHito>(`/hitos/${hitoId}/completar`, { fecha_real: fechaReal }),
};