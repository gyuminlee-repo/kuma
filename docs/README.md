# kuma Documentation

**Language**: 🇺🇸 English · [🇰🇷 한국어](./README.ko.md)

![kuma main window](./screenshots/04-design-complete.png)

**kuma** integrates two subtools into a single Tauri desktop app:

- **Kuro** (Kernel for Upstream Recombination Oligodesign) — batch SDM primer design from Gibson Assembly templates.
- **Mame** (Mutagenesis Assessment & Microplate Export) — Oxford Nanopore NGS verdict for screening which clones carry the intended mutations.

Both tabs share a project workspace; a hidden `__kuma_meta__` sheet in every Kuro xlsx export lets Mame auto-match sequencing reads back to the originating project weeks later. See the [project README](../README.md) for installation and architecture.

---

## 🦋 Kuro — SDM primer design

### 🚀 Start here
- [Installation](./en/installation.md) — Install on Windows / macOS / Linux
- [Quick Start](./en/quick-start.md) — Design your first primers in 5 steps
- [Interface Overview](./en/interface-overview.md) — Panel layout and menu reference
- [FAQ](./en/faq.md)

### 🧬 Input & preparation
- [Loading Sequences](./en/loading-sequences.md)
- [Entering Mutations](./en/entering-mutations.md)
- [UniProt and AlphaFold](./en/uniprot-and-alphafold.md)
- [Gene Selection](./en/gene-selection.md)

### ⚙️ Parameters & strategies
- [Parameter Panel](./en/parameter-panel.md)
- [Custom Polymerase Editor](./en/custom-polymerase-editor.md)
- [Diversity Strategies](./en/diversity-strategies.md)
- [Pipeline Mode](./en/pipeline-mode.md)

### 🔬 Designing & reviewing
- [Designing Primers](./en/designing-primers.md)
- [Result Table](./en/result-table.md)
- [Candidate Swap](./en/candidate-swap.md)
- [Failed Retry](./en/failed-retry.md)
- [Sequence Viewer](./en/sequence-viewer.md)

### 📦 Output
- [Plate Map](./en/plate-map.md)
- [Export Orders](./en/export-orders.md)
- [Export Liquid Handler](./en/export-liquid-handler.md)
- [Export Excel](./en/export-excel.md)
- [Workspace Save Load](./en/workspace-save-load.md)

### 📊 Analysis tools
- [Benchmark Dialog](./en/benchmark-dialog.md)
- [Design Report](./en/design-report.md)

### 🛠 Advanced
- [Configuration](./en/configuration.md)
- [Keyboard Shortcuts](./en/keyboard-shortcuts.md)
- [Troubleshooting](./en/troubleshooting.md)
- [Release Notes Index](./en/release-notes-index.md)
- [Contributing](./en/contributing.md)

---

## 🦠 Mame — NGS verdict

> Detailed page-by-page docs are under construction. The [project README — Mame tab section](../README.md#usage) covers the current usage flow.

What Mame does:

- Drop a raw MinKNOW run folder, or MAME-generated consensus FASTAs and a reference (`expected_mutations.xlsx` if available), into the Mame tab.
- Set the CDS end, ingest mode, and depth/identity cutoffs.
- **Run** produces a verdict table (PASS / WRONG_AA / FRAMESHIFT / AMBIGUOUS / LOWDEPTH / NOT_FOUND) and a 96-well plate map.
- **Export** writes a final xlsx with per-well verdicts.
- Dropping a Kuro-exported xlsx into Mame matches the file back to its source project via `__kuma_meta__ → project_id`.
- Raw FASTQ input keeps read IDs and Phred quality strings through MAME's own demux→consensus path; low-quality bases, low-depth sites, consensus N fraction, and mixed-read evidence are shown in the verdict table and Excel export.

Sample inputs are available via **Help → Load Sample Data** in the Mame menubar.

---

## 🔗 Links

- Source: https://github.com/gyuminlee-repo/kuma
- Latest release: https://github.com/gyuminlee-repo/kuma/releases
- Issue tracker: https://github.com/gyuminlee-repo/kuma/issues
