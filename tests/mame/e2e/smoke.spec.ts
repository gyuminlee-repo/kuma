import { expect, openWorkspace, test } from "./browser-fixture";

test("boots through Home and switches KURO and MAME by mouse and keyboard", async ({ page }, testInfo) => {
  await openWorkspace(page);
  await page.screenshot({ path: testInfo.outputPath("kuro-workspace.png"), fullPage: true });
  const mame = page.getByRole("tab", { name: "Mame", exact: true });
  const kuro = page.getByRole("tab", { name: "Kuro", exact: true });
  await mame.click();
  await expect(mame).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("navigation", { name: "MAME Workflow" })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("mame-initial-inputs.png"), fullPage: true });
  await mame.press("ArrowLeft");
  await expect(kuro).toBeFocused();
  await expect(kuro).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("navigation", { name: "MAME Workflow" })).toHaveCount(0);
  await kuro.press("ArrowRight");
  await expect(mame).toBeFocused();
  await expect(page.getByRole("navigation", { name: "MAME Workflow" })).toBeVisible();

  // Opt-in failing control exercises this test's actual teardown gate.
  if (process.env.MAME_E2E_INJECT_ERROR === "1") {
    const observed = page.waitForEvent("pageerror");
    await page.evaluate(() => { setTimeout(() => { throw new Error("analysis failed"); }, 0); });
    expect((await observed).message).toBe("analysis failed");
  }
});
