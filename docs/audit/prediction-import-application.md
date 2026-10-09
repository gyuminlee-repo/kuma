# Local prediction bundles in strict selection

This follow-up starts at PR #6 `c857b3560f45d2c5fd132b51bfd0920c25043983`.
It imports an existing prediction locally. It does not run AlphaFold, ColabFold,
MSA searches, model servers or uploads. Existing accession selection remains
available and the CSV candidate pool/score/budget algorithms are unchanged.

## Application contract

1. Inspect a local supported ZIP. A bounded parser checks archive safety and exact
   structure/confidence/query pairing before listing models and protein chains.
2. Explicitly choose a model and chain. Inspection does not automatically choose
   the best-ranked model or treat structural ranking as a variant fitness score.
3. Match the supplied reference through unique exact sequence correspondence.
   Supported terminal tags/truncations retain explicit unmapped positions. This
   path does not enable homolog alignment or synthesize missing coordinates.
4. Select the requested N from the supplied df_test candidate pool using the
   existing strict budget/cap policy. Missing coordinates remain excluded with
   reasons. pLDDT/PAE are explanatory and do not silently change ranking or N.
5. Review the result and a derived selected-chain C-alpha trace. The certificate
   retains original model, chain, author residue number and insertion code, plus
   the separate reference-to-viewer correspondence. All viewer highlights use it.
6. Before design, reload and revalidate the same bundle hash, model/chain, mapping,
   source/reference/candidate hashes and selected IDs. A change blocks design
   instead of substituting another model, dataset or fallback selection.

Source/model/chain changes invalidate the result. Late responses must not restore
an older choice. Workspace restoration does not reactivate a saved strict result.
The original ZIP stays on the user's filesystem. Source hashes describe the bytes
read; recognizing a layout is not proof of an authentic or unmodified producer run.

## Display and confidence

The imported view is deliberately a **C-alpha trace**, not an all-atom structure.
Its display PDB uses chain A and reference residue numbers. Original identities
remain separate and are not overwritten. Coordinates come only from the mapped
source model. PDB display rounding is bounded at 0.000501 angstrom per component;
out-of-range coordinates fail instead of shifting or rescaling the structure.
Selection calculations use the original coordinates. The display artifact has its
own hash. Its zero B-factor placeholder is never interpreted as confidence.

AF3 atom confidence is validated against the paired CIF and reported at each
observed C-alpha as CA pLDDT. It is not indexed as a residue-length atom array.
ColabFold pLDDT is checked against the full query/residue order. Missing confidence
is unknown, not zero or a declaration that a region is nonfunctional.

The paired native PAE matrix remains directional: row i is the alignment anchor
and column j is the evaluated residue/token. The application summary reports
mean and maximum **off-diagonal values for the selected chain's complete polymer**,
including positions without observed CA where supported. This summary is not a
whole-complex or domain-confidence assessment. Missing PAE stays unavailable;
malformed supplied PAE is rejected. The UI exposes reference-position pLDDT and
states that interdomain confidence is not assessed. No universal confidence filter,
functional score or biological validity cutoff is introduced.

Producer links and applicable terms links are visible. Bounded bundled
`terms_of_use.md` notices retain their text and hash. ColabFold query A3M member and
hash also remain in the certificate. Code licensing does not relicense prediction
outputs. Importing a file does not accept a service agreement or grant output-use
rights. See [AlphaFold Server output terms](https://alphafoldserver.com/output-terms)
and the [ColabFold repository](https://github.com/sokrypton/ColabFold).

## Supported scope and evidence gates

The initial producer layouts are AlphaFold **Server** model/full-data pairs and
ColabFold PDB/scores pairs with a matching query A3M. Local AlphaFold3 layouts,
ligands/nucleic acids/modified protein tokens, unsupported ambiguity and incomplete
ColabFold query evidence are explicit unsupported cases. Read the
[bundle contract](prediction-bundle-import-contract.md) for exact limits and errors.
A rejected archive does not fall back to accession lookup or sequence distances.

Synthetic fixtures exercise the parser and app contract without redistributing
third-party predictions. They do not establish compatibility with every producer
version or reproduce a user's real prediction/EVOLVEpro run. Native GUI execution
remains unverified because the previously established display/desktop limitations
were not changed by this work. Component/RPC/build checks are reported separately.

## DPAM compatibility assessment only

The existing importer can identify the selected protein chain, its complete
polymer order and its paired directional PAE. That is useful adapter input, but
**DPAM is not run and no domains are predicted by this feature**.

The inspected DPAM implementation assumes selected chain A with positions 1..L in
its [structure preprocessing](https://github.com/CongLabCode/DPAM/blob/main/docker/scripts/step2_get_AFDB_pdbs.py).
Its [PAE reader](https://github.com/CongLabCode/DPAM/blob/main/docker/scripts/step13_get_diso.py)
expects a one-element JSON list containing `predicted_aligned_error`, not a raw
AF3 token object or ColabFold scores object. A future adapter must preserve full
chain order and original identity/provenance, require an appropriate complete
PAE matrix and keep output-use notices. The application's reference-fragment CA
trace is not automatically a DPAM-ready full-polymer input. That export and actual
DPAM execution remain separate validation gates.

한국어 요약: 이미 만든 AF3 Server·ColabFold ZIP을 로컬에서 검사하고 모델과 단백질
chain을 직접 선택한다. 원본 잔기 번호와 참조 위치의 정확한 대응 및 같은 예측의
confidence를 보존해 strict 선정·CA trace·설계 재검증에 연결한다. 없는 좌표를
채우거나 신뢰도를 추정하지 않는다. PAE 요약은 선택 chain 범위이며 도메인 신뢰도나
기능을 판정하지 않는다. DPAM은 입력 호환성만 검토했고 실행·도메인 예측은 하지 않았다.
