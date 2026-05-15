# EVOLVEpro Integration

## Overview

KUMA provides an optional GUI wrapper for [EVOLVEpro](https://doi.org/10.1126/science.adr6006)
(Jiang et al. 2025, Science). EVOLVEpro is a machine-learning model that scores
protein-sequence variants for directed evolution. KUMA shells out to a
user-installed EVOLVEpro conda environment via subprocess and parses its
stdout for progress reporting.

**KUMA does not bundle, redistribute, or modify EVOLVEpro.** EVOLVEpro is
licensed under the MIT TLO Internal Research EULA (academic, non-commercial
use). Users install EVOLVEpro themselves and accept the EULA directly when
doing so.

## Prerequisites

- 16 GB RAM (8 GB for ESM-2 650M model + working set)
- 10 GB free disk space on the user cache volume (model weights + intermediate
  scoring artifacts)
- A working `conda` or `mamba` installation
- Network access on first run (for downloading ESM-2 weights, ~2.5 GB)

## Installation

1. Create a dedicated conda environment named `evolvepro`:

   ```bash
   conda create -n evolvepro python=3.11 -y
   conda activate evolvepro
   ```

2. Install EVOLVEpro following the upstream project instructions. The MIT
   TLO Internal Research EULA must be accepted directly when prompted by
   the upstream installer; KUMA never agrees to it on your behalf.

3. Verify the install from a shell:

   ```bash
   conda run -n evolvepro evolvepro --help
   ```

   When the command prints CLI help, KUMA will detect the environment.

## First Run

The first time the **Run** button is clicked in the EVOLVEpro panel, EVOLVEpro
downloads the ESM-2 650M model checkpoint (~2.5 GB) to:

```
~/.cache/torch/hub/checkpoints/esm2_t33_650M_UR50D.pt
```

This download happens inside the EVOLVEpro subprocess; KUMA only displays the
"Loading ESM-2 model" stage. The download is one-time per cache directory.

## Using EVOLVEpro from KUMA

1. Open the EVOLVEpro panel from the KUMA main window.
2. The onboarding card detects your `evolvepro` conda environment and reports
   `env_found`, version, and weight-cache status.
3. Fill in the run form:
   - **Input CSV**: variant table (column schema follows EVOLVEpro upstream)
   - **WT sequence**: wild-type protein sequence (amino acids)
   - **Rounds**: number of evolution rounds (1-10)
   - **Top N**: number of top variants to retain
   - **Output directory**: where EVOLVEpro writes output files
4. Click **Run**. Progress is reported in five stages: detect, loading,
   scoring, selecting, done.
5. The top variants table renders after the run completes.

## Offline Mode

For running EVOLVEpro without network access on first launch, manually place
the ESM-2 weights at:

```
~/.cache/torch/hub/checkpoints/esm2_t33_650M_UR50D.pt
```

The file SHA-256 must match the upstream checkpoint. KUMA only checks for
file existence; it does not validate the hash.

## Troubleshooting

| Error kind | Cause | Resolution |
| --- | --- | --- |
| `env_not_found` | conda not on PATH, or `evolvepro` env missing | Verify `conda env list` shows `evolvepro` |
| `network` | Cannot reach PyTorch hub or HuggingFace | Use offline mode (place weights manually) |
| `disk_full` | Cache volume out of space | Free 10 GB on the volume hosting `~/.cache/` |
| `permission` | KUMA cannot write to output directory | Pick a writable output directory |
| `runtime_error` | EVOLVEpro subprocess crashed | Check the full stdout/stderr log surfaced in the UI |

## License Disclaimer

EVOLVEpro is distributed under the MIT TLO Internal Research EULA. Installing
EVOLVEpro into your conda environment constitutes direct acceptance of that
EULA with MIT TLO. KUMA's role is limited to spawning subprocesses against
the user installation. KUMA itself is GPLv2 (see `LICENSE`).
