import { test, expect } from "@playwright/test";

test.describe("Entrega parcial — regla inviolable", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel(/Email/i).fill("operador@poluximport.pe");
    await page.getByLabel(/Contraseña/i).fill("Oper123!");
    await page.getByRole("button", { name: /Ingresar/i }).click();
    await expect(page.getByText(/Rol: OPERADOR/i)).toBeVisible();
  });

  test("formulario bloquea parcial sin motivo ni confirmación", async ({ page }) => {
    // Ir a la primera entrega con pedido
    await page.goto("/entregas");
    const selector = page.locator("select").first();
    await selector.selectOption({ index: 1 }); // primer pedido
    await page.getByRole("button", { name: /Programar nueva entrega/i }).click();

    // Cambiar a parcial
    await page.getByLabel(/Tipo/i).selectOption("PARCIAL");
    // Intento de enviar sin motivo ni confirmación
    await page.getByRole("button", { name: /Registrar entrega/i }).click();
    await expect(page.getByText(/motivo de la entrega parcial/i)).toBeVisible();
  });
});