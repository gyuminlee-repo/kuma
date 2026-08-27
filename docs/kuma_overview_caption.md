# Figure caption, kuma overview

Source figure: `docs/kuma_overview.svg`. Compact variant: `docs/kuma_overview_hero.svg`.
Builder: `scripts/build-overview-figure.py`.

---

## Caption

**Figure 1. kuma closes one directed-evolution round in four lanes.**
Lane A (DESIGN) is the KURO primer engine. A GenBank template with CDS annotation
enters, together with a variant list in one-letter notation such as Q232A; plain
FASTA is refused, because the engine needs the coding frame to place a codon.
Accepted template formats are `.gb`, `.gbk`, `.gbff` and SnapGene `.dna`.
Primer build runs under a polymerase profile, a codon strategy and an overlap
mode. The shipped default profile is KOD (SantaLucia nearest-neighbour Tm with
SantaLucia salt correction, 50 mM monovalent salt, 1.5 mM Mg2+, 0.8 mM dNTP,
250 nM primer, forward Tm target 62 C, reverse 58 C, overlap 42 C, overlap
window 18 nt, forward length 18-39 nt, reverse 19-27 nt, mutation held at least
4 nt from the 3' end of the overlap). Tm tolerance defaults to plus or minus
4.0 C, GC to 40-60 percent, and the codon strategy defaults to `closest`
(fewest nucleotide changes first) against the *E. coli* usage table, with
`optimal` (highest organism usage first) as the alternative. Overlap mode is
`partial` (Gibson style) by default; `full` is the NEB Q5 SDM geometry.
The canvas states the two rejection tiers as one bold phrase, advisory
penalties and hard rejects; the split is here. Every candidate pair is first
put through primer3 thermodynamics, which reports melting temperature, hairpin
formation and homodimer formation for each primer, and those hairpin and
homodimer figures ride back on the response beside the Tm. Advisory checks
score a candidate without discarding it: an oligo synthesis score out of 100
(deductions for homopolymer runs of 4 or more,
G/C runs of 6 or more, dinucleotide repeats of 8 bases, and GC below 30 or above
70 percent), a 3-prime G/C clamp check over the last 5 bases with at most 3 G/C,
and a vendor-specification check against the manufacturer window carried by the
profile (for KOD, 22-35 nt, GC 45-60 percent, Tm above 63 C, Toyobo KOD One
KMM-101/201). Hard rejects are the Tm window, the primer length window, and an
off-target scan of the template that discards a Tm-valid and length-valid pair
outright. Ranking is by penalty, and a variant that survives no candidate enters
the rescue cascade. The ranked pairs are then seated onto 96-well plates in
order, which is the plate mapping the 8 by 12 hairline grid in lane A states.
Batch export writes one dated folder holding eight files: a Macrogen plate
oligo `.xls`, a primers `.fasta`, an Echo cherry-pick `.csv` and
`.xlsx`, a Janus worklist `.csv` and `.xlsx`, a plate map `.xlsx`, and a
`run.json` carrying the run manifest. Every KURO workbook also carries a hidden
`__kuma_meta__` sheet, and single-file exports carry a sibling `.sha256`.

Lane B (BUILD) is bench work, drawn grey because kuma does not perform it.
The four steps are site-directed PCR with the ordered primers, transformation
of the PCR product, colony picking into 96-well plates (the well granularity
every later verdict and activity value is reported at), and a Nanopore run
under MinKNOW. The dashed ribbon between the lanes is the project bridge,
where the expected-variant
workbook crosses from design to verification and MAME matches a dropped KURO
workbook on `project_id`.

Lane C (TEST) is the MAME verification engine. A MinKNOW run folder, a
single-record reference FASTA, a custom barcode workbook and the expected-variant
list enter. Reads are taken from `fastq_pass/<barcode*|NB*>/` and both `*.fastq`
and `*.fastq.gz` are read. An amplicon reference is extracted, reads are aligned
with the bundled minimap2 2.30 (r1287) command-line binary under the `map-ont`
preset, and hits are kept at MAPQ 25 or better covering at least 0.98 of the
reference. Forward and reverse index barcodes are matched with edlib at an edit
distance of at most 0.25 of the barcode prefix length, and each hit is sliced
with 30 bp of flanking sequence. Per-well consensus is a Phred-aware majority
call: bases below Q10 are dropped from the pileup, and reference positions below
depth 3 are not called. Translation and comparison against the expected list
produce one of eight verdicts, PASS plus seven failure modes (AMBIGUOUS, MIXED,
FRAMESHIFT, MANY, LOWDEPTH, NO_CALL, WRONG_AA). One run leaves two files. The
first is the verdict workbook, named on the frontend as date, source token,
`MAME` and verdict count, and it is the primary record of the run. The second
is the pick list, the same stem plus `_picks.csv`, written automatically beside
it. The pick list holds one row per designed variant, chosen by walking the
verdict classes in priority order and breaking a tie between plates on the
lower bound of read support, with the lowest native barcode winning an exact
tie; where one mutant occupies several wells of a plate, the better verdict
takes the plate. The eight-column robot worklist, the `_janus` token beside the
same workbook, is written only by a manual export from the instrument screen,
because a worklist states a deck that describes the room at export time.

Lane D (LEARN) closes the loop. Activity measured on the picked colonies enters
as a long-format CSV or Excel sheet whose columns are `well_id`, `value`,
`plate_id` and `replicate_idx`; `well` and `sample name` are accepted aliases
for the first, `area` and `activity` for the second, `plate_id` is derived from
the declared plate when a single plate is known, and `replicate_idx` defaults
to 1. Two fields carry the answer. `fold_change` is the well mean over the
wild-type mean, and `log2_fc` is its base-2 logarithm. The EVOLVEpro CSV export
writes `log2_fc` into the `y_pred` column beside `variant`, `round_n`,
`plate_id`, `well_id`, `activity_raw_mean` and `activity_raw_sd`; the Excel
export path uses `fold_change` directly.
Rows without a passing NGS verdict, wild-type rows, and rows with no fold change
are written to a sibling `.excluded.csv` with the reason. The red rail returns
those scores to lane A as the variant list for round N+1.

Colour carries three meanings and nothing else: yellow marks an artefact that
crosses an ownership boundary, grey marks a passive state, and red marks the
single return loop. Grey runs in two tiers, both keyed at the foot. The lighter
tier marks work performed outside kuma, which covers lane B and the activity
assay slot in lane D. The darker tier marks a verdict class other than PASS,
which fills the seven failure modes in the verdict block while PASS alone keeps
a white fill and a bold label. A single asterisk marks a file every run
writes and a double asterisk one that only a manual export writes, both keyed
at the foot. An optional structure side-channel (UniProt, AlphaFold, PDB,
ESMFold) supplies domain and active-site residues; mean pairwise
C-alpha distance over the mapped positions drives structural-diversity selection,
scored against a null distribution by the dispersion module.

The figure is drawn to fit one A4 portrait page. A4 measures 210 by 297 mm, and
with 20 mm margins on four sides and 30 mm held under the figure for this
caption the block available is 170 by 227 mm. The 1112 by 1485 unit canvas
fills that block exactly, at 0.152862 mm per user unit (0.43329 pt), so the
body type of 21 user units prints at 9.10 pt and clears the 9 pt floor of the
house ladder. The rest of the ladder: foot key 18 uu (7.80 pt), band and lane-D
slot titles and engine names 22 uu (9.53 pt), the ribbon title 24 uu
(10.40 pt), box titles 26 uu (11.27 pt), lane words 30 uu (13.00 pt) and lane
letters 46 uu (19.93 pt). Box widths come from a table of real Source Sans 3
advance widths frozen as a constant in the builder and generated once by
`scripts/gen-font-metrics.py`, so one set of numbers drives both the layout and
the box-fit check while the committed SVG stays byte-identical on any machine.
The builder asserts the A4 fit and the 9 pt floor on every run and fails the
build when either slips. The compact variant is a screen artefact for a README
and claims no print width; at a 900 CSS px render its body type is 11.25 px.

---

## Provenance

Every value above, cited to the working tree. Paths are relative to the
repository root.

| Claim | File and line |
| --- | --- |
| Accepted template formats `.gb` `.gbk` `.gbff` `.dna`, plain FASTA refused | `kuma_core/kuro/sdm_engine.py:1758-1781` |
| Default polymerase profile is KOD (sidecar request models) | `python-core/sidecar_kuro/models.py:52`, `python-core/sidecar_kuro/models.py:89` |
| Default polymerase profile is KOD (frontend fresh state and Reset) | `src/lib/polymeraseAliases.ts:20` |
| KOD Tm method and salt model, 50 mM, 1.5 mM, 0.8 mM, 250 nM | `kuma_core/kuro/resources/polymerase_profiles.json:145-155` |
| KOD Tm targets 62 / 58 / 42 C, 3-prime distance 4, overlap 18, lengths 18-39 and 19-27 | `kuma_core/kuro/resources/polymerase_profiles.json:156-164` |
| KOD vendor specification 22-35 nt, GC 45-60, Tm above 63, Toyobo KMM-101/201 | `kuma_core/kuro/resources/polymerase_profiles.json:181-188` |
| Tm tolerance default 4.0 C, GC default 40-60 percent | `python-core/sidecar_kuro/models.py:62`, `python-core/sidecar_kuro/models.py:66-67` |
| Codon strategy default `closest`, organism default `ecoli` | `python-core/sidecar_kuro/models.py:55-56` |
| `closest` is fewest nucleotide changes, `optimal` is highest organism usage | `kuma_core/kuro/codon_table.py:206-222` |
| Overlap mode default `partial` (Gibson), `full` is NEB Q5 SDM | `python-core/sidecar_kuro/models.py:75-76` |
| Overlap window default 18 nt, upstream of the mutant codon | `kuma_core/kuro/overlap.py:21-31`, `kuma_core/kuro/sdm_engine.py:175` |
| Synthesis score deductions (homopolymer 4, GC run 6, dinucleotide 8 bases, GC below 30 or above 70) | `kuma_core/kuro/sdm_engine.py:242-295` |
| Synthesis score is advisory, warning plus penalty, never a reject | `kuma_core/kuro/sdm_engine.py:298-311` |
| 3-prime G/C clamp window 5, at most 3 G/C, warning only | `kuma_core/kuro/sdm_engine.py:321-325` |
| Vendor-specification check is warning only | `kuma_core/kuro/sdm_engine.py:362-366` |
| primer3 thermodynamics: Tm, hairpin, homodimer per primer | `kuma_core/kuro/sdm_engine.py:208-225` |
| Hairpin and homodimer figures ride back on the response | `python-core/sidecar_kuro/models.py:276-281` |
| Off-target scan discards Tm-valid and length-valid pairs | `kuma_core/kuro/sdm_engine.py:706`, `kuma_core/kuro/sdm_engine.py:1617-1618` |
| Batch export writes eight files into one dated folder | `python-core/sidecar_kuro/handlers/export.py:1027-1034`, `python-core/sidecar_kuro/handlers/export.py:1046-1127` |
| Batch export file names (macrogen .xls, primers .fasta, echo .csv and .xlsx, janus .csv and .xlsx, platemap .xlsx, run.json) | `python-core/sidecar_kuro/handlers/export.py:1027-1034` |
| `run.json` carries the run manifest | `python-core/sidecar_kuro/handlers/export.py:789-830`, `python-core/sidecar_kuro/handlers/export.py:1125-1127` |
| Hidden `__kuma_meta__` sheet on KURO workbooks | `python-core/sidecar_kuro/handlers/export.py:354-362` |
| Sibling `.sha256` on single-file exports | `kuma_core/shared/output_hash.py:1-20`, `python-core/sidecar_kuro/handlers/export.py:389`, `python-core/sidecar_kuro/handlers/export.py:446`, `python-core/sidecar_kuro/handlers/export.py:554` |
| MAME matches a dropped KURO workbook on `project_id` | `kuma_core/mame/io/kuma_meta.py:27-40` |
| Reads come from `fastq_pass/<barcode*|NB*>/`, both `.fastq` and `.fastq.gz` | `kuma_core/mame/ingest/demux.py:71`, `kuma_core/mame/ingest/sort_barcode.py:35` |
| minimap2 2.30 (r1287), bundled CLI, `map-ont` preset | `python-core/scripts/vendor-minimap2.py:33-34`, `kuma_core/mame/ingest/align.py:1-11`, `kuma_core/mame/ingest/align.py:348-351` |
| MAPQ default 25 | `python-core/sidecar_mame/models.py:62` |
| Coverage fraction default 0.98 | `python-core/sidecar_mame/models.py:63` |
| Barcode edit-distance ratio default 0.25 | `python-core/sidecar_mame/models.py:64` |
| Flanking slice default 30 bp | `python-core/sidecar_mame/models.py:65` |
| Consensus drops bases below Q10 | `kuma_core/mame/ingest/consensus.py:22-26`, `kuma_core/mame/ingest/consensus.py:396` |
| Minimum depth default 3 | `kuma_core/mame/ingest/run_pipeline.py:127`, `kuma_core/mame/ingest/combinatorial_demux.py:2061` |
| One run writes the verdict workbook and the pick list beside it | `python-core/sidecar_mame/handlers/analyze.py:1510-1517`, `python-core/sidecar_mame/handlers/analyze.py:2507` |
| Verdict workbook name: date, source token, MAME, verdict count | `src/lib/mameFilename.ts:29-41` |
| Pick list is the workbook stem plus `_picks.csv` | `python-core/sidecar_mame/handlers/analyze.py:535-553` |
| Robot worklist carries the `_janus` token and only a manual export writes it | `python-core/sidecar_mame/handlers/analyze.py:549-552`, `python-core/sidecar_mame/handlers/export.py:279-315` |
| Best replicate: verdict priority, then read-support lower bound, then lowest native barcode | `kuma_core/mame/select/best_pick.py:136-172` |
| Better verdict wins a within-plate collision | `kuma_core/mame/pipeline.py:325-334` |
| Eight verdict classes and their names | `kuma_core/mame/models.py:10-21` |
| Activity long-format columns and aliases | `kuma_core/mame/activity/ingest_long_csv.py:41-42`, `kuma_core/mame/activity/ingest_long_csv.py:92-123` |
| `fold_change` is the well mean over the wild-type mean, `log2_fc` its base-2 logarithm | `kuma_core/mame/activity/join.py:172-173`, `kuma_core/mame/activity/normalize.py:54-70`, `kuma_core/mame/activity/models.py:131-132` |
| The Excel export uses `fold_change` directly | `kuma_core/mame/activity/export_evolvepro.py:141-148` |
| `log2_fc` is written to the `y_pred` column | `kuma_core/mame/activity/export_evolvepro.py:66` |
| EVOLVEpro CSV column list | `kuma_core/mame/activity/export_evolvepro.py:12-21` |
| Excluded rows and their reasons go to `.excluded.csv` | `kuma_core/mame/activity/export_evolvepro.py:50-58`, `kuma_core/mame/activity/export_evolvepro.py:73-88` |
| Mean pairwise C-alpha distance against a null distribution | `kuma_core/kuro/dispersion.py:4`, `kuma_core/kuro/dispersion.py:79`, `kuma_core/kuro/dispersion.py:122` |
| Ranked pairs are seated onto 96-well plates in order (column order A1 to H1 to A2 by default) | `kuma_core/kuro/plate_mapper.py:1-53` |
| A4 portrait figure block 170 x 227 mm, 9.10 pt body, type ladder | `scripts/build-overview-figure.py:19-37` |
| Advance widths read from Source Sans 3 3.052 and frozen as a constant | `scripts/gen-font-metrics.py:1-14`, `scripts/build-overview-figure.py:122-167` |
| A4 fit and the 9 pt floor are asserted on every run | `scripts/build-overview-figure.py:979-1000` |
| Compact variant is a screen artefact, 900 px arithmetic | `scripts/build-overview-figure.py:1050-1061` |

### One stale string left in the code, flagged

The canvas now reads `order, robot bundle / 8 files`, matching the handler,
which names eight output files and attempts all eight
(`python-core/sidecar_kuro/handlers/export.py:1027-1034` and the eight `_try`
calls at `python-core/sidecar_kuro/handlers/export.py:1046-1127`). The handler
docstring at `python-core/sidecar_kuro/handlers/export.py:979` still says
"6-file", which is where the old figure number came from. That docstring is a
code change rather than a figure change and is left for whoever owns the
handler.
