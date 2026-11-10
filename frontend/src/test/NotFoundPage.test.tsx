import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { NotFoundPage } from "../pages/NotFoundPage";

test("muestra 404 y enlace al inicio", () => {
  render(
    <MemoryRouter>
      <NotFoundPage />
    </MemoryRouter>,
  );
  expect(screen.getByText("404")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Volver al inicio/i }))
    .toHaveAttribute("href", "/");
});