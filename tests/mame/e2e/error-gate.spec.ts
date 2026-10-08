import { expect, test } from "@playwright/test";
import { watchBrowserErrors } from "./browser-fixture";

for (const kind of ["pageerror", "console.error"] as const) {
  test(`gate rejects an injected ordinary ${kind}`, async ({ page }) => {
    const gate = watchBrowserErrors(page);
    try {
      await page.goto("/");
      await expect(page.getByRole("heading", { name: "kuma", exact: true })).toBeVisible();
      gate.assertClean();
      if (kind === "pageerror") {
        const observed = page.waitForEvent("pageerror");
        await page.evaluate(() => { setTimeout(() => { throw new Error("analysis failed"); }, 0); });
        const error = await observed;
        expect(error.name).toBe("Error");
        expect(error.message).toBe("analysis failed");
      } else {
        const observed = page.waitForEvent("console", (message) => message.type() === "error");
        await page.evaluate(() => console.error("analysis failed"));
        await observed;
      }
      expect(gate.errors).toEqual([`${kind}: analysis failed`]);
      expect(() => gate.assertClean()).toThrow("Unexpected browser errors");
    } finally {
      gate.dispose();
    }
  });
}
