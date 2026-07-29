# Interface Overview

Kuma is one project workspace with two connected tools:

- **Kuro** turns ranked protein variants into primer designs, plate layouts, and structure-aware review.
- **Mame** combines sequencing verdicts and activity measurements into the curated table used for the next learning round.

## Shared workspace

The top application bar switches between **Kuro** and **Mame**. The project bar immediately below it shows the active project, project stage, and autosave state. Results remain attached to that project when you change tools.

Each tool uses the same three-region layout:

1. **Workflow rail (left)** — ordered stages and current progress.
2. **Main workspace (centre)** — inputs, tables, plate views, sequence/structure views, and the active step's primary actions.
3. **Inspector (right)** — parameters, selected-item details, warnings, and export controls for the current step.

The status bar at the bottom reports sidecar state and long-running operation progress.

## Guided tour

A newly created project starts a short spotlight tour:

1. Project overview and Kuro/Mame navigation.
2. Kuro workflow rail, main workspace, and inspector.
3. A separate Mame tour the first time that project enters Mame.

The highlighted area is temporarily read-only while the explanation is open.

- **Back / Next / Finish** navigate the current tour.
- **Skip all tours** disables all automatic tours for that project.
- `Esc` only closes the current tour; it does not opt out permanently.
- **Help → Show Guided Tour** replays the tour for the current tab.
- Existing projects are never interrupted automatically.

After Kuro design and wet-lab execution, switch to Mame to validate clones, merge activity evidence, and prepare the next-round learning input.
