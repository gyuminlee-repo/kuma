# KUMA User Guide

KUMA is a desktop app for site-directed mutagenesis campaigns. **KURO** designs SDM primer pairs in batch from a Gibson Assembly template. **MAME** reads the Oxford Nanopore sequencing that comes back and tells which clones carry the intended mutation.

![Kuro output step: sequence map of 91 designed mutations, primer summary table, forward plate map and design report](https://raw.githubusercontent.com/gyuminlee-repo/kuma/main/docs/screenshots/04-design-complete.png)

<small>Kuro output step with the bundled demo project, captured from an earlier build.</small>

## Install

Download the installer for your system from [Releases](https://github.com/gyuminlee-repo/kuma/releases).

| System | File |
|---|---|
| Windows (x64) | `kuma_<version>_x64-setup.exe` |
| macOS (Apple Silicon) | `kuma_<version>_aarch64.dmg` |
| Linux (x64) | `kuma_<version>_amd64.AppImage` or `kuma_<version>_amd64.deb` |

On first launch KUMA asks for a projects folder (default `~/Documents/kuma`). macOS shows an unidentified-developer warning the first time; the [README](https://github.com/gyuminlee-repo/kuma#installation) lists the two ways past it.

## Where to start

- [KURO guide](kuro-index.md): from loading a sequence to the primer order sheet and liquid-handler files.
- [MAME guide](mame-index.md): from a MinKNOW run folder to verdicts and EVOLVEpro input.

These are the same pages the app shows in its help panel, so the guide and the app describe the same version.
