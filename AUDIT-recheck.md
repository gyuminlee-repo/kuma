# Adversarial re-verification of the codex-produced findings

The first three areas of this sweep were produced by a different tool from the
last three. This pass re-examines all of them, not to find new defects but to
check whether the recorded ones are true.

Scope: `AUDIT-mame-core.md`, `AUDIT-kuro-core.md`, `AUDIT-sidecar.md`.

## Why this pass exists

During the fifth area two lanes reached opposite conclusions about the same
number, each with executed evidence attached. Settling it needed the export code,
which showed both lanes had misjudged what the right answer was.

**Executed evidence establishes what the code prints. It does not establish what
the code ought to print.** A finding is wrong whenever its claim about the
correct output is wrong, however solid the reproduction.

A second reason applies specifically to these three documents: **none contains a
single self-refutation.** Every candidate that tool examined became a confirmed
finding. Each of the later lanes, run under a rule that forced execution before
confirmation, refuted two or three of its own candidates. A zero-refutation rate
is not evidence of accuracy.

## A counting error found first

`AUDIT-kuro-core.md` holds **32** findings, not the 36 its own numbering implies.
Ids **F3, F22, F23 and F31 do not exist** in the document. The published total
carried the highest id rather than the count, and this file repeated that figure
before checking it.

Corrected totals for the three documents: 26 + 32 + 19 = **77**.

## Method

Every finding was triaged into one of two buckets.

- **Bucket A, mechanical (27).** The claim is only about what the code does and
  the correct behaviour is not in dispute: an unhandled exception, a swallowed
  error, a duplicated constant, a value written and never read back. Not
  re-verified, by design.
- **Bucket B, judgement (50).** The finding asserts what the *correct* output
  would be: a count, a rate, a threshold, a coordinate, a unit, a
  classification, an ordering, a denominator.

For every bucket B finding the ground truth was established independently, from
the declared contract, the consuming code, the physical process, or the producing
code on the other side of a layer boundary. **All 50 were checked.**

## Outcome

| Verdict | Count |
|---|---|
| CONFIRMED cleanly | 36 |
| CONFIRMED, but the "correct output" clause is wrong | 8 |
| WRONG DIRECTION | 3 |
| NOT A DEFECT | 3 |

71 of 77 findings stand. Six do not, and eight need their remedy restated before
anyone acts on them.

## The six that did not survive

### Echo reverse source plate (kuro F26), WRONG DIRECTION

The finding said the Echo row names `Source [2]` for a reverse primer that lives
on plate 1, and that `Source [1]` is correct.

Ground truth: `_pair_rev_per_plate` (`plate_mapper.py:328-372`, called at
`:568-569`) **materialises a copy of the shared reverse primer on every forward
plate chunk**, re-indexing its well from `_well_name(0)`. Plate 2 therefore holds
its own physical copy, and `Source [N]` pairs with `Destination [N]` by
construction. `Source [1]` would aspirate from a plate that does not serve
destination 2.

The single-shared-reverse case in the finding is not a defect at all. A real
defect lives here with a different statement: with two or more reverse groups
spanning the plate boundary, `build_echo_rows:918` takes the well from the
*global* reverse list while the workbook re-indexes per chunk, so Echo says
`Source [2] / D1` and the workbook says `B1`. **The plate index is right; the
well is wrong.**

This one was also asserted in conversation on the strength of reading
`plate_mapper.py:917-918` alone, without checking what the workbook places on
plate 2. Recorded here because the correction changes which line gets fixed.

### NB label collisions (mame C4), WRONG DIRECTION

The finding fed in `barcode01` and `NB01` as two physical plates.
`sort_barcode.py:35,52-74` canonicalises **both to `sort_barcode01`**, with
`barcode06 -> sort_barcode06` and `NB06 -> sort_barcode06` given as worked
examples in the docstring. They are two spellings of one barcode, so merging them
into one rack is correct.

The duplicate-key symptoms are real: `nb_label` maps all three spellings to
`NB01`, openpyxl renames the second sheet, and the JANUS deck dict is
last-write-wins. Corrected statement: `nb_label` is a display label with no
injectivity guarantee (`nb_label.py:17-24`) and export keys on the label rather
than the source identifier. Whether two genuinely distinct sources can collide is
**undetermined**, and settling it needs a demonstration that a plate key other
than a canonical `sort_barcodeNN` reaches `excel_writer` or `janus_mapping`.

### Builder to renderer renders every well empty (mame C26), NOT A DEFECT

`render_html` documents the attachment as a caller precondition
(`report/html_renderer.py:511-514`) and the sole production caller satisfies it
(`handlers/report.py:88-89`). For the executed call, 96 empty wells is the
contract-correct output.

Corrected statement: the kernel is an API-shape flaw. `report/builder.py:3-6`
overclaims against the renderer own precondition, and a required input travels in
a private attribute rather than a field. No category 2 loss occurs on any
exercised production path.

### Negative scores erase entropy (kuro F6), WRONG DIRECTION

The stated requirement is mathematically invalid. `_position_entropy` normalises
per position (`evolvepro.py:265`) and takes Shannon entropy of the resulting
probability vector, which is scale-invariant but provably **not** shift-invariant.
Verified: multiplying scores by 3 reproduces the unscaled value exactly; adding 4
does not. Demanding additive invariance demands a different metric.

