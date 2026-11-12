export type Rol = "ADMIN" | "OPERADOR" | "GERENTE";

export type EstadoIngreso = "PRIMER_PAGO_VERIFICADO" | "PAGO_COMPLETO_VERIFICADO";
export type EstadoPedido =
  | "RECIBIDO" | "EN_PROCESO" | "LISTO_PARA_ENTREGA" | "EN_COORDINACION"
  | "ENTREGADO" | "CERRADO" | "CERRADO_CON_OBSERVACIONES" | "CANCELADO";
export type Modalidad = "DOMICILIO" | "RECOJO";
export type Origen = "STOCK_TRUJILLO" | "IMPORTACION";
export type EstadoItem = "PENDIENTE" | "EN_PROCESO" | "LISTO_PARA_ENTREGA"
  | "ENTREGADO" | "CON_OBSERVACIONES";
export type EstadoHito = "PENDIENTE" | "EN_PROCESO" | "COMPLETADO" | "ATRASADO" | "OMITIDO";
export type Canal = "WHATSAPP" | "EMAIL" | "WEB" | "TELEGRAM";
export type DireccionCom = "ENTRANTE" | "SALIENTE";
export type ClaseComunicacion = "CLIENTE" | "OPERATIVO";
export type TipoEntrega = "COMPLETA" | "PARCIAL";
export type EstadoEntrega = "PROGRAMADA" | "EN_RUTA" | "ENTREGADA" | "FALLIDA" | "REPROGRAMADA";
export type ResultadoConformidad = "CONFORME" | "CON_OBSERVACIONES";
export type TipoImprevisto = "OPERATIVO" | "ADUANERO" | "DAÑO" | "AGOTADO" | "OTRO";
export type EstadoImprevisto = "ABIERTO" | "EN_PROCESO" | "RESUELTO" | "CERRADO";
export type MotivoEscalamiento =
  | "RECLAMO" | "TONO_NEGATIVO" | "ENTREGA_PARCIAL" | "IMPREVISTO"
  | "RETRASO_CRITICO" | "FALTA_RESPUESTA" | "OTRO";
export type PrioridadCaso = "BAJA" | "MEDIA" | "ALTA" | "CRITICA";
export type EstadoCaso = "ABIERTO" | "EN_PROCESO" | "RESUELTO" | "CERRADO";
export type TipoAlerta =
  | "RETRASO_LEVE" | "RETRASO_CRITICO" | "IMPREVISTO"
  | "SILENCIO_CLIENTE" | "FALTA_RESPUESTA";
export type SeveridadAlerta = "BAJA" | "MEDIA" | "ALTA" | "CRITICA";
export type EstadoAlerta = "ABIERTA" | "ATENDIDA" | "CERRADA" | "IGNORADA";

export interface Page<T> { items: T[]; total: number; page: number; size: number; }

export interface ClienteResumen {
  id: number; nombre: string; telefono_whatsapp?: string | null;
  email?: string | null; consentimiento_datos: boolean;
}

export interface PedidoItem {
  id: number; producto_id?: number | null;
  descripcion_producto: string; modelo?: string | null;
  color?: string | null; capacidad?: string | null;
  cantidad: number; accesorios?: string | null;
  origen: Origen; estado: EstadoItem;
}

export interface ItemHito {
  id: number; hito_id: number; hito_codigo: string; hito_nombre: string;
  fecha_prevista?: string | null; fecha_real?: string | null;
  estado: EstadoHito; dias_atraso: number; notificado_cliente: boolean;
}

export interface Pedido {
  id: number; codigo: string; cliente_id: number; contrato_id?: number | null;
  estado_ingreso: EstadoIngreso; estado_actual: EstadoPedido;
  fecha_ingreso: string; fecha_prometida: string;
  modalidad_entrega: Modalidad; direccion_entrega?: string | null;
  consentimiento_comunicaciones: boolean;
}

export interface PedidoDetail extends Pedido {
  cliente: ClienteResumen;
  items: PedidoItem[];
}

export interface PedidoItemDetail extends PedidoItem { hitos: ItemHito[]; }
export interface PedidoFullDetail extends Pedido {
  cliente: ClienteResumen; items: PedidoItemDetail[];
}

