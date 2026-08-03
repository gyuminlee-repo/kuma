# Changelog

## v0.14.4 (A row per well, and a project that says when it disagrees with itself)

v0.14.3 put the expected sheet in plate order and stopped there. Order is only half of it. `export_excel` takes `mappings` from the UI, which carries the wells filled while relaxing conditions on a failed mutation, and `results` from the design state, which does not. A filled well therefore had a primer and no row, and dropping that row renames every later well. `V263I` at C7 of the 260722 R2-1 export is one: a forward primer, a reverse partner, and nothing in `expected_mutations`. Ordering 94 rows against 95 wells still misplaces everything from C7 on.

### Fixed

- v0.14.4: `expected_mutations` carries one row per plate well. A well whose mutation has no design result is written from its mapping, taking the residues from the notation and the codons from the mapping when it has them, leaving the rest empty rather than inventing it. Row count now equals well count, which is the property MAME depends on and the one v0.14.3 left unchecked.
- v0.14.4: The column picker on the MAME variant input is disabled while the KURO reader sheet is selected, and says why. It was live but inert: that path always reads `mutant_id` and applies the status filter first, so a chosen column changed nothing.

### Added

- v0.14.4: Loading a project reports an expected workbook that disagrees with itself. The plate sheets and `expected_mutations` in one file are the same statement written twice, and a workbook exported before v0.14.3 can have them differ. Nothing failed when they did: every well got a variant and the verdicts came out scored against a plate nobody built. The message names the well and both readings. A file missing either sheet is reported as not comparable rather than as consistent, so silence cannot be read as agreement.

### Changed

- v0.14.4: The well-layout controls state one precedence rule instead of two contradicting ones. `Sample Map` was described as the authority in one hint and as overridden in another, and which won depended on the order the two controls were touched. Both now say what the code does: a built layout, then the sample map, then the inference. The hint also says the inference happens on its own, so the button previews and pins that assignment rather than being a step to remember.

## v0.14.3 (The expected list is written in plate order)

A KURO export described two different plates. The `Fwd List` and `Fwd Plate` sheets are written from the plate mapping, so their order is the well order, while `expected_mutations` iterated the design output, whose order is whatever ranking produced it. On the 260722 R2-1 export both sheets carry the same 94 mutants and disagree on where they sit: the primer list puts `K53I` at A2, the expected sheet puts `I92D` there.

MAME reads row *i* of `expected_mutations` as well *i*, so it scored that plate against a list nobody built. Well `1_2` held K53I and was judged WRONG_AA for missing I92D, which is five rows away at `6_2`. Wells whose read depth fell under the gate reported LOWDEPTH instead, which hid the same mismatch rather than fixing it.

### Fixed

- v0.14.3: `expected_mutations` is written in the order the plate sheets use. The forward mappings carry the well order and the sheet now follows them, so one workbook describes one plate and a change to the primer ordering moves both together. A designed mutation with no forward mapping keeps its place at the end rather than being dropped. Reading an already-exported workbook is unchanged, so a file written before this still needs its sheet chosen by hand.
- v0.14.3: Naming a sheet on the MAME variant input overrides the KURO recognition instead of being discarded. A workbook carrying an `expected_mutations` sheet was routed to the strict reader before the choice was consulted, so pointing at the sheet that describes the bench plate silently read the other one. Naming no sheet, or naming `expected_mutations`, behaves exactly as before.
- v0.14.3: The variant input offers sheets and headers for a KURO export too. The picker was hidden entirely for those files, so there was nothing to override with. The strict sheet stays selected by default.

## v0.14.2 (Three features the app never announced)

No behaviour changes here. The Echo quadrant selector, the plain variant-list input and the run-report fix all shipped in the v0.14.0 build, but none of them was written into the release notes, so What's New has never mentioned that they exist. This release carries the announcement. The full write-up sits in the v0.13.39.2 to v0.13.39.4 section.

### Added

- v0.14.2: Shipped in v0.14.0 and announced now: the Echo source plate quadrant is selectable as A1, A2, B1 or B2, which is the set of starting points a 96-head can actually reach on a 384 plate. Choosing one fixes forward and reverse as a row-parity pair, and leaving it unset keeps the previous mapping.
- v0.14.2: Shipped in v0.14.0 and announced now: MAME accepts a plain variant list, one variant per row in file order, as csv, tsv or xlsx with the sheet and column chosen on screen. A workbook holding an `expected_mutations` sheet still takes the original path unchanged.

### Fixed

- v0.14.2: Shipped in v0.14.0 and announced now: a run report no longer comes out blank or refuses to write. A restored session seeds the export path from its own snapshot, and an analysis that found no wells is refused with the inputs to check rather than saved as an empty report that reads like a finished run.

## v0.14.1 (Frameshift is judged from the consensus)

A well whose consensus aligns to the reference without a single gap was being called FRAMESHIFT. The gate read the median net indel across raw reads rather than the net indel of the consensus, and ONT reads carry frequent single-base indel errors, so on a run where that median lands at one base the gate fired almost everywhere. Building a consensus is what averages those errors away, so the verdict was reading the very signal the consensus exists to remove.

### Fixed

- v0.14.1: Frameshift is decided from the consensus. The net indel now comes from the same majority vote that calls the bases, counting deletion-majority reference positions and majority insertion length. The per-read median is kept as a quality metric under a separate header key and no longer reaches the verdict. On the reference workload this moves 91 passing wells to 150; every one of the 83 wells that left FRAMESHIFT was checked to be gapless and full length, and every one of the 59 newly passing wells has an observed mutation matching its design. Real frame-breaking indels are still caught, and the tests that pin them pass unchanged.
- v0.14.1: The consensus and per-read figures are written as separate FASTA header keys. A file written by an earlier version keeps its old key read as the per-read metric, so reprocessing it does not re-condemn the same wells.

## v0.14.0 (MAME step 2 finishes a whole sequencing run)

Step 2 could not complete a full run on a 15 GiB machine. Peak memory grew with input size, because a whole native barcode of read slices was held until consensus, and a whole well was then flattened into one array per aligned base. A 5.9 GB run now peaks at 4.6 GB and completes. Measuring that also surfaced two defects that changed reported numbers, and both are fixed here.

### Fixed

- v0.14.0: Read chunk boundaries changed the result. Reads were renumbered from zero on every aligner call, and minimap2 seeds its per-read random state from a hash of the query name, so the same read got a different effective seed depending on which chunk it landed in. The shipped default splits a barcode of roughly a million reads into about 25 chunks, so production runs were already affected. Read numbering is now global across chunks, and every chunk size produces the same output.
- v0.14.0: The minus-strand consensus cursor started at the original-orientation query offset after the read was reverse complemented, which only holds when the leading and trailing clips are symmetric. In the reference workload 26 of 7779 minus-strand alignments had asymmetric clips and voted into the pileup at chance-level identity, meaning pure noise. Consensus sequences and verdicts on that data are unchanged; nine wells report different header quality metrics and one shallow well loses a noise-induced mixed position.
- v0.14.0: `assigned_reads` was undercounted and `chimera_splits` overcounted, because the first-hit flag was cleared even when a hit failed. In the reference workload 857 reads move from the second counter to the first. Sequence output is unaffected. A resume marker written by an earlier version still carries the old totals.
- v0.14.0: Step 2 no longer holds a whole barcode of read slices, or a whole well of pileup arrays, at once. Both are processed in bounded batches whose size is derived from the memory limit divided by the number of concurrent workers, reading a cgroup limit ahead of total system memory so a container does not size itself against host RAM.

### Changed

- v0.14.0: Step 2 is faster, mostly on setups where the output folder sits on a network or translated filesystem. Against a Windows share the reference workload goes from 21.2 s to 8.6 s end to end, with the analyze stage falling from 5.4 s to 0.7 s. On a local ext4 disk the same workload goes from 9.4 s to 7.6 s. Per-file durability calls, repeated directory scans and duplicate metadata lookups were the bulk of it, so a purely local disk sees the smaller share of the gain.
- v0.14.0: Consensus cost per aligned base no longer rises with well depth. It was climbing 1.9x between depth 50 and depth 3200 and is now flat.
- v0.14.0: Demux workers hand freed cores back to whichever native barcode is still running, so an uneven plate stops leaving cores idle once the smaller barcodes finish.

## v0.13.39.2 to v0.13.39.4 (Three items from the 260731 revision list)

Three requests arrived together and merged the same day, and this section is written afterwards because none of them was recorded at the time. They first shipped in the v0.14.0 build. The first of the three carried a `v0.13.39.1` label that was already taken by the raw-run path fix below, so it is grouped here rather than given a version of its own.

### Added

- v0.13.39.3-4: The Echo source plate quadrant is selectable as A1, A2, B1 or B2. A 96-head is on a 9 mm pitch and a 384 plate on 4.5 mm, so one stamp reaches every other row and every other column, and exactly four starting points exist. The previous mapping doubled the row and kept the column, which fills rows A-P against columns 1-12: reachable by hand but not by the head that actually makes the plate. Choosing a quadrant fixes forward and reverse as a row-parity pair, so A1 puts reverse at B1, and two pairs fill one plate, which is the `2 round primer set / 1 Echo source plate` working concept. Leaving the choice unset keeps the old mapping unchanged. Where a plate is part used, the operator states which quadrants are gone rather than the app guessing, and dispensing onto a used quadrant is refused rather than warned about, because the primers already there would be lost.
- v0.13.39.1: MAME accepts a plain variant list instead of only a KURO export. A workbook holding an `expected_mutations` sheet still goes to the original reader untouched, so status filtering and codon fields behave exactly as before; anything else is read as one variant per row in file order, and csv and tsv are accepted too. Of the ten columns the old format required, only `mutant_id`, `status` and the `wt_aa`/`position`/`mt_aa` triple are read anywhere downstream, so relaxing the shape costs no behaviour. A WT row is recognised rather than parsed as a variant, and a list carrying its own control does not get a second one added.

