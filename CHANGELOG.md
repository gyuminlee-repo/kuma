# Changelog

## v0.15.15.01 (The banner about inputs a restore lost stops describing a project it already left)

MAME lists the inputs a restore could not recover so the operator can point at them again. Nothing ever took an entry off that list except the browse button on the banner itself, and the list was only ever built once per hydration. Picking the file again in the normal input panel left the warning up, and a scratch entry inherited whatever the previous project had failed to find, because that path returns before the block that rebuilds the list. What the banner named was true at one moment and then kept being displayed as though it were still true.

### Fixed

- v0.15.15.01: An entry disappears as soon as its field holds a path again, whichever control filled it. The hydration hook and the banner now read one shared function instead of each carrying a copy of the field-to-value mapping.
- v0.15.15.01: The list is cleared at the start of every hydration, ahead of the scratch early return, so entering a scratch session no longer shows what a different project was missing.
- v0.15.15.01: Custom barcodes and sequencing summary are named by their file rather than by their own label twice. Both live under `parameters.raw_run_params` in the snapshot, and the lookup only searched the `input` block, so it found nothing and fell back to the label.

## v0.15.15 (A finished run is checked against itself, and stops describing the file it no longer reads)

The v0.15.10 refusal reads the workbook, so it only catches a plate that describes itself two ways. It cannot see a run whose verdicts were scored before the operator swapped the file underneath them. That is the shape the 2026-08-04 misscoring arrived in when the snapshot reached us: the expected path pointed at a re-exported workbook whose sheets agree, while the 288 verdicts beside it had been scored against the earlier one. Nothing on screen separated that from a run that simply went badly, because the well count, the plate map and the verdict tally all render the same either way. The finished analysis already carries the answer: of the 244 wells with an observed amino-acid change, none matched the variant assigned to that well and 241 matched the variant assigned to some other well. A permutation null over the same plate averages 2.49.

### Added

- v0.15.15: MAME compares each well against its own expected variant and against every other one after the run, and says so on the review screen when the second agreement is high and the first is near zero. The message carries the counts it was computed from rather than a fixed threshold, and it does not gate anything: the run is over by then, and what it can still do is stop the numbers from being read as biology. The check needs 24 wells before it will speak, so a small plate is not accused on thin evidence.
- v0.15.15: Every run records how the wells were placed, whether from a layout that was given, a sample map, or the order of the expected sheet, along with the workbook it read. A verdict table that looks ordinary is now traceable to the decision that produced it.

### Changed

- v0.15.15: Choosing a different run folder, expected workbook, reference or sample map clears what the previous run produced. The screen used to keep the verdicts, the plate map and the two instrument-file notices next to inputs that no longer made them, which reads as a description of the file now selected. Re-picking the same path changes nothing, and the export destination is not an input, so neither clears anything.
- v0.15.15: The analyze screens carry no Janus text at all. The instrument controls moved to step 3 in v0.15.12 but the notice about the files a run wrote stayed behind, which is the one thing an operator who stops at a sequencing verdict has no use for. It is stated in step 3, where the rest of the instrument work already lives.
- v0.15.15: Step 3 shows the instrument settings on the page instead of behind a button that opened a dialog. The deck preview and the row preview are what the operator checks before an export, and they were being read through a modal on a screen that exists to hold them. Nothing was gained by the extra click, and the preview had less room than the step had to give.
- v0.15.15: A run no longer writes the instrument mapping file. Analyzing produced the 9-column robot sheet next to the workbook whether or not anyone intended to touch a robot, which made step 3 a formality for an operator who only wanted a sequencing verdict. The pick list is still written by the run, since selecting clones is what the run is for, and the mapping file is written when it is exported from step 3.

### Fixed

- v0.15.15: A well layout MAME inferred for one run no longer comes back from a restored project as though the operator had chosen it. It used to be stored with the verdicts, restored into the input state, and sent to the next run as a layout that was given, which told validation the sheet order never reached a well and lowered the warning it would otherwise raise. A layout with no recorded origin is treated as inferred for the same reason.
- v0.15.15: An amplicon that cannot be extracted says which of the three reasons applied. It reported every case as primer boundaries that were not unique, including the ordinary one where a bare CDS reference simply does not contain the primer tails, which sent the reader looking for duplicate binding sites that were never there.

## v0.15.14 (The step 2.2 height fix reaches the people who needed it)

The panel sizing shipped in v0.15.11 did nothing on any machine that had opened step 2.2 before. It skipped the fit whenever a stored layout existed for the panel group, reading that as a size the operator had chosen. The panel library writes that entry on mount for its own default layout, so it was there for everyone who had ever opened the step, and the fix sat inert behind it. Reinstalling the app did not clear it either: the store lives in the webview profile, not in the installed files.

### Fixed

