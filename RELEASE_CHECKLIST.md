# KURO Release Checklist

Issues that MUST be resolved before any public/production release.

## CRITICAL — Security

### Verify updater signing configuration (`src-tauri/tauri.conf.json`)

**Status**: A public key and updater endpoint are configured. Signing-key ownership and a successful signed update must still be verified for a release.

The Tauri updater plugin is registered and the endpoint is configured
(`https://github.com/gyuminlee-repo/kuma/releases/latest/download/latest.json`).
The `plugins.updater.pubkey` field contains a minisign public key. Its presence
alone does not prove that release artifacts were signed with the matching key
or that an installed client can update successfully.

**Before release:**

1. Confirm the configured public key matches the private key held in CI. Do not
   replace the key without a rotation plan for already-installed clients.
2. Sign release artifacts with that private key. The build workflow passes
   `TAURI_SIGNING_PRIVATE_KEY` and `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` to Tauri.
3. Verify `latest.json`, its artifact URLs and signatures, then exercise an update
   from an installed previous release before announcing availability.
4. Never commit or print the private key.

Reference: <https://v2.tauri.app/plugin/updater/#signing-updates>

---

## CRITICAL, Release Integrity

### An announced release is not a released one until the tag is pushed

`.github/workflows/build.yml` runs on `push: tags: ["v*"]` and manual dispatch.
Landing a three-component label (`vA.BB.CC:`) on main and writing the CHANGELOG
section announce a release. Neither builds an artifact. On 2026-09-14 the newest
version tag was v0.16.54 while main had announced v0.16.55 through v0.16.58,
each with its CHANGELOG section and none of them built.

Before cutting a release, list what is outstanding:

```bash
pnpm run release:untagged     # node scripts/list-untagged-releases.mjs
```

Then, on main at the commit the release describes:

```bash
git tag vA.BB.CC && git push origin vA.BB.CC
```

This is not a CI gate on purpose. At merge time a missing tag is the normal
state, so failing on it would fire on every release merge and teach the reader
to skip the whole category.

### The label that lands is the one the squash writes, not the one on the branch

`squash_merge_commit_title` on this repository is `COMMIT_OR_PR_TITLE`: GitHub
writes the pull request title when the branch holds more than one commit, and
the single commit's own subject when it holds exactly one. So the subject
`scripts/check-version-label.mjs` reads on a branch is not the subject that
reaches main. Pull request 391 passed that way and turned main red: branch HEAD
said v0.16.58.05, the title said v0.16.59, three commits, manifests 0.16.58.

`scripts/check-landing-label.mjs` computes the landing subject from the pull
request payload and runs the label-against-manifest comparison on it, plus the
CHANGELOG requirement when the label claims a release. It runs as the
`Release label` workflow on every pull request, including on a title edit.

To see what it would say for a given pull request before opening one, set the
title first and let CI answer; locally the script needs an event payload:

```bash
node scripts/check-landing-label.mjs --event <payload.json>
```

---

## CRITICAL, Build Integrity

### Sidecar binary hash must match `src-tauri/sidecar-hashes.json`

Release builds enforce SHA-256 hash verification on the bundled sidecar binaries
(`src-tauri/src/sidecar.rs` `verify_binary_hash()`). If the manifest hash does
not match the on-disk binary, the sidecar refuses to spawn and the entire app
appears non-functional. Every RPC (`load_fasta`, `parse_mutations_text`, etc.)
fails silently from the user perspective.

**Historical cause**: rebuilding a binary without refreshing the manifest can
ship a release that cannot start its own sidecar. The current
`pnpm run sidecar:build` chains `scripts/sidecar-hash.mjs` automatically.
Direct `python-core/build_sidecar.py` invocation and `sidecar:build:onedir`
do not include that hash refresh.

**Always use one of these end-to-end commands instead of the raw sidecar build:**

```bash
# Full release pipeline (recommended)
pnpm run build:all

# OR, if only rebuilding the sidecar without a full Tauri build,
# the chained `sidecar:build` script now invokes `sidecar:hash` automatically
pnpm run sidecar:build
```

**Pre-release verification**:
```bash
pnpm run sync:check          # all cross-layer checks; not a binary-hash comparison
pnpm run i18n:check
# Compare each built sidecar with its full-filename entry in sidecar-hashes.json:
sha256sum 'src-tauri/binaries/<sidecar-filename>'  # Linux; replace the placeholder
# macOS: shasum -a 256 <path>; PowerShell: Get-FileHash <path> -Algorithm SHA256
```

Compare the digest with `src-tauri/sidecar-hashes.json`; `sync:check` does not
perform this comparison. For an intentionally rebuilt binary, refresh with
`pnpm run sidecar:hash` and review the manifest diff. On macOS, signing changes
the binary bytes: use `pnpm run sidecar:hash:postbuild` after bundling, and verify
the final bundled binaries against the bundled manifest.

---

## MEDIUM, Compliance

### Configure a contactable BLAST email (`python-core/sidecar_kuro/core.py`)

The EBI NCBI BLAST API email defaults to the placeholder `kuro-app@example.com`.
Set `KURO_CONTACT_EMAIL` or `contact_email` in `~/.kuma/kuro/config.json` to a
real, contactable address before submitting jobs. The environment variable takes
precedence over the config value; the placeholder is used only when both are absent.

---

## Cross-platform sidecar hash 관리

`src-tauri/sidecar-hashes.json`는 빌드 머신마다 머지(merge) 방식으로 갱신됨. 단일 머신에서 `pnpm run sidecar:hash` 실행 시 그 머신 플랫폼 키만 갱신, 타 플랫폼 키는 보존.

### 새 릴리스 절차

각 타겟 플랫폼에서:

1. `pnpm install`
2. `pnpm run sidecar:build` (PyInstaller로 platform-specific binary 생성)
3. `pnpm run sidecar:hash` (merge mode, 그 플랫폼 키만 추가/갱신)
4. `git diff src-tauri/sidecar-hashes.json` 확인
5. `git add src-tauri/sidecar-hashes.json && git commit -m "vX.X.X: refresh <platform> sidecar hashes"`

### 회귀 방지

- 빌드 머신은 자신의 플랫폼 키만 작성. base-name fallback 키(`kuro-sidecar`, `mame-sidecar`)는 더 이상 사용 안 함.
- Tauri 빌드 후 `scripts/sidecar-hash-postbuild.mjs`도 동일 merge 정책 따름.
- runtime `verify_binary_hash()` (src-tauri/src/sidecar.rs)는 triple_key/ext_key 미적중 시 fail-fast.

### 과거 회귀 참고

v0.9.7 (348098b)에서 macOS 머신이 manifest를 overwrite하여 Windows/Linux 키 소실, fallback base-name 키가 Mac hash 보유하여 Windows installer가 무결성 검증 실패. v0.9.8.x에서 merge mode + fail-fast로 해결.
