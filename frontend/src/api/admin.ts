import { api } from "./client";
import type {
  DimKpi, HitoCatalogo, Origen, Plantilla, Regla, Rol, SlaHito, Usuario,
} from "../types/domain";

export interface CrearHitoInput {
  codigo: string; nombre: string; origen: Origen; orden: number; activo?: boolean;
}
export interface ActualizarHitoInput {
  nombre?: string; orden?: number; activo?: boolean;
}
export interface CrearSlaInput {
  hito_id: number; origen: Origen;
  dias_maximos: number; horas_maximas?: number; activo?: boolean;
}
export interface ActualizarSlaInput {
  dias_maximos?: number; horas_maximas?: number; activo?: boolean;
}
export interface CrearPlantillaInput {
  codigo: string; nombre: string; canal: string; evento: string;
  cuerpo: string; whatsapp_template_id?: string | null;
  idioma?: string; activo?: boolean;
}
export interface ActualizarPlantillaInput {
  nombre?: string; cuerpo?: string;
  whatsapp_template_id?: string | null; activo?: boolean;
}

export const adminApi = {
  usuarios: {
    list: () => api.get<Usuario[]>("/usuarios"),
    crear: (payload: {
      email: string; nombre_completo: string; password: string; roles: Rol[];
    }) => api.post<Usuario>("/usuarios", payload),
    actualizar: (id: number, payload: {
      nombre_completo?: string; password?: string; activo?: boolean; roles?: Rol[];
    }) => api.patch<Usuario>(`/usuarios/${id}`, payload),
  },
  reglas: {
    list: () => api.get<Regla[]>("/reglas"),
    actualizar: (id: number, payload: { valor?: string; activo?: boolean }) =>
      api.patch<Regla>(`/reglas/${id}`, payload),
  },
  catalogos: {
    hitos: () => api.get<HitoCatalogo[]>("/catalogos/hitos"),
    crearHito: (p: CrearHitoInput) => api.post<HitoCatalogo>("/catalogos/hitos", p),
    actualizarHito: (id: number, p: ActualizarHitoInput) =>
      api.patch<HitoCatalogo>(`/catalogos/hitos/${id}`, p),
    sla: () => api.get<SlaHito[]>("/catalogos/sla"),
    crearSla: (p: CrearSlaInput) => api.post<SlaHito>("/catalogos/sla", p),
    actualizarSla: (id: number, p: ActualizarSlaInput) =>
      api.patch<SlaHito>(`/catalogos/sla/${id}`, p),
    plantillas: () => api.get<Plantilla[]>("/catalogos/plantillas"),
    crearPlantilla: (p: CrearPlantillaInput) =>
      api.post<Plantilla>("/catalogos/plantillas", p),
    actualizarPlantilla: (id: number, p: ActualizarPlantillaInput) =>
      api.patch<Plantilla>(`/catalogos/plantillas/${id}`, p),
    kpis: () => api.get<DimKpi[]>("/catalogos/kpis"),
    actualizarKpi: (id: number, payload: {
      umbral_optimo?: number; umbral_alerta?: number; umbral_critico?: number;
    }) => api.patch<DimKpi>(`/catalogos/kpis/${id}`, payload),
  },
  runRules: () => api.post<{ counts: Record<string, number> }>("/admin/run-rules"),
  syncFacts: () => api.post<{ counts: Record<string, number> }>("/admin/sync-facts"),
};