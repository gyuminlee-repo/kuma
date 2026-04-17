# Installation

KURO is distributed as a single desktop installer per platform. Downloads are attached to each [release](https://github.com/gyuminlee-repo/KURO/releases).

## Windows
- Download `KURO_<version>_x64-setup.exe` or `.msi`
- Run the installer; accept the SmartScreen prompt (code-signing pending)
- Launch from Start menu

## macOS
- Download `KURO_<version>_aarch64.dmg`
- Open the DMG and drag KURO.app into Applications
- First launch: right-click → Open to bypass Gatekeeper

## Linux (Debian/Ubuntu)
- Download `kuro_<version>_amd64.deb`
- Install via `sudo apt install ./kuro_<version>_amd64.deb`

## Linux (AppImage)
- Download `kuro_<version>_amd64.AppImage`
- `chmod +x kuro_<version>_amd64.AppImage` then run

## First launch

The Python sidecar starts automatically. Wait until the status bar shows **Ready**. On first start a firewall prompt may appear for network access — allow it for UniProt / BLAST / AlphaFold lookups.

*Stub page — screenshots coming.*
