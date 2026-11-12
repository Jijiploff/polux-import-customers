import { ReactNode } from "react";

export interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
}

export function DataTable<T>({
  columns, rows, empty = "Sin registros", onRowClick,
}: {
  columns: Column<T>[];
  rows: T[];
  empty?: string;
  onRowClick?: (row: T) => void;
}) {
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
          <tr
            key={i}
            onClick={onRowClick ? () => onRowClick(r) : undefined}
            onKeyDown={onRowClick ? (e) => {
              if (e.key === "Enter" || e.key === " ") onRowClick(r);
            } : undefined}
            tabIndex={onRowClick ? 0 : undefined}
            style={onRowClick ? { cursor: "pointer" } : undefined}
          >
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