- v0.15.14: Only a drag counts as a size the operator chose, and it is recorded under its own key. A layout the panel library persisted on its own no longer suppresses the content fit, so the plate map takes the height its rows need on machines that had used step 2.2 before v0.15.11. A split someone actually dragged is still left alone, across restarts.

## v0.15.13 (The replicate that reads cleanest is the one that ships)

MAME keeps three replicate plates per variant and ships one. Verdict class decides first, and below the mixed-position gate every plate reads PASS, so the pick fell to native barcode order. On the 260729 ispS run that sent a plate whose designed substitution rested on 82 percent of reads while its sibling sat at 98 percent, twice, for no reason other than a lower barcode number.

### Changed

- v0.15.13: A consensus reports the weakest read support among the substitutions it calls, together with the depth that fraction was measured on. The replicate picker orders equal-verdict plates by the Wilson score lower bound on that support, so a plate has to be both purer and backed by enough reads to win. A support of 0.98 taken from 12 reads no longer outranks the same figure taken from 562, and no hand-set margin is left in the code to tune.
- v0.15.13: Native barcode number breaks exact ties and nothing else now, and the module says so in as many words. It never carried quality meaning; it had been standing in for a measure that did not exist yet.
- v0.15.13: Both per-plate sheets and the Final sheet carry the purity evidence behind a pick: the weakest called-substitution support, the depth it was measured on, the lower bound the picker ordered by, and the fraction of reads carrying an indel. A cell left empty means unknown, so nothing reads as zero purity by accident.
- v0.15.13: A `review` column names the wells whose numbers stand out, judged against the plate they sit on rather than against a fixed gate. Each plate supplies its own median and median absolute deviation, and a well more than three MAD out is reported with the measured value and the baseline beside it. Nothing is excluded and no verdict changes; the operator decides. On the 260729 run this reports well G3, whose substitution reads 99% designed while 22% of its reads carry a 1 bp deletion, a frameshifted subpopulation the substitution view alone cannot see.
- v0.15.13: The value travels in the consensus FASTA header. It is absent for a well that calls no substitution and for files written before this release, and absent means unknown rather than zero, so an older run picks exactly what it picked before.

## v0.15.12 (A run that only sequences never passes a robot)

MAME asked about the cell-picking robot on the screen that collects a run's inputs. The transfer volume, the instrument settings button and, from the Activity step, a second export CTA all sat inside a workflow whose first two steps are the only ones a genotyping run needs: build the barcode package, read the plate. An operator who wanted a verdict and nothing else had the deck, the liquid class and the rack numbers in front of them on step 2.1 anyway, and nothing said any of it was optional.

### Changed

- v0.15.12: Janus instrument configuration is its own step 3, and the Activity step is step 4. Step 2 is the sequencing verdict and nothing else: the transfer volume, the settings/export dialog, the deck reference and the report of what the run wrote itself all live on the new step, which states in the first line that it can be skipped. The Activity pane's duplicate "Open JANUS export" button is gone, because the step that owns the dialog is now one click away in the rail rather than hidden behind a sub-step condition.
- v0.15.12: The step stays optional in the strict sense. A run still writes `..._picks.csv` and `..._janus.csv` from whatever is stored, no gate on step 2 or step 4 consults the new step, and step 3 reports itself done only once the liquid class (the one value nothing can derive) is supplied or a mapping file exists. The rail counts six sub-steps, so Activity reads 4.1 and 4.2 where it read 3.1 and 3.2.

## v0.15.11 (The plate map gets the height it needs, not the share it was assigned)

Step 2.2 stacks the plate map over the verdict breakdown and split them 34/66, a ratio with no idea how tall either one wants to be. The plate map wants 600 to 790 px for eight rows and a well inspector, so it scrolled from row D down on every window size measured, while the panel underneath had room left over: 381 px of grid hidden at 1920x1080, 442 px at 2560x1440. A scrollbar is worth having, but not while the neighbour leaves space unused.

### Changed

- v0.15.11: The two panels on step 2.2 are sized by what they hold. When both fit, the plate map takes exactly the height its rows need and the rest goes to the breakdown; when they do not both fit, the shortfall is split in proportion to what each asked for, so neither is starved by a number written in the source. The plate map goes from 312 px to 490 px at 1920x1080 and from 434 px to 756 px at 2560x1440, showing rows A to F where it used to stop at C.
- v0.15.11: A split the operator dragged is left alone, and so is one restored from an earlier session. The automatic fit is a starting point, not a correction applied over someone's decision.

## v0.15.10 (A workbook that writes one plate two ways does not start a run)

A KURO export carries the same plate twice, on `Fwd List` and on `expected_mutations`, and exports written before v0.14.3 wrote the two in different orders. MAME had reported that disagreement since v0.15.6 and then run anyway, on the reasoning that a sample map or a confirmed layout supplied the wells so the sheet order never reached one. That is true of the wells and false of the run: every verdict was still scored against whichever of the workbook's two plates the other input happened to match, with nothing checking that it matched at all. On `260722_Ep_R2-1_platemap.xlsx` the primer list puts `S11I` at A1 while the expected sheet puts `V233I` there, and `V263I` sits on the plate with no row in the list, shifting every well after it by one.

