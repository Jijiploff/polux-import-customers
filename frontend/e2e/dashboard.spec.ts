import { test, expect } from "@playwright/test";

test.describe("Dashboard de KPIs", () => {
  test("gerente ve los 7 KPIs y filtros", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel(/Email/i).fill("gerente@poluximport.pe");
    await page.getByLabel(/Contraseña/i).fill("Ger123!");
    await page.getByRole("button", { name: /Ingresar/i }).click();

    await expect(page.getByRole("heading", { name: /Dashboard de KPIs/i })).toBeVisible();
    for (const titulo of [
      "Actualización al cliente",
      "Resolución automática",
      "Tiempo respuesta escalados",
      "Resolución de imprevistos",
      "Entregas a tiempo",
      "Entregas sin observaciones",
      "% entregas parciales",
    ]) {
      await expect(page.getByText(titulo, { exact: false }).first()).toBeVisible();
    }
    // Filtros presentes
    await expect(page.getByLabel(/Desde/i)).toBeVisible();
    await expect(page.getByLabel(/Hasta/i)).toBeVisible();
    await expect(page.getByLabel(/Granularidad/i)).toBeVisible();
  });
});