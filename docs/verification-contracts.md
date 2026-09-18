# Verification contracts and remaining evidence

This follow-up preserves the operating behavior described in the September 2026
seminar. The presentation is a historical description, not an executable test
oracle; current code and explicit contract tests settle implementation details.
No presentation files or unpublished experimental data are included here.

## What is protected by executable contracts

- `tests/mame/test_verdict_behavior_contract.py` exercises first-match precedence,
  exact read-depth and indel boundaries, missing/wrong designed substitutions,
  legitimate multi-site designs, the distinction between read-level error and
  consensus frameshift, and preservation of legacy skipped-gate advisories.
  The coordinate-origin guard runs before the verdict gates. `VerdictClass` is a
  set of serialized/display labels, NOT the order in which gates execute.
- The indel-event gate uses **>= 0.50**, including equality. It awards AMBIGUOUS
  only once every designed mutation is confirmed. With an unconfirmed design,
  its note survives and later gates decide. This was already the implementation;
  the older diagram using `> 0.50` is not a reason to regress it.
- Only the covered strict-deletion-majority subset is excluded from the N gate.
  The reported N fraction remains unchanged. PASS can carry a legacy
  unevaluable-metric advisory; it is not a certification of unknown evidence.
- `barcode_window_bounds` isolates coordinate arithmetic from alignment,
  multiprocessing and file I/O. Tests compare its production caller against an
  independent whole-read reverse-complement construction on both strands,
  including asymmetric barcode lengths and clipped read ends. The inner edges
  stop at the alignment anchors. Read-level and top-level edit-distance defaults
  remain distinct; neither is changed here.

These are synthetic behavior contracts, not a measured sensitivity/specificity
benchmark. Existing samtools tests establish equivalence under matched calling
rules, not independent biological truth. MAPQ, mixture, indel, depth, Tm, codon
usage, and primer ranking policies are unchanged.

## CLI host selection and partial results

`kuro design --organism mextorquens ...` (alias `--host-organism`) forwards the
selected registered codon table to the same design engine used by the app.
Canonical keys come from `CodonTableRegistry`; its supported organism aliases
are accepted. An unknown host fails before output creation. The omitted option
remains `ecoli`. This does not implement custom-table import (a separate change).

`design_summary.json` records the host, requested parameters, successful mutation
labels, failed labels and reasons, counts, and the paths actually exported.
`None` in `requested_parameters` means a profile/default was requested, NOT that
the report resolved a numeric value. This is an execution summary, not a complete
input-content/version-fingerprinted reproducibility manifest or a replay format.

Partial success keeps its usable TSV/workbook, displays failure reasons and
returns the historical success exit code by default. `--fail-on-partial` returns
2 **after** writing these artifacts. No designed primers returns 1 and still
writes a failure report. An exception during design/export records `status=error`
and is propagated; the report must not claim completion. Old unrelated files in
an existing output directory are not deleted and are not listed as new artifacts.

## External-data coverage: executed is different from collected or skipped

The workbook scenarios and `TestReferenceGroundTruth` require external files.
The latter's name is historical: its reference comes from a read and it checks
self-consistency, not independent biological ground truth. Those data are not
committed here and CI does not acquire or publish them.

Every Python CI matrix leg writes JUnit and an external-coverage JSON artifact.
The inventory is derived from the test definitions without importing them; the
report reads **actual test outcomes**, not whether an environment variable exists.
Missing inventory entries or failures fail reporting. Documented skips are
allowed in normal CI but visibly state that external validation is incomplete.
Synthetic tests in the same files do not fill the external-data coverage count.

An authorized environment holding the original data can require real execution:

```bash
# Configure KUMA_TEST_DATA_DIR, WORKSPACE_ROOT and minimap2 for the existing tests.
python -m pytest tests/ -v -rs --junitxml=validation-python.xml
python scripts/report_validation_coverage.py \
  --junit validation-python.xml --output validation-coverage.json --require-executed
```

The second command fails on skipped, missing or failed external tests. The first
command's exit status must also be honored; the report is scoped and does not
replace the whole-suite gate. A shareable, independently annotated real-data
fixture and wet-lab threshold calibration remain work requiring approved data.

## Merge policy: repository settings are not source code

Required CI is not enforced merely by committing a workflow. An administrator
must enable a main-branch rule/ruleset requiring PRs, successful current checks,
and no force-push/deletion. The connected review tool does not have repository
Administration permission; this document does **not** assert that protection was
enabled. Do not weaken existing rules or substitute a successful old-head run.

Use the six `python-tests (OS, Python)` jobs, `python-typecheck`,
`frontend-typecheck`, `benchmark-tests`, and `rust-check` as required check names
from CI. Include new relevant workflows when adopted. Before merging, verify
all checks on the exact current PR head and pass that SHA to the merge request.
No extra human approval is prescribed for a solo-maintainer repository.
