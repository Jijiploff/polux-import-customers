const PALETTE: Record<string, { bg: string; fg: string }> = {
  // Línea de tiempo (criticidad)
  INFO: { bg: "#f1f5f9", fg: "#334155" },
  // Pedidos
  RECIBIDO: { bg: "#e0e7ff", fg: "#1e3a8a" },
  EN_PROCESO: { bg: "#dbeafe", fg: "#1d4ed8" },
  LISTO_PARA_ENTREGA: { bg: "#fef3c7", fg: "#92400e" },
  EN_COORDINACION: { bg: "#ede9fe", fg: "#5b21b6" },
  ENTREGADO: { bg: "#dcfce7", fg: "#166534" },
  CERRADO: { bg: "#d1fae5", fg: "#065f46" },
  CERRADO_CON_OBSERVACIONES: { bg: "#fee2e2", fg: "#991b1b" },
  CANCELADO: { bg: "#e5e7eb", fg: "#374151" },
  // Ítems / hitos
  PENDIENTE: { bg: "#e5e7eb", fg: "#374151" },
  COMPLETADO: { bg: "#d1fae5", fg: "#065f46" },
  ATRASADO: { bg: "#fee2e2", fg: "#991b1b" },
  OMITIDO: { bg: "#e5e7eb", fg: "#4b5563" },
  CON_OBSERVACIONES: { bg: "#fee2e2", fg: "#991b1b" },
  // Casos
  ABIERTO: { bg: "#fef9c3", fg: "#854d0e" },
  ABIERTA: { bg: "#fef9c3", fg: "#854d0e" },
  EN_PROCESO_CASO: { bg: "#dbeafe", fg: "#1d4ed8" },
  RESUELTO: { bg: "#dcfce7", fg: "#166534" },
  ATENDIDA: { bg: "#dcfce7", fg: "#166534" },
  CRITICA: { bg: "#fee2e2", fg: "#991b1b" },
  ALTA: { bg: "#ffedd5", fg: "#9a3412" },
  MEDIA: { bg: "#fef3c7", fg: "#92400e" },
  BAJA: { bg: "#e5e7eb", fg: "#374151" },
  // Entregas
  PROGRAMADA: { bg: "#dbeafe", fg: "#1d4ed8" },
  ENTREGADA: { bg: "#dcfce7", fg: "#166534" },
  FALLIDA: { bg: "#fee2e2", fg: "#991b1b" },
  REPROGRAMADA: { bg: "#fef3c7", fg: "#92400e" },
  EN_RUTA: { bg: "#ede9fe", fg: "#5b21b6" },
};

export function StatusBadge({ value }: { value: string }) {
  const p = PALETTE[value] ?? { bg: "#e5e7eb", fg: "#111827" };
  return (
    <span style={{
      display: "inline-block", padding: "2px 8px", borderRadius: "999px",
      fontSize: "0.75rem", fontWeight: 600, background: p.bg, color: p.fg,
    }}>
      {value.replace(/_/g, " ")}
    </span>
  );
}