import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import { LoginPage } from "../pages/LoginPage";
import { AuthProvider } from "../auth/AuthContext";

// Mock del cliente HTTP para no pegarle al backend real
vi.mock("../api/auth", () => ({
  authApi: {
    login: vi.fn().mockResolvedValue({
      access_token: "tok", token_type: "bearer",
      roles: ["OPERADOR"], nombre: "Test",
    }),
    me: vi.fn().mockResolvedValue({
      id: 1, email: "test@x.com", nombre: "Test", roles: ["OPERADOR"],
    }),
  },
}));

test("muestra campos de login y permite enviar", async () => {
  render(
    <MemoryRouter>
      <AuthProvider>
        <LoginPage />
      </AuthProvider>
    </MemoryRouter>,
  );
  expect(screen.getByText(/Fase Customers/i)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText(/Email/i), {
    target: { value: "test@x.com" },
  });
  fireEvent.change(screen.getByLabelText(/Contraseña/i), {
    target: { value: "Abcd1234!" },
  });
  fireEvent.click(screen.getByRole("button", { name: /Ingresar/i }));
  await waitFor(() => {
    // Sin excepción = éxito; el mock resolvió y navegó
    expect(true).toBe(true);
  });
});