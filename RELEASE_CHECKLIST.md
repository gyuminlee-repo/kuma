# KURO Release Checklist

Issues that MUST be resolved before any public/production release.

## CRITICAL — Security

### Updater pubkey is empty (`src-tauri/tauri.conf.json`)

**Status**: Infrastructure ready — key generation pending.

The Tauri updater plugin is registered and the endpoint is configured
(`https://github.com/gyuminlee-repo/KURO/releases/latest/download/latest.json`).
The `plugins.updater.pubkey` field is set to `""`, which means **update signature
verification is currently disabled**. Manual "Check for updates" in the About dialog
is functional; automatic on-startup checking is intentionally omitted until a valid
key is set.

An attacker who compromises the GitHub release endpoint (or performs a MITM) can
push arbitrary binaries to every user until the key is set.

**Before release:**

1. Generate a Tauri updater keypair:
   ```
   cargo tauri signer generate -w ~/.tauri/kuro.key
   ```
2. Set `pubkey` in `src-tauri/tauri.conf.json` → `plugins.updater.pubkey` to the
   **public** key string output by the command above.
3. Sign every release artifact with the corresponding private key (the CI release
   workflow should pass `--signing-key` / `TAURI_SIGNING_PRIVATE_KEY` env var).
4. Never commit the private key to the repository.

Reference: <https://v2.tauri.app/plugin/updater/#signing-updates>

---

## CRITICAL, Build Integrity

### Sidecar binary hash must match `src-tauri/sidecar-hashes.json`

Release builds enforce SHA-256 hash verification on the bundled sidecar binaries
(`src-tauri/src/sidecar.rs` `verify_binary_hash()`). If the manifest hash does
not match the on-disk binary, the sidecar refuses to spawn and the entire app
appears non-functional. Every RPC (`load_fasta`, `parse_mutations_text`, etc.)
fails silently from the user perspective.

**Cause of the regression**: `pnpm run sidecar:build` rebuilds the binary but
does NOT automatically refresh the manifest. If the engineer forgets the
follow-up `pnpm run sidecar:hash`, the next `tauri build` ships a release that
cannot start its own sidecar.

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
node scripts/sync-check.mjs   # includes tauri-resources + hash freshness
```

If `sync-check` reports drift between the binaries and the manifest, run
`pnpm run sidecar:hash` and commit the updated `src-tauri/sidecar-hashes.json`.

---

## MEDIUM, Compliance

### BLAST email hardcoded (`python-core/sidecar_main.py`)

The EBI NCBI BLAST API email is hardcoded as `kuro-app@example.com`. EBI Terms of
Use require a real, contactable email address. This should be read from user
configuration (e.g., `~/.kuro/config.toml` or an in-app settings panel).
