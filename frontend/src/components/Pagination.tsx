export function Pagination({
  page, size, total, onChange,
}: { page: number; size: number; total: number; onChange: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / size));
  return (
    <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", marginTop: "1rem" }}>
      <button disabled={page <= 1} onClick={() => onChange(page - 1)}>Anterior</button>
      <span>Página {page} de {pages} ({total} registros)</span>
      <button disabled={page >= pages} onClick={() => onChange(page + 1)}>Siguiente</button>
    </div>
  );
}