import { useEffect, useState } from "react";
import { adminApi } from "../../api/admin";
import { DataTable } from "../../components/DataTable";
import { Loading } from "../../components/Loading";
import type { Regla } from "../../types/domain";

export function ReglasPage() {
  const [rows, setRows] = useState<Regla[] | null>(null);
  const [editId, setEditId] = useState<number | null>(null);
  const [valor, setValor] = useState("");

  async function load() { setRows(await adminApi.reglas.list()); }
  useEffect(() => { load(); }, []);

  async function guardar(id: number) {
    await adminApi.reglas.actualizar(id, { valor });
    setEditId(null);
    load();
  }

  async function toggle(r: Regla) {
    await adminApi.reglas.actualizar(r.id, { activo: !r.activo });
    load();
  }

  return (
    <div>
      <h1 style={{ marginTop: 0 }}>Reglas de negocio</h1>
      <p style={{ color: "#64748b", fontSize: "0.9rem" }}>
        Parametrización del motor de reglas. Cada cambio se aplica en la siguiente
        corrida del scheduler.
      </p>
      {!rows ? <Loading /> : (
        <DataTable
          rows={rows}
          columns={[
            { key: "cod", header: "Código", render: (r) => r.codigo },
            { key: "nom", header: "Nombre", render: (r) => r.nombre },
            { key: "cat", header: "Categoría", render: (r) => r.categoria },
            { key: "val", header: "Valor", render: (r) =>
              editId === r.id ? (
                <span>
                  <input value={valor} onChange={(e) => setValor(e.target.value)} />
                  <button onClick={() => guardar(r.id)}>OK</button>
                </span>
              ) : r.valor
            },
            { key: "act", header: "Activa", render: (r) => r.activo ? "Sí" : "No" },
            { key: "acc", header: "",
              render: (r) => (
                <span style={{ display: "flex", gap: 4 }}>
                  <button onClick={() => { setEditId(r.id); setValor(r.valor); }}>Editar</button>
                  <button onClick={() => toggle(r)}>{r.activo ? "Desactivar" : "Activar"}</button>
                </span>
              ) },
          ]}
        />
      )}
    </div>
  );
}