### Fixed

- v0.13.39.2: A run report no longer comes out blank or refuses to write. Two paths produced the same complaint. The verdict table on screen is restored straight from the autosave snapshot, while every export reads a separate sidecar copy that was filled only from a result file, and a missing or unreadable result file failed silently: the table looked fine and the export then refused with `No prior analyze result`, writing nothing and warning no one. The snapshot now seeds the sidecar through the same load path when the result file cannot be read. Separately, an analysis finding no wells produced an empty verdict list that passed the null guard, and the renderer built a complete report scaffold with every count at zero and an empty plate map, which opens and reads like a finished run. That is now refused with a message naming the inputs to check.

Portable snapshot paths landed in v0.13.35.4, but two of them sit nested inside the raw-run parameters and were missed, so a moved project lost its custom barcodes and sequencing summary without saying so.

### Fixed

- v0.13.39.1: The custom barcode table and sequencing summary paths are stored relative to the project folder like every other input. Thresholds and length settings in the same block are not paths and are untouched. Older snapshots keep reading as absolute.

## v0.13.39 (Autosave survives a hard exit and a bad save)

Project folders became portable in v0.13.35.4, and a moved project re-detects its inputs since v0.13.38. Two ways of losing work were left.

### Fixed

- v0.13.39: Autosave is flushed when the app closes. The flush existed but nothing called it on the close path, so edits made inside the 1.5 second debounce window were lost on exit. Both autosave subscriptions now register the shutdown step themselves instead of depending on the screen to wire it.
- v0.13.39: The previous snapshot is kept before each overwrite, three generations deep, at most one every five minutes so the copies point at genuinely different times. Autosave used to overwrite a single file, leaving no way back from a bad save.
- v0.13.39: Inputs that a restore cannot recover are listed in a banner naming each one, and it stays until each is pointed at its new location. They were previously blanked behind a status message that disappeared after four seconds. A replacement that does not look like the original raises a warning, since attaching a same-named but different sequencing run is the mistake this guards against, while a deliberate replacement is still accepted.

## v0.13.38 (Reopening a moved project finds its files again)

Autosave records the absolute paths picked in a file dialog. Opening the project from a new folder, or on another machine, left those paths pointing at nothing. Auto-detect could not step in, because it only fills fields that are empty and a dead path is not empty.

### Fixed

- v0.13.38: Restored MAME input paths are checked before use. Ones that no longer resolve are cleared, so the existing auto-detect finds the same files inside the project again. A path whose check fails outright is kept, because a permission error or a slow network drive is not evidence that the file is gone.
- v0.13.38: Inputs that auto-detect cannot recover, a raw MinKNOW run folder outside the project being the common case, are named on screen. Previously they were blanked with no notice.
- v0.13.38: A sequence file that cannot be reopened during restore is reported by name. It used to fail into the console only, leaving a project that looked fully restored but had no sequence loaded.

## v0.13.37 (KURO exports land in the project)

MAME started routing its generated files through the open project. KURO did not, so a design exported from the same project could end up anywhere the last save dialog happened to point, and nothing downstream knew the files existed.

### Fixed

- v0.13.37: Export All opens on the project design folder and creates it first, so a project that has never been exported to is still a valid destination. Choosing somewhere else still works and behaves as before.
- v0.13.37: The files Export All writes are recorded in the project manifest, each under a type taken from its filename suffix. Steps that look for an earlier output can now find one. Files with an unrecognised suffix are skipped rather than filed under a guess, and a recording failure reports itself without turning a finished export into an error.

## v0.13.35 (Release version sync)

### Fixed

- v0.13.35: Release metadata now stays aligned across the frontend package, Tauri app, Python package, and Cargo lockfile so CI catches no version drift during tagged builds.
- v0.13.35: The release notes and in-app What's New source are refreshed for the current patch release instead of carrying the previous release version.

## v0.13.33 (Two step 3 inputs, chosen one at a time)

A single toggle named Activity source was deciding two unrelated things at once: what the primary screen measurement arrives as, and how the confirmation report labels its samples. Naming the pairs as modes collapsed six real combinations into two.

