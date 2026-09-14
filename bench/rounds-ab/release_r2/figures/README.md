# Round-2 verdict figure scripts

The two scripts that draw the round-2 verdict panels of the manuscript. They
live here, beside the workbook they read, because the earlier copies sat
outside version control and were overwritten with no way back.

## Canonical input

`../R2_FBF10847_v0.16.58_amplicon_MAME.xlsx`, sheets `Final`, `NB06`, `NB13`,
`NB20`. No other workbook feeds these figures. Verdicts are read, never
recomputed.

Path resolution in both scripts, in order:

1. `KUMA_MAME_XLSX`, an explicit override,
2. the directory above the script, which is this release folder,
3. `$WORKSPACE_ROOT` (env, else derived) plus
   `cc/kuma/.claude/worktrees/rounds-ab/bench/rounds-ab/release_r2/`.

The style kit is not vendored here. Both scripts import
`010.fig/_style_kit/palette.py` and apply `kuma_style.mplstyle`. Set
`KUMA_STYLE_KIT` when the kit is not at `<script>/../_style_kit`.

## Class vocabulary

Eight classes, in the order of `VerdictClass` in `kuma_core/mame/models.py`:
PASS, AMBIGUOUS, MIXED, FRAMESHIFT, MANY, LOWDEPTH, NO_CALL, WRONG_AA. A class
with zero observations keeps its axis slot and its legend row at n=0. The
six-class list these scripts used before dropped the FRAMESHIFT wells from
every panel without a warning; both scripts now raise on any class outside the
list. Note that `../count_workbook.py:32` calls the eighth class `NO_READS`;
the name in the code is `MANY`.

## Run

Run from the working copies under
`020.admin/projects/070.KUMA_elements/010.fig/`, which is where the outputs
belong:

```
cd <admin>/010.fig/260722_merged        && python3 make_mame_verification_merged.py
cd <admin>/010.fig/260826_suppfig3_replicate && python3 make_suppfig3_replicate.py
```

`python3` is the interpreter that carries matplotlib on this machine; the kuma
venv does not.

## Outputs (paths the manuscript captions cite, do not move)

- `010.fig/260722_merged/mame_verification_merged.svg` and `.pdf`
- `010.fig/260722_merged/mame_panel_a_verdict.svg`
- `010.fig/260722_merged/mame_panel_b_depth.svg`
- `010.fig/260722_merged/mame_panel_c_platemap.svg`
- `010.fig/260826_suppfig3_replicate/SuppFig3_replicate_260826.svg` and `.pdf`

SVG is the master; the PDF is for internal QA. No PNG.

## Expected counts (2026-09-14 re-analysis)

- panel (a), 95 design-variant wells: PASS 82, WRONG_AA 4, NO_CALL 3,
  LOWDEPTH 2, AMBIGUOUS 2, MIXED 1, FRAMESHIFT 1, MANY 0. The WT control H12 is
  PASS, so the 96-well total is PASS 83.
- panel (b) and Supplementary Figure 3, 288 well x plate records: PASS 191,
  WRONG_AA 37, MIXED 30, NO_CALL 12, AMBIGUOUS 8, FRAMESHIFT 5, LOWDEPTH 5,
  MANY 0.
- panel (c): 96 tiles classified, none left as `no verdict`.
