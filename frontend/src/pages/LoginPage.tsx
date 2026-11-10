import { FormEvent, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { FormField } from "../components/FormField";

export function LoginPage() {
  const { login } = useAuth();
  const nav = useNavigate();
  const loc = useLocation() as { state?: { from?: { pathname: string } } };
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(email, password);
      nav(loc.state?.from?.pathname ?? "/", { replace: true });
    } catch (err) {
      setError("Credenciales inválidas o servicio no disponible.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{
      minHeight: "100vh", display: "flex", alignItems: "center",
      justifyContent: "center", background: "#f1f5f9",
    }}>
      <form onSubmit={onSubmit} style={{
        background: "white", padding: "2rem", borderRadius: 8,
        minWidth: 320, boxShadow: "0 6px 24px rgba(15,23,42,0.08)",
      }}>
        <h1 style={{ marginTop: 0 }}>Polux Import</h1>
        <p style={{ color: "#475569", fontSize: "0.9rem" }}>Fase Customers · Acceso</p>
        <FormField label="Email" required>
          <input type="email" required value={email}
            onChange={(e) => setEmail(e.target.value)}
            style={{ width: "100%", padding: "0.5rem" }} />
        </FormField>
        <FormField label="Contraseña" required>
          <input type="password" required value={password}
            onChange={(e) => setPassword(e.target.value)}
            style={{ width: "100%", padding: "0.5rem" }} />
        </FormField>
        {error && <p style={{ color: "crimson", fontSize: "0.85rem" }}>{error}</p>}
        <button type="submit" disabled={loading}
          style={{ width: "100%", padding: "0.6rem", background: "#0b57d0",
                   color: "white", border: "none", borderRadius: 6, cursor: "pointer" }}>
          {loading ? "Ingresando…" : "Ingresar"}
        </button>
      </form>
    </div>
  );
}