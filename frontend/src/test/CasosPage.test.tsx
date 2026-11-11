import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, beforeEach, afterAll } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { CasosPage } from "../pages/casos/CasosPage";
import { AuthProvider } from "../auth/AuthContext";
import * as casosModule from "../api/casos";
import * as agentModule from "../api/agent";

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

vi.mock("../components/Timeline", () => ({
  Timeline: () => <div>timeline-stub</div>,
}));

vi.mock("../api/pedidos", () => ({
  pedidosApi: { list: vi.fn().mockResolvedValue({ items: [] }) },
}));

const CASO = {
  id: 7, pedido_id: 21, motivo: "RECLAMO", prioridad: "ALTA",
  descripcion: "Cliente molesto", fecha_apertura: "2026-11-10T10:00:00",
  fecha_primera_accion: null, responsable_id: null, estado: "ABIERTO",
  fecha_cierre: null,
};

vi.mock("../api/casos", () => ({
  casosApi: {
    list: vi.fn().mockResolvedValue([{
      id: 7, pedido_id: 21, motivo: "RECLAMO", prioridad: "ALTA",
      descripcion: "Cliente molesto", fecha_apertura: "2026-11-10T10:00:00",
      fecha_primera_accion: null, responsable_id: null, estado: "ABIERTO",
      fecha_cierre: null,
    }]),
    detalle: vi.fn().mockResolvedValue({
      id: 7, pedido_id: 21, motivo: "RECLAMO", prioridad: "ALTA",
      descripcion: "Cliente molesto", fecha_apertura: "2026-11-10T10:00:00",
      fecha_primera_accion: null, responsable_id: null, estado: "ABIERTO",
      fecha_cierre: null, responsable_nombre: null,
      pedido_codigo: "PD-2025-0021", cliente_nombre: "Ana Cliente",
      cliente_telegram_vinculado: true, puede_responder: true,
    }),
    responder: vi.fn().mockResolvedValue({
      message: {
        id: 99, direccion: "SALIENTE", autor: "HUMANO", canal: "TELEGRAM",
        clase: "CLIENTE", contenido: "Hola, ya te atendemos.",
        fecha: "2026-11-11T12:00:00", escalado: true, caso_id: 7,
        caso_estado: "EN_PROCESO", estado_entrega: "SENT",
      },
      caso_id: 7, caso_estado: "EN_PROCESO", enviado: true, aviso: null,
    }),
    cerrar: vi.fn(),
    actualizar: vi.fn(),
    crear: vi.fn(),
  },
}));

vi.mock("../api/agent", () => ({
  agentApi: {
    thread: vi.fn().mockResolvedValue([{
      id: 1, direccion: "ENTRANTE", autor: "CLIENTE", canal: "TELEGRAM",
      clase: "CLIENTE", contenido: "Quiero mi reembolso",
      fecha: "2026-11-10T10:05:00", escalado: true, caso_id: 7,
      caso_motivo: "RECLAMO", caso_estado: "ABIERTO", estado_entrega: null,
    }]),
  },
}));

function renderPage() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <CasosPage />
      </AuthProvider>
    </MemoryRouter>,
  );
}

test("permite responder un caso desde la plataforma", async () => {
  renderPage();

  expect(await screen.findByText("RECLAMO")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /Responder/i }));

  expect(await screen.findByText(/Conversación con el cliente/i)).toBeInTheDocument();
  expect(await screen.findByText("Quiero mi reembolso")).toBeInTheDocument();
  expect(screen.getByText(/vinculado ✅/)).toBeInTheDocument();

  fireEvent.change(screen.getByLabelText(/Respuesta al cliente/i), {
    target: { value: "Hola, ya te atendemos." },
  });
  fireEvent.click(screen.getByRole("button", { name: /Enviar respuesta/i }));

  await waitFor(() => {
    expect(vi.mocked(casosModule.casosApi.responder)).toHaveBeenCalledWith(
      7, "Hola, ya te atendemos.",
    );
  });
  expect(vi.mocked(agentModule.agentApi.thread)).toHaveBeenCalledWith(21);
});

test("bloquea la respuesta si el cliente no tiene Telegram", async () => {
  vi.mocked(casosModule.casosApi.detalle).mockResolvedValueOnce({
    ...CASO,
    responsable_nombre: null,
    pedido_codigo: "PD-2025-0021",
    cliente_nombre: "Ana Cliente",
    cliente_telegram_vinculado: false,
    puede_responder: true,
  } as never);

  renderPage();
  expect(await screen.findByText("RECLAMO")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /Responder/i }));

  expect(await screen.findByText(/sin vincular ⚠️/)).toBeInTheDocument();
  expect(screen.getByLabelText(/Respuesta al cliente/i)).toBeDisabled();
  expect(screen.getByRole("button", { name: /Enviar respuesta/i })).toBeDisabled();
});
