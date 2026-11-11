import { useMemo } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import type { Rol } from "../types/domain";

const LINKS_BY_ROLE: Record<Rol, { to: string; label: string }[]> = {
  ADMIN: [
    { to: "/", label: "Dashboard" },
    { to: "/pedidos", label: "Pedidos" },
    { to: "/alertas", label: "Alertas" },
    { to: "/casos", label: "Casos" },
    { to: "/imprevistos", label: "Imprevistos" },
    { to: "/entregas", label: "Entregas" },
    { to: "/comunicaciones", label: "Comunicaciones" },
    { to: "/agente", label: "Agente IA" },
    { to: "/admin/usuarios", label: "Usuarios" },
    { to: "/admin/reglas", label: "Reglas" },
    { to: "/admin/catalogos", label: "Catálogos" },
    { to: "/admin/ops", label: "Operaciones" },
  ],
  OPERADOR: [
    { to: "/", label: "Inicio" },
    { to: "/pedidos", label: "Pedidos" },
    { to: "/alertas", label: "Alertas" },
    { to: "/casos", label: "Casos" },
    { to: "/imprevistos", label: "Imprevistos" },
    { to: "/entregas", label: "Entregas" },
    { to: "/comunicaciones", label: "Comunicaciones" },
    { to: "/agente", label: "Agente IA" },
  ],
  GERENTE: [
    { to: "/", label: "Dashboard" },
  ],
};

const ROLE_PRIORITY: Rol[] = ["ADMIN", "OPERADOR", "GERENTE"];

export function Layout() {
  const { nombre, roles, logout } = useAuth();
  const nav = useNavigate();

  // Unión de menús por rol, sin duplicar rutas; se respeta prioridad ADMIN > OPERADOR > GERENTE.
  const links = useMemo(() => {
    const seen = new Set<string>();
    const result: { to: string; label: string }[] = [];
    for (const role of ROLE_PRIORITY) {
      if (!roles.includes(role)) continue;
      for (const link of LINKS_BY_ROLE[role]) {
        if (seen.has(link.to)) continue;
        seen.add(link.to);
        result.push(link);
      }
    }
    return result;
  }, [roles]);

  return (
    <div className="lay-raiz" style={{ display: "flex", minHeight: "100vh" }}>
      <style>{`
        /* Menú lateral que se adapta a pantallas angostas (móvil/tablet) */
        @media (max-width: 760px) {
          .lay-raiz { flex-direction: column; }
          .lay-side {
            width: 100% !important;
            flex-direction: row !important;
            flex-wrap: wrap;
            align-items: center;
            gap: 0.15rem;
            padding: 0.4rem 0.5rem !important;
          }
          .lay-brand { padding: 0.35rem 0.6rem !important; white-space: nowrap; }
          .lay-nav { flex-direction: row !important; flex-wrap: wrap; }
          .lay-nav a {
            border-left: none !important;
            border-bottom: 3px solid transparent !important;
            padding: 0.45rem 0.65rem !important;
            white-space: nowrap;
          }
          .lay-nav a[aria-current="page"] {
            border-bottom-color: #93c5fd !important;
            color: #93c5fd !important;
          }
          .lay-top { flex-wrap: wrap; gap: 0.5rem; }
          .lay-main { padding: 1rem !important; }
        }
      `}</style>
      <aside className="lay-side" style={{
        width: 240, background: "#0b1221", color: "white",
        display: "flex", flexDirection: "column", padding: "1rem 0",
      }}>
        <div className="lay-brand" style={{ padding: "0 1.25rem 1rem", fontWeight: 700, fontSize: "1.1rem" }}>
          <Link to="/" style={{ color: "white", textDecoration: "none" }}>
            Polux Import
          </Link>
        </div>
        <nav className="lay-nav" style={{ display: "flex", flexDirection: "column" }}>
          {links.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              end
              style={({ isActive }) => ({
                padding: "0.55rem 1.25rem",
                color: isActive ? "#a5b4fc" : "#cbd5e1",
                textDecoration: "none",
                borderLeft: isActive ? "3px solid #a5b4fc" : "3px solid transparent",
                fontSize: "0.9rem",
                background: isActive ? "rgba(99, 102, 241, .16)" : "transparent",
              })}
            >
              {l.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
        <header className="lay-top" style={{
          display: "flex", justifyContent: "space-between", alignItems: "center",
          padding: "0.75rem 1.5rem", background: "white",
          borderBottom: "1px solid #e2e8f0",
        }}>
          <span style={{ color: "#64748b", fontSize: "0.9rem" }}>
            Rol: {roles.join(", ")}
          </span>
          <div style={{ display: "flex", gap: "1rem", alignItems: "center" }}>
            <span>{nombre}</span>
            <button className="top-action" onClick={() => { logout(); nav("/login"); }}>Salir</button>
          </div>
        </header>
        <main className="lay-main" style={{ flex: 1, padding: "1.5rem", background: "#f8fafc" }}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}