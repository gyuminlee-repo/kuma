import { expect, test } from "@playwright/test";

test.describe("single-view rendering (MOCK_MODE)", () => {
  test("mounts all panels at once with no uncaught errors", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (err) => {
      consoleErrors.push(err.message);
    });

    await page.goto("/");

    await expect(page.getByTestId("sidebar")).toBeVisible();
    await expect(page.getByRole("main")).toBeVisible();
    await expect(page.getByRole("button", { name: /^Run/ })).toBeVisible();
    await expect(page.getByRole("button", { name: /^Validate/ })).toBeVisible();
    await expect(page.getByText("Verdict Table")).toBeVisible();
    await expect(page.getByText("Plate map")).toBeVisible();

    await page.waitForTimeout(300);

    const fatal = consoleErrors.filter(
      (m) =>
        m.includes("Uncaught") ||
        m.includes("TypeError") ||
        m.includes("ReferenceError"),
    );
    expect(fatal, `fatal console errors: ${JSON.stringify(fatal)}`).toHaveLength(0);
  });
});
