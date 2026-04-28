# Installation

kuma is distributed as a single desktop installer per platform. Downloads are attached to each [release](https://github.com/gyuminlee-repo/kuma/releases).

## Windows
- Download `kuma_<version>_x64-setup.exe` or `.msi`
- Run the installer; accept the SmartScreen prompt (code-signing pending)
- Launch from Start menu

## macOS
- Download `kuma_<version>_aarch64.dmg`
- Open the DMG and drag kuma.app into Applications
- First launch: right-click → Open to bypass Gatekeeper

## Linux (Debian/Ubuntu)
- Download `kuma_<version>_amd64.deb`
- Install via `sudo apt install ./kuma_<version>_amd64.deb`

## Linux (AppImage)
- Download `kuma_<version>_amd64.AppImage`
- `chmod +x kuma_<version>_amd64.AppImage` then run

## First launch

The Python sidecars (kuro and mame) start lazily on first tab activation. Wait until the status bar shows **Ready**. On first start a firewall prompt may appear for network access — allow it for UniProt / BLAST / AlphaFold lookups.
