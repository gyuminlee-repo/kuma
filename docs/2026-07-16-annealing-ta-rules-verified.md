# Per-enzyme Annealing Temperature (Ta) Rules (verified 2026-07-16)

KURO now reports a recommended annealing temperature (Ta) per polymerase
alongside each designed SDM primer pair. Ta is an additive output. The design
stays byte-for-byte identical: the design Tm scale (62/58/42 targets), salt
parameters, and primer selection are untouched. Only four output fields are
added.

## Design invariant, Ta only added

Ta never feeds back into design. Before and after this change the eight
built-in profiles produce identical `tm_no_fwd`, `tm_no_rev`, and `tm_overlap`
on the `fixtures/pSHCE-dmpR.gb` fixture (verified by re-running the same design
and diffing). Reading a primer sequence to compute Ta is read-only.

## Where enzyme identity lives (updated)

Design runs on one fixed Tm scale for every polymerase: SantaLucia 1998 with
santalucia salt correction at mv 50 / dv 1.5 / dntp 0.8 / dna 250, the Benchling
scale the paper targets (62/58/42) are defined on. A profile `tm_method`,
`salt_correction`, `salt_*`, and `dna_conc` therefore feed Ta only, never design,
and the NEB calibration table is Ta-only as well. Selecting a polymerase changes
the reported Ta, not the primers.

## Tm source for Ta

Ta uses the lower of the two whole-primer template-annealing Tm values (the
pair anneals no hotter than its weaker primer). The forward-vs-reverse overlap
Tm is never used.

Sequence source is the whole primer (`forward_seq` / `reverse_seq`), not the
non-overlap `forward_binding` / `reverse_binding` fragment. Rationale: in
partial-overlap mode the `*_binding` field is only the 3' extension (7-11 nt),
which yields a non-physical Ta (7-31 C) and falls outside the NEB offset
model's valid 17-39 nt calibration range; in full-overlap mode it equals the
whole primer. The whole primer is the mode-invariant, in-domain choice and
matches the design's own fwd/rev Tm target (the 62/58 whole-primer targets, not
the 42 overlap target). An integrator wanting the literal fragment can switch
the two arguments in `design.py::_serialize_result`.

## Rules table

| Profile | Ta Tm source | mode | Ta formula | 2-step promotion | touchdown | note |
|---|---|---|---|---|---|---|
| Benchling | primer3 (profile buffer) | 3-step | Tm(low) − 5 | none | none | reference profile, not an enzyme; select an actual enzyme for a usable Ta |
| Taq (NEB) | NEB Tm (neb_tm_offsets) | 3-step | min(NEB Tm) − 5 | none | optional (off) | NEB Standard Taq |
| Phusion (NEB) | NEB Tm (neb_tm_offsets) | 3-step | min(NEB Tm) + 3, or min(NEB Tm) itself when the lower-Tm primer is < 20 nt (approx) | Ta ≥ 72 → 72 C 2-step | optional (off) | approx; exact value from NEB Tm Calculator |
| Q5 / Q5 Hot Start (NEB) | NEB Tm (neb_tm_offsets) | 3-step | min(NEB Tm) + 1 | Ta ≥ 72 → 72 C 2-step | optional (off) | Q5 and Q5 Hot Start share one profile |
| Q5 SDM (NEB) | NEB Tm (neb_tm_offsets) | 3-step | min(NEB Tm) + 3 (fallback) | Ta ≥ 72 → 72 C 2-step | optional (off) | exact value from NEBaseChanger (mismatch-aware); offline approximation |
| KOD (KOD One) | primer3 NN (KOD buffer) | 3-step | min(NN Tm) − 5 | Tm(low) ≥ 73 → 68 C 2-step | 74→72→70→68 C (step-down, ~5 cyc each) | Toyobo KOD One recommended step-down |
| DreamTaq (Thermo) | Wallace (<25 nt) / NN (≥25 nt) | 3-step | Tm(low) − 5 | none | none | length cutoff at 25 nt |
| TAKARA_GXL | Wallace 2(A+T)+4(G+C)−5 | fixed | Wallace Tm(low) > 55 → 60 C, else 55 C | none | none | discrete steps, no continuous formula |

`recommended_ta` is reported in whole degrees.

The 2-step promotion is compared (`>=`) against whichever quantity the
manufacturer states the threshold on, declared per profile as
`two_step_basis`:

- `"ta"` for the NEB enzymes. NEB E0553 section 10 words the condition as
  "primers with **annealing temperatures** ≥ 72 C", so the probe is the
  computed Ta, not the raw Tm. Because Phusion adds +3 and Q5 adds +1, a
  raw-Tm probe let pairs slip through and emit an annealing step hotter than
  the 72 C extension step, which is not a runnable program.
- `"tm"` for KOD One, whose Toyobo threshold is stated on the primer Tm. This
  is also the default when a profile omits the field, so profiles without a
  promotion are unaffected.

Consequence: for every profile carrying a positive `delta`, the promotion is
what bounds Ta, and no separate clamp constant exists in the code. A clamp
would be unreachable, since the 3-step branch hands off before Ta can pass the
profile ceiling.

Phusion also carries a length branch (`short_primer_len` 20,
`short_primer_delta` 0) from NEB E0553 section 7 / M0530 section 8, which
directs primers shorter than 20 nt to anneal at the Tm of the lower primer
itself rather than at Tm + 3. The length consulted is that of the lower-Tm
primer, matching the manual wording. Both the threshold and the short-primer
offset live on the profile.

## Worked Ta values on the fixture

