import { FormEvent, useEffect, useState } from "react";
import { adminApi } from "../../api/admin";
import { DataTable } from "../../components/DataTable";
import { Modal } from "../../components/Modal";
import { FormField } from "../../components/FormField";
import { Loading } from "../../components/Loading";
import type { Rol, Usuario } from "../../types/domain";

export function UsuariosPage() {
  const [rows, setRows] = useState<Usuario[] | null>(null);
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [nombre, setNombre] = useState("");
  const [password, setPassword] = useState("");
  const [roles, setRoles] = useState<Rol[]>(["OPERADOR"]);
  const [error, setError] = useState<string | null>(null);

  async function load() { setRows(await adminApi.usuarios.list()); }
  useEffect(() => { load(); }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await adminApi.usuarios.crear({
        email, nombre_completo: nombre, password, roles,
      });
      setOpen(false); setEmail(""); setNombre(""); setPassword("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function toggleActivo(u: Usuario) {
    await adminApi.usuarios.actualizar(u.id, { activo: !u.activo });
    load();
  }

  return (
    <div>
      <h1 style={{ marginTop: 0 }}>Usuarios</h1>
      <button onClick={() => setOpen(true)} style={{ marginBottom: "1rem" }}>
        Nuevo usuario
      </button>
      {!rows ? <Loading /> : (
        <DataTable
          rows={rows}
          columns={[
            { key: "id", header: "#", render: (u) => u.id },
            { key: "email", header: "Email", render: (u) => u.email },
            { key: "nombre", header: "Nombre", render: (u) => u.nombre_completo },
            { key: "roles", header: "Roles", render: (u) => u.roles.join(", ") },
            { key: "activo", header: "Activo", render: (u) => u.activo ? "Sí" : "No" },
            { key: "acc", header: "",
              render: (u) => <button onClick={() => toggleActivo(u)}>
                {u.activo ? "Desactivar" : "Activar"}
              </button> },
          ]}
        />
      )}
      <Modal open={open} title="Nuevo usuario" onClose={() => setOpen(false)}>
        <form onSubmit={onSubmit}>
          <FormField label="Email" required>
            <input type="email" required value={email}
              onChange={(e) => setEmail(e.target.value)} style={{ width: "100%" }} />
          </FormField>
          <FormField label="Nombre completo" required>
            <input required value={nombre}
              onChange={(e) => setNombre(e.target.value)} style={{ width: "100%" }} />
          </FormField>
          <FormField label="Contraseña (mín. 8)" required>
            <input type="password" required minLength={8} value={password}
              onChange={(e) => setPassword(e.target.value)} style={{ width: "100%" }} />
          </FormField>
          <FormField label="Roles" required>
            {(["ADMIN", "OPERADOR", "GERENTE"] as Rol[]).map((r) => (
              <label key={r} style={{ marginRight: 8 }}>
                <input type="checkbox" checked={roles.includes(r)}
                  onChange={(e) => setRoles((prev) =>
                    e.target.checked ? [...prev, r] : prev.filter((x) => x !== r),
                  )} /> {r}
              </label>
            ))}
          </FormField>
          {error && <p style={{ color: "crimson" }}>{error}</p>}
          <button type="submit">Crear</button>
        </form>
      </Modal>
    </div>
  );
}