### Changed

- v0.15.10: A disagreement between the two plate descriptions in one workbook now fails validation instead of appearing beside a passing one. The run is refused whether or not a sample map or a well layout was chosen, because placing wells is not the same as recording which of the two plates went into the tubes, and no input on the analyze screen records that. The notice states the wells that disagree and what is missing, as before, and now says the run is held.
- v0.15.10: The refusal also holds before any validation is asked for. Picking the workbook checks it on its own, so the operator no longer reaches Run through a file picker without passing through validation, which is the route the 2026-08-04 misscoring took. A restored project applies the same check to the workbook it comes back with.
- v0.15.10: The way out is a workbook whose sheets agree: re-export from KURO v0.14.3 or later, or choose another file. Picking one clears the refusal, and the re-check reinstates it only when the new file disagrees with itself too. Naming the variant sheet and column no longer silences the notice, since that answers a different question and left the validation error with nothing on screen to explain it.

## v0.15.9 (A primer that leaves the manufacturer's range says so)

Each polymerase ships with a primer length and GC range in its own protocol, and KURO knew none of them. A 16 nt primer for KOD, whose manual asks for 22 to 35, designed and ranked exactly like any other; nothing on screen distinguished a primer the enzyme's maker would question from one it would not. The design itself was not wrong, since the ranking already balances Tm, structure and specificity, but the operator had no way to see that a particular oligo sat outside the range printed in the manual they were about to follow.

### Added

- v0.15.9: A designed primer that falls outside the polymerase manufacturer's recommended length or GC range is now flagged, naming the range and the document it comes from (NEB M0267 for Taq, M0530 for Phusion, M0491 for Q5, Toyobo KMM-101/201 for KOD, Thermo MAN0012036 for DreamTaq, Takara R050A for PrimeSTAR GXL). These are warnings only. Ranking, penalties and the designed sequences are untouched, because vendor guidance is advisory and the existing scoring already weighs what actually drives a reaction.
- v0.15.9: Where a manual does not document a range, nothing is flagged for it. PrimeSTAR GXL publishes no GC range, so GC is never questioned for that enzyme rather than borrowing a number from a different one.

### Changed

- v0.15.9: The JANUS deck the instrument files describe now has one definition instead of a copy in each writer. The mapping CSV, the workbook sheet and the on-screen preview built the same nine columns separately, each with its own rack numbers and liquid class, so an edit to one left the other two describing a different bench. The files themselves are unchanged, byte for byte, and the preview no longer works out which direction a transfer goes by reading the rack number back, which would have swapped forward and reverse on screen the first time anyone renumbered the deck.

## v0.15.8 (The mapping file comes out the way KURO already makes it)

The lab asked for one thing: the mapping file has to come out the way KURO makes it, and nobody wants to be asked for a liquid class. MAME was stricter than the program it sits beside. KURO writes its JANUS sheet at the end of a design without asking for anything, filling the deck numbers from the plates it just used; MAME refused to write at all unless an operator first typed a liquid class and a rack number for every plate. A run over `sort_barcode07/08/09` therefore produced no instrument file: those plates matched nothing in the fixed NB01/NB02/NB03 rack map, and v0.15.7 responded by not writing the sheet automatically at all. The one value that genuinely cannot be derived, how much of a cell stock to move, was buried in a dialog behind the two that can.

### Added

- v0.15.8: A finished analyze writes the instrument mapping too, `<result workbook>_janus.csv`, in the nine columns the robot reads. The pick list added in v0.15.7 stays exactly where it is as `<result workbook>_picks.csv`: one records what the run selected and reads without a deck in front of you, the other is the sheet that goes to the robot, and neither answers the other's question. Both outcomes are reported after the run, each naming its own file.
- v0.15.8: The transfer volume sits on step 2.1, next to the run's other inputs. It is the one instrument value nothing can derive, since how much of a cell stock to move is an experimental condition, and the shipped 100 µL is an assumption with no lab source in this repository, which the field says out loud.

### Changed

- v0.15.8: Deck rack numbers are derived from the plates of the run instead of being asked for. Source plates take the first racks in plate order and the destination takes the next, which is the convention KURO already writes for this instrument without consulting anybody (`Asp. Rack` 1 for the forward plate, 2 for the reverse, `Dsp. Rack` 3 for the destination). A run over `sort_barcode07/08/09` now numbers them 1, 2, 3 with the destination at 4. Anything typed in the export dialog still wins, and the dialog shows the derived numbers so what is on screen is what the file carries.
- v0.15.8: A blank liquid class no longer withholds the file. It still has no default, because it decides how the robot handles the cells and a guessed value would change that silently, so the column simply ships empty for the operator to fill. Nothing is invented to make a file come out: what shipped blank and what was derived from the run are reported next to the file, on screen and in the RPC response, as warnings that never block a run or an export.

