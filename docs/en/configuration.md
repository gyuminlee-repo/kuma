# Configuration

Per-user settings live in `~/.kuma/kuro/`.

## `~/.kuma/kuro/config.json`

```json
{
  "contact_email": "you@example.com",
  "ca_bundle": ""
}
```

### `contact_email`

Used for EBI BLAST and UniProt API requests. **Required for UniProt BLAST search** — without it, EBI rejects submissions and searches fall back to gene-name text matching (producing low-similarity candidates).

Environment variable `KURO_CONTACT_EMAIL` takes precedence.

If neither is set, the default placeholder `kuro-app@example.com` is used as of v1.33.6 to keep BLAST working; configure your own to comply with EBI ToS.

### `ca_bundle`

Path to an extra PEM file of trusted certificate authorities. A leading `~` is expanded. Default is empty, meaning no extra authority is loaded.

kuma verifies TLS against the operating system trust store (macOS Keychain, the Windows certificate store, the OpenSSL paths on Linux), so a site that runs a TLS inspection proxy normally needs nothing here: install the proxy CA in that store and every outbound call (UniProt search, InterPro domains, PDB and AlphaFold downloads) works, along with every other tool on the machine.

This key is the escape hatch for when that is not possible, or when the operating system store cannot be reached at all and kuma falls back to the bundled certifi roots, which can never contain a private proxy CA. Export the proxy CA from the browser as a PEM file and point this key at it. Without either, outbound calls fail with `CERTIFICATE_VERIFY_FAILED`.

Environment variable `KURO_CA_BUNDLE` takes precedence. `SSL_CERT_FILE` is honoured by OpenSSL itself before either of these, but on Linux it replaces the distribution certificate bundle rather than adding to it, so this key is the safer knob.

The certificate store is built once per process, so restart kuma after changing this.

## `~/.kuma/kuro/custom_polymerases.json`

Auto-managed by [Custom Polymerase Editor](custom-polymerase-editor.md). Manual edits are preserved but must match the bundled-profile schema.

## `~/.kuma/kuro/crash.log`

Last 50 sidecar-side exceptions with timestamp, method, and truncated traceback. Useful when reporting `Sidecar process exited` errors.
