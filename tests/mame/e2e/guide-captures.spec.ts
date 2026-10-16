import { mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import type { Locator, Page } from "@playwright/test";
import { expect, openWorkspace, test } from "./browser-fixture";

const root = resolve(process.cwd());
const samples = "src-tauri/samples";
type MameRecording = { readonly inputs: {
  readonly run_dir: string;
  readonly barcodes: string;
  readonly expected: string;
  readonly reference: string;
  readonly output_dir: string;
} };

// This file regenerates the tracked guide figures' inputs (docs/site/captures),
// so it runs only on request, never as part of the regular MAME e2e suite.
test.skip(!process.env.KUMA_GUIDE_CAPTURE, "Set KUMA_GUIDE_CAPTURE=1 to regenerate the user-guide captures");

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
    const mame: MameRecording =
      JSON.parse(readFileSync(resolve(root, "scripts/mame-real-data.json"), "utf8"));
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
    // A page can need more than one still: a control below the fold gets its own
    // shot, scrolled to the top of its panel, and numbering continues across the
    // shots of a page (and across later calls for the same page, e.g. a second
    // sub-screen), so the caption numbers always match the marks.
    const shotsOf = new Map<string, { shots: number; labels: number }>();
    const measure = (target: Target) => target.locator.evaluate((el) => {
      let r = el.getBoundingClientRect();
      const fullHeight = r.height;
      let left = r.left, top = r.top, right = r.right, bottom = r.bottom;
      // Height of the window the element is seen through (viewport cut by
      // every scrolling ancestor), so a tall table in a short panel can count.
      let panelTop = 0, panelBottom = window.innerHeight;
      // The middle panel scrolls on its own, so the box is clipped to every
      // scrolling ancestor as well as the viewport: a mark must cover what shows.
      for (let p = el.parentElement; p; p = p.parentElement) {
        const st = getComputedStyle(p);
        if (/(auto|scroll|hidden|clip)/.test(st.overflowY + st.overflowX)) {
          r = p.getBoundingClientRect();
          left = Math.max(left, r.left); top = Math.max(top, r.top);
          right = Math.min(right, r.right); bottom = Math.min(bottom, r.bottom);
          panelTop = Math.max(panelTop, r.top); panelBottom = Math.min(panelBottom, r.bottom);
        }
      }
      return { fullHeight, panelHeight: panelBottom - panelTop, left: Math.max(left, 0), top: Math.max(top, 0),
        right: Math.min(right, window.innerWidth), bottom: Math.min(bottom, window.innerHeight) };
    });
    const capture = async (slug: string, targets: readonly Target[]) => {
      // Transient toasts ("Design complete") would cover the header in a still.
      await page.addStyleTag({ content: "[data-sonner-toaster]{display:none !important}" });
      await expect(main).toBeVisible();
      await expect(page.getByText("Something went wrong.", { exact: true })).toHaveCount(0);
      await expect(page.locator("body")).not.toContainText("errorBoundary.");
      // A stale capture recording shows up as a rejected reply, not a crash.
      await expect(page.locator("body")).not.toContainText("Invalid RPC result shape");
      const out = resolve(root, "docs/site/captures", locale);
      mkdirSync(out, { recursive: true });
      if (!shotsOf.has(slug)) {
        // A page that now needs fewer shots must not keep the extra ones from an
        // earlier run: the site would publish them with clashing numbers.
        const extra = new RegExp(`^${slug}-\\d+\\.(png|regions\\.json)$`);
        for (const name of readdirSync(out)) if (extra.test(name)) rmSync(resolve(out, name));
      }
      const state = shotsOf.get(slug) ?? { shots: 0, labels: 0 };
      let pending = [...targets];
      while (pending.length > 0) {
        for (const target of pending) await expect(target.locator, `${slug}: ${target.selector}`).toBeVisible();
        // Lift the first unmarked control to the top of its panel so it, and as
        // many of the rest as fit, are in view for this shot.
        await pending[0].locator.evaluate((el) => {
          if (!(el instanceof HTMLElement)) throw new Error("Capture target must be an HTML element");
          // Leave room above so the label of the control stays in the shot, then
          // put the app style back so later clicks scroll as they normally do.
          const before = el.style.scrollMarginTop;
          el.style.scrollMarginTop = "56px";
          el.scrollIntoView({ block: "start" });
          el.style.scrollMarginTop = before;
        });
        const regions = [];
        const later: Target[] = [];
        for (const target of pending) {
          if (later.length > 0) {
            // Marks follow the help text order: once one control has to wait
            // for the next shot, everything after it waits too.
            later.push(target);
            continue;
          }
          const { fullHeight, panelHeight, left, top, right, bottom } = await measure(target);
          const shownHeight = bottom - top;
          // A sliver of a section is not a mark: most of it must show, or most
          // of the panel when the element is taller than the panel.
          const enough = right - left > 8 && shownHeight > 8
            // The 56 px left above for the label is not room the element can use.
            && shownHeight >= 0.85 * Math.min(fullHeight, panelHeight - 56);
          if (!enough) {
            later.push(target);
            continue;
          }
          state.labels += 1;
          regions.push({
            label: String(state.labels), ref: target.ref, role_or_testid: target.selector,
            bbox: [left / 1440, top / 900, (right - left) / 1440, (bottom - top) / 900],
          });
        }
        expect(regions.length, `${slug}: ${pending[0].selector} cannot be brought into view`).toBeGreaterThan(0);
        state.shots += 1;
        const name = state.shots === 1 ? slug : `${slug}-${state.shots}`;
        await page.screenshot({ path: resolve(out, `${name}.png`), fullPage: false, animations: "disabled" });
        writeFileSync(resolve(out, `${name}.regions.json`), JSON.stringify(regions, null, 2) + "\n");
        await testInfo.attach(`${name}-dom`, { body: await main.innerText(), contentType: "text/plain" });
        console.log(`CAPTURE ${locale}/${name} regions=${regions.length}`);
        pending = later;
      }
      shotsOf.set(slug, state);
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
      named(main.getByRole("button", { name: t("sequenceInput.browse"), exact: true }), `role=button[name="${t("sequenceInput.browse")}"]`, "`Browse`", "`찾아보기`"),
      named(main.getByRole("combobox").filter({ has: page.locator('option[value="60"]') }), 'role=combobox[has option[value="60"]]', "`Target Gene`", "`타겟 유전자`"),
      named(main.getByRole("combobox").filter({ has: page.locator('option[value="ecoli"]') }), 'role=combobox[has option[value="ecoli"]]', "`Organism`", "`생물체`"),
    ]);
    await next();
    await browseKuro(`${samples}/sample_evolvepro.csv`, "Browse");
    const round = page.getByRole("dialog");
    await expect(round).toBeVisible();
    await round.getByRole("button", { name: t("roundPrompt.dismissLabel"), exact: true }).click();
    await expect(round).toHaveCount(0);
    await expect(main.getByText("sample_evolvepro.csv", { exact: true })).toBeVisible();
    await capture("kuro-02-mutation", [
      named(main.getByRole("button", { name: "Browse", exact: true }), 'role=button[name="Browse"]', "`Browse` (prediction file)", "`Browse` (예측 파일)"),
      named(main.getByRole("spinbutton", { name: t("mutationInput.roundNumberAriaLabel") }), `role=spinbutton[name="${t("mutationInput.roundNumberAriaLabel")}"]`, "`Round` and `Size` under `Campaign round`", "`캠페인 라운드` 의 `라운드` 와 `크기`"),
      named(main.getByRole("combobox", { name: t("mutationInput.othersVariantColumn"), exact: true }), `role=combobox[name="${t("mutationInput.othersVariantColumn")}"]`, "`Mutation column`", "`Mutation column`"),
      named(main.getByRole("combobox", { name: t("mutationInput.othersScoreColumn"), exact: true }), `role=combobox[name="${t("mutationInput.othersScoreColumn")}"]`, "`Ranking column`", "`Ranking column`"),
      named(main.getByTestId("selection-mode"), "testid=selection-mode", "`Selection mode`", "`선택 방식`"),
      named(main.getByRole("table").filter({ has: page.getByRole("checkbox") }).first(), "role=table has checkbox", "Candidate table", "후보 표"),
    ]);
    await next();
    await main.getByRole("spinbutton").first().fill("24");
    await main.getByRole("spinbutton").first().blur();
    await capture("kuro-03-params", [
      named(main.locator("#design-strategy-select"), "#design-strategy-select", "`Strategy:`", "`전략:`"),
      named(main.locator("#polymerase-select"), "#polymerase-select", "`Polymerase:`", "`중합효소:`"),
      named(main.getByRole("spinbutton").first(), "main role=spinbutton first", "`Design count:`", "`설계 후보 수:`"),
      named(main.getByRole("button", { name: t("parameterPanel.advancedToggleShow"), exact: true }), `role=button[name="${t("parameterPanel.advancedToggleShow")}"]`, "`Advanced options`", "`고급 옵션`"),
    ]);
    await next();
    const run = main.getByRole("region", { name: t("phaseC.run.primary"), exact: true })
      .getByRole("button", { name: t("phaseC.run.primary"), exact: true });
    await capture("kuro-04-submit", [
      named(run, `role=region[name="${t("phaseC.run.primary")}"] role=button`, "`Run Design`", "`설계 실행`"),
    ]);
    await run.click();
    await expect(page.getByRole("alertdialog")).toBeVisible();
    await page.getByRole("alertdialog").getByRole("button").last().click();
    await expect(page.getByTestId("output-primer-panel")).toBeVisible();
    await capture("kuro-05-output", [
      named(page.getByTestId("output-primer-panel"), 'testid=output-primer-panel', "Statistics line and result table", "통계 한 줄과 결과 표"),
      named(page.getByTestId("output-plate-panel"), 'testid=output-plate-panel', "Plate map", "플레이트 맵"),
      named(page.getByTestId("selection3d-panel"), "testid=selection3d-panel", "`Candidate 3D structure analysis`", "`후보 3D 구조 분석`"),
    ]);
    await next();
    await main.locator("#project-name").fill("Synthetic_EGFP");
    await main.locator("#fwd-plate").fill("EGFP_FWD");
    await main.locator("#rvs-plate").fill("EGFP_REV");
    await capture("kuro-06-export", [
      named(main.locator("#project-name"), "#project-name", "`Export name`", "`내보내기 이름`"),
      named(main.locator("#fwd-plate"), "#fwd-plate", "`Forward primer plate name`", "`Forward 프라이머 플레이트 이름`"),
      named(main.locator("#rvs-plate"), "#rvs-plate", "`Reverse primer plate name`", "`Reverse 프라이머 플레이트 이름`"),
      named(main.locator("#amount"), "#amount", "Amount (0.05 or 0.2 μmole)", "합성량 (0.05 또는 0.2 μmole)"),
      named(main.locator("#echo-vol"), "#echo-vol", "`Echo transfer volume`", "`Echo 이송 부피`"),
      named(main.getByRole("radiogroup", { name: t("phaseC.export.all.quadrantLabel") }), `role=radiogroup[name="${t("phaseC.export.all.quadrantLabel")}"]`, "`Echo source plate quadrant`", "`Echo 소스 플레이트 사분면`"),
      named(main.locator("#janus-vol"), "#janus-vol", "`JANUS transfer volume`", "`JANUS 이송 부피`"),
      named(main.getByRole("button", { name: t("phaseC.export.all.runExport"), exact: true }), `role=button[name="${t("phaseC.export.all.runExport")}"]`, "`Export all`", "`전체 내보내기`"),
      named(main.getByTestId("export-plate-preview"), "testid=export-plate-preview", "Echo and JANUS mapping preview", "Echo·JANUS 매핑 미리보기"),
      named(main.getByRole("region", { name: t("phaseC.subSteps.export.summary"), exact: true }), `role=region[name="${t("phaseC.subSteps.export.summary")}"]`, "`Order summary`", "`주문 요약`"),
    ]);
    await page.getByRole("tab", { name: "Mame", exact: true }).click();
    await goMame("setup.files");
    await browseMame(`${samples}/sample_plasmid.gb`, "mame.barcodeSetup.cdsFasta");
    await browseMame(`${samples}/mame/02_mame_barcode_seeds.xlsx`, "mame.barcodeSetup.barcodeSeedsXlsx");
    await expect(main.locator("#cds-candidate")).toBeVisible();
    await capture("mame-01-setup", [
      named(main.locator('section[aria-labelledby="section-files"]'), "section-files", "**Input files**", "**입력 파일**"),
      named(main.locator("#cds-candidate"), "#cds-candidate", "**Gene coordinates**", "**유전자 좌표**"),
      named(main.locator("#gene-name"), "#gene-name", "Gene name", "유전자 이름"),
      named(main.locator("#polymerase"), "#polymerase", "Polymerase", "중합효소"),
      named(main.getByText(t("mame.barcodeSetup.advancedParameters"), { exact: true }).first(), "text=advancedParameters", "**Advanced options**", "**고급 옵션**"),
      named(main.locator('section[aria-labelledby="section-output-loc"]'), "section-output-loc", "**Output location**", "**출력 위치**"),
      named(main.getByRole("button", { name: t("mame.barcodeSetup.generateBarcodePackage"), exact: true }), "role=button[generateBarcodePackage]", "**Generate Barcode Package**", "**바코드 패키지 생성**"),
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
    await capture("mame-02-review", [
      named(main.getByRole("textbox", { name: t("mame.inputPanel.raw_run.label"), exact: true }), "textbox[raw_run]", "MinKNOW run folder", "MinKNOW 런 폴더"),
      named(main.getByRole("textbox", { name: t("mame.inputPanel.kuroXlsx.label"), exact: true }), "textbox[kuroXlsx]", "Expected variants (xlsx)", "기대 변이체 (xlsx)"),
      named(main.getByRole("textbox", { name: t("mame.inputPanel.referenceFasta.label"), exact: true }), "textbox[referenceFasta]", "Reference construct", "참조 컨스트럭트"),
      named(main.locator('section[aria-labelledby="mame-well-selection-heading"]'), "section-well-selection", "Wells used", "사용한 well"),
      named(main.getByRole("button", { name: t("mameSidebar.runBtn"), exact: true }), "role=button[runBtn]", "Run", "실행"),
    ]);
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
      named(main.getByRole("table").first(), "main role=table first", "Verdict table", "판정표"),
      named(main.getByRole("region", { name: t("mame.plateView.expandedRegionAriaLabel"), exact: true }), `role=region[name="${t("mame.plateView.expandedRegionAriaLabel")}"]`, "96-well plate map", "96-well 플레이트 맵"),
    ]);
    await goMame("janus.settings");
    await expect(main.getByRole("region", { name: t("mame.dialogs.janusMapping.previewHeading") })).toContainText("F28A");
    await capture("mame-03-janus", [
      named(main.getByRole("radiogroup", { name: t("mame.dialogs.janusMapping.destLayoutAriaLabel") }), `role=radiogroup[name="${t("mame.dialogs.janusMapping.destLayoutAriaLabel")}"]`, "**Destination layout**", "**대상 배치**"),
      named(main.locator("#janus-volume"), "#janus-volume", "Volume (µL)", "Volume (µL)"),
      named(main.locator("#janus-liquid-class"), "#janus-liquid-class", "Liquid class", "Liquid class"),
      named(main.locator("#janus-sample-type"), "#janus-sample-type", "type column value", "type 열 값"),
      named(main.getByRole("region", { name: t("mame.dialogs.janusMapping.previewHeading") }), "role=region[previewHeading]", "**Preview**", "**미리보기**"),
      named(main.getByText(new RegExp(`^${t("mame.dialogs.janusMapping.excludedHeading").split("{{count}}").map((part) => part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("\\d+")}$`)), "text=excludedHeading", "**Excluded**", "**제외**"),
      named(main.locator("#janus-output-path"), "#janus-output-path", "**Output file path**", "**출력 파일 경로**"),
      named(main.getByRole("button", { name: t("mame.dialogs.janusMapping.exportJanus"), exact: true }), "role=button[exportJanus]", "**Export Janus Mapping**", "**Janus 매핑 내보내기**"),
    ]);
    await goMame("activity.ingest");
    await answer(page, `${samples}/mame/15_mame_activity_variant.csv`);
    await main.getByRole("button", {
      name: t("mame.inputPanel.browseFolderAriaLabel").replace("{{label}}", t("mame.buildEvolvepro.measurementFile")), exact: true,
    }).click();
    await expect(main.locator("#bep-measurement")).toBeVisible();
    await capture("mame-04-activity", [
      named(main.getByText(t("mame.buildEvolvepro.measurementFile")).first().locator("xpath=ancestor::div[.//*[@id='bep-measurement']][1]"), "row containing #bep-measurement", "**Measurement file**", "**측정 파일**"),
      named(main.getByRole("radiogroup", { name: t("mame.buildEvolvepro.activityScale"), exact: true }), `role=radiogroup[name="${t("mame.buildEvolvepro.activityScale")}"]`, "Activity scale (raw or relative to WT)", "활성값 스케일 (raw 또는 WT 상대값)"),
      named(main.getByRole("radiogroup", { name: t("mame.buildEvolvepro.confirmationSourceLabel"), exact: true }), "role=radiogroup[confirmationSourceLabel]", "**Optional confirmation**", "**선택적 확인 측정**"),
      named(main.getByRole("textbox", { name: t("mame.buildEvolvepro.verdictXlsx"), exact: true }), "textbox[verdictXlsx]", "**NGS verdict xlsx**", "**NGS 판정 xlsx**"),
      named(main.locator('section[aria-labelledby="bep-output"]'), "section-bep-output", "**Output EVOLVEpro xlsx**", "**출력 EVOLVEpro xlsx**"),
      named(main.getByRole("button", { name: t("mame.buildEvolvepro.build"), exact: true }), "role=button[build]", "**Build EVOLVEpro input**", "**EVOLVEpro 입력 만들기**"),
    ]);
    await goMame("activity.signals");
    await capture("mame-04-activity", [
      named(main.getByRole("button").filter({ hasText: t("advisoryDecision.addFiles") }), "role=button hasText[addFiles]", "Per-round EVOLVEpro result xlsx files (4.2)", "라운드별 EVOLVEpro 결과 xlsx (4.2)"),
      named(main.getByRole("button").filter({ hasText: t("advisoryDecision.classify") }), "role=button hasText[classify]", "**Run classification** (4.2)", "**분류 실행** (4.2)"),
    ]);
  });
}
