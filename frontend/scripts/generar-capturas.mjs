/* Genera las capturas de pantalla del manual de usuario (docs/05).
 *
 * Requiere: stack levantado (localhost:5173 + localhost:8000) y
 * Chromium de Playwright (`npx playwright install chromium` la primera vez).
 *
 * Uso:  node scripts/generar-capturas.mjs   (desde frontend/)
 */
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const BASE = "http://localhost:5173";
const API = "http://localhost:8000/api/v1";
const OUT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../docs/capturas");
mkdirSync(OUT, { recursive: true });

async function apiLogin(email, password) {
  const r = await fetch(`${API}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!r.ok) throw new Error(`login api ${r.status}`);
  const data = await r.json();
  return data.access_token;
}

async function uiLogin(page, email, password) {
  await page.goto(`${BASE}/login`);
  await page.fill('input[type="email"]', email);
  await page.fill('input[type="password"]', password);
  await Promise.all([
    page.waitForURL((u) => !u.pathname.includes("/login"), { timeout: 15000 }),
    page.click('button[type="submit"]'),
  ]);
  await page.waitForLoadState("networkidle").catch(() => {});
  await page.waitForTimeout(600);
}

async function shot(page, name) {
  await page.waitForLoadState("networkidle").catch(() => {});
  await page.waitForTimeout(900);
  await page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage: true });
  console.log(`ok  ${name}`);
}

async function main() {
  const browser = await chromium.launch({ channel: "msedge" });

  // 1) Pantalla de acceso (sin sesión)
  const ctx0 = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const p0 = await ctx0.newPage();
  await p0.goto(`${BASE}/login`);
  await p0.waitForLoadState("networkidle").catch(() => {});
  await p0.waitForTimeout(500);
  await p0.screenshot({ path: path.join(OUT, "01-acceso.png") });
  console.log("ok  01-acceso");

  // Pedido demo para el detalle (los tests crean pedidos basura al principio)
  const token = await apiLogin("admin@poluximport.pe", "Admin123!");
  const pres = await fetch(`${API}/pedidos`, { headers: { Authorization: `Bearer ${token}` } });
  const pdata = await pres.json();
  const pedidos = Array.isArray(pdata) ? pdata : (pdata.items ?? pdata.data ?? []);
  const demo = pedidos.find((p) => p.codigo === "PD-2025-0001");
  const pid = demo?.id ?? pedidos[0]?.id ?? 1;

  // 2) Sesión ADMIN: todas las páginas
  const ctxA = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const a = await ctxA.newPage();
  await uiLogin(a, "admin@poluximport.pe", "Admin123!");
  await shot(a, "02-panel-admin");

  const rutas = [
    ["03-pedidos", "/pedidos"],
    ["04-pedido-detalle", `/pedidos/${pid}`],
    ["05-entregas", "/entregas"],
    ["06-comunicaciones", "/comunicaciones"],
    ["07-alertas", "/alertas"],
    ["08-casos", "/casos"],
    ["09-imprevistos", "/imprevistos"],
    ["10-usuarios", "/admin/usuarios"],
    ["11-reglas", "/admin/reglas"],
    ["12-catalogos", "/admin/catalogos"],
    ["13-operacion", "/admin/ops"],
  ];
  for (const [name, ruta] of rutas) {
    await a.goto(`${BASE}${ruta}`);
    await shot(a, name);
  }

  // 17) Agente IA con una conversación en curso (se limpia la BD después)
  await a.goto(`${BASE}/agente`);
  await a.waitForLoadState("networkidle").catch(() => {});
  await a.getByPlaceholder(/Cuándo llega/i).fill("¿Cuándo llega mi pedido PD-2025-0001?");
  await a.getByRole("button", { name: "Enviar mensaje" }).click();
  await a.getByText("Confianza:").first().waitFor({ timeout: 15000 }).catch(() => {});
  await shot(a, "17-agente-ia");

  // 18) Modal de nuevo caso (sin guardarlo)
  await a.goto(`${BASE}/casos`);
  await a.getByRole("button", { name: "+ Nuevo caso" }).click();
  await a.waitForTimeout(400);
  await shot(a, "18-nuevo-caso");

  // 19) Simulador de WhatsApp: cliente consulta, agente escala y asesor responde
  // Nota: el agente cede el paso 10 minutos tras la última respuesta de un asesor
  // (human_in_progress). Si PD-2025-0001 está "en manos de un asesor", espera a que
  // quede libre o usa otro pedido, o la captura saldrá sin respuesta del agente.
  await a.goto(`${BASE}/simulador`);
  await a.waitForLoadState("networkidle").catch(() => {});
  // Chat sin intervención humana reciente (ahí el agente responde con IA)
  await a.locator("aside button").filter({ hasText: "PD-2025-0001" }).first().click();
  await a.waitForTimeout(600);
  await a.getByLabel("Mensaje del cliente").fill("¿Dónde está mi pedido? ¿Cuándo llega?");
  await a.getByRole("button", { name: "Enviar" }).click();
  await a.getByText("Decisión del agente:").waitFor({ timeout: 60000 }).catch(() => {});
  await a.getByLabel("Mensaje del cliente").fill("Esto es una estafa, quiero mi dinero");
  await a.getByRole("button", { name: "Enviar" }).click();
  await a.getByText(/El agente derivó este caso/).first().waitFor({ timeout: 60000 }).catch(() => {});
  await a.getByRole("button", { name: "Asesor humano" }).click();
  await a.getByLabel("Respuesta del asesor")
    .fill("Hola, ya estamos revisando tu caso: un asesor te contactará en breve.");
  await a.getByRole("button", { name: "Enviar" }).click();
  await a.getByText(/Asesor humano \(tú\)/).first().waitFor({ timeout: 30000 }).catch(() => {});
  await shot(a, "19-simulador-whatsapp");

  // 3) Sesión GERENTE (solo lectura)
  const ctxG = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const g = await ctxG.newPage();
  await uiLogin(g, "gerente@poluximport.pe", "Ger123!");
  await shot(g, "14-panel-gerente");

  // 4) Sesión OPERADOR (operación diaria)
  const ctxO = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const o = await ctxO.newPage();
  await uiLogin(o, "operador@poluximport.pe", "Oper123!");
  await shot(o, "15-panel-operador");
  await o.goto(`${BASE}/pedidos`);
  await shot(o, "16-pedidos-operador");

  await browser.close();
  console.log(`\ncapturas en ${OUT}`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
