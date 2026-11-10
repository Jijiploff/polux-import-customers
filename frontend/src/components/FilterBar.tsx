import { FiltrosOpciones } from "../api/kpis";

export interface Filters {
  desde: string;
  hasta: string;
  granularidad: "dia" | "semana" | "mes";
  producto_id?: number;
  origen?: string;
  operador_id?: number;
}

export function defaultFilters(): Filters {
  const hoy = new Date();
  const hace90 = new Date(hoy.getTime() - 90 * 24 * 3600 * 1000);
  return {
    desde: hace90.toISOString().slice(0, 10),
    hasta: hoy.toISOString().slice(0, 10),
    granularidad: "mes",
  };
}

export function FilterBar({
  filters, opciones, onChange,
}: {
  filters: Filters;
  opciones: FiltrosOpciones | null;
  onChange: (f: Filters) => void;
}) {
  function set<K extends keyof Filters>(key: K, val: Filters[K]) {
    onChange({ ...filters, [key]: val });
  }
  return (
    <div style={{
      display: "flex", flexWrap: "wrap", gap: "0.75rem",
      background: "white", padding: "0.75rem", borderRadius: 8,
      marginBottom: "1rem", alignItems: "flex-end",
    }}>
      <label style={{ fontSize: "0.8rem" }}>
        Desde<br />
        <input type="date" value={filters.desde}
               onChange={(e) => set("desde", e.target.value)} />
      </label>
      <label style={{ fontSize: "0.8rem" }}>
        Hasta<br />
        <input type="date" value={filters.hasta}
               onChange={(e) => set("hasta", e.target.value)} />
      </label>
      <label style={{ fontSize: "0.8rem" }}>
        Granularidad<br />
        <select value={filters.granularidad}
                onChange={(e) => set("granularidad", e.target.value as any)}>
          <option value="dia">Día</option>
          <option value="semana">Semana</option>
          <option value="mes">Mes</option>
        </select>
      </label>
      <label style={{ fontSize: "0.8rem" }}>
        Producto<br />
        <select value={filters.producto_id ?? ""}
                onChange={(e) => set("producto_id", e.target.value ? Number(e.target.value) : undefined)}>
          <option value="">Todos</option>
          {opciones?.productos.map((p) => (
            <option key={p.id} value={p.id}>{p.nombre}</option>
          ))}
        </select>
      </label>
      <label style={{ fontSize: "0.8rem" }}>
        Origen<br />
        <select value={filters.origen ?? ""}
                onChange={(e) => set("origen", e.target.value || undefined)}>
          <option value="">Todos</option>
          {opciones?.origenes.map((o) => (
            <option key={o.codigo} value={o.codigo}>{o.nombre}</option>
          ))}
        </select>
      </label>
      <label style={{ fontSize: "0.8rem" }}>
        Operador<br />
        <select value={filters.operador_id ?? ""}
                onChange={(e) => set("operador_id", e.target.value ? Number(e.target.value) : undefined)}>
          <option value="">Todos</option>
          {opciones?.operadores.map((o) => (
            <option key={o.id} value={o.id}>{o.nombre}</option>
          ))}
        </select>
      </label>
    </div>
  );
}