import { test, expect } from "@playwright/test";

test.describe("Login y roles", () => {
  test("operador ve su menú y no accede a /admin", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel(/Email/i).fill("operador@poluximport.pe");
    await page.getByLabel(/Contraseña/i).fill("Oper123!");
    await page.getByRole("button", { name: /Ingresar/i }).click();

    await expect(page.getByText(/Rol: OPERADOR/i)).toBeVisible();
    await expect(page.getByRole("link", { name: "Pedidos" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Usuarios" })).toHaveCount(0);

    await page.goto("/admin/usuarios");
    await expect(page.getByText(/Acceso restringido/i)).toBeVisible();
  });

  test("gerente solo ve Dashboard", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel(/Email/i).fill("gerente@poluximport.pe");
    await page.getByLabel(/Contraseña/i).fill("Ger123!");
    await page.getByRole("button", { name: /Ingresar/i }).click();

    await expect(page.getByText(/Rol: GERENTE/i)).toBeVisible();
    await expect(page.getByRole("link", { name: "Dashboard" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Pedidos" })).toHaveCount(0);
  });

  test("credenciales inválidas muestran error", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel(/Email/i).fill("gerente@poluximport.pe");
    await page.getByLabel(/Contraseña/i).fill("malo");
    await page.getByRole("button", { name: /Ingresar/i }).click();
    await expect(page.getByText(/Credenciales inválidas/i)).toBeVisible();
  });
});