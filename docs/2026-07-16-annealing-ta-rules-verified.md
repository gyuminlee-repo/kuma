# Per-enzyme Annealing Temperature (Ta) Rules (verified 2026-07-16)

KURO now reports a recommended annealing temperature (Ta) per polymerase
alongside each designed SDM primer pair. Ta is an additive output. The design
stays byte-for-byte identical: the design Tm scale (62/58/42 targets), salt
parameters, and primer selection are untouched. Only four output fields are
added.

## Design invariant, Ta only added

Ta never feeds back into design. Reading primer sequences to compute Ta does
not alter the design Tm scale or primer selection.

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

**Correction (2026-07-21)**: the Benchling row records the state on 2026-07-16.
That profile was removed in v0.13.20, since "Benchling" names the fixed
design-time Tm scale rather than an enzyme. Seven profiles ship now and the
default is KOD. The rest of this table is unchanged.

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

## Ta limits and overlap modes

A positive Ta offset can exceed the extension temperature. The profile-specific
two-step rule bounds that output. Q5 SDM is an offline approximation without
the mismatch penalty of NEBaseChanger; consult that calculator for an exact
protocol recommendation.

The ceiling and length branches are covered by
`tests/test_annealing_ta_ceiling.py`. Full and partial overlap impose different
primer geometry and length constraints, so they can admit different designs
under the same Tm target. Ta remains an output and does not alter that search.

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
