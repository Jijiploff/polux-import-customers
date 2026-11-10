import { render, screen } from "@testing-library/react";
import { StatusBadge } from "../components/StatusBadge";

test("muestra el estado con guiones bajos reemplazados por espacios", () => {
  render(<StatusBadge value="EN_PROCESO" />);
  expect(screen.getByText("EN PROCESO")).toBeInTheDocument();
});

test("muestra estado no mapeado sin romper", () => {
  render(<StatusBadge value="NUEVO_ESTADO" />);
  expect(screen.getByText("NUEVO ESTADO")).toBeInTheDocument();
});