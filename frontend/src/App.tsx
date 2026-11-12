import { Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "./auth/AuthContext";
import { RequireAuth } from "./auth/RequireAuth";
import { RequireRole } from "./auth/RequireRole";
import { Layout } from "./components/Layout";
import { LoginPage } from "./pages/LoginPage";
import { DashboardPage } from "./pages/DashboardPage";
import { AlertasPage } from "./pages/AlertasPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { PedidosListPage } from "./pages/pedidos/PedidosListPage";
import { PedidoDetailPage } from "./pages/pedidos/PedidoDetailPage";
import { ComunicacionesPage } from "./pages/comunicaciones/ComunicacionesPage";
import { CasosPage } from "./pages/casos/CasosPage";
import { ContestadorPage } from "./pages/contestador/ContestadorPage";
import { ImprevistosPage } from "./pages/casos/ImprevistosPage";
import { EntregasPage } from "./pages/entregas/EntregasPage";
import { NuevaEntregaPage } from "./pages/entregas/NuevaEntregaPage";
import { UsuariosPage } from "./pages/admin/UsuariosPage";
import { ReglasPage } from "./pages/admin/ReglasPage";
import { CatalogosPage } from "./pages/admin/CatalogosPage";
import { AdminOpsPage } from "./pages/admin/AdminOpsPage";
import { AgentePage } from "./pages/agente/AgentePage";

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          element={
            <RequireAuth>
              <Layout />
            </RequireAuth>
          }
        >
          <Route path="/" element={<DashboardPage />} />
          <Route path="/pedidos" element={<PedidosListPage />} />
          <Route path="/pedidos/:id" element={<PedidoDetailPage />} />
          <Route path="/comunicaciones" element={<ComunicacionesPage />} />
          <Route path="/agente" element={<AgentePage />} />
          <Route path="/alertas" element={<AlertasPage />} />
          <Route path="/casos" element={<CasosPage />} />
          <Route
            path="/contestador"
            element={
              <RequireRole roles={["ADMIN", "OPERADOR"]}>
                <ContestadorPage />
              </RequireRole>
            }
          />
          <Route path="/imprevistos" element={<ImprevistosPage />} />
          <Route path="/entregas" element={<EntregasPage />} />
          <Route path="/entregas/nueva" element={<NuevaEntregaPage />} />
          <Route
            path="/admin/usuarios"
            element={<RequireRole roles={["ADMIN"]}><UsuariosPage /></RequireRole>}
          />
          <Route
            path="/admin/reglas"
            element={<RequireRole roles={["ADMIN"]}><ReglasPage /></RequireRole>}
          />
          <Route
            path="/admin/catalogos"
            element={<RequireRole roles={["ADMIN"]}><CatalogosPage /></RequireRole>}
          />
          <Route
            path="/admin/ops"
            element={<RequireRole roles={["ADMIN"]}><AdminOpsPage /></RequireRole>}
          />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  );
}