## v0.15.7 (A finished run leaves the picks, not a worklist for a deck nobody confirmed)

The file every analyze wrote for itself was an instrument sheet: liquid class, dispense volume, and deck rack numbers, none of which have a lab source in this repository. Every exploratory re-run dropped another one in the output folder stating a deck that may not be the deck in the room, and any of them could be carried to the robot. On a real run it did not even get that far: the deck map knows the plate names NB01 to NB03, the run produced `sort_barcode07` and up, and the export refused every clone. The remedy the message named, File > Export Janus Mapping, has not existed since v0.14.7.

### Changed

- v0.15.7: The file an analyze writes beside its result workbook is the selection, not a worklist. Five columns, `name | source_plate | source_well | dest_well | priority_score`: which variant was picked, where it sits, and where it goes when the picks are gathered. It carries no instrument setting, so it is written whether or not one has been entered, which is the point. The Janus dialog still writes the 9-column instrument sheet and still refuses to write one without a liquid class, and the automatic file deliberately ignores the schema chosen there: the two answer different questions. How the picks are chosen and gathered (`dest_layout`, `include_verdicts`, `include_fallback`) is still the operator's, and is honoured by both.
- v0.15.7: The automatic file is named `<result workbook>_picks.csv`, not `_janus.csv`. The old name promised a file that could be handed to the instrument.
- v0.15.7: The Janus export labels a plate the way every other MAME export labels it. `nb_label` is the declared single source of truth (`sort_barcode07` to `NB07`, padding preserved, a name without digits unchanged) and the result workbook has always used it, but the Janus export kept a private NB01 to P1 dictionary that the selected plate, a barcode directory name, never matched, so the raw folder name was written instead. The same run therefore said `NB07` in one file and `sort_barcode07` in the other, and the two could not be read side by side. The dictionary is gone; the deck rack map is keyed by the same labels for the same reason, so what is displayed is what is looked up.
- v0.15.7: The deck map in the Janus dialog names the plates the run actually produced. A run sorted into native barcode folders reaches the export as `NB07` and up, which the fixed three fields had no rack number for, so every clone was rejected with no field on screen to fix it. The fields are built from the preview the sidecar returns, so the labels are the keys it checks; before a run they fall back to whatever was stored, and say so.
### Fixed

- v0.15.7: The raw-run path no longer reads an amplicon span it has just found missing. The guard sat on the first coordinate branch only, so a resolution reporting extraction without a span fell into the next branch and read `span.end` there, ending a finished demux with an AttributeError. The four cases now live in one function with the missing span handled first, falling back to the coordinates the resolution reports for itself; the producer never pairs extraction with a missing span, so this is a contract guard, pinned by tests rather than silenced with a type escape.

### Changed

- v0.15.7: Janus instrument settings are reachable from step 2.1, the screen that collects the run's other inputs, since the File menu item that used to open them was removed in v0.14.7. They stay optional and gate nothing: a run needs none of them. The text reporting the automatic file points there too, instead of at a menu that is gone.

## v0.15.6 (MAME reads the list you point at, and stops asking about the plate it built for nobody)

MAME still treated a KURO export as the only variant list it could analyse, kept a Build well layout button whose 96 rows nobody ever checked, refused a run over two sheets disagreeing inside a workbook the operator had already chosen how to read, and offered two EVOLVEpro-input routes for a workflow that always sequences. The Janus mapping an analyze run writes for itself also failed on every run, because the settings it needs never left the export dialog.

### Added

- v0.15.6: The analyze path reads a plain variant list, not only a KURO export. `analyze`, `validate_inputs` and `mame.build_well_layout` take optional `variant_sheet` / `variant_column`, absent means the previous behaviour, and `mame.inspect_variant_source` reports what a picked file offers: whether it is a KURO export, its sheets, the headers per sheet, and the column the reader would choose on its own (`variant`, `mutation`, `mutant_id` and their plurals, case-insensitive, with `wt`/`wildtype`/`control` read as the control row).
- v0.15.6: The expected-list file field carries a sheet and column picker, following the convention the KURO input step set: the auto-detected column is preselected as a first-class option in the same select, so the mapping on screen is the mapping that runs and a wrong guess is visible before a run rather than after one. The three calls that read the file (validation and both analyze paths) are sent the same pair, so a run can never be validated against rows nobody looked at. A KURO export hides the controls: its reader knows its own sheet and column, and a picker that changes nothing is worse than none.
- v0.15.6: A finished analyze reports what became of the Janus mapping it wrote beside its result workbook: the path and row count when written, that nothing was selected when there was nothing to write, and the reason when it failed. The run also sends the Janus settings the export dialog holds, which is what turns a `missing_liquid_class` refusal into a file; those settings are kept between sessions, since the sidecar assumes no liquid class of its own (it decides how the robot handles the cells).