Measured on `fixtures/pSHCE-dmpR.gb` (target_start 1790,
`fixtures/mutation_list_insilico_test.csv`), whole primers, over every designed
pair per profile. Q5 SDM runs in its default full-overlap mode. No pair anneals
above the 72 C extension step.

| Profile | pairs | Tm(low) range | Ta range | mode |
|---|---|---|---|---|
| Benchling | 10 | 62.9 to 65.2 | 58 to 60 | 3-step |
| Taq | 10 | 60.2 to 65.1 | 55 to 60 | 3-step |
| Phusion | 10 | 62.7 to 65.1 | 63 to 67 | 3-step (3 pairs take the < 20 nt branch) |
| Q5 | 10 | 67.6 to 71.7 | 69 to 72 | 3-step, 1 pair promoted to 2-step |
| KOD | 10 | 62.9 to 65.2 | 58 to 60 | 3-step (touchdown 74→72→70→68 C) |
| DreamTaq | 10 | 62.0 to 70.0 | 57 to 65 | 3-step |
| TAKARA_GXL | 10 | 57.0 to 65.0 | 60 | fixed |
| Q5 SDM | 11 | 71.4 to 75.7 | 72 | 2-step (offline Tm+3 runs hot, capped at 72) |

The Q5 SDM row is the honest rendering of an offline approximation that has no
NEBaseChanger mismatch penalty: the raw Tm+3 lands at 74 to 79 C, above the
E0554 annealing range of 50 to 72 C, so every pair collapses to combined
anneal/extend at 72 C. Read the reported Ta as a ceiling, and take the exact
value from NEBaseChanger when it matters.

The ceiling and the length branch are pinned by
`tests/test_annealing_ta_ceiling.py`, so these values cannot silently go stale.

## Q5 SDM overlap-mode yield on the fixture

Measured on `fixtures/mutation_list_insilico_test.csv` (12 sites): full-overlap
mode, the kit default, designs 11 of 12 (only Y155A fails), and partial-overlap
mode designs 5 of 12. An earlier revision of this document claimed 4/12 full
with D227A and E335A lost, and 0/12 partial. Both claims are false against the
fixture; the corrected figures come from re-running the design and are pinned
by `tests/test_annealing_ta_ceiling.py`. The yield is Ta-independent, since Ta
never feeds back into design, so it is unchanged by the Ta rules.

Cause of the remaining tension: full-overlap design optimises a single primer
against `opt_tm_fwd`,
because reverse is the reverse complement of forward and SantaLucia
nearest-neighbour is strand-symmetric. Before the change the Q5 SDM profile
carried no `opt_tm_fwd`, so the target fell back to `opt_tm` 68 C on the NEB
calibration scale. It is now the declared 62 C on the fixed Benchling scale. The
Q5 SDM kit also floors primer length at 25 bp, so a site whose shortest legal
25 bp primer is already hotter than the tolerance window around 62 C yields
nothing.

Evidence on the fixed Benchling scale: the 11 sites that design land at
`tm_fwd` 61.7 to 64.8 C, inside the window, and Y155A is the single site whose
shortest legal primer stays outside it. Partial mode, whose geometry the
62/58/42 targets were defined for, designs a different and smaller subset
(5 of 12) at `tm_fwd` 62.0 to 65.8 C.

This is a consequence of the paper method, not a defect. The 62/58/42 targets are
defined for the partial-overlap geometry, where forward runs 17 to 39 bp and the
overlap is a separate shorter window. Full overlap is a different geometry with a
25 bp floor, so the same numeric target lands differently. Reconciling the two
would need a per-mode design target, which is a separate decision and is not
taken here. Full mode stays as-is.

## Output contract (4 fields per primer pair)

- `recommended_ta`: number | null (3-step Ta, 2-step temperature, or fixed step)
- `ta_mode`: "3step" | "2step" | "fixed"
- `ta_detail`: string (formula + enzyme + condition, for the tooltip)
- `ta_touchdown`: string | null (e.g. "74→72→70→68 C", null when none)

Fields are null for a profile without a `ta_rule` (custom profiles) or an empty
primer sequence.

## First sources

- NEB Tm scale and offline calibration: NEB Tm API (https://tmapi.neb.com),
  committed table `kuma_core/kuro/resources/neb_tm_offsets.json` (calibrated
  2026-06-18, primer conc 0.5 uM, len 17-39 nt, GC 40-60%).
- NEB annealing guidance: NEB application note "Universal Annealing
  Temperature in PCR", the Tm Calculator help (Q5 Ta = Tm(low) + 1), and
  Phusion E0553 section 10 / M0530, which state the 2-step condition on the
  annealing temperature ("primers with annealing temperatures ≥ 72 C"), the
  basis the code follows.
- NEB Phusion primer length branch: E0553 section 7 / M0530 section 8
  (primers over 20 nt anneal at Tm(low) + 3; primers under 20 nt anneal at the
  Tm of the lower primer).
- NEB SDM: NEBaseChanger / Q5 Site-Directed Mutagenesis Kit protocol (E0554)
  FAQ (Ta from the primer Tm; the kit calculator adds a mismatch penalty not
  reproduced offline).
- KOD One: Toyobo KOD One PCR Master Mix, product manuals KMM-101 / KMM-201
  (recommended annealing / step-down cycling).
- PrimeSTAR GXL: Takara PrimeSTAR GXL DNA Polymerase manual R050A, p. 4
  (discrete annealing, 60 C for primers with Tm > 55 C, else 55 C).
- DreamTaq: Thermo Fisher DreamTaq DNA Polymerase manual MAN0012036, p. 2-3
  (Ta = Tm − 5; Wallace rule for short primers, nearest-neighbour otherwise).