### Fixed
- v0.13.33: The step 3 inputs are chosen on their own axes. The one that mattered was a raw primary screen report paired with a numeric-index confirmation, which no mode could express and which is what arrives once Agilent reports come off the instrument without variant names in the sequence table. The five builders were already split along both axes, so this opens the pairs rather than adding arithmetic. A single entry point takes each axis independently and enforces only the companion each genuinely needs: a well-labelled primary screen needs the plate layout, a numeric-index confirmation needs a rank source. Both previous functions remain as thin wrappers with signatures, warnings, and error strings intact. (#187)
- v0.13.33: `prev_evolvepro_xlsx` meant opposite axes in the two previous functions, a rank source in one and a primary screen baseline in the other. The unified entry point separates them. (#187)
- v0.13.33: The provisional badge appears for a prev-EVOLVEpro primary screen with no confirmation. `confidence` is only emitted on the legacy rank branch, so that pair was provisional in fact and unmarked on screen. The badge now derives from the confirmation axis, and the panel names the pair it built from. (#187)

### Changed
- v0.13.33: An NGS verdict file now applies to every input combination. It carries no axis constraint in the backend, and its previous reports-only visibility was a side effect of the toggle. Callers that sent a GC data sheet together with a verdict file previously had the verdict ignored and will now see gating applied. (#187)

## v0.13.32 (Step 3 inputs named after what they hold)

A user reading the step 3 panel could not find where the triplicate re-measurement goes, asked why a primary screen source was needed at all, and pointed out that EVOLVEpro writes CSV so a request for an xlsx looked wrong. Every one of those traces back to a label rather than to behaviour.

### Fixed
- v0.13.32: The step 3 input labels say what each file is. `Round-1` read as the EVOLVEpro active-learning round when it meant the first pass over the whole plate, two senses the project notes already record as being confused. The panel had the right vocabulary in its own mismatch hints, a 1-replicate primary screen against a 3-replicate confirmation, so the labels adopt that pair and `round` leaves this panel. Both EVOLVEpro fields now state they want the input xlsx KUMA built and that the result CSV EVOLVEpro writes is a different file, which is what made the xlsx request look wrong. The confirmation report is optional so the provisional path stays open, and its helper says it is nonetheless what the panel exists for. `confirmedLabel` and `nAuthoritative` referred to a `rep-batch` name no longer on screen and were brought along. Values only across all ten locales, no key renamed and no component logic touched. (#185)

## v0.13.31 (Work that survives a crash, a structure you can supply yourself, and a selector that says what it changes)

Seven versions since the last tag. The theme running through them is a gap between what the app appeared to do and what it did: autosave that saved nothing for users who never made a project file, a polymerase selector named after a Tm preset it does not switch, a 3D panel reporting active while computing in one dimension, and a MAME verdict calling thin wells contaminated.

### Fixed
- v0.13.30.6: Autosave keeps work for projects that were never saved to a file. It returned early for scratch projects, so a user who had not created one had nothing saved and no save button. Scratch autosave now writes to the app data directory, gated on the KURO kind so MAME autosave is untouched. The snapshot schema also carries the nine result fields it used to drop, and schema 1 snapshots still load. (`src/lib/autosave.ts`)
- v0.13.30.6: A moved template no longer kills the whole restore. Restore called `load_fasta` unguarded, so a template that had been moved aborted the settings, the computed output, and the UI restore together. The failure is now contained, its cause reaches the status bar, and auto-redesign is skipped.
- v0.13.30.6: Step 2 no longer crashes on a pandas-written file. `df.to_csv(path)` writes an unnamed index column, and Radix throws on an empty `SelectItem` value from the component body, on the render right after preview and without anyone opening the dropdown. Headers map to index sentinels and the empty column stays listed, labelled unnamed.
- v0.13.30.6: Loading a different template clears the previous protein primers. Residue numbers are CDS-relative, so keeping them across a template change showed numbers that belong to another sequence.
- v0.13.30.6: The 3D panel stops claiming to be active while using distance in one dimension. A loaded structure file lives in a different slot than a UniProt accession, so its coordinates never reached the sidecar, and because they never arrived the frame guard never ran either.
- v0.13.30.6: A sidecar left running during an update no longer bricks the install. A live exe holds a Windows file lock, the installer skips it, and the stale binary then fails every integrity check. KURO and MAME are stopped before the installer runs, integrity failures name a recovery step, and sidecar stderr lands in a rolled log file instead of being truncated away.
- v0.13.30.2: A mixed MAME signal below three times the minimum read count reports LOWDEPTH rather than MIXED. At low depth a few minor-allele positions are indistinguishable from ONT error, so thin wells were published as confident contamination. (`kuma_core/mame/compare/verdict.py`)
- v0.13.30.2: The single-hit demux path honours `coverage_fraction` instead of collapsing it to `require_full_span=(coverage_fraction >= 1.0)`, which disabled the span filter at the 0.98 default. (`kuma_core/mame/ingest/combinatorial_demux.py`)
- v0.13.30.2: The read-length window scales with the amplicon. A fixed 30 bp window is about 1.7 percent of a 1.8 kb amplicon, far tighter than the ONT indel spread, so genuine full-length reads were discarded. On the ispS run it widens from 1765 to 1825 into 1615 to 1975. (`kuma_core/mame/ingest/quality_filter.py`)
- v0.13.30.2: The QC panel appears for MIN114 runs. Three MinKNOW health parsers returned nothing on real MIN114 column names, so a run with valid metadata showed no panel at all. (`kuma_core/mame/health.py`)
- v0.13.30.4: The What is New bundle is regenerated where the version bump happens. It went stale in two consecutive releases and both times the tag build would have died in quality gates, because the post-commit hook rewrites `package.json` (a generation input) and amends without regenerating. The three-stage `sync:check` also no longer short-circuits, so a later stage failing cannot hide behind an earlier stage passing. (`scripts/sync-version.sh`, `scripts/sync-check-all.mjs`)

### Changed
- v0.13.30.3: The polymerase selector states what it actually controls. The design Tm has run on one fixed SantaLucia 1998 scale for every polymerase since v0.13.19, but the selector was labelled a Tm calculation preset, so choosing KOD read as if the design Tm switched formula. NEB calibration applies to Ta only.
- v0.13.30.3: Switching polymerase now reports the GC range or overlap mode it overwrote instead of changing them silently. Enzymes differ on both, so a switch could change which primer is selected, or the design algorithm itself.
- v0.13.30.3: The Benchling profile is retired. It named a Tm scale rather than an enzyme, and it was both the default selection and the only profile allowing GC 30 to 70 while the other seven allow 40 to 60. The default is now KOD and seven profiles remain. A saved state carrying Benchling migrates to KOD with its stored GC range and overlap mode preserved, and reports the switch. Reproducing an older Benchling design stays possible by entering GC 30 to 70 in Advanced Options.
- v0.13.30.6: A user-predicted structure can be loaded directly. AlphaFold DB is keyed by UniProt accession, so a construct matching no entry exactly has no structure there, and ESMFold refuses sequences over 400 residues. PDB and mmCIF are parsed with the standard library, an AlphaFold Server zip picks its best model by ranking score rather than filename order, and the frame guard verifies the file against the CDS without a network call.
- v0.13.30.7: The dead `activity.export_evolvepro_csv` RPC layer and five unused MAME activity wrappers in `src/lib/ipc.ts` are gone, along with two orphan locale keys. Nothing changes at runtime: the store already called `sendRequest` directly, and the xlsx export path is untouched. The core `export_evolvepro_csv` function stays, since the round-trip integration test uses it to pin the column agreement between the MAME writer and the KURO reader.
- v0.13.30.5: The rescue and consensus documents describe what ships. They claimed `tol_max` defaults to 3 degrees when the engine has used 4 since v0.13.23, and a three-pass auto-relax cascade that does not exist.

### Known issues
- Golden Gate stays out of the build pending a go or no-go decision, and the branch holding it also carries the reverted original feature.
- Combo measurements stay out of the EVOLVEpro input, unchanged from v0.13.30.
- `251001_report.xlsx` remains a format exemplar rather than the round-1 measurement for the IspS campaign, unchanged from v0.13.27.

## v0.13.30 (The sample map the lab fills in now works end to end)

`05_mame_sample_map.xlsx` names every well `<sample>_r<n>` and marks empty wells `blank`. The layout parser read those literally, so a filled-in template produced no usable variants at all. Two independent reasons, fixed together.

### Fixed
- v0.13.30: The layout parser reads the replicate suffix the lab writes. A trailing `_r<n>` is stripped and the remaining text is the sample name, so `WT_r1` is WT and `Q232A_r1`, `Q232A_r2`, `Q232A_r3` collapse onto one mutant whose three wells accumulate as replicates. Only the trailing suffix goes, which keeps `A40P_E61Y_r1` intact as `A40P_E61Y`. Rows named `blank` are dropped. Names without a suffix behave exactly as before. (`kuma_core/mame/activity/plate_layout_xlsx.py`)
- v0.13.30: A variant that cannot become EVOLVEpro short notation no longer kills the build. Short notation is one position plus one residue, so a double substitution has no token, and `to_evolvepro` raised on it. Both fallback builders called that unguarded, so a single combo variant in a layout aborted everything and the singles beside it produced nothing. The conversion failure is now caught per mutant, that mutant alone is dropped, and one warning names it with its wells. (`kuma_core/mame/activity/build_evolvepro_input.py`)

### Known issues
- Combo measurements stay out of the EVOLVEpro input. The activity is read and the wells parse, but the value never reaches the next round, which matters as combinatorial variants grow in number. Giving them a short-notation form needs confirming what the external EVOLVEpro accepts, so it is deliberately left open.
- `to_evolvepro` and the multi-mutation parser in `kuma_core/kuro/mutation.py` disagree on the separator. The parser handles `A40P/E61Y` while the templates write `A40P_E61Y`.

## v0.13.28 (Files the lab already has, and a shared primer that reaches every well)

Three complaints, one shape: KUMA asked for a file or a column name the user did not have, and called the mismatch a bad file. A fourth item is worse than a complaint, since it produced a plausible looking export with primers missing from it.

### Fixed
- v0.13.28: Step 2 accepts mutation files whose headers merely differ in case, spacing, or a byte-order mark. Header comparison strips the BOM, trims, and casefolds, while the resolved name stays the original string so row lookup still works. Both the loader and the preview now read CSV as `utf-8-sig`, so the dropdown offers exactly what the loader will find; before, an Excel-exported CSV showed the preview a header the loader could not resolve. (`kuma_core/kuro/evolvepro.py`, `python-core/sidecar_kuro/handlers/misc.py`)
- v0.13.28: Step 2 column pickers work without hunting for the Preview button. The manual mapping panel was always rendered but its two selects were gated on a preview only that button fetched, so a failed auto-detect left two disabled dropdowns under a message reading "Load a file first" for a file already loaded. Choosing a file fetches the preview on its own, the selects survive a failed auto-detect, and the failure message says the columns can be picked below. A stale-response guard keeps a quick file switch from pairing one file headers with another file rows. (`src/components/panels/InputPanel/`)
- v0.13.28: MAME step 3.1 takes the sample map step 1 already produced. It demanded a plate layout workbook with `Mutant` and `Well Pos.` columns that nothing in the codebase writes, while the identical mapping existed as `sample_name` and `well` from `generate_mame_package`. The parser accepts either pair, prefers the plate layout pair when both appear, and says so. (`kuma_core/mame/activity/plate_layout_xlsx.py`)
- v0.13.28: Echo and JANUS exports no longer drop the reverse rows of shared primers. Mutations sharing a reverse primer are keyed through a dedup map; when a workspace carried none, `_build_rev_lookups` rebuilt that map from the already deduplicated list, which holds only each group representative. Every other mutation then failed the lookup and lost its reverse transfer row, meaning a reaction with no primer in it, from an export that otherwise looked complete. Old workspaces reach this through `dedupInfo: ws.dedupInfo ?? {}`. The export handlers now rebuild the map from the design results, and the mapper raises with the affected mutation names rather than dropping rows when rebuilding is impossible. (`kuma_core/kuro/plate_mapper.py`, `python-core/sidecar_kuro/handlers/export.py`)

### Added
- v0.13.28: Echo and JANUS layout sheets report how many reactions each source well feeds and the volume that draws. A shared reverse primer is aspirated once per destination, so a well feeding ten reactions gives up ten times the per-transfer volume, and nothing in the previous exports said so. The machine-readable transfer files are untouched, since their schemas are fixed and the total belongs where a human fills the plate. Dead volume stays out of the arithmetic: neither the Echo picklist nor the JANUS worklist has a field for it, vendor working ranges vary by fluid class, and the sheet says to add the labware figure.

### Known issues
- The required fill volume still needs the labware dead volume added by hand. Both instruments detect a shortfall only at run time, Echo through a survey exception report and JANUS through a liquid level error, which is after the plate is loaded.
- A mutation column named explicitly but absent from the file yields an empty result rather than an error. The dropdown only offers headers the preview returned, so the path is unreachable through the UI.

## v0.13.27 (Step 3 learns to read the instrument, and stops asking a human to normalise first)

MAME step 3 could parse a raw Agilent FID1B report but never use one. The parser had zero production callers, so the only way in was a GC sheet somebody had already divided by WT. The capability lived in an open PR that had gone stale for five weeks against a UI another open PR had since rewritten. Both are landed here.

### Added
- v0.13.27: A raw Agilent report can be the round source. `build_evolvepro_input_from_reports` normalises each replicate as `area / mean(WT block areas)` and is reachable from the plate-layout route through a source toggle, with a second toggle choosing the round-1 baseline between a raw report and a prior EVOLVEpro file. WT blocks are matched on `^WT_?\d+$`; pure-numeric sample names are treated as calibration and skipped. A missing WT block fails loudly rather than falling back. Optional NGS verdict gating drops variants whose well did not pass. (#173, supersedes #120)
- v0.13.27: Step 3 splits into an exclusive input route and cross-round signals, so the genotype path and the plate-layout path no longer share one crowded screen. (#173, supersedes #163)

### Changed
- v0.13.27: The WT denominator comes from the WT replicate rows the instrument ships. Long-format ingest dropped every row whose sample name failed to parse as a well coordinate, which silently discarded the `WT_1`/`WT_2`/`WT_3` blocks present in Agilent exports and forced the genotype route to back out a denominator from plate-designated WT wells instead. Those rows now land in a separate `wt_records` collection, keeping them out of the variant well space, and the join prefers their mean per plate. Plates with no dedicated rows keep the previous behaviour, and `n_wt_replicate_rows` plus `n_plates_wt_from_replicates` report which source applied. This aligns the genotype route with the definition reports mode already used.
- v0.13.27: `MergedRow.relative_activity` is gone. It was declared and read but never assigned, so the export ternary always resolved to `fold_change`, which is the same quantity by construction (`activity_mean / wt_mean`). The dead branch made the code read as if it honoured a separate relative-activity definition that was never wired.
- v0.13.27: The step 3 document is rewritten against the actual parsers and columns. It had claimed a 96-well grid input that no parser implements and named the output columns `mutation`, `activity` when the writer emits `Variant`, `activity`.

### Fixed
- v0.13.27: The two-file provisional build works again after the merge. The mode validator arriving from #120 judged rank mode by `all([gc_data_xlsx, rep_batch_xlsx, prev_evolvepro_xlsx])`, which rejected the layout-plus-GC path main had opened by making the last two optional; a copy of the same guard sat in the handler. Both now key off `gc_data_xlsx`. The regression survived the merge because the existing validator test supplies all three files, so three tests now pin the two-file path.
- v0.13.27: The reports branch no longer shows a false "Provisional" badge. It returns no `confidence` key, but the panel rendered the badge unconditionally. The types also missed the `mode` field the handler returns, and marked `layout_xlsx` and `gc_data_xlsx` required when the backend treats both as optional.

### Known issues
- `251001_report.xlsx` is a correct format exemplar but is not the round-1 measurement for the IspS campaign. Its normalised values match the expected round-2 input in 0 of 94 rows where `GC data.xlsx` matches 58, and per-well correlation between the two is -0.18. Feeding it as the round-1 source gives right answers for the 34 re-measured variants and wrong ones for the other 61. No raw round-1 report exists for that campaign, which is why rank mode stays.
- The `export_evolvepro_csv` output is log2 while both xlsx writers are linear. The CSV exists for the in-repo KURO round trip and is not an EVOLVEpro input, but the shared name invites confusion.

## v0.13.26 (Panels that announce themselves on a laptop screen, a sample map that arrives pre-filled)

A user on a MacBook reported that the KURO Step 5 plate view was missing, while the same build looked fine on Windows. The cause turned out to be two independent things that only combine on a short screen: a panel that shrinks instead of overflowing, and an OS that hides its scroll bars. Measurement drove the fix; the numbers below come from Playwright renders rather than from reading the code.

### Fixed
- v0.13.26: The KURO Step 5 plate grid no longer collapses out of sight. The Output split container was `h-full min-h-0`, so it could never exceed the wizard body and produced no overflow to scroll. At a 1280x800 viewport, the MacBook 13-inch default scaled resolution, the wizard body holds 143 px while the 96-well grid needs 316 px, so the grid was squeezed into a 75 px box with only its own hairline scroll bar. The container now carries a height floor, which lets the grid render at full size and hands the surplus to the wizard body scroll. Measured across 720 px to 1100 px of viewport height, the grid box tracks `viewport - 741` before the change and stays at 424 px after it. (`src/components/steps/OutputStepView.tsx`)
- v0.13.26: MAME Analyze fits on a laptop. The review container declared `min-h-[960px]`, so on any window shorter than roughly 1700 px the whole step sat inside a scroll trap; the verdict table and the efficiency chart added 640 px and 360 px floors of their own. All three now sit at or below 240 px and scroll inside themselves. This was never reported, and it bites harder than the plate view because it moves the entire step rather than one panel. (`src/components/mame/steps/AnalyzeStepView.tsx`)
- v0.13.26: The plate grid draws its own scroll bar. Nothing in the codebase styled a scroll bar, so every scrollable region inherited the platform default, and macOS keeps overlay scroll bars hidden until a scroll is already in progress. A clipped grid therefore read as "there is nothing more here" on a Mac and as "clipped, more below" on Windows, from one identical build. The plate view now renders a scroll bar as a real element, present on both platforms and assertable in a test, and a global rule opts WebKit out of the overlay style for every other panel. The thumb tracks the true ratio: at 1280x800 the horizontal thumb spans 42 % of the track against a 323/771 px viewport-to-content ratio. (`src/components/widgets/PlateMap.tsx`, `src/index.css`)
- v0.13.26: Seventeen interface strings stop rendering as raw key names. i18next echoes the key when it cannot resolve one, so `onboarding.maximizeHint` appeared verbatim in the first-run toast, and twelve MAME barcode-setup strings, two artifact badge strings and the sidebar resize label did the same. `i18n-parity` compares locale files against each other, so a key absent from all ten passed it. All seventeen are now defined in every locale. (`src/locales/*.json`)
- v0.13.26: The `--text-title` token is larger than `--text-body`. At 13 px against a 14 px body, every panel header rendered smaller than the text inside it. Now 15 px. (`src/index.css`)
- v0.13.26: The MAME sample map template arrives pre-filled. `generate_mame_package` accepts the KURO expected-mutations workbook and writes one row per designed mutant in column-major well order plus a trailing `WT` row, delegating placement to `build_draft_layout` so the file on disk and the in-app draft cannot diverge. Regeneration no longer discards a template that already carries operator rows. `build_draft_layout` previously truncated past well 96 and dropped the WT control at exactly 96 with no signal, which rendered as a correct full plate; it now reports `dropped_mutant_ids` and `wt_omitted`. (#171)

### Added
- v0.13.26: `i18n-lint` resolves every literal `t()` key against all ten locales and fails on any that no locale defines. The call span is sliced by paren balance rather than a fixed window, so a neighbouring call carrying a `defaultValue` cannot excuse the one beside it. Calls with their own fallback text are exempt, and plural keys are matched through their CLDR suffixes. (`scripts/i18n-lint.mjs`)

### Known issues
- At a 900x600 window, the floor allowed by `minHeight`, the Step 5 body holds 16 px and the plate is reachable only by scrolling. This is a hand-shrunk window rather than a display size, and it appears in no screen-resolution statistic, so it is out of scope for now.
- The plate grid is 745 px wide against a panel of 359 px at 1280x800, so horizontal scrolling remains necessary. The new scroll bar makes that state legible; narrowing the cells or promoting the grid to a full-width view is still open.
- A trivial sidecar call shares the same 60 s timeout budget as a heavy one. `get_polymerase_details` is an in-memory registry lookup, yet it can exhaust the budget and surface as `RPC timeout` when sidecar cold start is slow.

## v0.13.25 (Legacy .xls sources load in a packaged build, round hints name a step that exists)

Two defects that only a shipped build exposes. Both were found by reading the v0.13.24 release back rather than by a failing test, and neither had a test that could have caught it.

### Fixed
- v0.13.25: Legacy `.xls` EVOLVEpro sources load in a packaged build. `xlrd` is declared in `pyproject.toml` but was absent from the kuro `hidden_imports` list, and it is imported lazily in two places PyInstaller cannot see statically: the preview path (`sidecar_kuro/handlers/misc.py:125`) and the table load path (`kuma_core/kuro/evolvepro.py:339`). Any `.xls` source therefore raised `ModuleNotFoundError` in an installed build while a development run succeeded, because the wheel is present there. This affected loading, not only previewing. `openpyxl` was already listed, so `.xlsx` was never affected, and nothing on the MAME side imports `xlrd`. (`python-core/build_sidecar.py`)
- v0.13.25: The round hints name a step that exists. The v0.13.24 hints sent the user to "Step 1 (Load Variants)", but the inputs were added to `MutationInput`, which `DesignStepView` maps to `design.mutation`, the Mutations step. `SequenceInput` is Load Variants. The numbering was ambiguous besides, since `DiversitySections` labels the diversity pipeline stages Step 1 to Step 4 in its own separate scheme, so "Step 1" inside that panel meant something else. Both hints now name the step rather than numbering it, in all ten locales. (`src/locales/*.json`)

### Known issues
- A trivial sidecar call shares the same 60 s timeout budget as a heavy one. `get_polymerase_details` is an in-memory registry lookup, yet it can exhaust the budget and surface as `RPC timeout` when sidecar cold start is slow, which on Windows includes onefile extraction plus antivirus scanning a bundle of roughly 90 MB. The call itself is not slow; the startup ahead of it is.

## v0.13.24 (Plasmid input that works, campaign round asked for instead of assumed)

Two rounds of work on inputs the app accepted but could not actually use. MAME refused every circular plasmid and silently scanned SnapGene binaries as text; KURO collected the campaign round in a step the user reaches after the value has already been consumed, and treated "never entered" as round 1.

### Fixed
- v0.13.24: MAME designs primers on circular plasmids. `design_flanking_primers` placed the forward binding site in `[gene_start - flank_max, gene_start - flank_min)` and errored whenever a bound fell outside the sequence, so a gene near the origin was rejected even though the template exists on the other side of it. On `pTSN-PtIspS-idi(KanR)_corrected.gb` (6494 bp, LOCUS declares circular) ispS at `gene_start=267` produced a window of `[-133, 167)` and aborted with "sequence is too short upstream of the gene", where offset -133 is position 6361. Circular topology now indexes modulo the sequence length in both windows, detected from the Biopython record; linear templates keep the previous behaviour and error message byte for byte. Measured on that file, the forward primer lands at 6361 and the reverse ends at 2050. (`kuma_core/mame/ingest/barcode_package.py`, `kuma_core/kuro/sdm_engine.py`, `python-core/sidecar_mame/handlers/barcode_package.py`)
- v0.13.24: SnapGene `.dna` files are parsed instead of scanned as text. `BarcodeSetupPanel` read every input with `readTextFile`, so a binary `.dna` found no flat-file CDS lines, fell through to the FASTA ORF scanner, and filled the CDS dropdown with dozens of ORFs found in 3.16 MB of binary, then auto-wrote those coordinates into the form. Annotated formats now route through the existing Biopython-backed `load_fasta` RPC, which returns the same four genes at the same coordinates as the GenBank text path. Plain FASTA keeps the ORF scan, the scanner rejects content that is not plausibly text, and an RPC failure surfaces the error rather than falling back to the path that produced the junk. (`src/components/mame/panels/BarcodeSetupPanel.tsx`, `src/lib/sequence/autoDetectCds.ts`)
- v0.13.24: The MAME sequence field says what it needs. The helper read "Reference CDS sequence", inviting the one input that can never work, since a CDS-only FASTA has zero flank on either side. It now asks for a plasmid or construct map with flanking template, and an inline warning reports the shortfall in bp per side. The warning does not block, because circular templates legitimately succeed in those cases. (`src/locales/*.json`, `src/components/mame/panels/BarcodeSetupPanel.tsx`)
- v0.13.24: Annotated and ORF-derived CDS candidates report the same protein length. The sidecar counted the stop codon as a residue while the frontend candidate type excludes it, so the same gene read 561 aa from a GenBank map and 560 aa from a FASTA ORF. (`src/components/mame/panels/BarcodeSetupPanel.tsx`)
- v0.13.24: The KURO campaign round is set where it is used. Both inputs lived in Step 4 Pool Filters while the value is consumed at EVOLVEpro load time to derive the sigma-adaptive pool, so the field was only discovered after the load had run. They now sit in the Mutations step next to the variant file, bound to the same store fields, and an informational hint appears when recorded round history disagrees with the entered value. (`src/components/panels/InputPanel/MutationInput.tsx`, `DiversitySections.tsx`, `DiversityOptions.tsx`)
- v0.13.24: An unentered round is no longer read as round 1. The frontend initialised `evolveproRound` to 1 while the sidecar default, the Pydantic field, the source inspector display, and the request builder all treat 0 as unset, so an untouched round silently selected the round-1 pool parameters. Zero is now the initial value and a dismissible dialog asks for the round once an EVOLVEpro table is loaded, mounted app-level so it does not depend on which step the user opened first. With the round unset, Pool Filters points at the Mutations step rather than displaying the k and entropy values that `computeSigmaParams(0, size)` happens to return. (`src/store/slices/diversitySlice.ts`, `src/components/dialogs/RoundPromptDialog.tsx`, `src/components/layout/AppLayout.tsx`)
- v0.13.24: The KURO Tip card shows its text instead of a key name. The side-card key was assembled by splitting the substep id, which does not match the locale keys for three of six substeps (`design.mutation`, `output.summary`, `export.all` against `nominate`, `output`, `export`), so those steps rendered the raw key string in all ten locales. (`src/components/layout/KuroChrome.tsx`)
- v0.13.24: Prose no longer renders at the 8 px well-plate size. Seven status lines, section labels, and descriptions used the plate-label token; they now use the caption size. The 8 px token stays on plate badges and compact controls. (`src/components/panels/InputPanel/DiversitySections.tsx`, `UniprotSearch.tsx`)

### Added
- v0.13.24: Structural diversity is suggested in the regime where it is validated. The selector stays off by default, since the benchmark records a conditional win that loses on some assays, but the app now offers one-click enable when the candidate pool is combinatorial, the round is 1 or 2, and a real 3D structure is loaded, which are the three conditions the benchmark requires together. (`src/components/panels/InputPanel/DiversityOptions.tsx`, `src/store/slices/diversitySlice.helpers.ts`)

### Known issues
- The campaign round reaches the sidecar only when the Pareto optimisation step is enabled. `evolvepro_round` is attached to the request under `usePipeline && paretoDiversityEnabled`, so the round is stored, displayed, and persisted as campaign metadata while its only functional effect is on the sigma-adaptive pool inside that one path.

## v0.13.23 (Rescue levers that run, verdicts that stop overclaiming, annealing below extension)

A defect audit run straight after v0.13.22, aimed at one pattern: a declared contract that the code quietly contradicts, with nothing checking the two against each other. That is what the v0.13.22 Tm scale bug was, and five sweeps (constant provenance, hard bounds, hidden diagnostics, cross-layer drift, MAME thresholds) found more of it.

### Fixed
- v0.13.23: The Tm tolerance control now reaches the batch design. The frontend sent `tol_max` on every request, `DesignSdmPrimersParams` had no such field, and Pydantic dropped it silently under the default `extra="ignore"`, so the batch always ran at 4.0 while only the retry path honoured the value. Moving the control from 4 to 10 changed nothing. On a 95-mutation IspS input the yield now moves 91/95 at tolerance 4, 94/95 at 6, and 95/95 at 8. Auto-relax widens from the requested value rather than a constant, so asking for 8.0 no longer produces a 6.0 rescue narrower than the first attempt. (`python-core/sidecar_kuro/models.py`, `kuma_core/kuro/sdm_engine.py`, `python-core/sidecar_kuro/handlers/design.py`, `src/components/panels/ParameterPanel.tsx`)
- v0.13.23: Auto-relax rescue runs without a rescue pool. The block sat inside a guard that also required `rescue_pool`, and the frontend sends an empty pool outside EVOLVEpro mode, which made auto-relax dead code for manual and CSV input. Measured with an empty pool, the same input moves from 91/95 to 94/95. (`python-core/sidecar_kuro/handlers/design.py`)
- v0.13.23: A well counts as recovered only when its designed mutation is confirmed. The indel-event gate returned AMBIGUOUS before the expected mutation was ever compared, and `detected.py` treats AMBIGUOUS as a guarantee that every expected mutation matched, so a deletion-bearing well whose consensus lacked the designed mutation reported a recovery rate of 1.0 and won replicate selection. (`kuma_core/mame/compare/verdict.py`)
- v0.13.23: `consensus_n_fraction` is scoped to covered positions. Dividing by the whole alignment reference sent every well to NO_CALL when the reference was a plasmid map, which the translator explicitly supports: 150 perfect reads carrying the designed mutation measured 0.97. A file written before this change is recovered exactly from `low_depth_positions`, and when that is unavailable the value is marked unevaluable and the gate is skipped with a note, rather than reusing a differently defined number. (`kuma_core/mame/ingest/consensus.py`, `fasta_parser.py`, `consensus_metadata.py`)
- v0.13.23: A coordinate-origin mismatch fails loudly. The expected WT residue was parsed and discarded, so a tag, leader peptide, or plasmid offset shifted a whole plate onto the wrong residues and still reported PASS with empty notes. (`kuma_core/mame/compare/verdict.py`)
- v0.13.23: Cross-talk reports whether it ran. Four states, including a missing input file and a parse failure, collapsed into an empty list that the panel rendered as an all-clear, in a section that sat outside the MinKNOW guard. The z-score population also included the `unclassified` bin, which demux excludes by name, so a large unclassified count hid the real candidate. (`kuma_core/mame/health.py`, `src/components/mame/widgets/RunHealthPanel.tsx`)
- v0.13.23: Wells that cannot be identified stay unidentified. A failing well with no label match and no sample_map entry was attributed to `expected[idx % len(expected)]`, so its position in the ingest list decided which mutant it joined. (`kuma_core/mame/pipeline.py`)
- v0.13.23: The verdict inspector shows the note instead of an invented identity. The Identity row rendered 100 minus five per observed AA change; no identity field exists anywhere in the backend. (`src/components/mame/layout/MameInspectorContent.tsx`)
- v0.13.23: Recommended annealing never exceeds the extension temperature. Q5 SDM carried no two-step threshold, so all eleven pairs the fixture designs were recommended 74 to 79 C against a 72 C extension step. The demotion also tested the raw Tm rather than the annealing temperature NEB specifies, and Phusion lacked the documented sub-20-nucleotide branch. Across all eight profiles, pairs above 72 C fall from 12 to 0. (`kuma_core/kuro/annealing.py`, `kuma_core/kuro/resources/polymerase_profiles.json`)
- v0.13.23: The KURO sidecar surfaces the exception type and message instead of a bare "Internal error", matching the MAME sidecar under the same -32603 code. (`python-core/sidecar_kuro/dispatcher.py`)

### Known issues
- Reported MAME numbers can move. Scoping the N fraction to covered positions and requiring the designed mutation before AMBIGUOUS both change verdicts on existing data, and a coordinate-origin mismatch that used to pass now aborts the run. On an 8-well panel the distribution moves NO_CALL -5, PASS +3, WRONG_AA +2, with no well flipping into a false PASS.
- A well whose N fraction is unevaluable serializes as 0.000, so Excel, CLI, and the frontend read it as clean. The reason is carried in `verdict_notes` on the same row.
- The pool-cascade branch still designs at the default tolerance.

---
## v0.13.22 (SDM design Tm scale correction, failure reasons that name the blocking stage)

### Fixed
- v0.13.22.1: The design-time Tm no longer carries the Mg and dNTP terms the Benchling scale does not model. v0.13.19.0 pinned one fixed scale for every polymerase but populated it with a polymerase buffer (Mg 1.5 mM, dNTP 0.8 mM), while the Benchling SantaLucia 1998 calculator models monovalent salt and oligo concentration only. Every design Tm therefore ran about 5.4 C hot against unchanged 62/58/42 targets, and GC-rich sites lost their reverse primer: the shortest legal 19 bp reverse already exceeded 58+-4, so the site failed. Verified against a pair designed at the bench on pTSN-PtIspS-idi(KanR) F385Y, where Benchling reports 61.6 / 59.5 C and the corrected scale reproduces 61.2 / 59.5 C; the engine now regenerates that reverse primer byte for byte. Yield on a 95-mutation IspS input moves from 74/95 to 91/95 before rescue and 94/95 with auto-relax, and the 50-mutation dmpR fixture from 21/50 to 36/50. Targets, primer lengths, and the enzyme-specific annealing temperature path are untouched. (`kuma_core/kuro/sdm_engine.py`)
- v0.13.22.1: A failed mutation now reports which stage blocked it instead of one generic tolerance line. The reason names the overlap window, the forward primer, the reverse primer, or the full-overlap gate, and carries the closest reachable Tm, the target window, and the length limits, for example `reverse: closest Tm 64.4C at 19 bp, outside 58+-4.0C (length 19-27 bp)`. Diagnosis runs only after a failure is confirmed, so the success path is unchanged, and it observes through the same search primitives rather than reimplementing the ladder, so the message cannot drift from the search. (`kuma_core/kuro/sdm_engine.py`, `tests/test_sdm_engine.py`)

### Changed
- v0.13.22.0: KURO step 2 loads EVOLVEpro and Others through one loader with optional column mapping, `resetAll` no longer leaks candidates, export BOM is selected by locale, and UniProt BLAST auto-search is gated. (`src/store/slices/inputSlice.ts`, `src/store/slices/sequenceSlice.ts`, `src/store/slices/exportSlice.ts`)

### Known issues
- One IspS mutation (L265F) still fails, with the reverse primer at 64.4 C against 58+-6 even after auto-relax. The cause is the 19 bp reverse length floor, which is kept at the value the paper method specifies.

---
## v0.13.19 (Paper-standard SDM design for every polymerase)

### Changed
- v0.13.19.0: SDM design targets are now **method-level constants** (Fwd 62 / Rev 58 / Overlap 42 C, mutation site at least 4 bp from the 3' end) for **every** polymerase profile, and the design-time Tm runs on one fixed scale. Previously only the Benchling profile carried the paper values; the others derived targets from `opt_tm` (`opt_tm`, `-4`, `-20`), so selecting KOD or Q5 silently designed to 68/64/48, and the design Tm itself was computed on a per-enzyme scale (NEB-calibrated for Q5/Phusion/Taq). Every profile that shares the length spec now designs byte-identical primers matching the paper reference, and enzyme identity affects only the recommended annealing temperature. Targets and lengths follow Landwehr et al. 2025 (Nat Commun 16, 865), whose SI Fig. S4 defines 62/58 as whole-primer melting temperatures. (`kuma_core/kuro/sdm_engine.py`, `kuma_core/kuro/resources/polymerase_profiles.json`, `src/store/slices/designSlice.ts`)

### Fixed
- v0.13.19.0: CI now smoke-tests the frozen KURO sidecar (spawn, `ping`, `load_fasta`, import-stage marker) so an import crash cannot reach a release. The v0.13.17 startup failure shipped because the pipeline only checked that the binary existed. (`python-core/scripts/frozen_kuro_smoke.py`, `.github/workflows/build.yml`)

---
## v0.13.18 (Sidecar startup fix on non-UTF-8 Windows locales)

### Fixed
- v0.13.18.0: The KURO sidecar no longer dies at import on Windows systems whose locale encoding is not UTF-8 (cp949 on Korean Windows, for example). The profile loader opened the bundled polymerase table with the locale default encoding, so the non-ASCII touchdown text introduced in v0.13.17 raised `UnicodeDecodeError` before any RPC could run, which surfaced as "Sidecar process exited" for every command including sequence loading. The loader now pins utf-8, matching the three other readers in that module, and a regression test drives the registry under `PYTHONWARNDEFAULTENCODING` so a locale-default open cannot come back. (`kuma_core/kuro/polymerase.py`, `tests/test_polymerase.py`)

---
## v0.13.17 (Per-enzyme annealing temperature)

### Added
- v0.13.17.0: KURO now outputs a **recommended annealing temperature (Ta)** per SDM primer pair, calibrated to the selected polymerase with verified manufacturer rules: NEB Q5 (Tm+1), Phusion (Tm+3), Taq (Tm-5) via the existing NEB Tm offsets; KOD One (nearest-neighbor Tm-5, 3-step, step-down 74/72/70/68); Takara PrimeSTAR GXL (discrete 55/60); Thermo DreamTaq (Wallace, Tm-5), with 2-step promotion for high-Tm pairs. The design-time Tm scale (Fwd 62 / Rev 58 / Overlap 42) stays unchanged; Ta is an additive output in the result table with a mode and touchdown tooltip. Rules verified against primary sources (NEB Tm API, Toyobo/Takara/Thermo manuals). (`kuma_core/kuro/annealing.py`, `kuma_core/kuro/polymerase.py`, `kuma_core/kuro/resources/polymerase_profiles.json`, `python-core/sidecar_kuro/handlers/design.py`, `python-core/sidecar_kuro/models.py`, `src/components/widgets/resultTableColumns.tsx`, `docs/2026-07-16-annealing-ta-rules-verified.md`)

---
## v0.13.16 (In-app automatic updates)

### Added
- v0.13.16.0: Kuma can now **update itself in place**. When a newer signed release is detected, the update dialog offers **Update now**, which downloads the platform artifact, verifies its Ed25519 signature against the key embedded in the app, installs it, and relaunches — no manual installer step. Windows (NSIS), macOS, and Linux AppImage are fully automatic; Debian `.deb` has no updater artifact and falls back to opening the release page. Signing uses a self-generated Tauri updater key (not a paid code-signing certificate), so the free/unsigned distribution policy is unchanged and the SmartScreen guidance still applies. (`src-tauri/tauri.conf.json`, `src-tauri/src/lib.rs`, `src-tauri/capabilities/default.json`, `src/lib/updateCheck.ts`, `src/components/dialogs/UpdateAvailableDialog.tsx`, `.github/workflows/build.yml`, `scripts/gen-latest-json.mjs`)

---
## v0.13.15 (MAME Activity runs independently on layout + GC)

### Changed
- v0.13.15.0: MAME **Build EVOLVEpro input** no longer forces all four files. Layout + GC alone now produce a valid activity table for a first-round primary screen, marked **Provisional**; supplying the Agilent rep-batch (3-replicate re-measurement of positives) and the previous-round EVOLVEpro rank file upgrades the result to **Confirmed** (authoritative replicates merged over the primary screen, with per-variant mismatch QC preserved). Each pipeline step stays independently runnable and the result badge states the confidence level. The existing four-file confirmation workflow is unchanged. (`kuma_core/mame/activity/build_evolvepro_input.py`, `python-core/sidecar_mame/models.py`, `python-core/sidecar_mame/handlers/activity.py`, `src/types/mame/build_evolvepro_input.ts`, `src/components/mame/panels/BuildEvolveproInputPanel.tsx`, `src/locales/*.json`)

---
## v0.13.14 (KURO structure-accuracy guard for 3D selection)

### Fixed
- v0.13.14.0: KURO now uses AlphaFold Cα coordinates for structural-diversity and Pareto-3D selection only when the loaded structure exactly covers the reference sequence (identity or a clean substring; terminal tags/truncations are fine, interior substitutions are not). A near-but-not-exact structure would place coordinates on the wrong residues and silently corrupt selection; such cases now fall back to 1-D sequence distance with a status notice. Domain diversity is unaffected (sequence-based) and the benchmark comparison deliberately keeps both 1-D and 3-D arms. (`kuma_core/kuro/interface.py`, `python-core/sidecar_kuro/handlers/misc.py`, `src/store/slices/inputSlice.helpers.ts`)

---
## v0.13.13 (KURO ESMFold de-novo structure prediction)

### Added
- v0.13.13.0: The KURO 3D panel can predict a structure directly from the reference sequence via ESMFold (EMBL-EBI ESMAtlas) when no UniProt accession is available, enabling the 3D viewer, reference-frame dispersion, and pLDDT/variant/domain overlays for novel or synthetic constructs (≤400 residues). AlphaFold-by-accession remains the primary source; active/binding-site overlays require an accession and are hidden for ESMFold. (`kuma_core/kuro/esmfold.py`, `kuma_core/kuro/dispersion.py`, `python-core/sidecar_kuro/handlers/external.py`, `src/components/panels/Selection3DPanel.tsx`)
---
## v0.13.12 (KURO reference-sequence domains, guided tours, update checks, runtime fixes)

### Added
- v0.13.12.0: KURO **Scan sequence** annotates protein domains directly from the loaded reference sequence via EMBL-EBI InterProScan (after external-service consent), so domain coordinates match KURO mutation positions instead of UniProt accession numbering. Results cache by sequence SHA-256; reference-frame `refDomains` drive selection/benchmark while accession-frame `domains` stay dedicated to AlphaFold 3D coloring. (`kuma_core/kuro/domains.py`, `python-core/sidecar_kuro/handlers/external.py`, `src/store/slices/diversitySlice.ts`, `src/components/panels/InputPanel/UniprotSearch.tsx`)
- v0.13.12.0: New projects show a skippable spotlight tour of navigation and Kuro; Mame guidance appears separately on first entry. **Skip all tours** persists per project; `Esc` closes only the current tour; **Help → Show Guided Tour** replays it. Existing projects are never interrupted. (`src/components/dialogs/GuidedTour.tsx`, `src/components/dialogs/ProjectTourCoordinator.tsx`)
- v0.13.12.0: Kuma checks GitHub for a newer published release at startup and recommends it only when strictly newer; **Help → Check for updates** performs a real version check. Network failures never block startup. (`src/lib/updateCheck.ts`, `src/components/dialogs/UpdateAvailableDialog.tsx`)

### Fixed
- v0.13.12.0: **Export PNG** now has the binary file-write capability (`fs:allow-write-file`), reports save success/failure via toast, and no longer rejects the Tauri `fs.write_file` command. (`src-tauri/capabilities/default.json`, `src/components/panels/Selection3DPanel.tsx`)
- v0.13.12.0: The sequence viewer now draws domain bands from reference-frame domains so bands align with the loaded sequence; 3D residue spheres use a consistent opaque style to remove the 3Dmol ambiguous-opacity warning; title-only dialogs opt out of a missing description; an embedded favicon prevents the default `/favicon.ico` 404. (`src/components/widgets/SequenceViewer.tsx`, `src/components/panels/Selection3DPanel.tsx`, `index.html`)

---
## v0.13.11 (MAME single-step Activity, KURO 3D viewer background)

### Changed
- v0.13.11.0: MAME **Activity Data** is now a single step (3) that stacks Ingest, Merge, and Export in one scrollable view; the former 3.1 Ingest / 3.2 Merge & Export split is removed and the legacy `activity.mergeExport` id redirects to it. (`src/store/mame/slices/mameSubSteps.ts`, `src/components/mame/steps/ActivityStepView.tsx`, `src/components/mame/layout/MameWorkflowRail.tsx`, `src/components/mame/layout/MameAppLayout.tsx`, `src/locales/*.json`, `docs/mame/*`)

### Improved
- v0.13.11.0: the KURO 3D viewer defaults to a white background, and the Dark toggle now applies live (no reload). (`src/components/panels/Selection3DPanel.tsx`)

---

## v0.13.10 (KURO 3D surface + PNG export fixes)

### Fixed
- v0.13.10.0: the KURO 3D viewer **Surface** toggle now works in the packaged app. 3Dmol computes the molecular surface in a `blob:` Web Worker, which the app CSP blocked (no `worker-src`); the CSP now allows `worker-src 'self' blob:`, and surface generation degrades gracefully with a notice if a host webview still blocks workers. (`src-tauri/tauri.conf.json`, `src/components/panels/Selection3DPanel.tsx`, `src/locales/*.json`)
- v0.13.10.0: the KURO 3D viewer **Export PNG** button now saves a file. The Tauri webview ignores programmatic `<a download>`, so the export now uses the Tauri save dialog and writes the PNG via the fs plugin. (`src/components/panels/Selection3DPanel.tsx`)

---

## v0.13.9 (KURO dispersion structure-frame fix, release checksums)

### Fixed
- v0.13.9.0: KURO 3D dispersion no longer drops all positions ("N position(s) could not be mapped to the structure") when the structure loads but the UniProt FASTA fetch fails. The accession-frame sequence is now derived from the fetched AlphaFold/PDB structure itself (falling back to the UniProt FASTA only when the structure carries no sequence), so dispersion works whenever the structure is available. (`kuma_core/kuro/alphafold.py`, `kuma_core/kuro/dispersion.py`, `tests/test_g001_backend.py`)

### Improved
- v0.13.9.0: GitHub releases now attach a `SHA256SUMS.txt` for every installer and append Windows SmartScreen "Unknown publisher" guidance (More info → Run anyway), checksum-verification steps, and a macOS Gatekeeper note to the release body; a matching troubleshooting page is added. (`.github/workflows/build.yml`, `.github/release-footer.md`, `docs/troubleshooting/windows-smartscreen.md`, `docs/troubleshooting/index.md`)

---

## v0.13.8 (KURO 3D panel polish + packaged-sidecar dispersion fix)

### Improved
- v0.13.8.0: the KURO Candidate 3D structure analysis panel now explains itself inline — the Structural Dispersion card, its null-distribution histogram, and each metric row carry `?` help toggles; the histogram marker uses `P1`/`P96` percentile notation instead of `1%ile`; the metric is relabeled "Observed percentile vs random"; and a Color legend under the viewer maps every color (domain / pLDDT backbone, y_pred variant spheres, active-site sticks, binding-site spheres) to its meaning, adapting to the current coloring mode. (`src/components/panels/Selection3DPanel.tsx`, `src/locales/*.json`)
- v0.13.8.0: the Color legend rows are clickable toggles that show/hide each 3D layer (variant spheres, active-site sticks, binding-site spheres) while the backbone stays always-on; the standalone Interface checkbox is folded into the legend, and the panel is reordered to toolbar → 3D viewer → legend → Structural Dispersion → tables so toggle/coloring changes are visible in the viewer immediately. (`src/components/panels/Selection3DPanel.tsx`, `src/locales/*.json`)
- v0.13.8.0: corrected the mislabeled "Interface" overlay to "Binding site" across the viewer, legend, table column, and hover label — the magenta spheres are UniProt `Binding site` (ligand/cofactor/metal-binding) residues, not a protein-protein interface. (`src/components/panels/Selection3DPanel.tsx`, `src/locales/*.json`, `docs/kuro/05-output.md`)
- v0.13.8.0: documented that the 3D dispersion, pLDDT, and active/binding overlays are interpretation/QC aids, not candidate-selection filters — low-confidence or disordered residues are not auto-excluded from the mutation set, and EVOLVEpro y_pred ranking remains the sole selection authority. (`docs/kuro/05-output.md`)

### Fixed
- v0.13.8.0: the KURO 3D dispersion compute no longer fails in the packaged sidecar with `[Errno 2] No such file or directory: '..._MEI.../Bio/Align/substitution_matrices/data/BLOSUM62'`. The reference→accession position mapper now uses `PairwiseAligner` with explicit match/mismatch scoring instead of loading Biopython's loose `BLOSUM62` data file, which PyInstaller does not bundle into the temp extraction dir. (`kuma_core/kuro/interface.py`, `tests/test_g001_backend.py`)

---

## v0.13.7 (KURO Current-Selection 3D Analysis)

### Added
- v0.13.7.0: the KURO Output step gains a collapsible Current-Selection 3D Analysis panel that embeds a 3Dmol viewer (collapsed by default to avoid eager 3Dmol loading) and reports the spatial dispersion of the selected residue positions. (`src/components/panels/Selection3DPanel.tsx`, `src/lib/selection3d.ts`, `src/components/steps/OutputStepView.tsx`, `src/store/slices/diversitySlice.ts`)
- v0.13.7.0: the backend adds a stdlib-only 3D dispersion null-model (`compute_round_dispersion`, mean pairwise C-alpha distance versus random sampling) plus UniProt active/binding-site fetch in the accession frame, wired through the kuro dispatcher. (`kuma_core/kuro/dispersion.py`, `kuma_core/kuro/uniprot_features.py`, `python-core/sidecar_kuro/dispatcher.py`, `python-core/sidecar_kuro/handlers/external.py`, `python-core/sidecar_kuro/models.py`)
- v0.13.7.0: the panel strings are localized across all 10 locales, and `3dmol@^2.5.5` is added as a dependency. (`src/locales/*.json`, `package.json`)

---

## v0.13.6.1 (What's New automation)

### Added
- v0.13.6.1: the What's New dialog is auto-generated from `CHANGELOG.md` (`pnpm gen:whatsnew`); `sync:check` now fails the build when the generated module drifts or when the latest CHANGELOG section does not match `package.json`'s version. (`scripts/gen-whatsnew.mjs`, `src/components/dialogs/whatsNew.generated.ts`, `package.json`)

### Fixed
- v0.13.6.1: corrected the Kuro Export All BOM label to "UTF-8 BOM (Excel compatibility)" across all 10 locales. (`src/components/steps/ExportFormatSelector.tsx`, `src/locales/*.json`)
- v0.13.6.1: aligned KURO wizard step bodies and MAME file-picker field widths. (`src/components/steps/WizardContainer.tsx`, `src/components/mame/panels/FileField.tsx`)

---

## v0.13.5 - v0.13.6 (macOS SSL fix, MAME sample-data UX)

### Fixed
- v0.13.5: outbound HTTPS (Kuro UniProt search, AlphaFold, EBI BLAST, ESM) failed on the packaged macOS app with `CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate`. macOS OpenSSL does not read the Keychain and the frozen app has no build-machine CA store, so `ssl.create_default_context()` had no trust anchors. All external requests now route through a shared certifi-backed SSL context (`certifi.where()`, bundled by PyInstaller `hook-certifi`), identical on Windows, macOS, and Linux. Windows and Linux were unaffected because their OS CA stores are present on the target. (`kuma_core/shared/net.py`, `python-core/sidecar_kuro/core.py`, `kuma_core/kuro/alphafold.py`, `kuma_core/kuro/esm_embeddings.py`, `pyproject.toml`)
- v0.13.6: MAME step 1.1 "Generate Barcode Package" no longer requires the output directory to live inside the project root (it failed with `output_dir must be inside project_root`). `mame_context.json` stores paths relative when the output is inside the project root (portable) and absolute when outside, and the loader resolves both. (`kuma_core/mame/ingest/barcode_package.py`, `src/lib/mame/detectProjectFiles.ts`)

### Added
- v0.13.6: loading sample data populates a precomputed analysis result (`samples/mame/sample_analysis_result.json`, serialized from the real demux/consensus/verdict/health pipeline) so the Per-plate verdict breakdown renders instead of showing "Setup incomplete". (`python-core/scripts/generate_mame_sample_result.py`, `src/store/mame/slices/analysisSlice.ts`)
- v0.13.6: loading sample data seeds the Build EVOLVEpro Input form (layout / GC data / Agilent rep-batch / previous EVOLVEpro) from the bundled `06`/`08`/`09`/`10` sample xlsx files; fields already set by the user are preserved. (`src/store/mame/slices/analysisSlice.ts`, `src/lib/mame/buildEvolveproFormStorage.ts`, `src/components/mame/panels/BuildEvolveproInputPanel.tsx`)

---

## v0.13.3.1 - v0.13.4.0 (native MinKNOW run-folder ingestion, auto-updater removal, CI quality gates, i18n parity)

### Added
- v0.13.4.0: MAME `analyze` auto-detects a raw MinKNOW run folder (a directory containing `fastq_pass/`) and orchestrates demux → consensus internally, so a pre-demuxed consensus directory is no longer required. There is no new RPC: the pre-demuxed consensus path and the standalone `mame.run_combinatorial_demux` RPC are unchanged, and the `{R}_{F}` well-naming contract is preserved. (`kuma_core/mame/ingest/run_pipeline.py` `is_minknow_run_dir`/`ingest_run_folder`, `python-core/sidecar_mame/handlers/analyze.py`, `python-core/sidecar_mame/models.py` `DemuxParamsBase`/`AnalyzeRawRunParams`, `src/types/mame/models.ts`, `src/store/mame/slices/inputSlice.ts`, `src/hooks/mame/useMameSidecar.ts`)
- v0.13.4.0: raw-run analyze emits two-phase progress (demux 0–50, analyze 50–100) carrying a `stage` field, so the UI shows one demux→analyze flow from a single `analyze` call with a dedicated `MAME_RAWRUN_RPC_TIMEOUT_MS`; the consensus-directory path keeps its byte-identical 0–100 progress with no `stage` key. (`python-core/sidecar_mame/handlers/analyze.py`, `src/store/mame/slices/inputSlice.ts`, `src/hooks/mame/useMameSidecar.ts`)
- v0.13.4.0: CI gains a `quality-gates` job (pytest / `tsc --noEmit` / `sync:check` / `i18n:check`) that gates the release build, plus a new `mame-analyze-run-folder` cross-layer sync group keeping the demux params identical across Pydantic, TypeScript, and the dispatcher. (`.github/workflows/build.yml`, `.cross-layer-sync.json`)
- v0.13.4.0: all 10 locales brought to full key parity with `i18n-lint` hardening; UI locales and the Kuro/MAME screens now load on demand (dynamic `import()` + `React.lazy`/`Suspense`), trimming the initial JS bundle. (`src/locales/*.json`, `scripts/i18n-lint.mjs`, `src/lib/i18n.ts`, `src/screens/MainShell.tsx`)

### Removed
- v0.13.4.0: the Tauri auto-updater is removed — the frontend `src/lib/updater.ts`, the Cargo dependency, the updater capability, the `lib.rs` plugin registration, and the About-dialog wiring are all gone, and the Check-for-updates menu entry is repurposed to the release page. (`src/lib/updater.ts` deleted, `src-tauri/Cargo.toml`, `src-tauri/capabilities/default.json`, `src-tauri/src/lib.rs`, `src/components/layout/SharedAboutDialog.tsx`)

### Fixed
- v0.13.3.2: corrected an EVOLVEpro numeric overflow and four stale test expectations.
- v0.13.3.3: the verdict window note now reflects the real window instead of a hardcoded ±5, `compute_T3` is de-duplicated, and the SDM parse fallback is logged instead of failing silently.

---

## v0.13.0.1 - v0.13.3.0 (MAME verdict depth gate, analyze progress, resume hardening, export guards, macOS build)

### Fixed
- v0.13.0.1: MAME verdict depth gate uses the consensus header `depth=N` (real read depth) instead of the consensus FASTA file size; the file-size check is demoted to a fallback that fires only when `depth=N` is absent, and `CompareParams.min_read_count` now defaults to 30. Previously every well was flagged `LOWDEPTH` because a gene-length-fixed consensus FASTA (~1.8KB, identical across same-amplicon wells) could never reach the raw-read `min_file_size_kb=50` floor. (`kuma_core/mame/compare/verdict.py`, `kuma_core/mame/models.py`)
- v0.13.1.0: MAME analyze emits per-record sub-progress and runs a 30s keep-alive heartbeat, fixing the ETA stalling near 60% and the 300s "no response" deadlock popup on long but healthy analyze runs. (`kuma_core/mame/pipeline.py` `run_analyze`, `python-core/sidecar_mame/handlers/analyze.py`)
- v0.13.2.4: the resume orphan guard detects stray `.fa`/`.fas` files (not only `.fasta`) via a shared `CONSENSUS_FILE_PATTERNS`; resumed demux runs seed `n_input_reads`/`n_unassigned` from completion markers so totals no longer undercount or go negative. (`kuma_core/mame/ingest/stage_marker.py`, `kuma_core/mame/ingest/fasta_parser.py`, `python-core/sidecar_mame/handlers/demux.py`)
- v0.13.2.6: MAME resume/skip now also covers the raw_run path (`run_combinatorial_demux_per_nb`), not only `handle_demux_and_filter`. Re-running raw_run on a folder that has completion markers skips already-finished native barcodes instead of re-demuxing everything. (`kuma_core/mame/ingest/combinatorial_demux.py`, `kuma_core/mame/ingest/stage_marker.py`)

### Added
- v0.13.2.1: MAME step 2.1 (demux/consensus) writes are atomic (temp file + `os.replace`), each native-barcode group writes a `.demux_consensus_complete.json` completion marker, and a rerun skips groups whose marker matches the on-disk inventory. An asymmetric consumer guard fails fast on a present-but-invalid marker while still loading legacy or externally-sorted directories that have no marker. (`kuma_core/shared/atomic_write.py`, `kuma_core/mame/ingest/stage_marker.py`, `python-core/sidecar_mame/handlers/demux.py`, `kuma_core/mame/ingest/fasta_parser.py`)
- v0.13.2.2: overwrite confirmation for the MAME Janus mapping, Run report, and Barcode package exports; the Barcode package confirms at the `design/` directory level. (`src/components/mame/dialogs/JanusMappingDialog.tsx`, `RunReportDialog.tsx`, `src/components/mame/panels/BarcodeSetupPanel.tsx`, `src/lib/overwriteConfirm.ts`)
- v0.13.3.0: `max_consensus_n_fraction` is adjustable from the MAME analyze parameter panel (default 0.0, strict by default). (`src/components/mame/panels/ParameterPanel.tsx`, `src/store/mame/slices/inputSlice.ts`)
- v0.13.2.5: macOS minimap2 is compiled from source in CI (`make arm_neon=on aarch64=on`, pinned v2.30) and bundled into the macOS sidecar, mirroring the Windows MinGW step; previously the macOS build had no minimap2 source and failed at `build_sidecar.py`. (`.github/workflows/build.yml`)

---

## v0.12.1.0 – v0.12.3.4 (minimap2 CLI cross-platform)

In-process `mappy` 정렬기를 사이드카에 번들된 `minimap2` CLI 로 교체. mappy 는 Windows wheel 이 없어 MAME `raw_run` 이 Windows 에서 실패했음.

### Changed
- `kuma_core/mame/ingest/align.py`: `align_reads`/`align_reads_multi` 가 `minimap2` 바이너리를 subprocess 로 호출하고 SAM 을 파싱, 동일한 `Alignment` dataclass 반환. 바이너리는 `KURO_MINIMAP2` → 사이드카 `_MEIPASS/bin` → PATH 순으로 해석.
- reverse-strand `q_st`/`q_en` 를 원본 read 좌표로 환산, soft/hard clip 을 `Alignment.cigar` 에서 제거하여 mappy 와 일치(실 ONT 데이터에서 consensus byte-identical 검증).
- `build_sidecar.py` / `mame-sidecar.spec`: PyInstaller `--add-binary` 로 플랫폼별 `minimap2` 를 `_MEIPASS/bin/` 에 번들.
- `.github/workflows/build.yml`: 사이드카 빌드 전 vendor 채우기. Linux/macOS 는 `scripts/vendor-minimap2.py` 로 공식 바이너리 다운로드, Windows 는 MSYS2/MinGW 정적 빌드(`make LIBS="-Wl,-Bstatic -lm -lz -lpthread -Wl,-Bdynamic"`) + `ldd` 가드로 비정적 바이너리 거부.
- `.github/workflows/ci.yml`: `python-tests` 에 minimap2 제공(Linux/macOS). `tests/mame/conftest.py` 는 바이너리 부재 시 MAME 테스트 skip(Windows leg).

### Removed
- `pyproject.toml` 의 `mappy` 의존(main + `mame-raw` extra).

### Added
- `NOTICE-bundled.md`: minimap2(MIT)·zlib 서드파티 고지, 번들 `NOTICE.md` 에 병합.

---

## v0.11.0.0 (PR-B: Legacy cleanup)

Remove legacy sort_barcode pipeline and Trim Adapters UI fields.
Aporva-style alignment-based combinatorial demux becomes canonical.

### Removed
- `kuma_core.mame.ingest.sort_barcode`: sliding/edlib read-sorting algorithm
  (`sort_barcode_run`, `_sort_one_nb`, `_hamming_prefix_window_in_head`,
  `_hamming_suffix_window_in_tail`, `_FWD_SEARCH_WINDOW_BP`, `_EDIT_DIST_RATIO`,
  `SortBarcodeResult`, `_hamming_suffix_window`)
- `python-core/sidecar_mame/handlers/sort_barcode.py`: RPC handler
- `sort_barcode_run` method from dispatcher `_METHODS` and `_ASYNC_METHODS`
- `src/types/mame/sort_barcode.ts`: TypeScript type file
- `RawRunParams.minBarcodeScore`, `linkedTrim`, `revPrimerUniversal` state fields
- Trim Adapters, Universal Rev Primer, Min Barcode Score UI fields (9 keys x 10 locales)

### Changed
- `sort_barcode.py` retained as barcode xlsx parser module only
  (`parse_combinatorial_barcodes`, `parse_sample_map`, `_make_well_filename`,
  `_nb_to_sort_barcode_name`)
- `models.py`: removed `_check_pr_b_fields_deferred` validator;
  `sample_map_xlsx` and `kuro_xlsx` params now accepted without error
- `.cross-layer-sync.json`: removed `mame-sort-barcode` and
  `mame-dispatcher-sort-barcode` groups

---

## v0.10.3.0 (PR-A: combinatorial demux frontend)

Add combinatorial demux RPC and UI.

- ParameterPanel Advanced section (coverageFraction, editDistRatio, chimeraSplit)
- `mame.run_combinatorial_demux` RPC wired to `runAnalysis` in `inputSlice`
- `selectCanRun` updated for raw_run mode validation

---

## v0.10.2.0

Chimera-aware demux for concatenated nanopore reads.

---

## v0.10.1.0

Add combinatorial_demux pipeline for 96-well amplicon screening.
