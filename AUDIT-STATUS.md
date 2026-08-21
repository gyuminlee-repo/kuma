# What the audit pages are, and what landed from them

The eleven `AUDIT-*.md` pages record findings as of the sweep that produced them.
They are not a to-do list and they were never rewritten as fixes landed, so a
finding described there is open unless this page says otherwise.

That reading rule is the point of this page. Without it a reader meets a
paragraph describing a defect in the present tense and has no way to tell
whether it still holds.

## The pages

| Page | Surface | Confirmed |
|---|---|---:|
| `AUDIT-mame-core.md` | `kuma_core/mame/` | 26 |
| `AUDIT-kuro-core.md` | `kuma_core/kuro/` | 32 |
| `AUDIT-sidecar.md` | `python-core/` | 19 |
| `AUDIT-store-lib.md` | `src/store/`, `src/lib/` | 52 |
| `AUDIT-components.md` | `src/components/` | 51 |
| `AUDIT-tauri-scripts.md` | `src-tauri/`, `scripts/` | 51 |
| `AUDIT-strategy-hooks.md` | `kuma_core/strategy/`, `src/hooks/` | 18 |
| `AUDIT-types-screens-tests.md` | `src/types/`, `src/screens/`, tests | 34 |
| `AUDIT-shared-and-uncovered.md` | `kuma_core/shared/`, `benchmark/`, root configs | 5 |

`AUDIT-recheck.md` and `AUDIT-verification.md` hold the re-verification rather
than findings of their own.

The first six surfaces did not partition the tree. Surfaces seven and eight
exist because a coverage check found the gap, and the most consequential finding
of the sweep sits in one of them.

Neither did the first eight. Surface nine covers the 84 tracked code files that
no earlier list claimed, most of them `kuma_core/shared/`: the atomic write
every export publishes through, the run manifest that is the provenance record
for every artifact, and the memory guard both dispatchers ask. Each surface
list was written from directory names, and the check that catches an omission
was run once per opening rather than once at the end.

## Overturned

Six findings did not survive re-verification. They stand in place in their pages
with the correction attached rather than deleted, because a finding that failed
is worth as much to the next reader as one that held. `AUDIT-recheck.md` §"The
six that did not survive" carries the reasoning.

- Echo reverse source plate (kuro F26), wrong direction
- NB label collisions (mame C4), wrong direction
- Builder to renderer renders every well empty (mame C26), not a defect
- Negative scores erase entropy (kuro F6), wrong direction
- Missing C-alpha as maximum diversity (kuro F14), not a defect as filed
- Tripled round workbook (sidecar F10), not a defect

Eight more hold as defects but the remedy recorded with them is wrong. They are
listed in `AUDIT-recheck.md` §"The eight whose remedy needs restating".

## What landed

Fixes were made against causes rather than sites, so one commit usually answers
several findings.

