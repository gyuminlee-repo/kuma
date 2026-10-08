# TEST SCOPE

Python tests, cross-layer integration tests, fixture checks, and selected TypeScript
integration specs. Frontend unit tests also live beside source files under `src/`.

## STRUCTURE

| Area | Role |
| --- | --- |
| `test_*.py` | KURO, EVOLVEpro, sidecar, and export coverage |
| `mame/` | MAME domain, activity, integration, and browser specs |
| `sidecar_kuro/` | KURO dispatcher and export tests |
| `sidecar_mame/` | MAME dispatcher tests |
| `shared/` | Shared helper tests |
| `strategy/` | Strategy model and signal tests |
| `integration/` | End-to-end Python workflow tests |
| `fixtures/` | Fixture generator checks |
| `workspace/` | TypeScript workspace API checks |

## CONVENTIONS

- Match a changed module with its focused test subtree first, then broaden when contracts span layers.
- Use temporary directories for filesystem behavior; do not depend on user workspace state.
- MAME tests may skip minimap2-dependent paths when no vendor binary is available.
- Keep fixture schema tests aligned with `.cross-layer-sync.json` groups.
- Rust host tests live in `src-tauri/tests/`; frontend Vitest files generally stay beside source.

## WHERE TO LOOK

| Change | Focused tests |
| --- | --- |
| KURO design | `test_sdm_engine.py`, `test_overlap.py`, `test_plate_mapper.py` |
| EVOLVEpro | `test_evolvepro*.py`, `test_load_evolvepro_params.py` |
| MAME core | `mame/` |
| RPC contracts | `test_sidecar_rpc.py`, `sidecar_kuro/`, `sidecar_mame/` |
| Shared helpers | `shared/` |

## VERIFY

```bash
python -m pytest tests/path/to/test_file.py -v
python -m pytest tests/ -v
pnpm exec vitest run src/path/to/changed.test.ts
```