### Changed

- v0.15.6: Build well layout is gone, along with its confirmation dialog. Confirming 96 rows by hand was never done, and nothing is lost by removing it: analyze assigns the wells itself whether or not a layout was pinned. The `well_layout` parameter stays on the RPC, and a layout stored in an older project still restores and still outranks the sample map.
- v0.15.6: A plate-order disagreement no longer stops a run. Now that the operator names the sheet and the column the variant list is read from, the program has no standing to refuse: the finding is stated on the inputs panel and the run proceeds, and once the sheet and column have been picked by hand the notice says nothing at all, because it would only repeat a decision that was just made. What it keeps reporting either way is a mutant on the plate with no row in the list, which shifts every later well by one whatever the sheet order is and is invisible in the output. The escape wording names the sample map and the column mapping, not the button that no longer exists.
- v0.15.6: The Activity step offers one path instead of two routes. The route selector is now an activity value source: an uploaded long-format activity table joined to the round genotype, or a plate layout with GC data or a raw Agilent report. The plate-layout handling is absorbed, not deleted, so the WT-block normalisation and round-1 baseline selection added in v0.13.27 stay exactly where they were, and the NGS verdicts are part of the answer whichever source is chosen.
- v0.15.6: The per-plate verdict breakdown scrolls instead of clipping its last rows.

## v0.15.5 (A workbook that describes two plates is stopped before the run, not after it)

A KURO export writes the same plate twice, on the primer plate sheet and on `expected_mutations`, and MAME reads wells off the second one when nothing else supplies them. On 2026-08-04 the two disagreed and all 94 wells were scored against variants nobody had put there. The run reported the right number of wells and a full set of verdicts, so the only sign anything was wrong was a day spent chasing it. A check for exactly this existed and ran only when a project was restored from autosave, which is the one path that day did not take.

### Fixed

- v0.15.5: `validate_inputs` runs the same plate-order check on the expected workbook it already has open and returns the finding under `plate_order`, absent when there is nothing to report so `valid` and `errors` keep their meaning. Severity splits on whether the layout is inferred: `handle_analyze` falls back to a draft layout built from `expected_mutations` only when neither `well_layout` nor `sample_map_xlsx` is given, and only then is the sheet order a well coordinate system. Blocking there, informational otherwise. Both parameters are read as optional, so omitting them grades as inferred, the louder of the two answers.
- v0.15.5: Choosing an expected workbook checks that one file straight away, through `check_plate_order` rather than a full validation, so the answer arrives while the other inputs may still be unchosen and cannot be buried under errors about them. The finding is also shown with the validation result and refuses the run: a blocking one disables the Run button and is repeated as the reason if a run is started another way. The way past it is to state which sample sits in which well, by choosing a sample map or confirming a built well layout, which is what makes the sheet order irrelevant to the run. No sheet is picked automatically, because only the operator knows which plate was pipetted.
- v0.15.5: The restore-time notice and the analyze-inputs notice are built from one message, so the same disagreement is described the same way in both places instead of reading as two problems. Each names the plate sheet, the disagreeing wells with what each sheet puts there, and the mutants the plate carries that `expected_mutations` does not.

### Changed

- v0.15.5: A clipped verdict-table cell now has a real way to read the rest of it. The Notes, AA Changes and Quality cells clip a long value at the column edge and the only way past that was a native `title` tooltip: about a second of hover before it appears, no keyboard path to it at all, and one unwrapped line that the browser cuts off at the screen edge, which is how a 180-character fallback explanation stayed unreadable. Each clipped cell now carries a button that opens the full text in a wrapped panel with no delay, reachable by Tab and closed with Escape. The button appears only when the text actually overflows its column, measured per cell, so a short note or an empty one stays a plain span.
- v0.15.5: Verdict-table columns can be resized by dragging the header edge, and the widths are kept per machine in local storage so a column widened once stays widened after a reload. The drag handle is focusable and takes arrow keys, so the width can be set without a pointer, and a column dragged too narrow comes back through a double-click, the Home key, or "Reset column widths" in the column menu.

## v0.15.4 (The verdict table opens on the picks, and a well explains itself)

The review screen opened on ALL, so the first thing on screen was every replicate copy of every well instead of the per-variant picks that the run was made to produce. Nothing anywhere said why a well was called what it was called: the expected mutation, the observed change, the counters behind the call and the two rejected replicate copies all arrived in the analyze response and none of them were drawn. And the file field that has accepted a plain variant list since v0.14.0 was still labelled for KURO exports alone.

### Changed

