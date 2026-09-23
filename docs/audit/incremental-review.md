# Incremental review: reuse reasoning, not old test results

## Start here on the next debugging/refactoring request

Run the planner **before reading the whole repository again**:

```bash
python scripts/plan_incremental_audit.py
# Optional reports: choose a temporary directory outside the source checkout.
python scripts/plan_incremental_audit.py --json /tmp/kuma-audit-plan.json --markdown /tmp/kuma-audit-plan.md
```

The console command is cross-platform; use an OS-appropriate temporary path on
Windows. Python's standard library and Git are sufficient. No product packages,
network service, credentials, biological data or model calls are required.
It does not execute commands read from the registry or run/skip product tests.

새 디버깅·리팩토링 요청에서는 이 계획을 먼저 읽는다. **변경 파일과 영향받은
범위를 먼저 검토하고, 이전에 확인한 이유를 처음부터 다시 만들어내지 않는다.**
다만 기존 테스트를 생략하거나 과거 CI 통과를 새 커밋의 통과로 보고하지 않는다.

## Three review decisions

| Decision | Meaning | Next action |
|---|---|---|
| `reuse_candidate` | The recorded files/tests and declared context have no detected change since their own reviewed commit. | Reuse the previous explanation only after considering unrecorded changes and missing dependencies; rerun regressions and final CI. |
| `review_required` | Implementation, tests, a watched dependency/caller, a transitive group sibling or validation environment changed. | Read the listed changes and affected paths, not an unrelated whole-repository sweep. |
| `unverified` | A regression test disappeared or the ledger explicitly records work without sufficient evidence. | Obtain the missing evidence; do not promote this item because other tests passed. |

A status is about **manual review effort**, not correctness or merge eligibility.
Every changed path outside the ledger is listed for manual impact review, including
new code. A new caller outside a declared group must not be dismissed merely
because an old callee has a `reuse_candidate` row. Inspect and extend the dependency
map/watch list, or broaden review when the effect cannot be bounded.

The nine initial records concern specific guard/calculation contracts from
PR #425 and #428. A file named in a record is not certified line-by-line. In
particular, barcode-window extraction does not certify the entire demultiplexer.
Historical audit pages remain historical; do not treat every old finding as
newly open, but do not consider an unlisted finding resolved either.

## How changes are found

`docs/audit/registry.json` contains each scope's full immutable **merged commit**,
concrete files and regression tests, source PR, historical CI run/tested head,
explicit invalidation watches and limits. The planner reads Git trees at that
commit and at the current HEAD and reports the mode/object identities of the
recorded files. A test's existence is not proof that it ran; CI links are recorded
provenance, not an online attestation fetched by this script.

Each record is compared against **its own** `reviewed_commit`. The top-level
`comparison_base` (or `--base FULL_SHA`) only controls the general change inventory.
Overriding it cannot turn a changed old scope into an unchanged one. The initial
#425 baselines intentionally remain #425, not a later green commit: intervening
caller/configuration changes can therefore still request context review.

Default local mode includes staged, unstaged, deleted and untracked non-ignored
files. Renames are treated as deletion plus addition; both paths participate.
CI uses `--committed-only`: inputs come from the committed registry and group
map, and worktree modifications are ignored. Both modes report the exact HEAD;
local mode additionally enumerates its dirty paths. Reports should be written
outside the checkout to avoid becoming a new untracked input on the next run.

`.cross-layer-sync.json` is the existing source for cross-layer groups. All
severities participate in the planner's transitive impact closure; a warning-only
group can still matter for manual review. Explicit `watch` patterns add broader
caller/shared-module context. Glob matching is case-sensitive, supports brace
alternatives and zero-directory `**/`, and conservatively allows `*` to cross `/`.
It may over-select. It is **not** a full static/dynamic import, RPC or call graph.
Global manifests, lockfiles, test configuration, build/CI and model-generation
inputs invalidate the recorded context too. Extend these when new inputs matter.

Missing Git history, non-ancestor baselines, invalid/duplicate JSON, missing
recorded baseline files and malformed group maps fail closed: no automatic pass.
Fetch the necessary history or do a fresh review. An old baseline on an unrelated
branch is not reusable even if the file names happen to match. The planner never
fetches or resets Git, edits sources, creates approvals, or advances the ledger.

## A normal work cycle

1. Run the planner and read its reasons, unrecorded paths and unverified work.
2. Review changed scopes and callers. Reuse unaffected **bounded** explanations;
   inspect unclear cross-layer/new-code effects rather than guessing.
3. Reproduce new defects and add a regression that fails before the correction.
   Use the listed Python/Vitest test files for focused iteration, as appropriate.
4. Run the complete existing CI on the exact final PR head/merge tree. The planner
   and focused tests do not replace Python's full suite, frontend/model/i18n,
   Rust/build checks or existing test evidence reports. External skips stay skips.
5. In the PR summary, state what was reused, re-reviewed and still unverified.
   Update the ledger only for scopes actually reviewed with appropriate evidence.

The `Incremental audit` workflow runs fast stdlib planner tests and publishes
JSON/Markdown plans for PRs and main pushes. Its green status means the **planner
ran successfully**, not that all rows are reusable, tests were performed here,
or the PR was approved. Existing `ci.yml` remains unchanged and runs in full.
No branch-protection setting is enabled or weakened by this workflow.

## Updating evidence without laundering it

After a scope's substantive review and final CI have completed, add a new record
or update that record in a reviewed follow-up commit. Use the actual merged
commit whose code was reviewed, the tested PR head and the CI run for it. Retain
its source PR/finding and previous history in Git. Use exact tested file paths,
include relevant callers/shared dependencies and state excluded behavior.
Do not move every baseline to HEAD just to turn the report green.

Do not advance baselines automatically on test success, attach the entire module
to one narrow test, delete an unverified item because its data is unavailable, or
copy current output into a 'ground truth' fixture without independent approval.
Keep calibration, reference-rule equivalence, synthetic contracts, real-data
self-consistency, GUI presentation and instrument acceptance distinct.

## Scope of this change

This is developer/agent tooling. It adds no application screen, changes no
scientific threshold, publishes no installer, and does not upload the seminar
slides or unpublished experimental data. The seminar's distinction between
implemented behavior and validated evidence remains a constraint, not an
executable expected-output oracle.
