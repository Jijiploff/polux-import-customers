export function Loading({ label = "Cargando…" }: { label?: string }) {
  return <div style={{ padding: "2rem", textAlign: "center" }}>{label}</div>;
}