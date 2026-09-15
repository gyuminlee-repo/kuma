# KURO: 6-step workflow

KURO is a linear wizard made of 6 steps. Steps can be clicked freely in the Workflow Rail on the left, and the Next button at the bottom opens a guidance Dialog when an input is missing.

```
1. Load        →  sequence + gene + organism selection
2. Mutation    →  text / EVOLVEpro input
3. Parameters  →  polymerase · codon strategy · Tm range
4. Submit      →  Design summary card + Run Design
5. Output      →  per-mutation result table + DesignReportInspector on the right
6. Export      →  xlsx / Echo / JANUS / plate map
```

<!-- TODO: insert screenshot of KURO 6-step rail -->

## What changed in the v0.9.2.x patch

- **Free Sidebar navigation**: click to move to any step immediately. A step with unmet prerequisites shows an empty-state message rather than a blank screen.
- **Next button**: a validation Dialog when a required input is missing. Sidebar clicks are not blocked.
- **Run Design auto advance**: on success it moves automatically to `output.summary` without a popup.
- **DesignReportInspector**: the report is shown in a fixed panel on the right of Output. It is not a separate step.
- **DesignSummaryCard**: a summary of the key sequence/mutation/parameter values at the top of the Submit step.

For detailed step descriptions, see the per-step pages in the left menu.
