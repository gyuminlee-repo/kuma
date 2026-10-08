import type { Page } from "@playwright/test";
import { expect, openWorkspace, test } from "./browser-fixture";

// File names of the inputs the recorded replies came from
// (real-data.json `inputs`). MOCK_MODE answers load_fasta and
// load_evolvepro_csv from the recording whatever the path, so these only keep
// the picker answers consistent with what the replies describe.
const GENBANK = "~/Documents/kuma/inputs/construct.gb";
const EVOLVEPRO_CSV = "~/Documents/kuma/inputs/df_test.csv";

declare global {
  interface Window {
    __mockDialogQueue?: { open?: Array<string | string[] | null>; save?: Array<string | null> };
  }
}

const STEPS = [
  ["Load Variants", 16],
  ["Mutations", 34],
  ["Primer Parameters", 52],
  ["Submit Design", 72],
  ["Summary", 84],
] as const;

// A step already passed is named "<step> done" (WorkflowRail.tsx aria-label).
const stepButton = (page: Page, name: string) =>
  page.getByRole("navigation", { name: "KURO Workflow" })
    .getByRole("button", { name: new RegExp(`^${name}( done)?$`) });

async function expectAt(page: Page, index: number) {
  const [name, percent] = STEPS[index];
  const rail = page.getByRole("navigation", { name: "KURO Workflow" });
  await expect(stepButton(page, name)).toHaveAttribute("aria-current", "step");
  await expect(rail.getByRole("progressbar")).toHaveAttribute("aria-valuenow", String(percent));
}

// Answer the next native file picker, then press the Browse button an operator
// presses. The store is filled by the app's own handler (scripts/stubs/dialog.ts).
async function browse(page: Page, path: string) {
  await page.evaluate((answer) => {
    window.__mockDialogQueue = { ...window.__mockDialogQueue, open: [answer] };
  }, path);
  await page.getByRole("main").getByRole("button", { name: "Browse", exact: true }).click();
}

test("KURO designs primers from browsed inputs through the rail to Summary", async ({ page }, testInfo) => {
  const shot = (name: string) => page.screenshot({ path: testInfo.outputPath(`${name}.png`), fullPage: true });
  const main = page.getByRole("main");
  const next = main.getByRole("button", { name: "Next", exact: true });

  await openWorkspace(page);
  await expectAt(page, 0);
  await expect(main.getByText("construct.gb")).toHaveCount(0);
  await shot("01-load-before");

  await browse(page, GENBANK);
  // Loading a sequence starts the UniProt lookup, which asks for consent to
  // call external services first. A fresh browser context has none stored.
  const consent = page.getByRole("dialog", { name: "External database consent" });
  await expect(consent).toBeVisible();
  await shot("02-load-consent");
  await consent.getByRole("button", { name: "Accept and continue" }).click();
  await expect(consent).toHaveCount(0);
  await expect(main.getByText("construct.gb", { exact: true })).toBeVisible();
  await expect(main.getByText(/\| 4 gene\(s\)$/)).toBeVisible();
  await shot("03-load-after");

  await next.click();
  await expectAt(page, 1);
  await expect(stepButton(page, "Load Variants")).toHaveAccessibleName("Load Variants done");
  await shot("04-mutations-before");

  await browse(page, EVOLVEPRO_CSV);
  // A table with no campaign round asks for one. "Not now" keeps the
  // round-driven defaults off, matching the recorded design_params.
  const round = page.getByRole("dialog", { name: "Set EVOLVEpro round" });
  await expect(round).toBeVisible();
  await round.getByRole("button", { name: "Not now" }).click();
  await expect(round).toHaveCount(0);
  await expect(main.getByText("df_test.csv", { exact: true })).toBeVisible();
  await expect(main.getByText(/^EVOLVEpro: \d+ variants loaded$/)).toBeVisible();
  await shot("05-mutations-after");

  await next.click();
  await expectAt(page, 2);
  await next.click();
  await expectAt(page, 3);
  await shot("06-submit-before");

  await expect(page.getByTestId("output-primer-panel")).toHaveCount(0);
  // The wizard footer's Next is also labelled "Run Design" on this step, so
  // take the primary button inside the run region (RunDesignAction.tsx).
  await main.getByRole("region", { name: "Run Design" })
    .getByRole("button", { name: "Run Design", exact: true }).click();
  // Pre-flight always warns that free disk space cannot be checked
  // (src/lib/preflight.ts), so every run passes through this dialog.
  const preflight = page.getByRole("alertdialog", { name: "Pre-flight check (warnings)" });
  await expect(preflight).toBeVisible();
  await shot("07-submit-preflight");
  await preflight.getByRole("button", { name: "Continue with warnings" }).click();
  await expectAt(page, 4);
  await expect(page.getByTestId("output-primer-panel")).toBeVisible();
  await expect(page.getByTestId("output-plate-panel")).toBeVisible();
  await shot("08-summary-after");
});
