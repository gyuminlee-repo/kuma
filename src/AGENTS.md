# FRONTEND SCOPE

React 19 UI, Zustand state, IPC clients, and frontend type contracts.
Root instructions still apply; this file adds `src/`-specific guidance only.

## STRUCTURE

| Area | Role |
| --- | --- |
| `screens/` | App-level routes, onboarding, and shell flows |
| `components/` | KURO, MAME, EVOLVEpro, shell, and shared UI |
| `store/slices/` | KURO Zustand slices |
| `store/mame/` | MAME Zustand store and domain slices |
| `store/evolvepro/` | EVOLVEpro run state |
| `lib/ipc.ts` | Tauri invoke-based KURO RPC client |
| `lib/ipc-mame/` | MAME RPC client and progress subscription |
| `lib/ipc-evolvepro/` | EVOLVEpro IPC path; inspect deprecation notes before reuse |
| `types/` | Hand-written and generated frontend contracts |

## WHERE TO LOOK

| Task | Location |
| --- | --- |
| App boot and crash boundary | `main.tsx` |
| Main workflow shell | `screens/MainShell.tsx` |
| KURO store composition | `store/types.ts`, `store/slice-interfaces.ts` |
| MAME UI entry | `components/mame/layout/MameAppLayout.tsx` |
| EVOLVEpro UI entry | `components/evolvepro/EvolveProPanel.tsx` |
| Workspace persistence | `lib/workspace/`, `store/slices/exportSlice.ts` |

## CONVENTIONS

- Treat `.cross-layer-sync.json` as the dependency map before editing store, type, navigation, or export contracts.
- Do not hand-edit `types/models.generated.ts` or `types/models.evolvepro.generated.ts`; run `pnpm gen:models`.
- Keep hand-written `types/models.ts` validators and RPC maps aligned with `python-core/sidecar_kuro/`.
- Add navigation keys to both `locales/en.json` and `locales/ko.json`.
- For new UI, release, export, reset, cancel, settings, and error-state work, read `docs/standards/common-frontend-standards.md`.
- MAME file pickers use Browse plus filename preview; export destinations use save dialogs.

## ANTI-PATTERNS

- Do not add `as any` or `@ts-ignore`.
- Do not hardcode backend-returned thresholds, percentages, labels, or status values.
- Do not omit `min-w-0` on flexible selects or long text children.

## VERIFY

```bash
npx tsc --noEmit
pnpm exec vitest run path/to/changed.test.ts
pnpm sync:check
```
