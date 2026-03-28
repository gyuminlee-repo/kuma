# KURO Release Checklist

Issues that MUST be resolved before any public/production release.

## CRITICAL — Security

### Updater pubkey is empty (`src-tauri/tauri.conf.json`)

The `plugins.updater.pubkey` field is set to `""`, which means **update signature
verification is disabled**. An attacker who compromises the GitHub release endpoint
(or performs a MITM) can push arbitrary binaries to every user.

**Before release:**

1. Generate a Tauri updater keypair:
   ```
   cargo tauri signer generate -w ~/.tauri/kuro.key
   ```
2. Set `pubkey` in `tauri.conf.json` to the **public** key string.
3. Sign every release artifact with the corresponding private key.
4. Never commit the private key to the repository.

Reference: <https://v2.tauri.app/plugin/updater/#signing-updates>

---

## MEDIUM — Compliance

### BLAST email hardcoded (`python-core/sidecar_main.py`)

The EBI NCBI BLAST API email is hardcoded as `kuro-app@example.com`. EBI Terms of
Use require a real, contactable email address. This should be read from user
configuration (e.g., `~/.kuro/config.toml` or an in-app settings panel).