The real defect is the clamp at `:257`, `max(y, 0.0)`: every position whose
scores are all at or below zero collapses to 0.0, so a perfect tie and a clear
standout are reported identically. Corrected remedy: map real-valued scores into
a valid non-negative weight domain before normalising, or reject a negative-score
domain at the boundary.

### Missing Cα as maximum diversity (kuro F14), NOT A DEFECT as filed

The cited location does not contain the cited function. The real code is
`pairwise_ca_distance` (`alphafold.py:294-315`), whose docstring at `:302`
**documents 1.0 as a sentinel**: "Returns 1.0 when either coordinate is missing".
The consumer is a maximin rule using the same convention in two other branches,
an intentional policy that keeps unmodelled residues eligible.

Corrected scope: the defect belongs at `benchmark.py:47-58`, where
`_structural_spread` averages that same sentinel into a **reported** metric. There
a missing coordinate is consumed as a measured distance and inflates the number.

### Tripled round workbook (sidecar F10), NOT A DEFECT

The guard exists one layer up and its comment names this exact failure:
`AdvisoryDecisionCard.tsx:371-376` dedups by normalised path before the RPC,
saying "Raw string equality lets the same file in twice under two spellings on
Windows, and the handler counts entries as rounds." The reproduction bypassed the
only production caller.

Residual and unadjudicated: the UI dedups by path only, so two copies at
different paths would still accumulate.

## The eight whose remedy needs restating

| Id | Correction |
|---|---|
| mame C1 | "Reject non-positive raw areas" is over-broad. An area of exactly `0.0` is a real dead-variant measurement and `normalize.py:78-84` already handles it. Reject non-finite and **negative** areas, and non-finite or non-positive **WT denominators**. |
| mame C12 | "Never PASS" is right; the second remedy is not. Marking non-finite as not evaluable still PASSes (`verdict.py:302-314` skips the gate with a note). Hard-reject a nan under a `basis=covered` header, or recover to 1.0 so the NO_CALL gate fires. |
| mame C21 | With `min_length=0` the documented return is the empty string, not `None`. No production caller passes a non-positive `min_length`. |
| kuro F5 | Broader than filed. `_combo_positions` splits on `[\s/,]+` while the exclusion uses `[/,]`, so **whitespace**-delimited combos leak identically, not only colon-delimited ones. |
| kuro F10 | Not user-facing. `designSlice.ts:113` always sends the mode explicitly. Impact is confined to the CLI and direct library callers. |
| kuro F18 | C-terminal truncation, the common tag case, is harmless. The defect is specific to **N-terminal** offsets. |
| sidecar F15 | Two defects under one id. The `{}` against `None` conflation is one; accepting `selected_wells=["Z99"]` is a separate defect in a different function (`analyze.py:597-619`). Split them. |
| sidecar F18 | The rationale is false and the truth is worse. The design path **can** reach residue zero: `resolve_mutation` (`mutation.py:105-118`) computes `codon_start = target_start - 3` and guards only `< 0`, so whenever `target_start >= 3` it silently mutates a base **outside the CDS**. |

## Findings whose correctness remains most doubtful

Ranked, including ones that landed on CONFIRMED, so a later pass knows where to
look.

1. **mame C4**, the WRONG DIRECTION verdict rests on canonicalisation; the
   reachability of a genuine two-source collision is unresolved.
2. **sidecar F10**, turns on whether a UI guard discharges an RPC boundary
   obligation. A reviewer holding that every RPC validates its own input, which
   is the standard sidecar F17 applies, would restore CONFIRMED.
3. **mame C26**, two contradicting docstrings. If the builder docstring
   governs rather than the renderer parameter doc, this reverts to CONFIRMED.
4. **kuro F14**, rests on a judgement about documented-sentinel intent. The
   `benchmark.py` re-scope is not in doubt.
5. **mame C1**, the only finding whose remedy contains an outright wrong clause
   while still being a real defect.
6. **kuro F10**, `polymerase.py:49` calls the field a hint, which supports the
   opposite reading.
7. **kuro F11**, the mathematics is airtight; reachability is limited to the
   RPC boundary.
8. **mame C6**, the n at or above 9 boundary is derived arithmetic, not a
   stated contract.
9. **kuro F9**, Python includes the stop codon (`sdm_engine.py:1808`) and
   TypeScript excludes it (`autoDetectCds.ts:12`). The audited value is right for
   its layer. **This cross-layer disagreement is covered by no group in
   `.cross-layer-sync.json` and is a genuine uncovered finding.**
10. **mame C21 and C10**, C21 is unreachable in production; the specific 490 bp
    in C10 is fixture-dependent and unverified, though the defect and its
    direction are certain.

## What remains unchecked

Nothing in bucket B. All 50 received an independent ground-truth determination.
Bucket A was not re-verified by design, though kuro F21 and F28 were incidentally
executed and hold.

Two items were left open rather than guessed:

- **mame C4 reachability**, settled by demonstrating whether a plate key other
  than a canonical `sort_barcodeNN` can reach `excel_writer` or `janus_mapping`.
- **mame C10 specific value**, which needs the original fixture template length.

The 103 findings from the fourth and fifth areas were not re-verified in this
pass. Each of those lanes already refuted candidates of its own under the same
execution rule, so they carry a different risk profile, but they are not
exempt: at least one of them, the plate count, was corrected during the fifth
area itself.

## Scope

Zero writes. No file was created, modified or deleted; no git state was changed.
All reproductions ran against the unchanged worktree.
