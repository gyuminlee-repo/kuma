# Copilot instructions for KURO

## Build, test, and static-check commands

```bash
# Frontend / app development
pnpm dev
pnpm tauri dev

# Builds
pnpm run build
pnpm run sidecar:build
pnpm run build:all

# Python test setup
pip install -e . pytest

# Python tests
python -m pytest tests/ -v
python -m pytest tests/test_sdm_engine.py -v
python -m pytest tests/test_sdm_engine.py::test_name -v

# TypeScript / Rust checks used in CI
npx tsc --noEmit
cd src-tauri && cargo check
```

`cargo check` in CI is run only after the frontend is built and a sidecar stub exists under `src-tauri/binaries/`, because `tauri::generate_context` expects bundled assets to be present.

On Linux, the Rust/Tauri checks also need the same system packages installed in CI: `libwebkit2gtk-4.1-dev`, `libjavascriptcoregtk-4.1-dev`, `libsoup-3.0-dev`, `libappindicator3-dev`, `librsvg2-dev`, `patchelf`, and `libgtk-3-dev`.

## High-level architecture

KURO is a Tauri v2 desktop app with a thin Rust shell, a React 19 frontend, and a Python sidecar. The Rust layer in `src-tauri/` is only responsible for the desktop host, windowing, menu integration, and bundling. The frontend in `src/` owns the application state and UI. The scientific logic does not live in Rust.

The frontend talks to the Python sidecar through JSON-RPC over stdin/stdout. `src/lib/ipc.ts` spawns `binaries/kuro-sidecar` via the Tauri shell plugin, tracks pending request IDs, and handles `progress` / `ready` notifications. The sidecar entrypoint is `python-core/sidecar/dispatcher.py`, which routes JSON-RPC methods to handler modules in `python-core/sidecar/handlers/` and validates request payloads with Pydantic models from `python-core/sidecar/models.py`.

The actual primer-design and EVOLVEpro logic lives in the pure-Python `kuro/` package. Keep that layer independent of Tauri or frontend concerns. When request or response shapes change, update both `python-core/sidecar/models.py` and `src/types/models.ts` together.

The React state store is split into five Zustand slices under `src/store/slices/`: sequence, diversity, input, design, and export. Their dependencies are intentional: `sequenceSlice -> diversitySlice.searchUniprot`, `diversitySlice -> inputSlice.loadEvolveproCsv` and `sequenceSlice.seqInfo`, `inputSlice -> diversitySlice.pipelineMode/domains/disabledDomains`, `designSlice -> inputSlice.mutationText` and `diversitySlice.cancelDiversityReload`, and `exportSlice` reads from the others for workspace save/load.

## Key conventions

- Do not hardcode absolute paths. Use relative paths or environment-aware paths only.
- Do not hardcode values that already come from backend responses. UI labels, thresholds, and percentages should reflect returned data instead of fixed literals.
- Keep the Rust host thin. Cross-platform behavior and scientific logic should usually be implemented in the frontend or Python layers, not `src-tauri/`.
- `src/types/models.ts` and `python-core/sidecar/models.py` must stay in sync. This is especially important for workspace payloads, excluded ranges, rescue stats, and any JSON-RPC request/response fields.
- If you change `kuro/evolvepro.py` selection columns or validation-related fields, also check fixtures and any sample-data generation paths that depend on them.
- When adding bundled sample/resource files, add explicit file-to-file mappings in `src-tauri/tauri.conf.json`. Do not use glob patterns in Tauri resources.
- For flex layouts in the React UI, any `flex-1` select or text-heavy child should also have `min-w-0`; fixed-width panels should usually add `overflow-x-hidden`.
- Keep TypeScript strictness intact: avoid `as any`, avoid `@ts-ignore`, prefer null guards over non-null assertions, and avoid module-level `let` values that are reassigned asynchronously.
- Release versioning is synchronized across `package.json`, `src-tauri/tauri.conf.json`, and `src-tauri/Cargo.toml`.
- Windows-targeted builds should be run from a native Windows terminal rather than WSL when reinstalling Node dependencies.
