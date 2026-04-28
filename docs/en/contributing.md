# Contributing

## Report an issue

Use the [issue tracker](https://github.com/gyuminlee-repo/kuma/issues). Include:
- OS + kuma version (Help → About or the installer filename)
- Steps to reproduce
- `~/.kuma/crash.log` contents if a sidecar crash is involved (or `~/.kuro/crash.log` from earlier installs)
- Sample sequence / CSV if possible (minimally reproducing set)

## Development environment

```bash
git clone https://github.com/gyuminlee-repo/kuma.git
cd kuma
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

MIT — see [LICENSE](https://github.com/gyuminlee-repo/kuma/blob/main/LICENSE).
