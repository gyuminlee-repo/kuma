# Configuration

Per-user settings live in `~/.kuro/`.

## `~/.kuro/config.json`

```json
{
  "contact_email": "you@example.com"
}
```

### `contact_email`

Used for EBI BLAST and UniProt API requests. **Required for UniProt BLAST search** — without it, EBI rejects submissions and searches fall back to gene-name text matching (producing low-similarity candidates).

Environment variable `KURO_CONTACT_EMAIL` takes precedence.

If neither is set, the default placeholder `kuro-app@example.com` is used as of v1.33.6 to keep BLAST working; configure your own to comply with EBI ToS.

## `~/.kuro/custom_polymerases.json`

Auto-managed by [Custom Polymerase Editor](custom-polymerase-editor.md). Manual edits are preserved but must match the bundled-profile schema.

## `~/.kuro/crash.log`

Last 50 sidecar-side exceptions with timestamp, method, and truncated traceback. Useful when reporting `Sidecar process exited` errors.

*Stub — config sample coming.*