- v0.15.4: FINAL is the default verdict-table tab. FINAL fills only once replicate selection has run, so a run without a selection would open on an empty table that reads as a broken screen: FINAL degrades to ALL in that case and says so in a status line, and returns to FINAL by itself once selection data arrives. The stored filter is left untouched by the degrade.
- v0.15.4: Clicking a variant id in the verdict table, or a well in the plate map, opens the same detail panel in the right inspector. It puts `expected_mutations` beside `observed_aa_changes` (an empty observation reads as "No change observed" rather than blank), compares every replicate copy of the variant with the selected plate, the selection reason and any fallback reason marked, lists the confidence counters (reads, alignment drops, mixed and low-depth positions, consensus N, low-quality bases), shows the nucleotide changes, and offers the consensus FASTA path and the amino acid sequence as copy buttons instead of printing the sequence. Both entry points write the same `selectedWell`, so the plate highlight follows a table click. A field the backend did not report drops its row rather than being drawn as 0.
- v0.15.4: The expected-variant file field is labelled for both inputs it accepts. The help text states that a KURO export is read from its `expected_mutations` sheet with the status filter applied first, and that any other workbook lets the sheet and the variant column be chosen by hand.

## v0.15.3 (A zero-well MAME run names the gate that emptied it)

A raw run given a reference from another construct still finished with `Analysis complete` and an empty plate. The counts that could have said why (reads read, reads that cleared MAPQ, reads that cleared coverage) existed inside the demux and were dropped at the ingest boundary, so the only way to find the cause was to open the run folder and read the per-barcode statistics by hand.

### Changed

- v0.15.3: The analyze response carries the three demux gate counters, `total_reads`, `passed_mapq` and `passed_coverage`, filled by `ingest_run_folder` through a stats sink (pooled, or summed across native barcodes). Consensus-dir mode runs no aligner, so it produces no gate counters and the keys stay absent rather than zero-filled: a 0 there would read as "every read was rejected", the opposite of "this mode never counted".
- v0.15.3: The zero-result notice reads those counters and names a cause where the counts prove one. Reads present with none clearing MAPQ is reported as nothing aligning to the reference, the signature of a reference from a different sequence. Reads clearing MAPQ with none clearing coverage is reported as the separate case it is, what a whole-construct reference looks like against amplicon reads. Every other combination, including a run whose `fastq_pass` held no reads and consensus-dir mode where the counters do not exist, names no cause and keeps the checklist: asserting a cause without the counts behind it is worse than asking for a look. The counters themselves are shown as their own rows, and `pickAnalyzeYield` now carries all five yield fields instead of discarding a response that held only gate counts.

## v0.15.2 (A MAME run that cannot answer says so)

Three ways a raw MAME analysis could finish successfully while reporting nothing usable. v0.15.1 taught the raw path to extract the sequenced amplicon from a whole-plasmid FASTA, but only when the custom barcode workbook yields the shared primer tails; hand a plate map instead and the extraction was skipped without a word, the whole construct went to the aligner, and the coverage gate discarded every read: 180k to 290k reads in, 0 assigned, 0 wells, an empty consensus FASTA, and a completion marker that called it a success. The per-barcode counters could not name the gate that did it, because both carried the same number. And a rerun that swapped the reference resumed the completed units anyway, translating consensus called against the previous reference and reporting about 530 amino-acid changes per well for one real substitution.

### Fixed

- v0.15.2: Raw MinKNOW analysis refuses to start when the amplicon span cannot be derived from the custom barcode workbook AND the reference as supplied cannot pass the coverage filter. The two cases are told apart on the data: an alignment cannot span more reference than the read is long, so a run whose longest read falls short of `coverage_fraction` times the reference length can place no read in any well. A reference that is already an amplicon keeps running exactly as before. The refusal names the barcode file, the expected `*_f_<n>` / `*_r_<n>` primer naming rule, the reference length and the coverage fraction, so the file to correct is obvious.
- v0.15.2: `passed_mapq` and `passed_coverage` count their own gate. Both used to be assigned the post-filter total, which made a coverage wipeout indistinguishable from a MAPQ wipeout in the per-barcode statistics and nearly sent the diagnosis above down the wrong path. The native-barcode resume check now reads `passed_coverage`, the last gate, so a completed unit whose reads all died there is reprocessed rather than resumed as empty; markers written before the split carry equal values and are judged as they were.
- v0.15.2: Completion markers record the identity of what produced the unit, the reference digest and the gates applied, and resume compares it. A unit whose reference or parameters differ from the current run is reprocessed instead of reused, and a marker written before this record existed is reprocessed too, because nothing in it says which reference it used. Inventory alone said the files were all there, never what they were made from, which is how a one-second rerun rewrote the verdict table from consensus it had not recalled.
- v0.15.2: The verdict diff refuses a consensus that ends before the coding sequence it is compared against, naming both lengths and pointing at a stale output directory. Consensus is called one base per reference position, so such a pair cannot share a reference; a consensus that reaches the CDS end is still accepted, since an externally supplied one may carry insertions past it.