export interface Entrega {
  id: number; pedido_id: number; tipo: TipoEntrega; modalidad: Modalidad;
  estado: EstadoEntrega; fecha_programada: string; fecha_real?: string | null;
  autorizada_por_id?: number | null; fecha_autorizacion?: string | null;
  motivo_parcial?: string | null;
  items: EntregaItem[];
}

export interface ConformidadItemIn {
  pedido_item_id: number;
  checklist_caja_sellada: boolean; checklist_modelo_ok: boolean;
  checklist_color_ok: boolean; checklist_capacidad_ok: boolean;
  checklist_imei_ok: boolean; checklist_accesorios_ok: boolean;
  resultado: ResultadoConformidad; observaciones?: string | null;
  evidencias_urls?: string | null;
}

export interface Comunicacion {
  id: number; pedido_id?: number | null; direccion: DireccionCom; canal: Canal;
  clase: ClaseComunicacion;
  contenido: string; intencion_detectada?: string | null;
  sentimiento?: string | null; autor: string; escalado: boolean; fecha: string;
}

export interface Alerta {
  id: number; tipo: TipoAlerta; pedido_id: number;
  severidad: SeveridadAlerta; mensaje: string;
  estado: EstadoAlerta; fecha_deteccion: string;
}

export interface Imprevisto {
  id: number; pedido_id: number; pedido_item_id?: number | null;
  tipo: TipoImprevisto; descripcion: string;
  fecha_deteccion: string; fecha_resolucion?: string | null;
  estado: EstadoImprevisto; resolucion?: string | null;
}

export interface Caso {
  id: number; pedido_id: number; motivo: MotivoEscalamiento;
  prioridad: PrioridadCaso; descripcion: string;
  fecha_apertura: string; fecha_primera_accion?: string | null;
  responsable_id?: number | null; responsable_nombre?: string | null;
  estado: EstadoCaso; fecha_cierre?: string | null;
}

export interface CasoDetalle extends Caso {
  responsable_nombre?: string | null;
  pedido_codigo: string;
  cliente_nombre: string;
  cliente_telegram_vinculado: boolean;
  puede_responder: boolean;
}

export interface Usuario {
  id: number; email: string; nombre_completo: string;
  activo: boolean; ultimo_login?: string | null; roles: Rol[];
}

export interface Regla {
  id: number; codigo: string; nombre: string; categoria: string;
  valor: string; tipo_valor: string; activo: boolean;
}

export interface Plantilla {
  id: number; codigo: string; nombre: string; canal: Canal;
  evento: string; cuerpo: string;
  whatsapp_template_id?: string | null;
  idioma: string; activo: boolean;
}

export interface SlaHito {
  id: number; hito_id: number; origen: Origen;
  dias_maximos: number; horas_maximas?: number | null;
  activo: boolean;
}

export interface EntregaItem {
  id: number;
  pedido_item_id: number;
}

export interface HitoCatalogo {
  id: number; codigo: string; nombre: string; origen: Origen;
  orden: number; activo: boolean;
}

export interface DimKpi {
  id: number; codigo: string; nombre: string; definicion: string;
  unidad: string; umbral_optimo: number; umbral_alerta: number;
  umbral_critico: number; sentido: string; es_complementario: boolean;
}

export interface KpiSnapshot {
  codigo: string; kpi_porcentaje?: number | null;
  kpi_horas_promedio?: number | null;
  kpi_dias_promedio?: number | null;
  semaforo: "OPTIMO" | "ALERTA" | "CRITICO" | "SIN_DATOS";
  calculado_en: string;
}

// ---- Línea de tiempo (Fase H) ----
export type TipoEventoTimeline =
  | "pedido" | "hito" | "mensaje" | "operativo" | "caso" | "imprevisto"
  | "entrega" | "alerta";

export interface TimelineEvento {
  fecha: string;
  tipo: TipoEventoTimeline;
  titulo: string;
  detalle?: string | null;
  criticidad: "INFO" | "MEDIA" | "ALTA";
  ref_tipo?: string | null;
  ref_id?: number | null;
  autor?: string | null;
}

export interface TimelineResumen {
  mensajes: number;
  mensajes_clave: number;
  mensajes_operativos: number;
  hitos_atrasados: number;
  casos_abiertos: number;
  imprevistos_abiertos: number;
  alertas_activas: number;
}

export interface Timeline {
  pedido_id: number;
  resumen: TimelineResumen;
  eventos: TimelineEvento[];
  incluyendo_mensajes: boolean;
}