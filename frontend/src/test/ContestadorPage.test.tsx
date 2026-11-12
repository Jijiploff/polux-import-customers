import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, beforeEach, afterAll } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { ContestadorPage } from "../pages/contestador/ContestadorPage";
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

const CHAT = {
  pedido_id: 21, codigo: "PD-2025-0021", estado_pedido: "EN_PROCESO",
  cliente_id: 5, cliente_nombre: "Ana Cliente", total_mensajes: 1,
  ultima_fecha: "2026-11-10T10:05:00", ultima_preview: "Quiero mi reembolso",
  ultima_autor: "CLIENTE", caso_abierto_id: 7, caso_abierto_motivo: "RECLAMO",
  responsable_id: 1, responsable_nombre: "Operador",
  puede_responder: true, cliente_telegram_vinculado: true,
  asesor_reciente: false,
};

vi.mock("../api/agent", () => ({
  agentApi: {
    chats: vi.fn().mockResolvedValue([{
      pedido_id: 21, codigo: "PD-2025-0021", estado_pedido: "EN_PROCESO",
      cliente_id: 5, cliente_nombre: "Ana Cliente", total_mensajes: 1,
      ultima_fecha: "2026-11-10T10:05:00", ultima_preview: "Quiero mi reembolso",
      ultima_autor: "CLIENTE", caso_abierto_id: 7, caso_abierto_motivo: "RECLAMO",
      responsable_id: 1, responsable_nombre: "Operador",
      puede_responder: true, cliente_telegram_vinculado: true,
      asesor_reciente: false,
    }]),
    thread: vi.fn().mockResolvedValue([{
      id: 1, direccion: "ENTRANTE", autor: "CLIENTE", canal: "TELEGRAM",
      clase: "CLIENTE", contenido: "Quiero mi reembolso",
      fecha: "2026-11-10T10:05:00", escalado: true, caso_id: 7,
      caso_motivo: "RECLAMO", caso_estado: "ABIERTO", estado_entrega: null,
    }]),
    humanReply: vi.fn(),
  },
}));

vi.mock("../api/casos", () => ({
  casosApi: {
    responder: vi.fn().mockResolvedValue({
      message: { id: 99, contenido: "Hola" },
      caso_id: 7, caso_estado: "EN_PROCESO", enviado: true, aviso: null,
    }),
  },
}));

function renderPage() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <ContestadorPage />
      </AuthProvider>
    </MemoryRouter>,
  );
}

test("el operador ve su conversación asignada y responde por el caso", async () => {
  renderPage();

  expect((await screen.findAllByText("Ana Cliente")).length).toBeGreaterThan(0);
  expect((await screen.findAllByText("Quiero mi reembolso")).length)
    .toBeGreaterThan(0);
  expect((await screen.findAllByText(/Caso #7/)).length).toBeGreaterThan(0);
  expect((await screen.findAllByText("Operador")).length).toBeGreaterThan(0);

  fireEvent.change(screen.getByLabelText(/Respuesta al cliente/i), {
    target: { value: "Hola, ya te atendemos." },
  });
  fireEvent.click(screen.getByRole("button", { name: /^Enviar$/i }));

  await waitFor(() => {
    expect(vi.mocked(casosModule.casosApi.responder)).toHaveBeenCalledWith(
      7, "Hola, ya te atendemos.",
    );
  });
  expect(vi.mocked(agentModule.agentApi.thread)).toHaveBeenCalledWith(21);
});

test("muestra un aviso cuando el cliente no tiene Telegram vinculado", async () => {
  vi.mocked(agentModule.agentApi.chats).mockResolvedValueOnce([{
    ...CHAT,
    cliente_telegram_vinculado: false,
  } as never]);

  renderPage();

  expect(await screen.findByText(/no tiene Telegram vinculado/i))
    .toBeInTheDocument();
  expect(screen.getByLabelText(/Respuesta al cliente/i)).toBeDisabled();
  expect(screen.getByRole("button", { name: /^Enviar$/i })).toBeDisabled();
});
