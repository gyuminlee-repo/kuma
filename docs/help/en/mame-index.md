# MAME: Major.Sub workflow

MAME consists of 4 major steps, and each major has sub-steps under it. Unlike the single 1..6 count of KURO, it uses **Major.Sub hierarchical numbering** (`1.1`, `2.1`, `2.2`, `3.1`, `4.1`). The rail counts 6 sub-steps, and the canonical source is `ALL_SUBSTEPS` and `SUBSTEP_DISPLAY` in `src/components/mame/layout/MameWorkflowRail.tsx`.

```
1. Barcode Setup
   1.1 Files & Coordinates
2. Analyze
   2.1 Inputs                 (run inputs, Run/Validate)
   2.2 Review                 (verdict + plate + per-plate verdict bar)
3. Janus instrument settings
   3.1 Janus                  (optional step. Skipping it does not affect a run)
4. Activity Data
   4.1 Ingest
   4.2 Signals                (includes merge + export)
```

Janus instrument settings moved out of step 2.1 in v0.15.12 and became a major step 3 of its own. Activity was pushed to 4.x. The split keeps an operator who only needs a sequencing verdict from walking past robot settings they will not use, and step 3 does not block any run.

## step 3 (as of v0.16.1)

The only Janus file a run writes by itself is the selected clone pick list (`..._picks.csv`). The 8-column mapping sheet the robot reads (`..._janus.csv`) is created only when export is pressed in step 3. The robot sheet is a file that states the deck, and that value states the lab state at export time, so it is not rewritten automatically on every re-run. The two rack columns hold plate names rather than deck numbers, and there is no liquid class column.

The dialog is gone from the step 3 screen. Instead of an "Open Janus instrument settings" button and a popup, the same content (volume, liquid class, sample type, row preview, excluded clones, export button) unfolds inline on the step 3 page.

The analyze screens (2.x) have no Janus. Instrument settings, and the notice that a run wrote an instrument file, appear only in step 3.

<!-- TODO: insert screenshot of MAME rail with Major.Sub labels -->

## Where the labels appear

- WizardContainer header: `Step 1.1: Files & Coordinates`
- Sidebar rail: major in bold (`1. Barcode Setup`), sub indented (`  1.1 Files & Coordinates`)
- Footer progress: `Step 1.1 / 4.2`

## Changes in v0.9.2.x

- Free Sidebar navigation: click to move to any sub-step from 1.1 → 4.2 immediately.
- Blank screen fallback removed. The default path of every step is handled with an empty-state message.
- Unified 2.1/2.2 review sub-step + per-plate verdict bar (the NGS efficiency graph of PPT slide 6): **Task #12 implementation in progress**.

For detailed step descriptions, see the left menu.
