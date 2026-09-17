import { expect, test as base } from "@playwright/test";
import type { ConsoleMessage, Page } from "@playwright/test";

export function watchBrowserErrors(page: Page) {
  const errors: string[] = [];
  const onPageError = (error: Error) => errors.push(`pageerror: ${error.message}`);
  const onConsole = (message: ConsoleMessage) => {
    if (message.type() === "error") errors.push(`console.error: ${message.text()}`);
  };
  page.on("pageerror", onPageError);
  page.on("console", onConsole);
  return {
    errors,
    assertClean: () => expect(errors, "Unexpected browser errors").toEqual([]),
    dispose: () => {
      page.off("pageerror", onPageError);
      page.off("console", onConsole);
    },
  };
}

export const test = base.extend<{ browserErrorGate: void }>({
  browserErrorGate: [async ({ page }, use, testInfo) => {
    const gate = watchBrowserErrors(page);
    try {
      await use();
    } finally {
      await testInfo.attach("browser-errors", {
        body: JSON.stringify(gate.errors, null, 2), contentType: "application/json",
      });
      gate.dispose();
      gate.assertClean();
    }
  }, { auto: true }],
});

export { expect };

export async function openWorkspace(page: Page) {
  await page.goto("/");
  await expect(page).toHaveTitle("kuma");
  await expect(page.getByRole("heading", { name: "kuma", exact: true })).toBeVisible();
  await page.getByRole("button", { name: /^ispS_evolvepro_round1/ }).click();
  await expect(page.getByRole("tab", { name: "Kuro", exact: true })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("main")).toBeVisible();
}
