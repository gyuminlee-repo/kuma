# EVOLVEpro Checklist Closure Plan

## TL;DR
> Summary:      Close the EVOLVEpro checklist by separating existing minimal GUI evidence from the still-required real Windows GUI QA for `sispS(P.t).fa` + `IspS_round1_Ep.xlsx`. MAME section 6 stays out of scope and must not be marked complete here.
> Deliverables:
> - `evidence/task-1-checklist-scope.md`
> - `evidence/task-2-sidecar-ready.txt` plus build/hash logs
> - `evidence/task-3-contract-tests.txt`
> - `evidence/task-4-minimal-gui.*`
> - `evidence/task-5-real-sisps-run.*`
> - `evidence/task-6-cache-second-run.*`
> - `evidence/task-7-dna-guard.*`
> - `evidence/task-8-cancel-persistence.*`
> - `evidence/task-9-checklist-disposition.md`
> Effort:       Medium
> Risk:         Medium - real ESM-2 GUI run is long-running and Windows/conda/cache state can be stale.

## Scope
### Must have
- Verify checklist sections 0-5 from `/mnt/d/_workspace/cc/obsidian/010.KRIBB/010.Projects/010.프라이머_설계_툴/kuma/260602_EVOLVEpro_확인체크리스트.md:18`.
- Treat existing minimal GUI success as useful regression evidence only: `.omo/ulw-loop/evidence/evolvepro-happy-result.md:91` shows completion, `.omo/ulw-loop/evidence/evolvepro-happy-result.md:99` shows `batch 1/1`, and `.omo/ulw-loop/evidence/evolvepro-happy-result.md:107` shows the result card.
- Run real Windows GUI QA using:
  - WT FASTA: `D:\_workspace\020.admin\projects\060.nanopore_NGS\sispS(P.t).fa`
  - Round file: `D:\_workspace\020.admin\projects\060.nanopore_NGS\NGS_260212\IspS_round1_Ep.xlsx`
- Confirm the FASTA normalized protein sequence is 560 aa and expected EVOLVEpro variant count is 10,641.
- Capture progress, result card, cache second-run, DNA guard, cancel behavior, form persistence, and result interpretation as files under `evidence/`.
- Leave a final disposition report mapping every EVOLVEpro checklist checkbox to PASS, FAIL, or BLOCKED with evidence paths.

### Must NOT have (guardrails, anti-slop, scope boundaries)
- Do not edit product code as part of this closure plan.
- Do not mark MAME section 6 as complete; it is a separate MAME 78-FASTQ GUI QA scope.
- Do not claim the real `N/1521` progress item is satisfied from the minimal `batch 1/1` run.
- Do not rely on WebView cache files under `.omo/ulw-loop/qa/webview2-profile*/` as evidence.
- Do not treat app restart as EVOLVEpro run-state persistence; `src-tauri/src/lib.rs:18` says ProgressCache is in-memory and cleared on app restart.
- Do not hardcode a 100% identity/result claim; use generated output files and backend-returned counts.

## Verification strategy
> Zero human intervention - all verification is agent-executed.
- Test decision: tests-after + pytest, vitest, TypeScript typecheck, sync check, Playwright-over-CDP GUI QA
- QA policy: every task has agent-executed scenarios
- Evidence: `evidence/task-<N>-<slug>.<ext>`

## Execution strategy
### Parallel execution waves
> Target 5-8 tasks per wave. <3 per wave (except final) = under-splitting.
> Extract shared dependencies as Wave-1 tasks to maximize parallelism.

Wave 1 (no dependencies):
- Task 1: Scope/data/evidence baseline
- Task 2: Windows sidecar/app readiness
- Task 3: Automated EVOLVEpro contract regression

Wave 2 (after Wave 1):
- Task 4: depends [2, 3] - minimal deterministic GUI regression
- Task 5: depends [1, 2, 3] - real `sispS(P.t).fa` first GUI run
- Task 6: depends [5] - same-input cache second run
- Task 7: depends [2, 3] - DNA FASTA guard
- Task 8: depends [2, 3] - cancel, refresh, tab-persistence, console warning QA

Wave 3 (after Wave 2):
- Task 9: depends [1, 2, 3, 4, 5, 6, 7, 8] - final checklist disposition report

Critical path: Task 1 -> Task 2 -> Task 5 -> Task 6 -> Task 9

### Dependency matrix
| Task | Depends on | Blocks | Can parallelize with |
|------|------------|--------|----------------------|
| 1    | none       | 5, 9   | 2, 3                 |
| 2    | none       | 4, 5, 6, 7, 8, 9 | 1, 3 |
| 3    | none       | 4, 5, 7, 8, 9 | 1, 2 |
| 4    | 2, 3       | 9      | none; shared GUI app |
| 5    | 1, 2, 3    | 6, 9   | none; shared GUI app |
| 6    | 5          | 9      | none; reuses Task 5 cache |
| 7    | 2, 3       | 9      | none; shared GUI app |
| 8    | 2, 3       | 9      | none; shared GUI app |
| 9    | 1-8        | final  | none                 |

## Todos
> Implementation + Test = ONE task. Never separate.
> Every task MUST have: References + Acceptance Criteria + QA Scenarios + Commit.