## v0.15.1 (MAME raw runs reach the review plate)

MAME could report `Analysis complete` while leaving the verdict table and plate empty when a whole-plasmid FASTA was supplied for a shorter sequenced amplicon. The default 98% coverage gate was applied to the full plasmid, so every read was rejected, and the resulting zero-hit completion marker caused later runs to skip the same input.

### Fixed

- v0.15.1: Raw MinKNOW analysis derives the shared primer tails from the custom barcode workbook and, when they uniquely bound the reference, extracts the sequenced amplicon before mapping. CDS coordinates are translated into the extracted reference, and the resolution details are returned with the analysis result.
- v0.15.1: A completed native-barcode marker with input reads but no MAPQ-passing alignments is reprocessed instead of resumed as a successful empty unit. If no wells are recovered after processing, the run now reports an actionable input/reference error rather than a false successful completion.

## v0.14.8 (Off-target scanning sees the sites the 3' end never touches)

Both off-target rules required the last bases of a primer to match the template exactly before a site was examined at all, so the 3' terminus decided which sites reached the thermodynamic test rather than only whether one could be extended. A site where a non-terminal stretch anneals was never scored, however strong the duplex. Widening the prefilter also surfaces sites whose 3' terminus does not pair, and those cannot prime, so each hit now records which failure mode it belongs to and only the two modes that can actually spoil a reaction are reported.

### Fixed

