# Contributing

## Report an issue

Use the [issue tracker](https://github.com/gyuminlee-repo/kuma/issues). Include:
- OS + kuma version (Help → About or the installer filename)
- Steps to reproduce
- `~/.kuma/crash.log` contents if a sidecar crash is involved (or `~/.kuro/crash.log` from earlier installs)
- Sample sequence / CSV if possible (minimally reproducing set)

## Development environment

Linux builds need the Tauri/WebKitGTK development packages before running
`cargo check`, `pnpm tauri dev`, or `pnpm run build:all`:

```bash
sudo apt-get update
sudo apt-get install -y \
  libwebkit2gtk-4.1-dev \
  libjavascriptcoregtk-4.1-dev \
  libsoup-3.0-dev \
  libappindicator3-dev \
  librsvg2-dev \
  patchelf \
  libgtk-3-dev
```

For Windows target builds, run Node dependency installation and Tauri packaging
from a native Windows terminal, not from WSL.

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

## Third-party license collection

kuma bundles a `NOTICE.md` file in each distribution package that lists all
third-party Rust, Node, and Python dependencies with their license texts.

This file is generated automatically during the tag-triggered build
(`.github/workflows/build.yml`) and is never committed to the repository.
The three tools involved are:

| Layer | Tool | Output |
|---|---|---|
| Rust | `cargo-about` with `src-tauri/about.hbs` template | `NOTICE-rust.md` |
| Node | `pnpm licenses list --json --prod` + `scripts/collect-node-licenses.mjs` | `NOTICE-node.md` |
| Python | `pip-licenses --format=markdown` | `NOTICE-python.md` |

`scripts/build-notice.mjs` merges the three files into `NOTICE.md` and copies
it to `src-tauri/resources/NOTICE.md` so Tauri bundles it as a resource.

To regenerate locally (after a full Python + Node install):

```bash
# Rust
cd src-tauri && cargo about generate -m Cargo.toml about.hbs > ../NOTICE-rust.md && cd ..

# Node
pnpm licenses list --json --prod > pnpm-licenses.json
node scripts/collect-node-licenses.mjs pnpm-licenses.json NOTICE-node.md

# Python (within the kuma venv)
pip install pip-licenses
pip-licenses --format=markdown --output-file NOTICE-python.md \
  --packages primer3-py biopython openpyxl pydantic pandas python-calamine pyinstaller

# Merge
node scripts/build-notice.mjs
```

If any of the three partial-notice files is missing, `build-notice.mjs` exits 1
(silent skip is disabled).

## License

MIT — see [LICENSE](https://github.com/gyuminlee-repo/kuma/blob/main/LICENSE).
