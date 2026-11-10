import { useAuth } from "./AuthContext";
import type { Rol } from "../types/domain";

export function RequireRole({ roles, children }: { roles: Rol[]; children: JSX.Element }) {
  const { hasRole } = useAuth();
  if (!hasRole(...roles)) {
    return (
      <div style={{ padding: "2rem", textAlign: "center" }}>
        <h2>Acceso restringido</h2>
        <p>Necesitas uno de estos roles: {roles.join(", ")}.</p>
      </div>
    );
  }
  return children;
}