# kuma — Kuro Subtool Documentation

**Language**: 🇺🇸 English · [🇰🇷 한국어](./README.ko.md)

![Kuro main window](./screenshots/04-design-complete.png)

This page documents the **Kuro** subtool inside [kuma](../README.md). Kuro (Kernel for Upstream Recombination Oligodesign) is the SDM primer-design tab that designs batch Site-Directed Mutagenesis primer pairs from Gibson Assembly templates. The other subtool, Mame (Mutagenesis Assessment & Microplate Export), handles NGS verdict on the same project workspace.

## 🚀 Start here

- [Installation](./en/installation.md) — Install on Windows / macOS / Linux
- [Quick Start](./en/quick-start.md) — Design your first primers in 5 steps
- [Interface Overview](./en/interface-overview.md) — Panel layout and menu reference

## 📚 Full documentation

Navigate using the sidebar on the right. Pages are organised by workflow phase (Input → Parameters → Designing → Output → Analysis).

## 🧪 What Kuro does

Given a mutation list (plain text or EVOLVEpro CSV) and a template sequence (GenBank / SnapGene), Kuro automatically designs SDM primer pairs using the overlap-extension method. Outputs include IDT/Twist order CSVs, Echo/JANUS liquid-handler mapping files, and a full Excel workbook with per-mutation statistics. Each export carries a hidden `__kuma_meta__` sheet so the Mame tab can later match sequencing reads back to the originating project.

## 📑 All pages

### 📘 Getting Started
- [Installation](./en/installation.md)
- [Quick Start](./en/quick-start.md)
- [Interface Overview](./en/interface-overview.md)
- [FAQ](./en/faq.md)

### 🧬 Input & Preparation
- [Loading Sequences](./en/loading-sequences.md)
- [Entering Mutations](./en/entering-mutations.md)
- [UniProt and AlphaFold](./en/uniprot-and-alphafold.md)
- [Gene Selection](./en/gene-selection.md)

### ⚙️ Parameters & Strategies
- [Parameter Panel](./en/parameter-panel.md)
- [Custom Polymerase Editor](./en/custom-polymerase-editor.md)
- [Diversity Strategies](./en/diversity-strategies.md)
- [Pipeline Mode](./en/pipeline-mode.md)

### 🔬 Designing & Reviewing
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

### 📊 Analysis Tools
- [Benchmark Dialog](./en/benchmark-dialog.md)
- [Design Report](./en/design-report.md)

### 🛠 Advanced
- [Configuration](./en/configuration.md)
- [Keyboard Shortcuts](./en/keyboard-shortcuts.md)
- [Troubleshooting](./en/troubleshooting.md)
- [Release Notes Index](./en/release-notes-index.md)
- [Contributing](./en/contributing.md)

## 🔗 Links

- Source: https://github.com/gyuminlee-repo/kuma
- Latest release: https://github.com/gyuminlee-repo/kuma/releases
- Issue tracker: https://github.com/gyuminlee-repo/kuma/issues

