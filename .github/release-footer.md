---

### Windows: "Unknown publisher" / SmartScreen warning

These installers are **not code-signed** (no certificate yet), so Windows SmartScreen may
show "Publisher: Unknown" and block the first run. This is caused by the **lack of code
signing, not by malicious code** — every artifact is built transparently in GitHub Actions
from the tagged commit.

To install: on the SmartScreen dialog click **More info → Run anyway**.

### Verify your download (recommended)

Compare the SHA-256 of your file against `SHA256SUMS.txt` attached to this release:

- **Windows (PowerShell):** `Get-FileHash .\kuma_<version>_x64-setup.exe -Algorithm SHA256`
- **macOS / Linux:** `shasum -a 256 <file>`  (or `sha256sum <file>`)

The printed hash must match the line for that filename in `SHA256SUMS.txt`.

### macOS note

macOS bundles are ad-hoc signed only (no Apple Developer ID / notarization), so Gatekeeper
may warn as well. Right-click the app → **Open**, or allow it in
**System Settings → Privacy & Security**.
