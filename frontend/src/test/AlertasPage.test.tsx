import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, beforeEach, afterAll } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { AlertasPage } from "../pages/AlertasPage";
import { AuthProvider } from "../auth/AuthContext";
import * as alertasModule from "../api/alertas";

// AuthProvider solo llama a /auth/me si hay token guardado
beforeEach(() => localStorage.setItem("polux.token", "test-token"));
afterAll(() => localStorage.clear());

vi.mock("../api/auth", () => ({
  authApi: {
    login: vi.fn(),
    me: vi.fn().mockResolvedValue({
      id: 1, email: "admin@x", nombre: "Admin", roles: ["ADMIN"],
    }),
  },
}));

vi.mock("../api/alertas", () => ({
  alertasApi: {
    list: vi.fn().mockResolvedValue([
      { id: 1, tipo: "RETRASO_LEVE", pedido_id: 10, severidad: "MEDIA",
        mensaje: "Hito retrasado", estado: "ABIERTA",
        fecha_deteccion: new Date().toISOString() },
    ]),
    atender: vi.fn().mockResolvedValue({}),
    actualizar: vi.fn().mockResolvedValue({}),
  },
}));

test("muestra alertas y permite atender", async () => {
  render(
    <MemoryRouter>
      <AuthProvider>
        <AlertasPage />
      </AuthProvider>
    </MemoryRouter>,
  );
  expect(await screen.findByText("RETRASO LEVE")).toBeInTheDocument();
  const btn = screen.getByRole("button", { name: /Atender/i });
  fireEvent.click(btn);
  await waitFor(() => {
    expect(vi.mocked(alertasModule.alertasApi.atender))
      .toHaveBeenCalledWith(1);
  });
});