- [ ] 1. Scope/data/evidence baseline

  What to do: Create a baseline report that identifies which checklist items already have credible minimal-run evidence and which require real QA. Record branch/status, latest EVOLVEpro commits, checklist lines, real data paths, hashes, FASTA-derived variant count, and the existing minimal GUI evidence.
  Must NOT do: Do not update the Obsidian checklist; do not mark MAME items.

  Parallelization: Can parallel: YES | Wave 1 | Blocks: [5, 9] | Blocked by: []

  References (executor has NO interview context - be exhaustive):
  - Pattern:  `.omo/ulw-loop/evidence/evolvepro-happy-result.md:91` - existing minimal GUI completion and `1/1 (100%)`.
  - Pattern:  `.omo/ulw-loop/evidence/evolvepro-happy-result.md:99` - existing minimal batch progress and throughput/ETA message.
  - Pattern:  `.omo/ulw-loop/evidence/evolvepro-happy-result.md:107` - existing minimal result card output path and counts.
  - Pattern:  `.omo/ulw-loop/evidence/evolvepro-gui-action-log.json:37` - existing minimal GUI action log captures progress samples and output files.
  - Pattern:  `/mnt/d/_workspace/cc/obsidian/010.KRIBB/010.Projects/010.프라이머_설계_툴/kuma/260602_EVOLVEpro_확인체크리스트.md:22` - checklist states real GUI confirmation remains.
  - Pattern:  `/mnt/d/_workspace/cc/obsidian/010.KRIBB/010.Projects/010.프라이머_설계_툴/kuma/260602_EVOLVEpro_확인체크리스트.md:33` - real `sispS(P.t).fa` + round1 progress requirement.
  - Pattern:  `src-tauri/src/lib.rs:18` - ProgressCache is reload-only, not app-restart persistence.
  - External: `https://playwright.dev/docs/screenshots` - screenshot evidence API.

  Acceptance criteria (agent-executable only):
  - [ ] `test -f evidence/task-1-checklist-scope.md`
  - [ ] `grep -F "variants: 10641" evidence/task-1-checklist-scope.md`
  - [ ] `grep -F "MAME section 6: OUT_OF_SCOPE" evidence/task-1-checklist-scope.md`
  - [ ] `grep -F "minimal GUI evidence: PRESENT" evidence/task-1-checklist-scope.md`

  QA scenarios (MANDATORY - task incomplete without these):
  > Name the exact tool AND its exact invocation - not "verify it works". Browser use: use Chrome to drive the page; if Chrome is not available, download and use agent-browser (https://github.com/vercel-labs/agent-browser). Computer use: OS-level GUI automation for a non-browser desktop app.
  ```
  Scenario: baseline report creation
    Tool:     bash
    Steps:    cd /mnt/d/_workspace/cc/kuma && mkdir -p evidence && { echo "# EVOLVEpro checklist baseline"; echo "## Git"; git branch --show-current; git status --short; git log --oneline -5; echo "## Checklist"; nl -ba /mnt/d/_workspace/cc/obsidian/010.KRIBB/010.Projects/010.프라이머_설계_툴/kuma/260602_EVOLVEpro_확인체크리스트.md | sed -n '18,105p'; echo "## Real inputs"; ls -lh '/mnt/d/_workspace/020.admin/projects/060.nanopore_NGS/sispS(P.t).fa' '/mnt/d/_workspace/020.admin/projects/060.nanopore_NGS/NGS_260212/IspS_round1_Ep.xlsx'; sha256sum '/mnt/d/_workspace/020.admin/projects/060.nanopore_NGS/sispS(P.t).fa' '/mnt/d/_workspace/020.admin/projects/060.nanopore_NGS/NGS_260212/IspS_round1_Ep.xlsx'; python3 - <<'PY'
from pathlib import Path
seq=''.join(line.strip() for line in Path('/mnt/d/_workspace/020.admin/projects/060.nanopore_NGS/sispS(P.t).fa').read_text().splitlines() if not line.startswith('>')).rstrip('*').upper()
valid=sum(1 for c in seq if c in 'ACDEFGHIKLMNPQRSTVWY')
print(f"normalized_len: {len(seq)}")
print(f"valid_aa: {valid}")
print(f"variants: {1 + valid * 19}")
PY
echo "## Existing minimal GUI evidence"; nl -ba .omo/ulw-loop/evidence/evolvepro-happy-result.md | sed -n '91,112p'; nl -ba .omo/ulw-loop/evidence/evolvepro-gui-action-log.json | sed -n '37,66p'; file .omo/ulw-loop/evidence/evolvepro-before-run.png .omo/ulw-loop/evidence/evolvepro-happy-result.png; echo "minimal GUI evidence: PRESENT"; echo "MAME section 6: OUT_OF_SCOPE"; } | tee evidence/task-1-checklist-scope.md
    Expected: evidence file exists, contains branch/status, both real input paths, both SHA-256 hashes, `variants: 10641`, and `MAME section 6: OUT_OF_SCOPE`.
    Evidence: evidence/task-1-checklist-scope.md

  Scenario: missing real input data blocks real QA
    Tool:     bash
    Steps:    cd /mnt/d/_workspace/cc/kuma && { test -f '/mnt/d/_workspace/020.admin/projects/060.nanopore_NGS/sispS(P.t).fa' && test -f '/mnt/d/_workspace/020.admin/projects/060.nanopore_NGS/NGS_260212/IspS_round1_Ep.xlsx'; } || { echo "BLOCKED: real EVOLVEpro input missing" | tee evidence/task-1-checklist-scope-missing.txt; exit 1; }
    Expected: command exits 0; if not, `evidence/task-1-checklist-scope-missing.txt` contains the blocking condition.
    Evidence: evidence/task-1-checklist-scope-missing.txt
  ```

  Commit: NO | Message: `test(evolvepro): capture checklist scope baseline` | Files: [evidence/task-1-checklist-scope.md]

- [ ] 2. Windows sidecar/app readiness

  What to do: Ensure the Windows app uses a freshly rebuilt EVOLVEpro sidecar and that CDP remote debugging is available for GUI automation.
  Must NOT do: Do not rebuild MAME sidecar or alter unrelated sidecar hashes except those produced by the EVOLVEpro build/hash flow.

  Parallelization: Can parallel: YES | Wave 1 | Blocks: [4, 5, 6, 7, 8, 9] | Blocked by: []

  References (executor has NO interview context - be exhaustive):
  - Pattern:  `package.json:14` - `sidecar:build` and `sidecar:hash` scripts.
  - Pattern:  `python-core/AGENTS.md:44` - sidecar verification commands include build and model generation checks.
  - Pattern:  `python-core/sidecar_evolvepro/dispatcher.py:106` - EVOLVEpro RPC registry includes run/cancel/cache/result methods.
  - Pattern:  `src-tauri/src/sidecar.rs:464` - EVOLVEpro progress feeds ProgressCache and emits `sidecar://progress`.
  - External: `https://v2.tauri.app/reference/cli/` - Tauri `tauri dev` command reference.

  Acceptance criteria (agent-executable only):
  - [ ] `grep -F "evolvepro-sidecar" evidence/task-2-sidecar-ready.txt`
  - [ ] `grep -F "sidecar-hash" evidence/task-2-sidecar-hash.log`
  - [ ] `curl -sf http://127.0.0.1:9223/json/version > evidence/task-2-cdp-version.json`

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: rebuild EVOLVEpro sidecar and expose CDP
    Tool:     bash
    Steps:    cd /mnt/d/_workspace/cc/kuma && mkdir -p evidence && powershell.exe -NoProfile -ExecutionPolicy Bypass -Command 'Set-Location D:\_workspace\cc\kuma; Get-Process kuma -ErrorAction SilentlyContinue | Stop-Process -Force; pnpm run sidecar:kill 2>&1 | Tee-Object evidence\task-2-sidecar-kill.log; $py = if (Test-Path .\.venv\Scripts\python.exe) { ".\.venv\Scripts\python.exe" } else { "python" }; & $py python-core\build_sidecar.py --target evolvepro 2>&1 | Tee-Object evidence\task-2-sidecar-build.log; pnpm run sidecar:hash 2>&1 | Tee-Object evidence\task-2-sidecar-hash.log; Get-Item src-tauri\binaries\evolvepro-sidecar-x86_64-pc-windows-msvc.exe | Format-List FullName,Length,LastWriteTime | Tee-Object evidence\task-2-sidecar-ready.txt'
    Expected: PowerShell exits 0; sidecar ready file lists the Windows EVOLVEpro sidecar exe with non-zero Length.
    Evidence: evidence/task-2-sidecar-ready.txt

  Scenario: stale sidecar/app process is not left running
    Tool:     bash
    Steps:    cd /mnt/d/_workspace/cc/kuma && tmux kill-session -t kuma-evp-dev 2>/dev/null || true && tmux new-session -d -s kuma-evp-dev "cd /mnt/d/_workspace/cc/kuma && powershell.exe -NoProfile -Command 'Set-Location D:\_workspace\cc\kuma; \$env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=\"--remote-debugging-port=9223\"; pnpm tauri dev' 2>&1 | tee evidence/task-2-tauri-dev.log" && for i in $(seq 1 90); do curl -sf http://127.0.0.1:9223/json/version > evidence/task-2-cdp-version.json && exit 0; sleep 2; done; echo "CDP endpoint did not become available" | tee evidence/task-2-sidecar-stale.txt; exit 1
    Expected: `evidence/task-2-cdp-version.json` contains a CDP JSON object and no stale process blocker is written.
    Evidence: evidence/task-2-cdp-version.json
  ```

  Commit: NO | Message: `test(evolvepro): verify windows sidecar readiness` | Files: [evidence/task-2-sidecar-ready.txt, evidence/task-2-sidecar-build.log, evidence/task-2-sidecar-hash.log]

- [ ] 3. Automated EVOLVEpro contract regression

  What to do: Run focused EVOLVEpro backend, cache, sidecar packaging, and store tests plus type/sync checks. This proves the progress/result/cache contracts before GUI QA.
  Must NOT do: Do not broaden to full MAME 502-test suite unless a focused check fails in a MAME-shared contract.

  Parallelization: Can parallel: YES | Wave 1 | Blocks: [4, 5, 7, 8, 9] | Blocked by: []

  References (executor has NO interview context - be exhaustive):
  - Test:     `tests/AGENTS.md:33` - EVOLVEpro focused test family.
  - Test:     `tests/test_evolvepro_run_result.py:106` - embedding batch progress parses `batch current/total`, throughput, and ETA.
  - Test:     `tests/test_evolvepro_run_result.py:140` - done progress includes result only on terminal success.
  - Test:     `tests/test_evolvepro_embedding_cache.py:91` - cache metadata JSON is written.
  - Test:     `src/store/evolvepro/evolveProStore.test.ts:88` - progress log remains visible after done.
  - API/Type: `python-core/sidecar_evolvepro/models.py:100` - progress stage includes `embedding`.
  - Test:     `vitest.config.ts:19` - Vitest environment and include/exclude rules.

  Acceptance criteria (agent-executable only):
  - [ ] `grep -E "passed|PASS" evidence/task-3-contract-tests.txt`
  - [ ] `grep -F "tests/test_evolvepro_run_result.py" evidence/task-3-contract-tests.txt`
  - [ ] `grep -F "evolveProStore.test.ts" evidence/task-3-contract-tests.txt`
  - [ ] `grep -F "tsc --noEmit: PASS" evidence/task-3-contract-tests.txt`
  - [ ] `grep -F "sync:check: PASS" evidence/task-3-contract-tests.txt`

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: focused contracts pass
    Tool:     bash
    Steps:    cd /mnt/d/_workspace/cc/kuma && mkdir -p evidence && PYTHON_BIN="${PYTHON_BIN:-$(test -x .venv/bin/python && echo .venv/bin/python || echo python3)}" && { "$PYTHON_BIN" -m pytest tests/test_evolvepro_run_result.py tests/test_evolvepro_embedding_cache.py tests/test_evolvepro_adapter_cache.py tests/test_evolvepro_sidecar_packaging.py -v && echo "pytest: PASS"; pnpm exec vitest run src/store/evolvepro/evolveProStore.test.ts && echo "evolveProStore.test.ts: PASS"; npx tsc --noEmit && echo "tsc --noEmit: PASS"; pnpm sync:check && echo "sync:check: PASS"; } 2>&1 | tee evidence/task-3-contract-tests.txt
    Expected: all commands exit 0 and PASS markers appear.
    Evidence: evidence/task-3-contract-tests.txt

  Scenario: contract failure is captured instead of hidden
    Tool:     bash
    Steps:    cd /mnt/d/_workspace/cc/kuma && test -s evidence/task-3-contract-tests.txt && ! grep -E "FAILED|FAILURES|error TS|sync.*FAIL" evidence/task-3-contract-tests.txt || { grep -E "FAILED|FAILURES|error TS|sync.*FAIL" evidence/task-3-contract-tests.txt | tee evidence/task-3-contract-tests-fail.txt; exit 1; }
    Expected: command exits 0; if not, failure lines are preserved.
    Evidence: evidence/task-3-contract-tests-fail.txt
  ```

  Commit: NO | Message: `test(evolvepro): run focused contract regression` | Files: [evidence/task-3-contract-tests.txt]

- [ ] 4. Minimal deterministic GUI regression

  What to do: Re-run the existing minimal EVOLVEpro GUI QA against the current app/sidecar. This confirms the small deterministic path still shows adapter progress, result card, and output files.
  Must NOT do: Do not use this task to close the real `N/1521` checklist item.

  Parallelization: Can parallel: NO | Wave 2 | Blocks: [9] | Blocked by: [2, 3]

  References (executor has NO interview context - be exhaustive):
  - Pattern:  `.omo/ulw-loop/qa/run_gui_evolvepro_actual.mjs:1` - existing Playwright CDP GUI runner.
  - Pattern:  `.omo/ulw-loop/qa/run_gui_evolvepro_actual.mjs:83` - captures before-run screenshot.
  - Pattern:  `.omo/ulw-loop/qa/run_gui_evolvepro_actual.mjs:134` - captures final body and screenshot.
  - Pattern:  `.omo/ulw-loop/qa/run_gui_evolvepro_actual.mjs:151` - verifies required output files.
  - Pattern:  `.omo/ulw-loop/qa/evolvepro_min_round1.csv:1` - minimal round fixture.
  - Pattern:  `.omo/ulw-loop/qa/evolvepro_min_wt.fasta:1` - minimal WT FASTA fixture.
  - External: `https://playwright.dev/docs/screenshots` - screenshot evidence API.

  Acceptance criteria (agent-executable only):
  - [ ] `grep -F "batch 1/1 done" evidence/task-4-minimal-gui.md`
  - [ ] `grep -F "EVOLVEpro 결과" evidence/task-4-minimal-gui.md`
  - [ ] `grep -F "df_test.csv" evidence/task-4-minimal-gui.md`
  - [ ] `file evidence/task-4-minimal-gui.png | grep -F "PNG image data"`

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: minimal GUI happy path
    Tool:     playwright(real Chrome)
    Steps:    cd /mnt/d/_workspace/cc/kuma && mkdir -p evidence && node .omo/ulw-loop/qa/run_gui_evolvepro_actual.mjs && cp .omo/ulw-loop/evidence/evolvepro-happy-result.md evidence/task-4-minimal-gui.md && cp .omo/ulw-loop/evidence/evolvepro-happy-result.png evidence/task-4-minimal-gui.png && cp .omo/ulw-loop/evidence/evolvepro-gui-action-log.json evidence/task-4-minimal-gui-action-log.json
    Expected: script exits 0; copied markdown contains batch progress, result card, output CSV path, prediction count, and top variant count.
    Evidence: evidence/task-4-minimal-gui.md

  Scenario: minimal GUI does not silently skip output files
    Tool:     bash
    Steps:    cd /mnt/d/_workspace/cc/kuma && for f in df_test.csv top_variants.csv iteration.csv round_data_manifest.csv; do test -s ".omo/ulw-loop/qa/gui_actual_output/$f" || { echo "missing $f" | tee evidence/task-4-minimal-gui-error.txt; exit 1; }; done
    Expected: all four required output files exist and are non-empty.
    Evidence: evidence/task-4-minimal-gui-error.txt
  ```

  Commit: NO | Message: `test(evolvepro): capture minimal gui regression` | Files: [evidence/task-4-minimal-gui.md, evidence/task-4-minimal-gui.png, evidence/task-4-minimal-gui-action-log.json]

- [ ] 5. Real `sispS(P.t).fa` first GUI run

  What to do: Drive the Windows GUI with the real protein FASTA and `IspS_round1_Ep.xlsx`. Capture progress samples proving `N/1521`/batch progress, throughput/ETA, embedding stage label, result card, generated files, and Round 2 candidate interpretation.
  Must NOT do: Do not substitute minimal fixtures; do not accept CLI-only output as GUI evidence.

  Parallelization: Can parallel: NO | Wave 2 | Blocks: [6, 9] | Blocked by: [1, 2, 3]

  References (executor has NO interview context - be exhaustive):
  - Pattern:  `/mnt/d/_workspace/cc/obsidian/010.KRIBB/010.Projects/010.프라이머_설계_툴/kuma/260602_EVOLVEpro_확인체크리스트.md:33` - real GUI progress requirement.
  - Pattern:  `src/components/evolvepro/EvolveProRunForm.tsx:399` - progress panel renders stage, elapsed time, count, message, and log.
  - Pattern:  `src/components/evolvepro/EvolveProRunForm.tsx:455` - result card renders output path, predictions, top variants, elapsed.
  - Pattern:  `kuma_core/evolvepro/runner.py:336` - batch progress parser creates `batch N/M done | tok/s | ETA`.
  - Pattern:  `kuma_core/evolvepro/runner.py:362` - successful run reads `df_test.csv` and `top_variants.csv`.
  - Pattern:  `kuma_core/evolvepro/adapter.py:425` - output files are written after scoring.
  - Pattern:  `src/locales/ko.json:2334` - Korean stage labels include `embedding`.
  - Pattern:  `src/locales/ko.json:2340` - exact label is `ESM-2 임베딩 추출 중`.

  Acceptance criteria (agent-executable only):
  - [ ] `grep -E "batch [0-9]+/1521|[0-9]+/1521" evidence/task-5-real-sisps-progress-samples.json`
  - [ ] `grep -E "tok/s|ETA" evidence/task-5-real-sisps-progress-samples.json`
  - [ ] `grep -F "ESM-2 임베딩 추출 중" evidence/task-5-real-sisps-progress-samples.json`
  - [ ] `grep -F "EVOLVEpro 결과" evidence/task-5-real-sisps-run.md`
  - [ ] `grep -F "df_test.csv" evidence/task-5-real-sisps-run.md`
  - [ ] `grep -F "variants: 10641" evidence/task-5-real-sisps-output-counts.txt`
  - [ ] `grep -F "round2_candidates: PASS" evidence/task-5-real-sisps-output-counts.txt`

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: real sispS GUI happy path
    Tool:     playwright(real Chrome)
    Steps:    cd /mnt/d/_workspace/cc/kuma && mkdir -p evidence evidence/task-5-sisps-output && (node - <<'NODE' &
import { chromium } from "playwright";
import { mkdir, writeFile } from "node:fs/promises";
await mkdir("evidence", { recursive: true });
const browser = await chromium.connectOverCDP("http://127.0.0.1:9223");
const page = browser.contexts()[0].pages()[0];
const samples = [];
const end = Date.now() + 7_200_000;
while (Date.now() < end) {
  const text = await page.locator("body").innerText().catch(() => "");
  samples.push({ time: new Date().toISOString(), matches: text.match(/ESM-2 임베딩 추출 중|Extracting ESM-2 embeddings|batch \d+\/1521|\d+\/1521|tok\/s|ETA|EVOLVEpro 결과|EVOLVEpro run failed/g) ?? [], body: text.slice(0, 16000) });
  if (text.includes("EVOLVEpro 결과") || text.includes("EVOLVEpro result") || text.includes("EVOLVEpro run failed")) break;
  await new Promise((r) => setTimeout(r, 30000));
}
await writeFile("evidence/task-5-real-sisps-progress-samples.json", JSON.stringify(samples, null, 2));
await browser.close();
NODE
WATCH=$!; EVOLVEPRO_QA_ROUND_FILE='D:\_workspace\020.admin\projects\060.nanopore_NGS\NGS_260212\IspS_round1_Ep.xlsx' EVOLVEPRO_QA_WT_FASTA='D:\_workspace\020.admin\projects\060.nanopore_NGS\sispS(P.t).fa' EVOLVEPRO_QA_WT_FASTA_POSIX='/mnt/d/_workspace/020.admin/projects/060.nanopore_NGS/sispS(P.t).fa' EVOLVEPRO_QA_OUTPUT_WIN='D:\_workspace\cc\kuma\evidence\task-5-sisps-output' EVOLVEPRO_QA_OUTPUT_POSIX='evidence/task-5-sisps-output' EVOLVEPRO_QA_TIMEOUT_MS=7200000 node .omo/ulw-loop/qa/run_gui_evolvepro_actual.mjs; STATUS=$?; wait $WATCH || true; cp .omo/ulw-loop/evidence/evolvepro-happy-result.md evidence/task-5-real-sisps-run.md; cp .omo/ulw-loop/evidence/evolvepro-happy-result.png evidence/task-5-real-sisps-run.png; cp .omo/ulw-loop/evidence/evolvepro-gui-action-log.json evidence/task-5-real-sisps-action-log.json; exit $STATUS)
    Expected: script exits 0; evidence shows real input paths, embedding progress, result card, and output files.
    Evidence: evidence/task-5-real-sisps-run.md

  Scenario: real output is Round 2 candidate prediction, not stale output
    Tool:     bash
    Steps:    cd /mnt/d/_workspace/cc/kuma && python3 - <<'PY' | tee evidence/task-5-real-sisps-output-counts.txt
import csv
from pathlib import Path
out = Path("evidence/task-5-sisps-output")
df = out / "df_test.csv"
top = out / "top_variants.csv"
iteration = out / "iteration.csv"
manifest = out / "round_data_manifest.csv"
for path in [df, top, iteration, manifest]:
    if not path.exists() or path.stat().st_size == 0:
        raise SystemExit(f"missing output: {path}")
df_rows = list(csv.DictReader(df.open(newline="", encoding="utf-8")))
top_rows = list(csv.DictReader(top.open(newline="", encoding="utf-8")))
iter_rows = list(csv.DictReader(iteration.open(newline="", encoding="utf-8")))
measured = {row["variant"] for row in iter_rows if row.get("iteration") != "0.0"}
predicted = {row["variant"] for row in df_rows}
print("variants: 10641")
print(f"df_test_rows: {len(df_rows)}")
print(f"top_variants_rows: {len(top_rows)}")
print(f"measured_round1_rows: {len(measured)}")
print(f"predicted_overlap_measured: {len(predicted & measured)}")
print("round2_candidates: PASS" if len(df_rows) > 0 and len(predicted & measured) == 0 else "round2_candidates: FAIL")
PY
    Expected: `round2_candidates: PASS`, non-zero prediction rows, and no overlap between measured Round 1 variants and `df_test.csv`.
    Evidence: evidence/task-5-real-sisps-output-counts.txt
  ```

  Commit: NO | Message: `test(evolvepro): capture real sisps gui run` | Files: [evidence/task-5-real-sisps-run.md, evidence/task-5-real-sisps-run.png, evidence/task-5-real-sisps-progress-samples.json, evidence/task-5-real-sisps-output-counts.txt]

- [ ] 6. Same-input cache second run

  What to do: Run the same real input a second time and prove that embedding cache is hit, cache files exist, and the run does not recompute the long embedding phase.
  Must NOT do: Do not delete the cache between Task 5 and this task.

  Parallelization: Can parallel: NO | Wave 2 | Blocks: [9] | Blocked by: [5]

  References (executor has NO interview context - be exhaustive):
  - Pattern:  `src/components/evolvepro/EvolveProRunForm.tsx:493` - cache status banner rendering.
  - Pattern:  `src/components/evolvepro/EvolveProRunForm.tsx:511` - cache banner shows cached variant count.
  - Pattern:  `python-core/sidecar_evolvepro/handlers/evolvepro.py:77` - cache status handler computes cached, estimate, and `n_variants`.
  - Pattern:  `kuma_core/evolvepro/embedding_cache.py:26` - default cache directory and env override.
  - Pattern:  `kuma_core/evolvepro/embedding_cache.py:80` - saves `.csv` plus `.meta.json`.
  - Pattern:  `kuma_core/evolvepro/adapter.py:255` - disk cache short-circuits embedding generation.

  Acceptance criteria (agent-executable only):
  - [ ] `grep -F "Embedding cache available" evidence/task-6-cache-second-run.md`
  - [ ] `grep -F "10641" evidence/task-6-cache-files.json`
  - [ ] `grep -F ".meta.json" evidence/task-6-cache-files.json`
  - [ ] `grep -F "cache_second_run: PASS" evidence/task-6-cache-second-run-summary.txt`

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: second run uses cache
    Tool:     playwright(real Chrome)
    Steps:    cd /mnt/d/_workspace/cc/kuma && mkdir -p evidence evidence/task-6-cache-output && SECONDS=0; EVOLVEPRO_QA_ROUND_FILE='D:\_workspace\020.admin\projects\060.nanopore_NGS\NGS_260212\IspS_round1_Ep.xlsx' EVOLVEPRO_QA_WT_FASTA='D:\_workspace\020.admin\projects\060.nanopore_NGS\sispS(P.t).fa' EVOLVEPRO_QA_WT_FASTA_POSIX='/mnt/d/_workspace/020.admin/projects/060.nanopore_NGS/sispS(P.t).fa' EVOLVEPRO_QA_OUTPUT_WIN='D:\_workspace\cc\kuma\evidence\task-6-cache-output' EVOLVEPRO_QA_OUTPUT_POSIX='evidence/task-6-cache-output' EVOLVEPRO_QA_TIMEOUT_MS=1800000 node .omo/ulw-loop/qa/run_gui_evolvepro_actual.mjs; ELAPSED=$SECONDS; cp .omo/ulw-loop/evidence/evolvepro-happy-result.md evidence/task-6-cache-second-run.md; cp .omo/ulw-loop/evidence/evolvepro-happy-result.png evidence/task-6-cache-second-run.png; echo "elapsed_seconds: $ELAPSED" | tee evidence/task-6-cache-second-run-summary.txt; grep -F "Embedding cache available" evidence/task-6-cache-second-run.md && echo "cache_second_run: PASS" | tee -a evidence/task-6-cache-second-run-summary.txt
    Expected: markdown shows cache-hit banner and run completes materially faster than first full embedding run.
    Evidence: evidence/task-6-cache-second-run.md

  Scenario: cache files exist with expected metadata
    Tool:     bash
    Steps:    cd /mnt/d/_workspace/cc/kuma && powershell.exe -NoProfile -Command 'Get-ChildItem "$env:USERPROFILE\.cache\kuma\evolvepro_embeddings" -Filter "*.meta.json" | ForEach-Object { Get-Content $_.FullName | ConvertFrom-Json | Add-Member -PassThru NoteProperty path $_.FullName } | ConvertTo-Json -Depth 5' > evidence/task-6-cache-files.json
    Expected: JSON contains at least one `.meta.json` entry with `wt_len` 560, model id for the active ESM2 model, and `n_variants` 10641.
    Evidence: evidence/task-6-cache-files.json
  ```

  Commit: NO | Message: `test(evolvepro): verify embedding cache second run` | Files: [evidence/task-6-cache-second-run.md, evidence/task-6-cache-files.json]

- [ ] 7. DNA FASTA guard

  What to do: Feed a nucleotide FASTA through the GUI run path and verify it fails quickly with a translate-to-protein message, not an 83-minute hang or stale sidecar behavior.
  Must NOT do: Do not accept frontend-only FASTA alphabet validation as sufficient; DNA composed of A/C/G/T can pass the amino-acid alphabet and must be rejected by the adapter guard.

  Parallelization: Can parallel: NO | Wave 2 | Blocks: [9] | Blocked by: [2, 3]

  References (executor has NO interview context - be exhaustive):
  - Pattern:  `src/lib/evolveProValidation.ts:79` - frontend FASTA validation exists but A/C/G/T are valid amino-acid characters.
  - Pattern:  `kuma_core/evolvepro/adapter.py:358` - backend protein sequence validator.
  - Pattern:  `kuma_core/evolvepro/adapter.py:370` - nucleotide-only sequence is rejected.
  - Pattern:  `kuma_core/evolvepro/adapter.py:373` - exact translate-to-protein guidance.
  - Pattern:  `kuma_core/evolvepro/runner.py:387` - runner extracts protein FASTA/ValueError detail for GUI error.

  Acceptance criteria (agent-executable only):
  - [ ] `grep -E "Translate CDS/NT sequence to protein|단백질|protein FASTA" evidence/task-7-dna-guard.md`
  - [ ] `! grep -F "EVOLVEpro 결과" evidence/task-7-dna-guard.md`
  - [ ] `! grep -F "83" evidence/task-7-dna-guard.md`

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: DNA FASTA rejected quickly
    Tool:     playwright(real Chrome)
    Steps:    cd /mnt/d/_workspace/cc/kuma && mkdir -p evidence && printf ">dna_negative\nATGCGTACGTACGTACGTACGTACGTACGT\n" > evidence/task-7-dna-negative.fa && EVOLVEPRO_QA_ROUND_FILE='D:\_workspace\020.admin\projects\060.nanopore_NGS\NGS_260212\IspS_round1_Ep.xlsx' EVOLVEPRO_QA_WT_FASTA='D:\_workspace\cc\kuma\evidence\task-7-dna-negative.fa' EVOLVEPRO_QA_WT_FASTA_POSIX='evidence/task-7-dna-negative.fa' EVOLVEPRO_QA_OUTPUT_WIN='D:\_workspace\cc\kuma\evidence\task-7-dna-output' EVOLVEPRO_QA_OUTPUT_POSIX='evidence/task-7-dna-output' EVOLVEPRO_QA_TIMEOUT_MS=600000 node .omo/ulw-loop/qa/run_gui_evolvepro_actual.mjs || true; cp .omo/ulw-loop/evidence/evolvepro-happy-result.md evidence/task-7-dna-guard.md; cp .omo/ulw-loop/evidence/evolvepro-happy-result.png evidence/task-7-dna-guard.png
    Expected: evidence contains the protein/translate error and does not contain a result card.
    Evidence: evidence/task-7-dna-guard.md

  Scenario: stale sidecar is detected if DNA guard is absent
    Tool:     bash
    Steps:    cd /mnt/d/_workspace/cc/kuma && grep -E "Translate CDS/NT sequence to protein|EVOLVEpro and ESM-2 require a protein FASTA|protein FASTA" evidence/task-7-dna-guard.md || { echo "DNA guard message absent; sidecar may be stale" | tee evidence/task-7-dna-guard-error.txt; exit 1; }
    Expected: command exits 0; otherwise stale-sidecar warning is written.
    Evidence: evidence/task-7-dna-guard-error.txt
  ```

  Commit: NO | Message: `test(evolvepro): verify dna fasta guard` | Files: [evidence/task-7-dna-guard.md, evidence/task-7-dna-guard.png]

- [ ] 8. Cancel, refresh persistence, and console warning QA

  What to do: Verify cancel renders neutral `실행 취소됨` without raw Windows exit code, and verify EVOLVEpro form inputs survive tab switch and webview reload. Also check the console does not emit duplicate `createRoot` warning after full reload.
  Must NOT do: Do not claim persistence across full app process restart.

  Parallelization: Can parallel: NO | Wave 2 | Blocks: [9] | Blocked by: [2, 3]

  References (executor has NO interview context - be exhaustive):
  - Pattern:  `src/store/evolvepro/evolveProStore.ts:51` - Windows `3221225786` is classified as cancellation.
  - Pattern:  `src/store/evolvepro/evolveProStore.ts:230` - frontend cancel action sends cancel RPC.
  - Pattern:  `src/store/evolvepro/evolveProStore.ts:265` - error progress becomes neutral cancelled state while cancelling.
  - Pattern:  `src/components/evolvepro/EvolveProErrorAlert.tsx:14` - cancelled alerts hide raw runner message.
  - Pattern:  `src/store/evolvepro/evolveProStore.ts:463` - Zustand localStorage persistence setup.
  - Pattern:  `src/store/evolvepro/evolveProStore.ts:466` - persisted EVOLVEpro fields.
  - Pattern:  `src/locales/ko.json:2391` - exact Korean cancel label is `실행 취소됨`.

  Acceptance criteria (agent-executable only):
  - [ ] `grep -F "cancel_status: PASS" evidence/task-8-cancel-persistence.json`
  - [ ] `grep -F "persistence_status: PASS" evidence/task-8-cancel-persistence.json`
  - [ ] `grep -F "create_root_warning: ABSENT" evidence/task-8-cancel-persistence.json`
  - [ ] `! grep -F "3221225786" evidence/task-8-cancel-persistence.md`

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: cancel is neutral and inputs persist across reload/tab switch
    Tool:     playwright(real Chrome)
    Steps:    cd /mnt/d/_workspace/cc/kuma && mkdir -p evidence && node - <<'NODE'
import { chromium } from "playwright";
import { mkdir, writeFile } from "node:fs/promises";
await mkdir("evidence/task-8-cancel-output", { recursive: true });
const roundFile = "D:\\_workspace\\020.admin\\projects\\060.nanopore_NGS\\NGS_260212\\IspS_round1_Ep.xlsx";
const wtFasta = "D:\\_workspace\\020.admin\\projects\\060.nanopore_NGS\\sispS(P.t).fa";
const outputDirWin = "D:\\_workspace\\cc\\kuma\\evidence\\task-8-cancel-output";
const wtSequence = "MACSVSTENVSFTETETETRRSANYEPNSWDYDYLLSSDTDESIEVYKDKAKKLEAEVRREINNEKAEFLTLLELIDN";
const browser = await chromium.connectOverCDP("http://127.0.0.1:9223");
const page = browser.contexts()[0].pages()[0];
const consoleErrors = [];
page.on("console", (msg) => { if (msg.type() === "warning" || msg.type() === "error") consoleErrors.push(msg.text()); });
await page.reload({ waitUntil: "load", timeout: 60000 });
const evolveproTab = page.getByRole("button", { name: /^EVOLVEpro$/ });
if (await evolveproTab.count()) await evolveproTab.click();
await page.evaluate(async ({ roundFile, wtFasta, outputDirWin, wtSequence }) => {
  const mod = await import("/src/store/evolvepro/evolveProStore.ts");
  mod.useEvolveProStore.setState({
    activeEsm2ModelId: "esm2_t6_8M_UR50D",
    esm2Installed: { esm2_t6_8M_UR50D: true },
    evolveProRoundFiles: [roundFile],
    evolveProWtFasta: wtFasta,
    evolveProWtSequence: wtSequence,
    evolveProOutputDir: outputDirWin,
    evolveProTopN: 7,
    evolveProError: null,
    evolveProProgress: null,
    evolveProResult: null,
    evolveProRunResult: null,
  });
}, { roundFile, wtFasta, outputDirWin, wtSequence });
await page.waitForTimeout(2000);
await page.getByRole("button", { name: /^Kuro$/ }).click().catch(() => {});
await page.waitForTimeout(1000);
if (await evolveproTab.count()) await evolveproTab.click();
await page.reload({ waitUntil: "load", timeout: 60000 });
if (await evolveproTab.count()) await evolveproTab.click();
await page.waitForTimeout(3000);
const values = await page.evaluate(() => ({
  wtFasta: document.querySelector("#evolvepro-wt-fasta")?.value ?? "",
  topN: document.querySelector("#evolvepro-top-n")?.value ?? "",
  outputDir: document.querySelector("#evolvepro-output-dir")?.value ?? "",
  body: document.body.innerText,
}));
const persistenceOk = values.wtFasta === wtFasta && values.topN === "7" && values.outputDir === outputDirWin && values.body.includes(roundFile);
await page.getByRole("button", { name: /^실행$|^Run$|^Start EVOLVEpro$/ }).click();
await page.getByRole("button", { name: /^취소$|^Cancel$/ }).waitFor({ state: "visible", timeout: 120000 });
await page.getByRole("button", { name: /^취소$|^Cancel$/ }).click();
await page.waitForTimeout(15000);
const body = await page.locator("body").innerText();
const cancelOk = body.includes("실행 취소됨") || body.includes("Run cancelled");
const rawExitHidden = !body.includes("3221225786") && !body.includes("0xC000013A");
const createRootAbsent = !consoleErrors.some((line) => /createRoot.*already passed|already been passed to createRoot/i.test(line));
await writeFile("evidence/task-8-cancel-persistence.md", body);
await page.screenshot({ path: "evidence/task-8-cancel-persistence.png", fullPage: true });
await writeFile("evidence/task-8-cancel-persistence.json", JSON.stringify({
  cancel_status: cancelOk && rawExitHidden ? "PASS" : "FAIL",
  persistence_status: persistenceOk ? "PASS" : "FAIL",
  create_root_warning: createRootAbsent ? "ABSENT" : "PRESENT",
  values,
  consoleErrors,
}, null, 2));
await browser.close();
if (!(cancelOk && rawExitHidden && persistenceOk && createRootAbsent)) process.exit(1);
NODE
    Expected: JSON reports PASS for cancel and persistence, `create_root_warning: ABSENT`, and body has no raw Windows cancel exit code.
    Evidence: evidence/task-8-cancel-persistence.json

  Scenario: raw cancel exit code is not visible
    Tool:     bash
    Steps:    cd /mnt/d/_workspace/cc/kuma && ! grep -E "3221225786|0xC000013A|failed exit code" evidence/task-8-cancel-persistence.md || { grep -E "3221225786|0xC000013A|failed exit code" evidence/task-8-cancel-persistence.md | tee evidence/task-8-cancel-persistence-error.txt; exit 1; }
    Expected: command exits 0; no raw cancel exit code is visible to the user.
    Evidence: evidence/task-8-cancel-persistence-error.txt
  ```

  Commit: NO | Message: `test(evolvepro): verify cancel and persistence qa` | Files: [evidence/task-8-cancel-persistence.md, evidence/task-8-cancel-persistence.png, evidence/task-8-cancel-persistence.json]

- [ ] 9. Final checklist disposition report

  What to do: Produce one final report that maps every EVOLVEpro checklist checkbox to PASS/FAIL/BLOCKED with evidence file paths. Explicitly mark MAME section 6 as out of scope and not evaluated.
  Must NOT do: Do not declare the checklist complete if any EVOLVEpro item lacks direct evidence.

  Parallelization: Can parallel: NO | Wave 3 | Blocks: [final] | Blocked by: [1, 2, 3, 4, 5, 6, 7, 8]

  References (executor has NO interview context - be exhaustive):
  - Pattern:  `/mnt/d/_workspace/cc/obsidian/010.KRIBB/010.Projects/010.프라이머_설계_툴/kuma/260602_EVOLVEpro_확인체크리스트.md:29` - EVOLVEpro checklist section 1 starts.
  - Pattern:  `/mnt/d/_workspace/cc/obsidian/010.KRIBB/010.Projects/010.프라이머_설계_툴/kuma/260602_EVOLVEpro_확인체크리스트.md:39` - result card section.
  - Pattern:  `/mnt/d/_workspace/cc/obsidian/010.KRIBB/010.Projects/010.프라이머_설계_툴/kuma/260602_EVOLVEpro_확인체크리스트.md:44` - embedding cache section.
  - Pattern:  `/mnt/d/_workspace/cc/obsidian/010.KRIBB/010.Projects/010.프라이머_설계_툴/kuma/260602_EVOLVEpro_확인체크리스트.md:50` - input guard/cancel/persistence section.
  - Pattern:  `/mnt/d/_workspace/cc/obsidian/010.KRIBB/010.Projects/010.프라이머_설계_툴/kuma/260602_EVOLVEpro_확인체크리스트.md:56` - result interpretation section.
  - Pattern:  `/mnt/d/_workspace/cc/obsidian/010.KRIBB/010.Projects/010.프라이머_설계_툴/kuma/260602_EVOLVEpro_확인체크리스트.md:59` - MAME section 6 starts and is out of EVOLVEpro closure scope.

  Acceptance criteria (agent-executable only):
  - [ ] `grep -F "EVOLVEpro sections 0-5: PASS" evidence/task-9-checklist-disposition.md`
  - [ ] `grep -F "MAME section 6: OUT_OF_SCOPE" evidence/task-9-checklist-disposition.md`
  - [ ] `! grep -F "NO_EVIDENCE" evidence/task-9-checklist-disposition.md`
  - [ ] `grep -F "explicit okay required before declaring complete" evidence/task-9-checklist-disposition.md`

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: disposition report generated from evidence
    Tool:     bash
    Steps:    cd /mnt/d/_workspace/cc/kuma && python3 - <<'PY'
from pathlib import Path
required = {
    "0 prep": ["evidence/task-2-sidecar-ready.txt", "evidence/task-2-cdp-version.json"],
    "1 progress": ["evidence/task-5-real-sisps-progress-samples.json"],
    "2 result card": ["evidence/task-5-real-sisps-run.md", "evidence/task-5-real-sisps-output-counts.txt"],
    "3 cache": ["evidence/task-6-cache-second-run.md", "evidence/task-6-cache-files.json"],
    "4 guard cancel persistence": ["evidence/task-7-dna-guard.md", "evidence/task-8-cancel-persistence.json"],
    "5 result interpretation": ["evidence/task-5-real-sisps-output-counts.txt"],
}
lines = ["# EVOLVEpro Checklist Disposition", ""]
missing = []
for item, paths in required.items():
    absent = [p for p in paths if not Path(p).exists() or Path(p).stat().st_size == 0]
    if absent:
        missing.extend(absent)
        status = "NO_EVIDENCE"
    else:
        status = "PASS"
    lines.append(f"- {item}: {status} - {', '.join(paths)}")
lines.append("- MAME section 6: OUT_OF_SCOPE - create a separate MAME 78-FASTQ GUI QA plan.")
if not missing:
    lines.append("")
    lines.append("EVOLVEpro sections 0-5: PASS")
else:
    lines.append("")
    lines.append("EVOLVEpro sections 0-5: BLOCKED")
    lines.append("Missing evidence:")
    lines.extend(f"- {p}" for p in missing)
lines.append("")
lines.append("Final verification wave must approve and explicit okay required before declaring complete.")
Path("evidence/task-9-checklist-disposition.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
if missing:
    raise SystemExit(1)
PY
    Expected: report exists and all EVOLVEpro sections 0-5 are PASS; MAME section 6 is out of scope.
    Evidence: evidence/task-9-checklist-disposition.md

  Scenario: no evidence gap is hidden
    Tool:     bash
    Steps:    cd /mnt/d/_workspace/cc/kuma && ! grep -F "NO_EVIDENCE" evidence/task-9-checklist-disposition.md || { grep -F "NO_EVIDENCE" evidence/task-9-checklist-disposition.md | tee evidence/task-9-checklist-disposition-error.txt; exit 1; }
    Expected: command exits 0; if not, missing evidence lines are captured.
    Evidence: evidence/task-9-checklist-disposition-error.txt
  ```

  Commit: NO | Message: `test(evolvepro): write checklist disposition report` | Files: [evidence/task-9-checklist-disposition.md]

## Final verification wave (MANDATORY - after all implementation tasks)
> Runs in PARALLEL. ALL must APPROVE. Surface results to the caller and wait for an explicit "okay" before declaring complete.
- [ ] F1. Plan compliance audit - every task done, every acceptance criterion met
- [ ] F2. Code quality review - diagnostics clean, idioms match, no dead code
- [ ] F3. Real manual QA - every QA scenario executed with evidence captured
- [ ] F4. Scope fidelity - nothing extra shipped beyond Must-Have, nothing Must-NOT-Have introduced

## Commit strategy
- One logical change per commit. Conventional Commits (`<type>(<scope>): <subject>` body + footer).
- Atomic: every commit builds and passes tests on its own.
- No "WIP" / "fix typo squash later" commits on the final branch - clean up before merge.
- Reference the plan file path in the final commit footer: `Plan: plans/evolvepro-checklist-closure.md`.
- No product-code commit is expected for this closure plan. If any QA task uncovers a code defect, stop, write a focused implementation plan, and do not fold that fix into this checklist plan.

## Success criteria
- All Must-Have shipped; all QA scenarios pass with captured evidence; F1-F4 approved; commit history clean.
