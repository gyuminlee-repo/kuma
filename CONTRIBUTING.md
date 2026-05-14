# Contributing to KUMA

## Versioning Convention

KUMA uses a **4-segment commit/tag version** (`vA.BB.CC.DD`) but **3-segment build artifact version** (`A.BB.CC`).

### Build artifacts (3-segment SemVer)

The following files are kept in lock-step and must use **3-segment SemVer** (`A.BB.CC`) — Tauri 1.x/2.x bundlers (MSI, NSIS, AppImage) and Cargo do not accept 4-segment versions in their manifests:

- `package.json` → `version`
- `src-tauri/tauri.conf.json` → `version`
- `src-tauri/Cargo.toml` → `[package].version`

The `version-sync` check in `.cross-layer-sync.json` enforces equality across these three files (`pnpm sync:check`).

### Git commits and tags (4-segment)

Commit messages and git tags use the 4-segment convention:

```
vA.BB.CC.DD: <english summary>
```

- `DD`: bug fix / typo (default; bump per commit)
- `CC`: feature / refactor (resets `DD` to `00`)
- `BB`: new feature / architecture (resets `CC.DD` to `00.00`)
- `A`: full redesign (resets `BB.CC.DD` to `00.00.00`)

The 4th segment (`DD`) is **commit-level metadata only**. It is intentionally absent from build manifests; bundle filenames track the 3-segment build version.

### Workflow when bumping versions

1. Decide whether the change is a `DD` (bug/typo), `CC` (feature/refactor), `BB` (architecture), or `A` (redesign) bump per the rules above.
2. Update commit message tag (`vA.BB.CC.DD`).
3. If `A`, `BB`, or `CC` changes, also update the three build manifest files to the new 3-segment value and re-run `pnpm sync:check`.
4. If only `DD` changes, leave the manifest files untouched.
