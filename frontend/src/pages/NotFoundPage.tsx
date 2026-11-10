import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <div style={{ textAlign: "center", padding: "4rem" }}>
      <h1 style={{ fontSize: "3rem", margin: 0 }}>404</h1>
      <p style={{ color: "#64748b" }}>La página que buscas no existe.</p>
      <Link to="/" style={{ color: "#0b57d0" }}>Volver al inicio</Link>
    </div>
  );
}