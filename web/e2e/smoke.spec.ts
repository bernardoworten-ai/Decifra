import { test, expect } from "@playwright/test";

test("homepage carrega e lista produtos", async ({ page }) => {
  const res = await page.goto("/");
  expect(res?.ok()).toBeTruthy();
  await expect(page.locator("h1")).toBeVisible();
  await expect(page.locator('a[href^="/produto/"]').first()).toBeVisible();
});

test("ficha renderiza DECIFRA Score e proveniência", async ({ page }) => {
  await page.goto("/");
  await page.locator('a[href^="/produto/"]').first().click();
  await expect(page).toHaveURL(/\/produto\//);
  await expect(page.locator("h1")).toBeVisible();
  await expect(page.getByText(/score/i).first()).toBeVisible();
  await expect(page.getByText(/confian|fonte/i).first()).toBeVisible();
});

test("API de lookup responde 200", async ({ request }) => {
  const r = await request.get("/api/lookup?q=sony");
  expect(r.ok()).toBeTruthy();
});
