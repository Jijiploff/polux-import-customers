import { ReactNode } from "react";

export interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
}

export function DataTable<T>({
  columns, rows, empty = "Sin registros",
}: { columns: Column<T>[]; rows: T[]; empty?: string }) {
  if (!rows.length) return <div className="empty-state">{empty}</div>;
  return (
    <div className="data-table-wrap">
      <table className="data-table">
      <thead>
        <tr style={{ background: "#f1f5f9" }}>
          {columns.map((c) => (
            <th key={c.key} style={{ textAlign: "left" }}>
              {c.header}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}>
            {columns.map((c) => (
              <td key={c.key} style={{ verticalAlign: "top" }}>
                {c.render(r)}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
      </table>
    </div>
  );
}