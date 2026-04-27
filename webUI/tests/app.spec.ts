import { expect, test } from "@playwright/test";

test("home page calls backend api", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Hi from infiapp" })).toBeVisible();
  await page.getByRole("textbox", { name: "Message" }).fill("echo this message");
  await page.getByRole("button", { name: "Store message" }).click();
  await expect(page.getByText("Stored echo this message")).toBeVisible();
  await expect(page.getByRole("list", { name: "Stored messages" })).toContainText("echo this message");
  await page.getByRole("button", { name: "List messages" }).click();
  await expect(page.getByRole("list", { name: "Stored messages" })).toContainText("echo this message");
  const screenshot = await page.screenshot({ fullPage: true });
  expect(screenshot.length).toBeGreaterThan(1000);
});