| Commit | What it addressed |
|---|---|
| `e2ba9439` v0.16.29 | The root causes: non-finite payloads presenting as RPC timeouts, a confidence reported for a bootstrap that could not measure it, a workspace group read whole, the raw sidecar transport made unreachable from feature code, the suite made to run on Windows, release stamping made to fail loudly, and the translation gate rebuilt before the strings |
| `1900feb2` v0.16.29.01 | The manifests carrying the version their label claims, and a check that compares the two |
| `79b60336` v0.16.29.02 | `delta_best_ema` moved to the log2 scale it is compared against |
| `53d2d312` v0.16.29.03 | The best-of-N count supplied, so the registered null is the one in force |
| `b25fce3b` v0.16.30.01 | The replicates behind each exported activity recorded |
| (this page's commit) | This index |
| `dfaa5d54` v0.16.33.03 | The shared primitives under every export: the memory guard failing open when it cannot measure, an unreadable input recorded as one never supplied, a staging name shared by every writer of a target, and a checksum published without the atomicity its neighbour uses |
| `1e9d81f2` v0.16.33.05 | The 196 benchmark tests nothing collected, and the guards that could not say they had not decided: no `isfinite` anywhere in `analyze.py`, a NaN consensus header read as evaluable, `nan < min_qscore` keeping a read, one duplicate rule on one of two input paths, and `success_rate` reported as 100 in every export |
| `ac2a24e7` v0.16.33.07 | One copy of the lifecycle code both sidecars run, and the two assay-noise figures this document registered as unmeasured |
| `37e59111` v0.16.33.08 | Four checks answering questions they could not answer: a reverse-strand CDS offered with forward coordinates, cross-talk reporting `ok` at sample sizes where its statistic cannot reach its threshold, `A0` and `A13` accepted as wells, and a missing prediction written as a fitness of zero |
| `39ad09a3` v0.16.33.12 | The coding window checked before a run is accepted, and the quality filter fix finished on the second of its two copies |
| `dd56435a` v0.16.33.13 | The purity evidence carried through a save and restore, and one rule shared by three activity readers |
| `3a4b3adb` v0.16.34.01 | Bare `NaN` and `Infinity` refused at the RPC door, one threshold validated on both of its paths, and plates chunked by the capacity that filled them rather than by a count of 96 |
| `6a952e1b` v0.16.34.02 | The shutdown tests budgeted for the clean exit they assert rather than for a fast one, with a real hang confirmed to still fail |
| `03eb1594` v0.16.34.03 | Non-finite cells kept out of the run report figures, unknown fitness scores dropped rather than ranked as zero, an unreadable position refused, colliding wells counted, and the structure parsers given one finite-or-absent rule |
| `e8924aca` v0.16.34.04 | Every reverse diagnostic carried through a primer swap on both propagation paths and in the store, an empty mapping payload told apart from an absent one, the entropy weight given the ceiling its twin already had (closes sidecar F16), and the quality gate actually run when there is no sequencing summary |

`v0.16.30.02` added `docs/2026-08-19-mame-assay-noise-model.md`, which is not a
fix: it records why the replicate counts recorded in `v0.16.30.01` are not the
`r` that `compute_T2` takes, before anything started supplying them.

Two Windows defects reached in `v0.16.29` are worth naming separately, because
no run on Linux or macOS could have found them. Every Step 3 artifact publish
raised an error there, and the checksum file written beside every export was
unreadable by the checker it exists for. Both were invisible while a blanket
skip meant the Windows leg reported nothing passed and 1301 skipped, as success.

## What is open

Two surfaces of the sweep were reworked after the fixes above, and the reason is
worth keeping. Both defect families that this audit keeps meeting are visible in
the same three commits:

- A guard that tests a relation rather than finiteness. `x < threshold` cannot
  express "not comparable", because every comparison against NaN is false, so a
  gate written that way reports a pass it never made.
- An invariant enforced on one input path and not on its twin. The path nobody
  wrote a test for is the one that ships. Two of these were found only because a
  comment still described behaviour the code had lost.


Everything else. The count is not stated here because the pages do not share a
status field and inventing one from prose would be a guess dressed as a number.
A reader wanting to act on a specific finding has to check the code.

Two items are open by decision rather than by omission, and both need a
measurement rather than a patch:

- The assay noise estimate. `sigma_assay` stays None and T2 stays NA.
  `docs/2026-08-19-mame-assay-noise-model.md` states what has to be measured
  first and why supplying the available numbers would make it worse.
- The bootstrap of a maximum. A with-replacement resample cannot exceed the
  observed maximum and loses it in about 37 percent of draws, which pulls
  `delta*` down in one direction only. It is inert while `sigma_assay` is None,
  since the quantity it distorts reaches nothing but `compute_T2`.

One finding was reverted after being applied: collapsing duplicate ids in
`build_draft_layout` would attach measurements to the wrong variant, because
`numeric_id_decode.py` maps the sheet to wells by row index. Reproducing it
needs the sheet that produced the empty layout.

## Why the tests did not catch any of this

They were written against the implementation rather than against the contract.
A cross-talk test pins a threshold at five because the code says five, while the
reachable value is nine. A volume test supplies only zero, which separates no
two behaviours. A suite written that way agrees with the code by construction,
including where the code is wrong.

The tests added with the fixes were each checked against the defect they
describe: reverted to the old spelling, they fail. A test that passes both ways
witnesses nothing, and several of the ones already here do exactly that.
