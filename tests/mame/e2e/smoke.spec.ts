import { expect, test } from "@playwright/test";

test.describe("smoke", () => {
  test("app boots and renders single-view layout", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveTitle(/MAME/i);

    // Sidebar and main sections rendered together (no screen switching)
    await expect(page.getByTestId("sidebar")).toBeVisible();
    await expect(page.getByRole("main")).toBeVisible();
    await expect(page.getByText("Verdict Table")).toBeVisible();
    await expect(page.getByText("Plate map")).toBeVisible();

    // MenuBar wordmark
    await expect(page.getByRole("banner").getByText("mame")).toBeVisible();
  });
});
