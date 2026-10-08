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

The submitter address sent to EBI Job Dispatcher for BLAST and InterProScan jobs. There is no default. Without an address kuma skips the EBI BLAST and InterProScan submissions: UniProt search finds candidates from the remaining lookups (gene name, accession) without BLAST, and InterProScan domain annotation is skipped for a sequence that is not already cached.

The first time a job needs an address, kuma asks for it in a dialog and saves it in Settings. You can change it later under Settings > Network.

Lookup order: the environment variable `KURO_CONTACT_EMAIL`, then the address saved in Settings (`network.contact_email` in `~/.kuma/preferences.json`), then `contact_email` in this file. The first non-empty value is used. If that value does not look like an address it counts as absent, and the later sources are not consulted.

### `ca_bundle`

Path to an extra PEM file of trusted certificate authorities. A leading `~` is expanded. Default is empty, meaning no extra authority is loaded.

kuma verifies TLS against the operating system trust store (macOS Keychain, the Windows certificate store, the OpenSSL paths on Linux), so a site that runs a TLS inspection proxy normally needs nothing here: install the proxy CA in that store and every outbound call (UniProt search, InterPro domains, PDB and AlphaFold downloads) works, along with every other tool on the machine.

This key is the escape hatch for when that is not possible, or when the operating system store cannot be reached at all and kuma falls back to the bundled certifi roots, which can never contain a private proxy CA. Export the proxy CA from the browser as a PEM file and point this key at it. Without either, outbound calls fail with `CERTIFICATE_VERIFY_FAILED`.

Environment variable `KURO_CA_BUNDLE` takes precedence. `SSL_CERT_FILE` is honoured by OpenSSL itself before either of these, but on Linux it replaces the distribution certificate bundle rather than adding to it, so this key is the safer knob.

The certificate store is built once per process, so restart kuma after changing this.

## `~/.kuma/kuro/codon_tables`

The folder holding user codon tables, one organism per `.json` file. Every table found here joins the five bundled ones in the **Organism** dropdown beside the target gene. Settings → Codon tables shows the path, how many tables came from each source, an **Open folder** button, a **Refresh** button that re-reads the folder without restarting kuma, and every file that was refused with the reason it was refused.

The file name decides the key, so `mextorquens_am1.json` installs the organism `mextorquens_am1`. `TEMPLATE.json.txt`, `README.txt` and `mextorquens_am1.json.txt` are placed here for reference and are not read as tables. The last of the three is a finished *M. extorquens* AM1 table rather than a placeholder, so renaming it to `mextorquens_am1.json` installs the organism with nothing else to edit.

Three ways to put a table here:

- Copy `TEMPLATE.json.txt` to `<key>.json`, replace the numbers, and press **Refresh**
- **Add organism...**, the last entry of the Organism dropdown, then the *Import a table file* tab: a kuma table (JSON), a three-column CSV, EMBOSS `cusp` output, or a Kazusa codon usage page pasted as text
- **Add organism...**, then the *Compute from a genome* tab: kuma counts the codons of a GenBank file (`.gb`, `.gbk`, `.gbff`) or a CDS FASTA and builds the table from that tally

A table has to carry all 20 amino acids plus the stop, all 64 codons exactly once, and frequencies that add up to about 1 per amino acid. NCBI genetic code 1 or 11 only. The nine built-in keys (`ecoli`, `bsubtilis`, `hsapiens`, `scerevisiae`, `kphaffii`, `cgriseus`, `cglutamicum`, `aniger`, `pputida`) cannot be replaced, so a modified copy goes in under a different key such as `ecoli_lab`. Nothing is installed partially: a file is accepted whole or refused whole.

## `~/.kuma/kuro/custom_polymerases.json`

Auto-managed by [Custom Polymerase Editor](custom-polymerase-editor.md). Manual edits are preserved but must match the bundled-profile schema.

## `~/.kuma/kuro/crash.log`

Last 50 sidecar-side exceptions with timestamp, method, and truncated traceback. Useful when reporting `Sidecar process exited` errors.
