# Overview figure, the detail the canvas does not carry

Companion page to `docs/kuma_overview.svg` and its caption
`docs/kuma_overview_caption.md`. Parameter defaults and file lists live in the
caption. What follows is the mechanism detail: material that a reader needs only
when reading the code, and that would otherwise sit as prose inside a box.

Every claim is cited to a file and a line. Paths are relative to the repository
root.

---

## 1. Overlap window and Tm-guided extension

KURO designs a partially overlapping primer pair in the EVOLVEpro geometry,
following Landwehr et al. 2025, Nat Commun 16, 865
(<https://doi.org/10.1038/s41467-024-55399-0>):

```
Forward = [overlap upstream] + [mutant codon] + [downstream extension]
Reverse = [upstream extension] + [reverse complement of the overlap]
```

The overlap window sits entirely **upstream** of the mutant codon and ends at the
codon start, exclusive, so the mutation is never inside the shared arm. One
window is generated per requested length, default 18 nt. A window that would run
off the 5-prime end of a circular template wraps, and the sequence is then
linearised at the window start so the overlap begins at position 0
(`kuma_core/kuro/overlap.py:19-86`). Requested lengths are capped at 18 nt on the
design path and at 40 nt on the rescue path
(`python-core/sidecar_kuro/models.py:54`, `python-core/sidecar_kuro/models.py:92`).

Extension is Tm guided rather than length driven. Each side grows one base at a
time and the whole primer Tm, not the non-overlap fragment Tm, is the quantity
compared against the target:

- Forward: bases are appended from the downstream sequence, starting at a
  minimum of 4 downstream bases, and every candidate whose total length falls
  inside the forward length window is scored. A candidate inside the tolerance
  band is kept when it beats the running best, and the walk stops as soon as the
  Tm passes the target with a best already in hand, or as soon as it leaves the
  band from above (`kuma_core/kuro/sdm_engine.py:494-540`).
- Reverse: the same walk runs over upstream bases, starting from a zero-length
  extension, that is the bare reverse complement of the overlap
  (`kuma_core/kuro/sdm_engine.py:542-590`).

Full-overlap mode is a different search. Forward and reverse cover the same
region with the mutant codon centred, so the reverse primer is the reverse
complement of the forward one and a single Tm optimises both. Left and right
extensions are enumerated as a grid under a unified length window, and the pair
closest to the target Tm inside tolerance wins
(`kuma_core/kuro/sdm_engine.py:419-490`).

Forward and reverse each carry an independent tolerance step, and the pair
records the wider of the two for display and export
(`kuma_core/kuro/sdm_engine.py:967-1051`).

## 2. Checksum scope, which exports write one and which do not

A checksum is a sibling file, not a field. `write_output_checksum` computes
SHA-256 over an exported file and writes `<name>.sha256` beside it, in the
two-space `shasum -c` format, with the extension appended rather than replaced
(`kuma_core/shared/output_hash.py:1-45`).

Writes a checksum:

| Export | Handler |
| --- | --- |
| Excel design workbook | `python-core/sidecar_kuro/handlers/export.py:389` |
| Order sheet | `python-core/sidecar_kuro/handlers/export.py:446` |
| Plate mapping | `python-core/sidecar_kuro/handlers/export.py:554` |

Writes no checksum: the batch export. `handle_export_all` names eight output
files and calls each exporter through a per-file `_try` wrapper that records a
failure without raising, and no branch of it calls `write_output_checksum`
(`python-core/sidecar_kuro/handlers/export.py:977-1132`). Integrity for that
folder is carried instead by the run manifest inside `<prefix>_run.json`
(`python-core/sidecar_kuro/handlers/export.py:1109-1127`), which hashes the
**inputs** of the run (`kuma_core/shared/run_manifest.py:54-142`). An input that
cannot be hashed is recorded with `sha256: null` rather than omitted, so a
missing hash is visible rather than silent
(`kuma_core/shared/run_manifest.py:22`, `kuma_core/shared/run_manifest.py:124-142`).

Practical reading: a single exported file can be verified against its own
`.sha256`; a batch export folder cannot, file by file, and a reviewer who needs
that has to hash the folder separately.

## 3. The five `__kuma_meta__` keys

Every KURO workbook export appends a hidden sheet named `__kuma_meta__`, deleting
any earlier copy first, and writes five key-value rows
(`python-core/sidecar_kuro/handlers/export.py:354-362`):

| Key | Value |
| --- | --- |
| `project_id` | Project identifier, empty when the caller sends none |
| `kuma_version` | Application version, falling back to the built-in constant |
| `kuro_module_version` | KURO module version constant |
| `exported_at` | UTC timestamp in ISO 8601 |
| `overlap_mode` | The overlap mode the run was designed under |

MAME reads the sheet back and treats a workbook with no `project_id` row as
carrying no metadata at all, returning nothing rather than a partly filled
record. The reader consumes four of the five keys, `overlap_mode` being for the
design side (`kuma_core/mame/io/kuma_meta.py:20-42`). This sheet is what lets
MAME match a dropped KURO workbook to the open project.

## 4. Project folder layout

Creating a project makes two directories and one marker file
(`src-tauri/src/project.rs:24-47`):

```
<project>/
  kuma.project.json      project marker and manifest, schema 1
  design/
  analysis/
    consensus/
```

The manifest holds `schema`, `project_id`, `name`, `created_at`, `updated_at`,
`stage`, `kuro_workspace`, `expected_mutations`, `analysis_input`,
`analysis_output` and `last_opened_tab` (`src-tauri/src/project.rs:9-22`). A
manifest with a schema above 1 is refused with `SchemaTooNew` rather than being
read best-effort (`src-tauri/src/project.rs:49-59`). The marker file name is also
what marks a folder as a kuma project for the recent-project list and for archive
import (`src-tauri/src/config.rs:196`, `src-tauri/src/project_archive.rs:25`).

Stage is derived from what is on disk, never stored as an independent truth:
a verdict workbook under `analysis/` gives `done`, non-hidden files under
`analysis/consensus/` give `analyzing`, a design workbook gives `design_complete`,
and an empty project stays `draft` (`src-tauri/src/project.rs:61-85`).

Two more names appear inside a project and both begin with a dot, which matters
for the Tauri filesystem scope (see `AGENTS.md`):

- `.autosave/<kind>.json` plus rotated generations, written per tab
  (`src/lib/autosave.ts:40`, `src/lib/autosave.ts:182-186`). The write is
  debounced at 1500 ms, so a burst of edits produces one file write rather than
  one per keystroke, and a pending write can be promoted immediately by a flush
  (`src/lib/autosave.ts:21`, `src/lib/autosave.ts:488-493`). The figure says
  only "per-tab autosave"; the interval is here.
- `.kuma-workspace.json`, the multi-project workspace manifest
  (`src/lib/workspace/types.ts:51`, `src-tauri/capabilities/default.json:46`).

## 5. Optional MinKNOW files MAME reads when present

One file group is required. Everything below it is auto-detected, and absence
degrades a report rather than failing a run.

**Required.** `fastq_pass/<barcode*|NB*>/` holding `*.fastq` or `*.fastq.gz`.
Both extensions are read, so an older uncompressed run is not a corner case
(`kuma_core/mame/ingest/demux.py:71`, `kuma_core/mame/ingest/sort_barcode.py:35`).

**Run metadata.**

| Glob | Read by |
| --- | --- |
| `final_summary_*.txt` | `kuma_core/mame/ingest/run_meta.py:240` |
| `sample_sheet_*.csv` | `kuma_core/mame/ingest/run_meta.py:250` |

**QC and health.**

| Glob | Read by |
| --- | --- |
| `sequencing_summary*.{txt,tsv}`, including `_passed_` variants | `kuma_core/mame/ingest/quality_filter.py:267`, `kuma_core/mame/__init__.py:14-15` |
| `pore_activity_*.csv` | `kuma_core/mame/health.py:213` |
| `throughput_*.csv` | `kuma_core/mame/health.py:261` |
| `barcode_alignment_passed*.tsv`, falling back to `barcode_alignment*.tsv` | `kuma_core/mame/health.py:327-329` |
| `report_*.json` | `kuma_core/mame/ingest/flow_cell.py:93` |

`report_*.json` is searched in the run folder and then one level up, because a
raw run is analysed with the run folder as input while a consensus-directory run
is analysed with a directory inside it. Only two paths inside it are used, the
flow cell block and the mux scan pore counts, and a missing, truncated or
reshaped file comes back empty rather than raising, so a pore field stays null
and must not be rendered as zero
(`kuma_core/mame/ingest/flow_cell.py:76-135`).

Everything else under a MinKNOW run directory (`pod5/`, `fast5/`, `bam_pass/`,
`other_reports/`, `report_*.html`) is ignored
(`kuma_core/mame/__init__.py:20-21`).

> The module docstring at `kuma_core/mame/__init__.py:20-21` still lists
> `report_*.json` among the ignored names. That line is stale: `flow_cell.py`
> has read the file since v0.16.19, as `AGENTS.md` records. The table above
> follows the code.
