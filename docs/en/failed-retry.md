# Failed Retry

![Failed rows](../screenshots/11-failed-rows.png)

When a mutation fails the Tm / GC / length / HP filters, it appears with a red row and a reason (e.g. `Tm out of range`, `hairpin ΔG below threshold`).

## Rescue cascade

Kuro tries three auto-relax passes before giving up:

1. Widen Tm tolerance by 1 step
2. Expand primer length range by ±2 bp
3. Relax GC range by ±5 %

`tol_max` (default 3 °C) caps the final tolerance. Rescued rows are annotated `[rescued]` in the Note column.

## Manual retry

Click **Retry** next to a failed row to re-run with relaxed parameters. Adjust **Tm targets** or **primer length** first for more aggressive recovery.

## Bulk retry

File → *Retry all failed* re-runs every failure with the current parameter state.

*Stub — failed-rows screenshot coming.*
