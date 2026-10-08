import { expect, openWorkspace, test } from "./browser-fixture";

test("MAME navigates from setup to QC inputs and empty review", async ({ page }, testInfo) => {
  await openWorkspace(page);
  await page.getByRole("tab", { name: "Mame", exact: true }).click();
  const rail = page.getByRole("navigation", { name: "MAME Workflow" });
  await expect(rail).toBeVisible();
  await expect(rail.getByRole("button", { name: "Inputs", exact: true })).toHaveAttribute("aria-current", "step");
  await rail.getByRole("button", { name: "Barcode Package", exact: true }).click();
  await expect(rail.getByRole("button", { name: "Barcode Package", exact: true })).toHaveAttribute("aria-current", "step");
  await page.screenshot({ path: testInfo.outputPath("mame-setup.png"), fullPage: true });
  await rail.getByRole("button", { name: "Inputs", exact: true }).click();
  await expect(rail.getByRole("button", { name: "Inputs", exact: true })).toHaveAttribute("aria-current", "step");
  await expect(page.getByRole("button", { name: /^Validate/ })).toBeVisible();
  await expect(page.getByRole("main").getByRole("button", { name: "Run", exact: true })).toBeDisabled();
  await page.screenshot({ path: testInfo.outputPath("mame-qc-inputs.png"), fullPage: true });
  await rail.getByRole("button", { name: "Review (Verdict + Plate)", exact: true }).click();
  await expect(rail.getByRole("button", { name: "Review (Verdict + Plate)", exact: true })).toHaveAttribute("aria-current", "step");
  await expect(page.getByRole("main")).toBeVisible();
  await expect(page.getByText("Verdict table", { exact: true })).toBeVisible();
  await expect(page.getByText("Plate map", { exact: true })).toBeVisible();
  await expect(page.getByText("Run analysis to populate the verdict table.", { exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("mame-qc-review.png"), fullPage: true });
  await rail.getByRole("button", { name: "Inputs", exact: true }).click();
  await expect(page.getByRole("button", { name: /^Validate/ })).toBeVisible();
});