- v0.14.8: Candidate off-target windows now come from the union of the existing 4 nt 3' anchor and a position-agnostic 8 nt seed scan, each seed hit expanded back to a full-primer-length window and deduplicated by coordinate. The anchor path is kept because a site dense in internal mismatches can contain no exact seed anywhere, so the window set is a strict superset of the previous one. The verdict is still the `calc_heterodimer` Tm against the same 45.0 C threshold, and both design fixtures come out character-identical.
- v0.14.8: Every hit is classified as extendable (the 3' terminal base pairs, so a polymerase can extend from it, a spurious-amplicon risk) or as confined to the 5' overlap arm (the Gibson homology, so an assembly risk), and a site that is neither is no longer reported. The arm mode requires at least 15 nt of shared sequence, the bottom of the 15-30 bp overlap range NEB documents for HiFi assembly; without that floor an 8 nt partial match inside an 11 nt arm rejected a valid H277G design outright and displaced the winning P297I pair.

## v0.14.7 (One File menu, drawn once)

v0.13.35.1 renamed the two app-name triggers to `File` so the menubars had the same shape. The contents stayed in two files and drifted anyway. KURO offered project zip import and export and MAME did not, although the archive holds the whole project folder and therefore the work of both apps. The two menus also reached for different label keys for the same word, so fixing one left the other behind without any sign of it.

### Changed

- v0.14.7: Both menubars render one `FileMenu`. Project open, archive import, archive export, sidecar restart and quit live in it once; each app passes only what it alone can do. `useProjectArchiveActions` holds the two archive callbacks so their dialogs, toasts and cancel-is-not-an-error behaviour cannot diverge either. MAME gains archive import and export, which is the gap this closes: a project carries KURO and MAME work together, so exporting one from the app that produced the second half was never a KURO-only action.
- v0.14.7: Both menubars use `menu.file` and `menu.edit`. KURO was reading `menuBar.edit.title` for the same word.
- v0.14.7: A cross-layer group ties the two menubars to `FileMenu`, so touching one alone is reported rather than noticed months later.

### Removed

- v0.14.7: The File menu no longer repeats what a button already does during normal work. `Open sequence` duplicated the Browse button in `SequenceInput`, and the two behaved differently: the panel rejects a FASTA with an explanation while the menu path accepted it. `Export JANUS mapping` duplicated the `Open JANUS export` button in the pane that has the data in front of the operator. `Export run report` stays, being the only way in. The dead `onJanusOpen` prop goes with it.

### Added

- v0.14.7: CI runs the frontend unit tests. Around 900 vitest cases had no job and were only ever run by hand, which on this repo cannot be done from WSL at all: a `pnpm install` into the shared folder replaces the Windows `node_modules` and breaks the Windows build. New tests pin the shared File menu, including the absence of the two duplicated entries.

## v0.14.5 (Reopening a project brings back the session that was left)

Autosave was on, yet closing KURO and reopening the project landed on step 5 with nothing in it. Two separate causes stacked. The check that decides whether a restored design table is still valid compared each row against the reselected variant list plus the candidate pool it was drawn from, but never against what had actually been saved, so every row that fill-on-failure or rescue had filled in from that pool read as a leftover from an edited CSV and the whole table went. On one real autosave pair, 95 saved primer rows dropped to 0 two minutes later, and the emptied state then overwrote the good snapshot. Underneath that, restore was never treating the snapshot as authoritative: it reran `load_fasta` and the EVOLVEpro pipeline from the source files on every launch, and that rerun overwrote the domain selection, the variant selection, the pipeline statistics and the pool it had just restored. Saving more fields alone could not have fixed it.

### Fixed

- v0.14.5: Whether to keep a restored design table is now decided by comparing the saved mutation list against the mutation list a reload of the same EVOLVEpro source produces, not by checking each row against that list. A row whose mutation came from the candidate pool rather than the typed-in list is no longer read as evidence the source changed. A genuinely stale autosave (source file edited, round advanced) still discards the table and says so, unchanged.
- v0.14.5: The autosave snapshot stores the candidate variant pool (`poolVariants`) next to `designResults`, so pool-dependent UI such as the combinatorial-variant ratio no longer flashes empty during a restore.

### Added

- v0.14.5: Autosave keeps the rest of the session too (schema 5): the wizard position and per-step completion, the EVOLVEpro derived state (selection, ranking, per-step statistics, score map, domain statistics), the reference domain annotation and its hash, the loaded structure, the parsed sequence itself, table sorting, and the benchmark settings and output. Reopening a project restores where the work was, not just its inputs.
- v0.14.5: A restore that finds the sequence file and the EVOLVEpro source unchanged since the snapshot was written skips the pipeline rerun entirely and uses the saved state as it stands. Sameness is judged by file size and modification time, so no hashing cost is added. A file that did change, or one that cannot be inspected, falls back to the previous reload path and to the divergence check above.
- v0.14.5: `Ctrl/Cmd+S` saves the open project immediately instead of waiting out the autosave debounce, and reports the time it saved at. It works while a text field has focus, where the other global shortcuts deliberately stand aside, and it is listed in the keyboard shortcuts dialog.

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
- v0.13.16.0: Kuma can now **update itself in place**. When a newer signed release is detected, the update dialog offers **Update now**, which downloads the platform artifact, verifies its Ed25519 signature against the key embedded in the app, installs it, and relaunches, no manual installer step. Windows (NSIS), macOS, and Linux AppImage are fully automatic; Debian `.deb` has no updater artifact and falls back to opening the release page. Signing uses a self-generated Tauri updater key (not a paid code-signing certificate), so the free/unsigned distribution policy is unchanged and the SmartScreen guidance still applies. (`src-tauri/tauri.conf.json`, `src-tauri/src/lib.rs`, `src-tauri/capabilities/default.json`, `src/lib/updateCheck.ts`, `src/components/dialogs/UpdateAvailableDialog.tsx`, `.github/workflows/build.yml`, `scripts/gen-latest-json.mjs`)

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
- v0.13.8.0: the KURO Candidate 3D structure analysis panel now explains itself inline, the Structural Dispersion card, its null-distribution histogram, and each metric row carry `?` help toggles; the histogram marker uses `P1`/`P96` percentile notation instead of `1%ile`; the metric is relabeled "Observed percentile vs random"; and a Color legend under the viewer maps every color (domain / pLDDT backbone, y_pred variant spheres, active-site sticks, binding-site spheres) to its meaning, adapting to the current coloring mode. (`src/components/panels/Selection3DPanel.tsx`, `src/locales/*.json`)
- v0.13.8.0: the Color legend rows are clickable toggles that show/hide each 3D layer (variant spheres, active-site sticks, binding-site spheres) while the backbone stays always-on; the standalone Interface checkbox is folded into the legend, and the panel is reordered to toolbar → 3D viewer → legend → Structural Dispersion → tables so toggle/coloring changes are visible in the viewer immediately. (`src/components/panels/Selection3DPanel.tsx`, `src/locales/*.json`)
- v0.13.8.0: corrected the mislabeled "Interface" overlay to "Binding site" across the viewer, legend, table column, and hover label, the magenta spheres are UniProt `Binding site` (ligand/cofactor/metal-binding) residues, not a protein-protein interface. (`src/components/panels/Selection3DPanel.tsx`, `src/locales/*.json`, `docs/kuro/05-output.md`)
- v0.13.8.0: documented that the 3D dispersion, pLDDT, and active/binding overlays are interpretation/QC aids, not candidate-selection filters, low-confidence or disordered residues are not auto-excluded from the mutation set, and EVOLVEpro y_pred ranking remains the sole selection authority. (`docs/kuro/05-output.md`)

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
- v0.13.4.0: the Tauri auto-updater is removed, the frontend `src/lib/updater.ts`, the Cargo dependency, the updater capability, the `lib.rs` plugin registration, and the About-dialog wiring are all gone, and the Check-for-updates menu entry is repurposed to the release page. (`src/lib/updater.ts` deleted, `src-tauri/Cargo.toml`, `src-tauri/capabilities/default.json`, `src-tauri/src/lib.rs`, `src/components/layout/SharedAboutDialog.tsx`)

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
