import { useEffect, useState } from "react";
import { adminApi } from "../../api/admin";
import { DataTable } from "../../components/DataTable";
import { Loading } from "../../components/Loading";
import type { Regla } from "../../types/domain";

export function ReglasPage() {
  const [rows, setRows] = useState<Regla[] | null>(null);
  const [editId, setEditId] = useState<number | null>(null);
  const [valor, setValor] = useState("");
  const [savingId, setSavingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      setError(null);
      setRows(await adminApi.reglas.list());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }
  useEffect(() => { load(); }, []);

  async function guardar(id: number) {
    try {
      setSavingId(id);
      setError(null);
      await adminApi.reglas.actualizar(id, { valor });
      setEditId(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSavingId(null);
    }
  }

  async function toggle(r: Regla) {
    try {
      setSavingId(r.id);
      setError(null);
      await adminApi.reglas.actualizar(r.id, { activo: !r.activo });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSavingId(null);
    }
  }

  return (
    <div>
      <h1 style={{ marginTop: 0 }}>Reglas de negocio</h1>
      <p style={{ color: "#64748b", fontSize: "0.9rem" }}>
        Parametrización del motor de reglas. Cada cambio se aplica en la siguiente
        corrida del scheduler.
      </p>
      {error && <p style={{ color: "crimson" }}>{error}</p>}
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
                  <input
                    value={valor}
                    onChange={(e) => setValor(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") guardar(r.id);
                      if (e.key === "Escape") setEditId(null);
                    }}
                    autoFocus
                    disabled={savingId === r.id}
                  />
                  <button
                    onClick={() => guardar(r.id)}
                    disabled={savingId === r.id}
                  >
                    {savingId === r.id ? "Guardando…" : "Guardar"}
                  </button>
                  <button
                    onClick={() => setEditId(null)}
                    disabled={savingId === r.id}
                  >
                    Cancelar
                  </button>
                </span>
              ) : r.valor
            },
            { key: "act", header: "Activa", render: (r) => r.activo ? "Sí" : "No" },
            { key: "acc", header: "",
              render: (r) => (
                <span style={{ display: "flex", gap: 4 }}>
                  <button
                    onClick={() => { setEditId(r.id); setValor(r.valor); }}
                    disabled={savingId !== null}
                  >
                    Editar
                  </button>
                  <button onClick={() => toggle(r)} disabled={savingId !== null}>
                    {r.activo ? "Desactivar" : "Activar"}
                  </button>
                </span>
              ) },
          ]}
        />
      )}
    </div>
  );
}