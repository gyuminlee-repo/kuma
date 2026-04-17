# Contributing

## Report an issue

Use the [issue tracker](https://github.com/gyuminlee-repo/KURO/issues). Include:
- OS + KURO version (Help → About or the installer filename)
- Steps to reproduce
- `~/.kuro/crash.log` contents if a sidecar crash is involved
- Sample sequence / CSV if possible (minimally reproducing set)

## Development environment

```bash
git clone https://github.com/gyuminlee-repo/KURO.git
cd KURO
pip install -e '.[build]'
pnpm install
pnpm run sidecar:build
pnpm tauri dev
```

Testing:
```bash
python -m pytest tests/ -v
npx tsc --noEmit
cd src-tauri && cargo check
```

## Code style

- TypeScript: no `as any`, no `@ts-ignore`
- Python: Pydantic for RPC boundary validation; keep `kuro/` library pure (no Tauri imports)
- Commit: `vX.Y.Z: summary in English`

## Pull request checklist

1. Tests pass (`pytest`, `tsc`, `cargo check`)
2. `UPDATE-NOTES.md` / `UPDATE-NOTES.ko.md` updated
3. Screenshots regenerated if UI changed (`pnpm run capture-guide`)
4. Wiki updated for new features (this repo's `.wiki.git`)

## License

MIT — see [LICENSE](https://github.com/gyuminlee-repo/KURO/blob/main/LICENSE).
