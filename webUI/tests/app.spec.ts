import { expect, test } from "@playwright/test";

test("Nora exposes approval-gated clinic workflows", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("Nora", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Open local demo" }).click();
  await expect(page.getByText("Nora", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: /Good (morning|afternoon|evening), Doctor/ })).toBeVisible();
  await expect(page.getByText("Needs your attention")).toBeVisible();

  await page.getByRole("button", { name: /Rachel Davies/i }).click();
  await expect(page.getByText("Draft reply")).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve & send" })).toBeVisible();

  await page.getByRole("button", { name: "Inbox", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Inbox" })).toBeVisible();
  await page.getByRole("button", { name: /Rachel Davies/i }).click();
  await expect(page.getByText("Latest AI draft")).toBeVisible();
  await page.getByRole("button", { name: "Review & send in Rounds" }).click();
  await expect(page.getByText("Draft reply")).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve & send" })).toBeVisible();

  await page.getByRole("button", { name: "Patients", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Patients" })).toBeVisible();
  await page.getByRole("textbox", { name: "Search" }).fill("Rachel");
  await expect(page.getByRole("button", { name: /Rachel Davies/i })).toBeVisible();

  await page.getByRole("button", { name: "Schedule", exact: true }).click();
  await expect(page.getByRole("heading", { name: "This Week" })).toBeVisible();
  await expect(page.getByText("Read only")).toBeVisible();

  await page.getByRole("button", { name: "Open settings" }).click();
  await expect(page.getByRole("heading", { name: "Google Workspace" })).toBeVisible();
  await expect(page.getByText("Google Calendar", { exact: true })).toBeVisible();
  await expect(page.getByText("Gmail", { exact: true })).toBeVisible();
});
