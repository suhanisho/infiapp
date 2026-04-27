import { expect, test } from "@playwright/test";

test("home page calls backend api", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Hi from infiapp" })).toBeVisible();
  await page.getByLabel("Message").fill("echo this message");
  await page.getByRole("button", { name: "Call backend" }).click();
  await expect(page.getByText("echo this message")).toBeVisible();
  const screenshot = await page.screenshot({ fullPage: true });
  expect(screenshot.length).toBeGreaterThan(1000);
});
