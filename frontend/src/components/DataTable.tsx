import { ReactNode } from "react";

export interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
}

export function DataTable<T>({
  columns, rows, empty = "Sin registros",
}: { columns: Column<T>[]; rows: T[]; empty?: string }) {
  if (!rows.length) return <div style={{ padding: "1rem" }}>{empty}</div>;
  return (
    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.9rem" }}>
      <thead>
        <tr style={{ background: "#f1f5f9" }}>
          {columns.map((c) => (
            <th key={c.key} style={{ textAlign: "left", padding: "8px 12px", borderBottom: "1px solid #e2e8f0" }}>
              {c.header}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i} style={{ borderBottom: "1px solid #f1f5f9" }}>
            {columns.map((c) => (
              <td key={c.key} style={{ padding: "8px 12px", verticalAlign: "top" }}>
                {c.render(r)}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}