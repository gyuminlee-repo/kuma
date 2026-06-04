# SIDECAR SCOPE

Python JSON-RPC adapters and PyInstaller packaging for KURO, MAME, and EVOLVEpro.
Domain logic belongs in `kuma_core/`, not in this adapter layer.

## STRUCTURE

| Area | Role |
| --- | --- |
| `sidecar_main_kuro.py` | KURO process entry |
| `sidecar_main_mame.py` | MAME process entry |
| `sidecar_main_evolvepro.py` | EVOLVEpro process entry |
| `sidecar_kuro/` | KURO dispatcher, Pydantic models, handlers |
| `sidecar_mame/` | MAME dispatcher, models, handlers |
| `sidecar_evolvepro/` | Conda-backed EVOLVEpro dispatcher and handlers |
| `build_sidecar.py` | PyInstaller orchestration for all three binaries |
| `vendor/minimap2/` | Platform minimap2 binaries bundled into MAME |

## WHERE TO LOOK

| Task | Location |
| --- | --- |
| KURO RPC registry | `sidecar_kuro/dispatcher.py` `_METHODS` |
| KURO request and response schema | `sidecar_kuro/models.py` |
| MAME RPC registry | `sidecar_mame/dispatcher.py` |
| EVOLVEpro RPC registry | `sidecar_evolvepro/dispatcher.py` |
| Shared path and RPC helpers | `sidecar_kuro/core.py`, `sidecar_mame/core.py`, `kuma_core/shared/sidecar.py` |
| Packaging exclusions and loose data | `build_sidecar.py` |

## CONVENTIONS

- Keep dispatchers thin: validate, call `kuma_core`, serialize.
- KURO Pydantic changes may require `pnpm gen:models`, `src/types/models.ts`, and `.cross-layer-sync.json` updates.
- EVOLVEpro adapter code runs in the user conda environment. Keep heavy ML imports out of the packaged sidecar path.
- MAME packaging excludes heavy ML modules to stay below PyInstaller archive limits.
- Build outputs under `build/`, `dist/`, and `__pycache__/` are generated artifacts.

## ANTI-PATTERNS

- Do not add business logic to dispatch loops.
- Do not hand-edit generated TS model outputs after changing Pydantic models.
- Do not build MAME without checking the platform minimap2 vendor binary.

## VERIFY

```bash
python -m pytest tests/sidecar_kuro tests/sidecar_mame -v
pnpm gen:models:check
pnpm sync:check
pnpm run sidecar:build
```
