import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, beforeEach, afterAll } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { ComunicacionesPage } from "../pages/comunicaciones/ComunicacionesPage";
import { AuthProvider } from "../auth/AuthContext";
import * as comunicacionesModule from "../api/comunicaciones";

beforeEach(() => localStorage.setItem("polux.token", "test-token"));
afterAll(() => localStorage.clear());

vi.mock("../api/auth", () => ({
  authApi: {
    login: vi.fn(),
    me: vi.fn().mockResolvedValue({
      id: 1, email: "oper@x", nombre: "Operador", roles: ["OPERADOR"],
    }),
  },
}));

vi.mock("../api/pedidos", () => ({
  pedidosApi: { list: vi.fn().mockResolvedValue({ items: [] }) },
}));

vi.mock("../api/comunicaciones", () => ({
  comunicacionesApi: {
    list: vi.fn().mockResolvedValue([
      {
        id: 1, pedido_id: 10, direccion: "ENTRANTE", canal: "TELEGRAM",
        clase: "CLIENTE", contenido: "Hola, ¿cómo va mi pedido?",
        autor: "CLIENTE", escalado: false, fecha: "2026-11-10T10:00:00",
      },
      {
        id: 2, pedido_id: 10, direccion: "SALIENTE", canal: "TELEGRAM",
        clase: "OPERATIVO", contenido: "✅ Vinculado al pedido PD-2025-0010",
        autor: "AGENTE", escalado: false, fecha: "2026-11-10T10:01:00",
      },
    ]),
    crear: vi.fn(),
  },
}));

function renderPage() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <ComunicacionesPage />
      </AuthProvider>
    </MemoryRouter>,
  );
}

test("muestra la clase de cada mensaje y filtra por operativo", async () => {
  renderPage();

  expect(await screen.findByText("Hola, ¿cómo va mi pedido?")).toBeInTheDocument();
  expect(screen.getByText("CLIENTE")).toBeInTheDocument();
  expect(screen.getByText("OPERATIVO")).toBeInTheDocument();

  fireEvent.change(screen.getByLabelText(/Clase/i), {
    target: { value: "OPERATIVO" },
  });

  await waitFor(() => {
    expect(vi.mocked(comunicacionesModule.comunicacionesApi.list))
      .toHaveBeenLastCalledWith({
        page: 1, size: 50, pedido_id: undefined, clase: "OPERATIVO",
      });
  });
});
