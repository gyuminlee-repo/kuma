import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import type { Locator, Page } from "@playwright/test";
import { expect, openWorkspace, test } from "./browser-fixture";

const root = resolve(process.cwd());
const samples = "src-tauri/samples";
const mame: { readonly inputs: {
  readonly run_dir: string;
  readonly barcodes: string;
  readonly expected: string;
  readonly reference: string;
  readonly output_dir: string;
} } =
  JSON.parse(readFileSync(resolve(root, "scripts/mame-real-data.json"), "utf8"));

test.use({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });

type Target = {
  readonly ref: string;
  readonly selector: string;
  readonly locator: Locator;
};

async function answer(page: Page, path: string, kind: "open" | "save" = "open") {
  await page.evaluate(({ path, kind }) => {
    window.__mockDialogQueue = { ...window.__mockDialogQueue, [kind]: [path] };
  }, { path, kind });
}

for (const locale of ["en", "ko"] as const) {
  test(`public guide captures ${locale}`, async ({ page }, testInfo) => {
    test.setTimeout(300_000);
    const strings: unknown = JSON.parse(readFileSync(resolve(root, `src/locales/${locale}.json`), "utf8"));
    const t = (key: string): string => {
      const value = key.split(".").reduce<unknown>((node, part) => {
        if (typeof node !== "object" || node === null) throw new Error(`Missing translation ${key}`);
        return Object.entries(node).find(([name]) => name === part)?.[1];
      }, strings);
      if (typeof value !== "string") throw new Error(`Missing translation ${key}`);
      return value;
    };
    const main = page.getByRole("main");
    const named = (locator: Locator, selector: string, en: string, ko: string): Target =>
      ({ locator, selector, ref: locale === "en" ? en : ko });
    const capture = async (slug: string, targets: readonly Target[]) => {
      // Transient toasts ("Design complete") would cover the header in a still.
      await page.addStyleTag({ content: "[data-sonner-toaster]{display:none !important}" });
      await expect(main).toBeVisible();
      await expect(page.getByText("Something went wrong.", { exact: true })).toHaveCount(0);
      await expect(page.locator("body")).not.toContainText("errorBoundary.");
      const regions = [];
      // Lift the first mark to the top of its scrolling panel so the rest get the most room.
      await targets[0].locator.evaluate((el) => el.scrollIntoView({ block: "start" }));
      for (const target of targets) {
        await expect(target.locator).toBeVisible();
        // The middle panel scrolls on its own, so the box is clipped to every
        // scrolling ancestor as well as the viewport: a mark must cover what shows.
        const shown = await target.locator.evaluate((el) => {
          let r = el.getBoundingClientRect();
          let left = r.left, top = r.top, right = r.right, bottom = r.bottom;
          for (let p = el.parentElement; p; p = p.parentElement) {
            const st = getComputedStyle(p);
            if (/(auto|scroll|hidden|clip)/.test(st.overflowY + st.overflowX)) {
              r = p.getBoundingClientRect();
              left = Math.max(left, r.left); top = Math.max(top, r.top);
              right = Math.min(right, r.right); bottom = Math.min(bottom, r.bottom);
            }
          }
          return { left: Math.max(left, 0), top: Math.max(top, 0),
            right: Math.min(right, window.innerWidth), bottom: Math.min(bottom, window.innerHeight) };
        });
        const { left, top, right, bottom } = shown;
        if (right - left <= 8 || bottom - top <= 8) {
          console.log(`SKIP ${locale}/${slug} ${target.selector}: outside the visible panel`);
          continue;
        }
        regions.push({
          label: String(regions.length + 1), ref: target.ref, role_or_testid: target.selector,
          bbox: [left / 1440, top / 900, (right - left) / 1440, (bottom - top) / 900],
        });
      }
      expect(regions.length, `${slug}: no mark is visible`).toBeGreaterThan(0);
      const out = resolve(root, "docs/site/captures", locale);
      mkdirSync(out, { recursive: true });
      await page.screenshot({ path: resolve(out, `${slug}.png`), fullPage: false, animations: "disabled" });
      writeFileSync(resolve(out, `${slug}.regions.json`), JSON.stringify(regions, null, 2) + "\n");
      await testInfo.attach(`${slug}-dom`, {
        body: await main.innerText(), contentType: "text/plain",
      });
      console.log(`CAPTURE ${locale}/${slug} regions=${regions.length}`);
    };
    const next = () => main.getByRole("button", { name: t("phaseE.wizard.next"), exact: true }).click();
    const browseKuro = async (path: string, name: string) => {
      await answer(page, path);
      await main.getByRole("button", { name, exact: true }).click();
    };
    const mameRail = () => page.getByRole("navigation", { name: t("mame.setup.files.railTitle") });
    const goMame = async (id: string) => {
      const name = t(`phaseC.mameSubSteps.${id}`);
      await mameRail().getByRole("button", { name: new RegExp(`^${name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?: .*)?$`) }).click();
    };
    const browseMame = async (path: string, key: string) => {
      await answer(page, path);
      const name = t("mame.inputPanel.browseFolderAriaLabel").replace("{{label}}", t(key));
      await page.getByRole("button", { name, exact: true }).click();
    };
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.addInitScript((locale) => {
      localStorage.setItem("kuma:locale", locale);
      localStorage.setItem("kuma.onboarding.maximizeShown", "1");
      localStorage.setItem("kuma:autosave-intro-shown", "1");
    }, locale);
    // Captures show the app as a user who declined external lookups sees it:
    // no InterPro, ESMFold or UniProt call, so nothing unrecorded is attempted.
    await page.addLocatorHandler(
      page.getByRole("dialog", { name: t("networkConsent.title") }),
      async (dialog) => {
        await dialog.getByRole("button", { name: t("networkConsent.btnCancel"), exact: true }).click();
      },
    );
    await openWorkspace(page);
    await browseKuro(`${samples}/sample_plasmid.gb`, t("sequenceInput.browse"));
    await expect(main.getByText("sample_plasmid.gb", { exact: true })).toBeVisible();
    await expect(main.getByText(/pSampleKURO_EGFP/)).toBeVisible();
    await expect(main.getByRole("button", { name: t("phaseE.wizard.next"), exact: true })).toBeEnabled();
    await capture("kuro-01-load", [
      named(main.getByRole("button", { name: t("sequenceInput.browse"), exact: true }), `role=button[name="${t("sequenceInput.browse")}"]`, "Press `Browse`", "`찾아보기` 를 누르거나"),
      named(main.getByRole("combobox").filter({ has: page.locator('option[value="60"]') }), 'role=combobox[has option[value="60"]]', "Pick the target CDS under `Target Gene`", "`타겟 유전자` 에서 설계 대상 CDS 를 고른다."),
      named(main.getByRole("combobox").filter({ has: page.locator('option[value="ecoli"]') }), 'role=combobox[has option[value="ecoli"]]', "Check `Organism`", "`생물체` 에서 코돈 사용 빈도표를 확인한다."),
    ]);
    await next();
    await browseKuro(`${samples}/sample_evolvepro.csv`, "Browse");
    const round = page.getByRole("dialog");
    await expect(round).toBeVisible();
    await round.getByRole("button", { name: t("roundPrompt.dismissLabel"), exact: true }).click();
    await expect(round).toHaveCount(0);
    await expect(main.getByText("sample_evolvepro.csv", { exact: true })).toBeVisible();
    await capture("kuro-02-mutation", [
      named(main.getByRole("button", { name: "Browse", exact: true }), 'role=button[name="Browse"]', "Press `Browse` and pick the prediction file.", "`Browse` 로 예측 파일을 고른다."),
      named(main.getByRole("spinbutton", { name: t("mutationInput.roundNumberAriaLabel") }), `role=spinbutton[name="${t("mutationInput.roundNumberAriaLabel")}"]`, "Check `Round` and `Size` under `Campaign round`.", "`캠페인 라운드` 에서 `라운드` 번호와 `크기` 를 확인한다."),
      named(main.getByRole("combobox", { name: t("mutationInput.othersVariantColumn"), exact: true }), `role=combobox[name="${t("mutationInput.othersVariantColumn")}"]`, "Confirm `Mutation column`", "`Mutation column` 과 `Ranking column` 이 제대로 잡혔는지 본다."),
      named(main.getByRole("combobox", { name: t("mutationInput.othersScoreColumn"), exact: true }), `role=combobox[name="${t("mutationInput.othersScoreColumn")}"]`, "and `Ranking column` under `Column mapping`.", "`Column 매핑` 에서"),
    ]);
    await next();
    await main.getByRole("spinbutton").first().fill("24");
    await main.getByRole("spinbutton").first().blur();
    await capture("kuro-03-params", [
      named(main.locator("#design-strategy-select"), "#design-strategy-select", "`Strategy:`", "`전략:`"),
      named(main.locator("#polymerase-select"), "#polymerase-select", "`Polymerase:`", "`중합효소:`"),
      named(main.getByRole("spinbutton").first(), "main role=spinbutton first", "`Design count:`", "`설계 후보 수:`"),
      named(main.getByRole("button", { name: t("parameterPanel.advancedToggleShow"), exact: true }), `role=button[name="${t("parameterPanel.advancedToggleShow")}"]`, "Expand `Advanced options`", "`고급 옵션` 을 펼치면"),
    ]);
    await next();
    const run = main.getByRole("region", { name: t("phaseC.run.primary"), exact: true })
      .getByRole("button", { name: t("phaseC.run.primary"), exact: true });
    await capture("kuro-04-submit", [
      named(run, `role=region[name="${t("phaseC.run.primary")}"] role=button`, "Click `Run Design`.", "`설계 실행` 을 누른다."),
    ]);
    await run.click();
    await expect(page.getByRole("alertdialog")).toBeVisible();
    await page.getByRole("alertdialog").getByRole("button").last().click();
    await expect(page.getByTestId("output-primer-panel")).toBeVisible();
    await capture("kuro-05-output", [
      named(page.getByTestId("output-primer-panel"), 'testid=output-primer-panel', "The left side holds a statistics line, the result table", "왼쪽은 통계 한 줄과 결과 표"),
      named(page.getByTestId("output-plate-panel"), 'testid=output-plate-panel', "The right side holds the plate map.", "오른쪽은 플레이트 맵이다."),
    ]);
    await next();
    await main.locator("#project-name").fill("Synthetic_EGFP");
    await main.locator("#fwd-plate").fill("EGFP_FWD");
    await main.locator("#rvs-plate").fill("EGFP_REV");
    await main.locator("#project-name").evaluate((el) => el.scrollIntoView({ block: "start" }));
    await capture("kuro-06-export", [
      named(main.locator("#project-name"), "#project-name", "`Export name` sets the folder name", "`내보내기 이름`, 폴더 이름과 파일 앞머리가 된다."),
      named(main.locator("#fwd-plate"), "#fwd-plate", "`Forward primer plate name`", "`Forward 프라이머 플레이트 이름`"),
      named(main.locator("#rvs-plate"), "#rvs-plate", "and `Reverse primer plate name`", "`Reverse 프라이머 플레이트 이름`"),
      named(main.locator("#amount"), "#amount", "Choose 0.05 or 0.2 μmole for the amount.", "합성량은 0.05 또는 0.2 μmole 중 고르고"),
    ]);
    await page.getByRole("tab", { name: "Mame", exact: true }).click();
    await goMame("setup.files");
    await browseMame(`${samples}/sample_plasmid.gb`, "mame.barcodeSetup.cdsFasta");
    await browseMame(`${samples}/mame/02_mame_barcode_seeds.xlsx`, "mame.barcodeSetup.barcodeSeedsXlsx");
    await expect(main.locator("#cds-candidate")).toBeVisible();
    await main.locator("#polymerase").scrollIntoViewIfNeeded();
    await capture("mame-01-setup", [
      named(main.locator("#cds-candidate"), "#cds-candidate", "Check **Gene coordinates**.", "**유전자 좌표** 를 확인한다."),
      named(main.locator("#gene-name"), "#gene-name", "enter the gene name", "유전자 이름을 넣고"),
      named(main.locator("#polymerase"), "#polymerase", "and pick a polymerase.", "중합효소를 고른다."),
    ]);
    await goMame("analyze.inputs");
    await browseMame(mame.inputs.run_dir, "mame.inputPanel.raw_run.label");
    await browseMame(mame.inputs.barcodes, "mame.inputPanel.customBarcodes.label");
    await browseMame(mame.inputs.expected, "mame.inputPanel.kuroXlsx.label");
    await browseMame(mame.inputs.reference, "mame.inputPanel.referenceFasta.label");
    await answer(page, mame.inputs.output_dir);
    await page.getByRole("button", {
      name: t("mame.inputPanel.browseFolderAriaLabel").replace("{{label}}", t("mame.inputPanel.exportDest.label")),
      exact: true,
    }).click();
    await main.getByRole("button", { name: t("mameSidebar.runBtn"), exact: true }).click();
    await expect(page.getByRole("alertdialog")).toBeVisible();
    await page.getByRole("alertdialog").getByRole("button").last().click();
    // The public fixture has one native barcode, so Run does not ask for a
    // replicate selection. Its completion popup is the bounded finish signal.
    await expect(page.getByTestId("analyze-duration-dialog")).toBeVisible({ timeout: 120_000 });
    await page.getByTestId("analyze-duration-dialog")
      .getByRole("button", { name: t("common.close"), exact: true }).click();
    await goMame("analyze.review");
    await expect(main.getByText("F28A", { exact: true }).first()).toBeVisible({ timeout: 120_000 });
    await capture("mame-02-review", [
      named(main.getByRole("table").first(), "main role=table first", "The verdict table sits on the left.", "왼쪽에 판정표"),
      named(main.getByRole("region", { name: t("mame.plateView.expandedRegionAriaLabel"), exact: true }), `role=region[name="${t("mame.plateView.expandedRegionAriaLabel")}"]`, "The 96-well plate map", "오른쪽에 96-well 플레이트 맵"),
    ]);
    await goMame("janus.settings");
    await expect(main.getByRole("region", { name: t("mame.dialogs.janusMapping.previewHeading") })).toContainText("F28A");
    await main.getByRole("radiogroup", { name: t("mame.dialogs.janusMapping.destLayoutAriaLabel") }).evaluate((el) => el.scrollIntoView({ block: "start" }));
    await capture("mame-03-janus", [
      named(main.getByRole("radiogroup", { name: t("mame.dialogs.janusMapping.destLayoutAriaLabel") }), `role=radiogroup[name="${t("mame.dialogs.janusMapping.destLayoutAriaLabel")}"]`, "Pick a **Destination layout**.", "**대상 배치** 를 고른다."),
      named(main.locator("#janus-volume"), "#janus-volume", "enter Volume (µL)", "Volume (µL)"),
      named(main.locator("#janus-liquid-class"), "#janus-liquid-class", "Liquid class", "Liquid class"),
      named(main.locator("#janus-sample-type"), "#janus-sample-type", "and the type column value.", "type 열 값을 넣는다."),
    ]);
    await goMame("activity.ingest");
    await answer(page, `${samples}/mame/15_mame_activity_variant.csv`);
    await main.getByRole("button", {
      name: t("mame.inputPanel.browseFolderAriaLabel").replace("{{label}}", t("mame.buildEvolvepro.measurementFile")), exact: true,
    }).click();
    await expect(main.locator("#bep-measurement")).toBeVisible();
    await capture("mame-04-activity", [
      named(main.locator("#bep-measurement"), "#bep-measurement", "Choose the **Measurement file**.", "**측정 파일**을 고른다."),
      named(main.getByRole("radiogroup", { name: t("mame.buildEvolvepro.activityScale"), exact: true }), `role=radiogroup[name="${t("mame.buildEvolvepro.activityScale")}"]`, "Activity scale selects raw or relative to WT", "활성값 스케일에서 raw 또는 WT 상대값을 고른다"),
    ]);
  });
}
