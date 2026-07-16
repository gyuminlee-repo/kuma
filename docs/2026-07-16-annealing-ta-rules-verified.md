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
| Phusion (NEB) | NEB Tm (neb_tm_offsets) | 3-step | min(NEB Tm) + 3 (approx) | Tm(low) ≥ 72 → 72 C 2-step | optional (off) | approx; exact value from NEB Tm Calculator |
| Q5 / Q5 Hot Start (NEB) | NEB Tm (neb_tm_offsets) | 3-step | min(NEB Tm) + 1 | Tm(low) ≥ 72 → 72 C 2-step | optional (off) | Q5 and Q5 Hot Start share one profile |
| Q5 SDM (NEB) | NEB Tm (neb_tm_offsets) | 3-step | min(NEB Tm) + 3 (fallback) | none | optional (off) | exact value from NEBaseChanger (mismatch-aware); offline approximation |
| KOD (KOD One) | primer3 NN (KOD buffer) | 3-step | min(NN Tm) − 5 | Tm(low) ≥ 73 → 68 C 2-step | 74→72→70→68 C (step-down, ~5 cyc each) | Toyobo KOD One recommended step-down |
| DreamTaq (Thermo) | Wallace (<25 nt) / NN (≥25 nt) | 3-step | Tm(low) − 5 | none | none | length cutoff at 25 nt |
| TAKARA_GXL | Wallace 2(A+T)+4(G+C)−5 | fixed | Wallace Tm(low) > 55 → 60 C, else 55 C | none | none | discrete steps, no continuous formula |

2-step promotion compares the raw lower Tm against the threshold (`>=`).
`recommended_ta` is reported in whole degrees.

## Worked Ta values on the fixture

Computed on `fixtures/pSHCE-dmpR.gb` (first designed pair per profile), whole
primers. All physical, none near the pre-fix 81.5 artefact.

| Profile | Mut | Tm(low) | Ta | mode |
|---|---|---|---|---|
| Benchling | Q232A | 60.4 | 55 | 3-step |
| Taq | Q232A | 60.5 | 56 | 3-step |
| Phusion | Q232A | 63.5 | 66 | 3-step |
| Q5 | Q232A | 66.0 | 67 | 3-step |
| KOD | Q232A | 63.6 | 59 | 3-step (touchdown 74→72→70→68 C) |
| DreamTaq | Q232A | 55.0 | 50 | 3-step |
| TAKARA_GXL | Q232A | 53.0 | 55 | fixed |
| Q5 SDM | E335A | 71.2 | 74 | 3-step |

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
  Temperature in PCR" and the Tm Calculator help (Q5 Ta = Tm(low) + 1; 2-step
  for Tm ≥ 72 C).
- NEB SDM: NEBaseChanger / Q5 Site-Directed Mutagenesis Kit protocol (E0554)
  FAQ (Ta from the primer Tm; the kit calculator adds a mismatch penalty not
  reproduced offline).
- KOD One: Toyobo KOD One PCR Master Mix, product manuals KMM-101 / KMM-201
  (recommended annealing / step-down cycling).
- PrimeSTAR GXL: Takara PrimeSTAR GXL DNA Polymerase manual R050A, p. 4
  (discrete annealing, 60 C for primers with Tm > 55 C, else 55 C).
- DreamTaq: Thermo Fisher DreamTaq DNA Polymerase manual MAN0012036, p. 2-3
  (Ta = Tm − 5; Wallace rule for short primers, nearest-neighbour otherwise).
