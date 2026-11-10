import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, beforeEach, afterAll } from "vitest";
import { Timeline } from "../components/Timeline";
import * as pedidosModule from "../api/pedidos";
import type { Timeline as TimelineData } from "../types/domain";

beforeEach(() => localStorage.setItem("polux.token", "test-token"));
afterAll(() => localStorage.clear());

vi.mock("../api/pedidos", () => ({
  pedidosApi: {
    timeline: vi.fn(),
    list: vi.fn(),
    detail: vi.fn(),
    full: vi.fn(),
  },
}));

const TIMELINE: TimelineData = {
  pedido_id: 7,
  resumen: {
    mensajes: 5, mensajes_clave: 2, hitos_atrasados: 1,
    casos_abiertos: 1, imprevistos_abiertos: 0, alertas_activas: 1,
  },
  eventos: [
    {
      fecha: "2026-11-10T10:00:00", tipo: "caso",
      titulo: "Caso #12: RECLAMO",
      detalle: "Agente detectó RECLAMO · prioridad ALTA · estado EN_PROCESO",
      criticidad: "ALTA", ref_tipo: "caso", ref_id: 12, autor: null,
    },
    {
      fecha: "2026-11-09T09:00:00", tipo: "mensaje",
      titulo: "Mensaje del cliente", detalle: "¿Dónde está mi pedido?",
      criticidad: "INFO", ref_tipo: "comunicacion", ref_id: 1,
      autor: "CLIENTE",
    },
    {
      fecha: "2026-11-01T08:00:00", tipo: "pedido",
      titulo: "Pedido ingresado", detalle: "primer pago verificado · fecha prometida 19/11/2026",
      criticidad: "INFO", ref_tipo: "pedido", ref_id: 7, autor: null,
    },
  ],
  incluyendo_mensajes: false,
};

test("carga la línea de tiempo y muestra eventos, resumen y título", async () => {
  vi.mocked(pedidosModule.pedidosApi.timeline).mockResolvedValue(TIMELINE);

  render(<Timeline pedidoId={7} titulo="Historial del pedido" />);

  expect(
    await screen.findByText("Historial del pedido")
  ).toBeInTheDocument();
  expect(await screen.findByText("Caso #12: RECLAMO")).toBeInTheDocument();
  expect(screen.getByText("¿Dónde está mi pedido?")).toBeInTheDocument();
  // Chips de resumen (solo valores > 0): número + etiqueta en nodos de texto
  expect(screen.getByText("5")).toBeInTheDocument();
  expect(screen.getByText("mensajes")).toBeInTheDocument();
  expect(screen.getByText("hito(s) atrasado(s)")).toBeInTheDocument();
  // Arranca en modo eventos clave (incluir_mensajes=false)
  expect(pedidosModule.pedidosApi.timeline).toHaveBeenCalledWith(7, {
    incluir_mensajes: false,
  });
});

test("el toggle 'Ver todos los mensajes' recarga con incluir_mensajes=true", async () => {
  vi.mocked(pedidosModule.pedidosApi.timeline).mockResolvedValue(TIMELINE);

  render(<Timeline pedidoId={7} />);
  const toggle = await screen.findByLabelText("Ver todos los mensajes e interacciones");
  expect(toggle).not.toBeChecked();

  fireEvent.click(toggle);

  await waitFor(() => {
    expect(pedidosModule.pedidosApi.timeline).toHaveBeenCalledWith(7, {
      incluir_mensajes: true,
    });
  });
  expect(toggle).toBeChecked();
});

test("muestra mensaje cuando no hay eventos", async () => {
  vi.mocked(pedidosModule.pedidosApi.timeline).mockResolvedValue({
    pedido_id: 7,
    resumen: {
      mensajes: 0, mensajes_clave: 0, hitos_atrasados: 0,
      casos_abiertos: 0, imprevistos_abiertos: 0, alertas_activas: 0,
    },
    eventos: [],
    incluyendo_mensajes: false,
  });

  render(<Timeline pedidoId={7} />);

  expect(
    await screen.findByText("Sin eventos registrados todavía.")
  ).toBeInTheDocument();
});

test("muestra error si la carga falla", async () => {
  vi.mocked(pedidosModule.pedidosApi.timeline).mockRejectedValue(
    new Error("500")
  );

  render(<Timeline pedidoId={7} />);

  expect(
    await screen.findByText("No se pudo cargar la línea de tiempo.")
  ).toBeInTheDocument();
});
