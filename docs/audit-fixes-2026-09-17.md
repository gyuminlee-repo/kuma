# Audit Fixes: September 17, 2026

Baseline: `db6a2e9eac65ee2bf1b9a67b11da618014277107` (0.16.63).
This summary distinguishes code changes from platform execution evidence.
It does not certify laboratory hardware or every possible application workflow.

## Before and After

| Area | Previous behavior | Correction |
| --- | --- | --- |
| Deletion verdict | A plurality deletion could be exempted from the N-fraction gate despite lacking majority support. | Exempt only the intersection of deletion no-calls and strictly greater than 50% deletion support; preserve that evidence through serialization. |
| Activity identity | NGS evidence could be attached to a different output variant. | Require matching normalized variant identities before export. |
| Input boundaries | Non-finite numeric inputs and inconsistent delimiter handling could fail or corrupt processing. | Validate boundary values and use the detected delimiter consistently. |
| Primer placement | A binding interval could extend outside its flank. | Validate the complete forward and reverse intervals, including circular templates. |
| Echo and JANUS | Reduced plate ranges and multiple plates could lose primer ownership or disagree with order workbooks. | Preserve actual source and destination plate identities and stock positions throughout export and preview. |
| Demultiplexing | Changed inputs could reuse obsolete results; insertion evidence could be duplicated or insufficiently filtered. | Bind reuse to input content and filter evidence per read and quality. |
| GenBank loading | CDS annotations from another record could be associated with the first sequence. | Use only the first record's CDS and document the supported scope. |
| Workspace restoration | Stale results, lost selections, and malformed nested QC data could survive restoration. | Validate snapshot boundaries, preserve input identity, and cancel obsolete asynchronous work. |
| Empty benchmark state | A legitimate null benchmark result triggered a corruption warning. | Restore the empty state and clear stale results. |
| Desktop permissions | Scratch autosave could fail under hidden Linux app-data paths; File > Quit lacked close permission. | Permit the app-data root and descendants explicitly and grant window-close permission. |
| Native host | Cancelled requests could retain response registrations; archive export could include its own output. | Tie registrations to request lifetime and exclude the output archive. |
| RPC and packaging | Invalid requests, incomplete bundle copying, and shutdown failures could be mishandled. | Validate envelopes, retain required bundle structure, and propagate failures. |
| UI lifecycle | Event listeners, keyboard callbacks, and 3D selection could retain stale state. | Clean up listeners and guard asynchronous updates against input changes. |
| Test integrity | Some tests accepted empty or contradictory results; browser tests could miss ordinary uncaught errors. | Assert observable contracts and reject uncaught errors explicitly. |
| Audit evidence | Duplicate paths and malformed review receipts could be accepted. | Add a strict successor CLI validating receipt structure, hashes, and covered ranges. |
| Resource checks | Invalid resource source values could pass the generic existence check. | Reject non-string and blank source paths in upstream and import that guard without overwriting Kuma's other vendor fixes. Keep the local defense as well. |

## Evidence Reuse

Unchanged files retain their exact SHA-256 review receipts; a matching Git HEAD
alone is not evidence for uncommitted changes. Historical checks include the
full Python suite (3,883 passed, 27 skipped), the frontend suite (1,977 passed),
and Rust library/archive tests (43 and 2 passed). These numbers are historical
executions, not claims that those suites were rerun for each subsequent delta.

The deletion public-path reproduction returned NO_CALL at 40% and 50%, and
PASS at 60%. Linux native execution of the frozen application exercised KURO
sample loading, save, quit, and restoration of 2,700 bp / EGFP 240 aa without
the false benchmark warning.

A separate Cargo target, `src-tauri/tests/native_sidecar`, drives the real Wry
event loop and the production sidecar manager through ready, pong, invalid
method survival, shutdown, and process disappearance. That target has been
executed on Linux under Xvfb only. The macOS step registered in
`.github/workflows/build.yml` has not been run at the time of writing, so no
macOS runtime result is claimed here. Windows is outside this target and has
no native runtime record.

These fixes live on the branch `fix/audit-latest-20260917` and are being
committed there. They are not merged into `main` and are not released; the
installed application still carries the baseline behaviour.

At release preparation, the pre-push wrapper passed 89 checks and 81 groups;
TypeScript, i18n lint/parity, and whitespace checks exited zero. The audit
checker and local resource regression suite passed 85 tests. Platform,
upstream, PR, and release results must be recorded separately when observed;
this document alone is not a merge or deployment approval.

## Generic Checker Provenance

The resource-source guard is imported from claude-dotfiles commit
`376de76038b7cb0289e9f4ecfbd43c5ddf5bf040`. Only its source-loop patch is
imported into `scripts/sync-check.mjs`; Kuma's newer extraction, empty-list,
registry-key, and group checks are retained. The upstream regression suite
passed 21 cases. Kuma's suite passed 25 cases after the import, including
eight invalid-input cases that failed before it when the local extension
was disabled. Destination-map values remain destinations, not local files.
