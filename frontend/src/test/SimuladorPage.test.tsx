import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, beforeEach, afterAll } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { SimuladorPage } from "../pages/simulador/SimuladorPage";
import * as agentModule from "../api/agent";

beforeEach(() => localStorage.setItem("polux.token", "test-token"));
afterAll(() => localStorage.clear());

vi.mock("../api/agent", () => ({
  agentApi: {
    provider: vi.fn().mockResolvedValue({ provider: "gemini" }),
    chats: vi.fn().mockResolvedValue([
      {
        pedido_id: 1, codigo: "PD-2025-0001", estado_pedido: "EN_PROCESO",
        cliente_id: 10, cliente_nombre: "Cliente Demo", total_mensajes: 2,
        ultima_fecha: "2026-11-10T12:00:00",
        ultima_preview: "Hola, ¿dónde está mi pedido?",
        ultima_autor: "CLIENTE", caso_abierto_id: null,
        caso_abierto_motivo: null, asesor_reciente: false,
      },
    ]),
    thread: vi.fn().mockResolvedValue([
      {
        id: 1, direccion: "ENTRANTE", autor: "CLIENTE", canal: "WHATSAPP",
        contenido: "Hola, ¿dónde está mi pedido?", fecha: "2026-11-10T12:00:00",
        intencion_detectada: "ESTADO_PEDIDO", sentimiento: "NEUTRO",
        escalado: false, caso_id: null, plantilla_id: null,
        estado_entrega: null,
      },
      {
        id: 2, direccion: "SALIENTE", autor: "AGENTE", canal: "WHATSAPP",
        contenido: "Tu pedido está en proceso.", fecha: "2026-11-10T12:00:05",
        intencion_detectada: null, sentimiento: null,
        escalado: false, caso_id: null, plantilla_id: 3,
        estado_entrega: "SENT",
      },
    ]),
    incoming: vi.fn().mockResolvedValue({
      incoming_comunicacion_id: 5,
      outgoing_comunicacion_id: 6,
      classification: {
        intent: "ESTADO_PEDIDO", sentiment: "NEUTRO",
        confidence: 0.95, provider_used: "gemini",
      },
      escalated: false,
      escalation_reason: null,
      caso_id: null,
      response_text: "Tu pedido está en proceso.",
      fallback_used: false,
      human_in_progress: false,
      fecha_procesamiento: "2026-11-10T12:01:00",
    }),
    humanReply: vi.fn().mockResolvedValue({
      message: {
        id: 7, direccion: "SALIENTE", autor: "HUMANO", canal: "WHATSAPP",
        contenido: "Ya estamos en contacto.", fecha: "2026-11-10T12:02:00",
        intencion_detectada: null, sentimiento: null, escalado: true,
        caso_id: 12, plantilla_id: null, estado_entrega: "SENT",
      },
      caso_id: 12,
      caso_estado: "EN_PROCESO",
      aviso: "Caso #12 en proceso (registrada la primera respuesta humana).",
    }),
  },
}));

test("carga la bandeja de chats y el hilo de conversación", async () => {
  render(
    <MemoryRouter>
      <SimuladorPage />
    </MemoryRouter>,
  );

  expect(await screen.findAllByText("Cliente Demo")).not.toHaveLength(0);
  expect(await screen.findByText("Hola, ¿dónde está mi pedido?")).toBeInTheDocument();
  expect(await screen.findByText("Tu pedido está en proceso.")).toBeInTheDocument();
  expect(await screen.findByText("ESTADO_PEDIDO")).toBeInTheDocument();
  expect(await screen.findByText(/Motor: gemini/)).toBeInTheDocument();
});

test("envía un mensaje como cliente y muestra la decisión del agente", async () => {
  render(
    <MemoryRouter>
      <SimuladorPage />
    </MemoryRouter>,
  );
  await screen.findAllByText("Cliente Demo");

  const textarea = screen.getByLabelText("Mensaje del cliente");
  fireEvent.change(textarea, { target: { value: "¿Cuándo llega mi pedido?" } });
  fireEvent.click(screen.getByRole("button", { name: "Enviar" }));

  await waitFor(() => {
    expect(vi.mocked(agentModule.agentApi.incoming)).toHaveBeenCalledWith({
      pedido_id: 1,
      canal: "WHATSAPP",
      contenido: "¿Cuándo llega mi pedido?",
    });
  });
  expect(await screen.findByText("Decisión del agente:")).toBeInTheDocument();
  expect(screen.getByText("respondió solo")).toBeInTheDocument();
});

test("permite responder como asesor humano desde la plataforma", async () => {
  render(
    <MemoryRouter>
      <SimuladorPage />
    </MemoryRouter>,
  );
  await screen.findAllByText("Cliente Demo");

  fireEvent.click(screen.getByRole("button", { name: "Asesor humano" }));
  const textarea = screen.getByLabelText("Respuesta del asesor");
  fireEvent.change(textarea, { target: { value: "Ya estamos en contacto." } });
  fireEvent.click(screen.getByRole("button", { name: "Enviar" }));

  await waitFor(() => {
    expect(vi.mocked(agentModule.agentApi.humanReply)).toHaveBeenCalledWith(
      1,
      "Ya estamos en contacto.",
    );
  });
  expect(
    await screen.findByText(/Caso #12 en proceso/),
  ).toBeInTheDocument();
});
