# Contributing

## Report an issue

Use the [issue tracker](https://github.com/gyuminlee-repo/kuma/issues). Include:
- OS + kuma version (Help → About or the installer filename)
- Steps to reproduce
- `~/.kuma/kuro/crash.log` contents if a sidecar crash is involved (or `~/.kuro/crash.log` from earlier installs)
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

## Developer Certificate of Origin

Every commit needs a `Signed-off-by` trailer. The trailer certifies the
Developer Certificate of Origin 1.1, kept verbatim in [`DCO`](../../DCO) at the
repository root: the contribution is yours to submit under the license this
project carries, or it comes from work that may be submitted that way, and the
record of the contribution stays public.

Sign a commit while making it:

```bash
git commit -s -m "summary in English"
```

The trailer has to name the commit author, so `git config user.name` and
`git config user.email` must hold the identity that authors the commit.

A branch that already has commits without the trailer takes it from a rebase:

```bash
git rebase --signoff main   # or the sha the branch started from
git push --force-with-lease
```

A pull request that is already open needs the same treatment. Rebase it with
`--signoff` and push the branch again, or the DCO workflow keeps blocking it.

The DCO workflow inspects only the commits a pull request adds and names every
commit whose trailer is missing or disagrees with the commit author. A merge
commit is exempt only when it adds no content of its own, because the parents
are covered on their own pull requests. A merge that resolved a conflict holds
lines that exist in no parent, so it needs a sign-off like any other commit and
the workflow says how many merges it skipped.

## Third-party license collection

The release build generates `NOTICE.md` from the unchanged project LICENSE,
Rust legal texts, installed Node production dependencies, the installed Python
runtime closure and separately identified packaging dependencies, and the
committed `NOTICE-bundled.md` for binaries. Generated notices are not committed.

| Layer | Tool | Output |
|---|---|---|
| Rust | `cargo-about` with `src-tauri/about.hbs` | `NOTICE-rust.md` |
| Node | pnpm production inventory + `scripts/collect-node-licenses.mjs` | `NOTICE-node.md` and `.json` |
| Python | `scripts/collect-python-licenses.py --include-build` | `NOTICE-python.md` and `.json` |

The Node collector reads original legal texts, not just SPDX identifiers.
The Python collector follows pyproject.toml requirements and transitive installed
metadata, including platform markers and requested extras. No hand-maintained
package list can silently omit certifi or a new transitive dependency.

After installing Python build dependencies and Node dependencies:

```bash
# Rust
cd src-tauri && cargo about generate -m Cargo.toml about.hbs > ../NOTICE-rust.md && cd ..
# Node
pnpm licenses list --json --prod > pnpm-licenses.json
node scripts/collect-node-licenses.mjs pnpm-licenses.json NOTICE-node.md
# Python
python scripts/collect-python-licenses.py --include-build
# Merge and copy into src-tauri/resources/NOTICE.md
node scripts/build-notice.mjs
# Regression tests
python -m pytest tests/scripts/test_license_notices.py -q
```

Missing/empty evidence fails collection or merging. The License evidence CI
workflow exercises the installed Node/Python collectors on all three platforms.
Collection does not certify compatibility or commercial rights; follow the
[release licensing checklist](license-compliance.md) for source obligations,
native runtimes, assets, data, provider terms and rights-holder authorization.

## License

GNU GPL version 2 — see [LICENSE](../../LICENSE). This corrects the former MIT
label; it does not change the grant in the root license or third-party terms.
