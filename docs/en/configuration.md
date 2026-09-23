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

## `~/.kuma/kuro/codon_tables`

The folder holding user codon tables, one organism per `.json` file. Every table found here joins the five bundled ones in the **Organism** dropdown beside the target gene. Settings → Codon tables shows the path, how many tables came from each source, an **Open folder** button, a **Refresh** button that re-reads the folder without restarting kuma, and every file that was refused with the reason it was refused.

The file name decides the key, so `mextorquens_am1.json` installs the organism `mextorquens_am1`. `TEMPLATE.json.txt` and `README.txt` are placed here for reference and are not read as tables.

Three ways to put a table here:

- Copy `TEMPLATE.json.txt` to `<key>.json`, replace the numbers, and press **Refresh**
- **Add organism...**, the last entry of the Organism dropdown, then the *Import a table file* tab: a kuma table (JSON), a three-column CSV, EMBOSS `cusp` output, or a Kazusa codon usage page pasted as text
- **Add organism...**, then the *Compute from a genome* tab: kuma counts the codons of a GenBank file (`.gb`, `.gbk`, `.gbff`) or a CDS FASTA and builds the table from that tally

A table has to carry all 20 amino acids plus the stop, all 64 codons exactly once, and frequencies that add up to about 1 per amino acid. NCBI genetic code 1 or 11 only. The five built-in keys (`ecoli`, `bsubtilis`, `hsapiens`, `mextorquens`, `scerevisiae`) cannot be replaced, so a modified copy goes in under a different key such as `ecoli_lab`. Nothing is installed partially: a file is accepted whole or refused whole.

## `~/.kuma/kuro/custom_polymerases.json`

Auto-managed by [Custom Polymerase Editor](custom-polymerase-editor.md). Manual edits are preserved but must match the bundled-profile schema.

## `~/.kuma/kuro/crash.log`

Last 50 sidecar-side exceptions with timestamp, method, and truncated traceback. Useful when reporting `Sidecar process exited` errors.
