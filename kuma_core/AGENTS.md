# PYTHON CORE SCOPE

Installable Python domain package for KURO design, MAME analysis, EVOLVEpro execution,
shared infrastructure, and strategy models. Keep it independent of Tauri UI concerns.

## STRUCTURE

| Area | Role |
| --- | --- |
| `kuro/` | SDM design, overlap, codons, plate mapping, benchmark, EVOLVEpro input |
| `mame/` | MinKNOW ingest, analysis, activity merge, translate, compare, select, export |
| `evolvepro/` | Conda runner, adapter, timing, and embedding cache |
| `shared/` | Sidecar helpers, paths, manifests, logging, system info |
| `strategy/` | Small strategy schemas and signal calculations |

## WHERE TO LOOK

| Task | Location |
| --- | --- |
| Primer design | `kuro/sdm_engine.py` |
| EVOLVEpro CSV parsing | `kuro/evolvepro.py` |
| Plate exports | `kuro/plate_mapper.py` |
| MAME pipeline | `mame/pipeline.py` |
| Raw MinKNOW ingest | `mame/ingest/` |
| MAME activity workflow | `mame/activity/` |
| EVOLVEpro subprocess boundary | `evolvepro/runner.py`, `evolvepro/adapter.py` |
| Shared RPC validation | `shared/sidecar.py` |

## CONVENTIONS

- Put reusable scientific behavior here; sidecar handlers only adapt RPC.
- Check `.cross-layer-sync.json` before changing model fields, fixture columns, rescue defaults, MAME enums, or activity schemas.
- Preserve the raw MinKNOW folder workflow: `fastq_pass/<barcode*|NB*>/*.fastq.gz` is the primary input.
- `strategy/signals.py` stays stdlib-only.
- `evolvepro/adapter.py` runs outside the packaged app in the user conda environment.
- Changes to `kuro/evolvepro.py` columns may require fixture regeneration.

## ANTI-PATTERNS

- Do not import Tauri or frontend concerns into this package.
- Do not make MAME users pre-sort barcode folders for the normal workflow.
- Do not add heavy ML dependencies to packaged KURO or MAME paths without reviewing `python-core/build_sidecar.py`.

## VERIFY

```bash
python -m pytest tests/test_sdm_engine.py tests/mame tests/shared tests/strategy -v
python -m pytest tests/test_evolvepro.py tests/test_evolvepro_others_mode.py -v
pnpm sync:check
```
