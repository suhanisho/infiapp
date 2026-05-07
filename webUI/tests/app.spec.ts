import { expect, test } from "@playwright/test";

test("clinic app stores approved actions without external side effects", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Open local demo" }).click();
  await expect(page.getByRole("heading", { name: "Daily cockpit" })).toBeVisible();
  await expect(page.getByText("Open actions needing attention")).toBeVisible();

  await page.getByRole("button", { name: /Rachel Davies/i }).click();
  await expect(page.getByText("Draft reply")).toBeVisible();
  await page.getByRole("button", { name: "Approve and store" }).click();
  await expect(page.getByText("Doctor approved and stored this action.")).toBeVisible();

  await page.getByRole("button", { name: "Patients" }).click();
  await expect(page.getByRole("heading", { name: "Patients" })).toBeVisible();
  await page.getByRole("textbox", { name: "Search" }).fill("Rachel");
  await expect(page.getByRole("button", { name: /Rachel Davies/i })).toBeVisible();

  await page.getByRole("button", { name: "Schedule" }).click();
  await expect(page.getByRole("heading", { name: "This Week" })).toBeVisible();
  await expect(page.getByText("Read only")).toBeVisible();

  await page.getByRole("button", { name: "Open settings" }).click();
  await expect(page.getByRole("heading", { name: "Google Workspace" })).toBeVisible();
  await expect(page.getByText("Google Calendar")).toBeVisible();
  await expect(page.getByText("Gmail")).toBeVisible();
});
