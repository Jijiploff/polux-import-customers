import { createContext, useContext, useEffect, useMemo, useState, ReactNode } from "react";
import { authApi } from "../api/auth";
import { clearToken, getToken, setToken } from "../api/client";
import type { Rol } from "../types/domain";

interface AuthState {
  userId: number | null;
  email: string | null;
  nombre: string | null;
  roles: Rol[];
  ready: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  hasRole: (...roles: Rol[]) => boolean;
}

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [userId, setUserId] = useState<number | null>(null);
  const [email, setEmail] = useState<string | null>(null);
  const [nombre, setNombre] = useState<string | null>(null);
  const [roles, setRoles] = useState<Rol[]>([]);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const token = getToken();
    if (!token) { setReady(true); return; }
    authApi.me()
      .then((m) => {
        setUserId(m.id); setEmail(m.email); setNombre(m.nombre);
        setRoles(m.roles as Rol[]);
      })
      .catch(() => { clearToken(); })
      .finally(() => setReady(true));
  }, []);

  async function login(emailIn: string, password: string) {
    const res = await authApi.login(emailIn, password);
    setToken(res.access_token);
    const m = await authApi.me();
    setUserId(m.id); setEmail(m.email); setNombre(m.nombre);
    setRoles(m.roles as Rol[]);
  }

  function logout() {
    clearToken();
    setUserId(null); setEmail(null); setNombre(null); setRoles([]);
  }

  const value = useMemo<AuthState>(() => ({
    userId, email, nombre, roles, ready, login, logout,
    hasRole: (...needed) => needed.some((r) => roles.includes(r)),
  }), [userId, email, nombre, roles, ready]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth fuera de AuthProvider");
  return ctx;
}