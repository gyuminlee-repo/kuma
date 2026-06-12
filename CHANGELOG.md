# Changelog

## v0.13.5 - v0.13.6 (macOS SSL fix, MAME sample-data UX)

### Fixed
- v0.13.5: outbound HTTPS (Kuro UniProt search, AlphaFold, EBI BLAST, ESM) failed on the packaged macOS app with `CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate`. macOS OpenSSL does not read the Keychain and the frozen app has no build-machine CA store, so `ssl.create_default_context()` had no trust anchors. All external requests now route through a shared certifi-backed SSL context (`certifi.where()`, bundled by PyInstaller `hook-certifi`), identical on Windows, macOS, and Linux. Windows and Linux were unaffected because their OS CA stores are present on the target. (`kuma_core/shared/net.py`, `python-core/sidecar_kuro/core.py`, `kuma_core/kuro/alphafold.py`, `kuma_core/kuro/esm_embeddings.py`, `pyproject.toml`)
- v0.13.6: MAME step 1.1 "Generate Barcode Package" no longer requires the output directory to live inside the project root (it failed with `output_dir must be inside project_root`). `mame_context.json` stores paths relative when the output is inside the project root (portable) and absolute when outside, and the loader resolves both. (`kuma_core/mame/ingest/barcode_package.py`, `src/lib/mame/detectProjectFiles.ts`)

### Added
- v0.13.6: loading sample data populates a precomputed analysis result (`samples/mame/sample_analysis_result.json`, serialized from the real demux/consensus/verdict/health pipeline) so the Per-plate verdict breakdown renders instead of showing "Setup incomplete". (`python-core/scripts/generate_mame_sample_result.py`, `src/store/mame/slices/analysisSlice.ts`)
- v0.13.6: loading sample data seeds the Build EVOLVEpro Input form (layout / GC data / Agilent rep-batch / previous EVOLVEpro) from the bundled `06`/`08`/`09`/`10` sample xlsx files; fields already set by the user are preserved. (`src/store/mame/slices/analysisSlice.ts`, `src/lib/mame/buildEvolveproFormStorage.ts`, `src/components/mame/panels/BuildEvolveproInputPanel.tsx`)

---

## v0.13.3.1 - v0.13.4.0 (native MinKNOW run-folder ingestion, auto-updater removal, CI quality gates, i18n parity)

### Added
- v0.13.4.0: MAME `analyze` auto-detects a raw MinKNOW run folder (a directory containing `fastq_pass/`) and orchestrates demux → consensus internally, so a pre-demuxed consensus directory is no longer required. There is no new RPC: the pre-demuxed consensus path and the standalone `mame.run_combinatorial_demux` RPC are unchanged, and the `{R}_{F}` well-naming contract is preserved. (`kuma_core/mame/ingest/run_pipeline.py` `is_minknow_run_dir`/`ingest_run_folder`, `python-core/sidecar_mame/handlers/analyze.py`, `python-core/sidecar_mame/models.py` `DemuxParamsBase`/`AnalyzeRawRunParams`, `src/types/mame/models.ts`, `src/store/mame/slices/inputSlice.ts`, `src/hooks/mame/useMameSidecar.ts`)
- v0.13.4.0: raw-run analyze emits two-phase progress (demux 0–50, analyze 50–100) carrying a `stage` field, so the UI shows one demux→analyze flow from a single `analyze` call with a dedicated `MAME_RAWRUN_RPC_TIMEOUT_MS`; the consensus-directory path keeps its byte-identical 0–100 progress with no `stage` key. (`python-core/sidecar_mame/handlers/analyze.py`, `src/store/mame/slices/inputSlice.ts`, `src/hooks/mame/useMameSidecar.ts`)
- v0.13.4.0: CI gains a `quality-gates` job (pytest / `tsc --noEmit` / `sync:check` / `i18n:check`) that gates the release build, plus a new `mame-analyze-run-folder` cross-layer sync group keeping the demux params identical across Pydantic, TypeScript, and the dispatcher. (`.github/workflows/build.yml`, `.cross-layer-sync.json`)
- v0.13.4.0: all 10 locales brought to full key parity with `i18n-lint` hardening; UI locales and the Kuro/MAME screens now load on demand (dynamic `import()` + `React.lazy`/`Suspense`), trimming the initial JS bundle. (`src/locales/*.json`, `scripts/i18n-lint.mjs`, `src/lib/i18n.ts`, `src/screens/MainShell.tsx`)

### Removed
- v0.13.4.0: the Tauri auto-updater is removed — the frontend `src/lib/updater.ts`, the Cargo dependency, the updater capability, the `lib.rs` plugin registration, and the About-dialog wiring are all gone, and the Check-for-updates menu entry is repurposed to the release page. (`src/lib/updater.ts` deleted, `src-tauri/Cargo.toml`, `src-tauri/capabilities/default.json`, `src-tauri/src/lib.rs`, `src/components/layout/SharedAboutDialog.tsx`)

### Fixed
- v0.13.3.2: corrected an EVOLVEpro numeric overflow and four stale test expectations.
- v0.13.3.3: the verdict window note now reflects the real window instead of a hardcoded ±5, `compute_T3` is de-duplicated, and the SDM parse fallback is logged instead of failing silently.

---

## v0.13.0.1 - v0.13.3.0 (MAME verdict depth gate, analyze progress, resume hardening, export guards, macOS build)

### Fixed
- v0.13.0.1: MAME verdict depth gate uses the consensus header `depth=N` (real read depth) instead of the consensus FASTA file size; the file-size check is demoted to a fallback that fires only when `depth=N` is absent, and `CompareParams.min_read_count` now defaults to 30. Previously every well was flagged `LOWDEPTH` because a gene-length-fixed consensus FASTA (~1.8KB, identical across same-amplicon wells) could never reach the raw-read `min_file_size_kb=50` floor. (`kuma_core/mame/compare/verdict.py`, `kuma_core/mame/models.py`)
- v0.13.1.0: MAME analyze emits per-record sub-progress and runs a 30s keep-alive heartbeat, fixing the ETA stalling near 60% and the 300s "no response" deadlock popup on long but healthy analyze runs. (`kuma_core/mame/pipeline.py` `run_analyze`, `python-core/sidecar_mame/handlers/analyze.py`)
- v0.13.2.4: the resume orphan guard detects stray `.fa`/`.fas` files (not only `.fasta`) via a shared `CONSENSUS_FILE_PATTERNS`; resumed demux runs seed `n_input_reads`/`n_unassigned` from completion markers so totals no longer undercount or go negative. (`kuma_core/mame/ingest/stage_marker.py`, `kuma_core/mame/ingest/fasta_parser.py`, `python-core/sidecar_mame/handlers/demux.py`)
- v0.13.2.6: MAME resume/skip now also covers the raw_run path (`run_combinatorial_demux_per_nb`), not only `handle_demux_and_filter`. Re-running raw_run on a folder that has completion markers skips already-finished native barcodes instead of re-demuxing everything. (`kuma_core/mame/ingest/combinatorial_demux.py`, `kuma_core/mame/ingest/stage_marker.py`)

### Added
- v0.13.2.1: MAME step 2.1 (demux/consensus) writes are atomic (temp file + `os.replace`), each native-barcode group writes a `.demux_consensus_complete.json` completion marker, and a rerun skips groups whose marker matches the on-disk inventory. An asymmetric consumer guard fails fast on a present-but-invalid marker while still loading legacy or externally-sorted directories that have no marker. (`kuma_core/shared/atomic_write.py`, `kuma_core/mame/ingest/stage_marker.py`, `python-core/sidecar_mame/handlers/demux.py`, `kuma_core/mame/ingest/fasta_parser.py`)
- v0.13.2.2: overwrite confirmation for the MAME Janus mapping, Run report, and Barcode package exports; the Barcode package confirms at the `design/` directory level. (`src/components/mame/dialogs/JanusMappingDialog.tsx`, `RunReportDialog.tsx`, `src/components/mame/panels/BarcodeSetupPanel.tsx`, `src/lib/overwriteConfirm.ts`)
- v0.13.3.0: `max_consensus_n_fraction` is adjustable from the MAME analyze parameter panel (default 0.0, strict by default). (`src/components/mame/panels/ParameterPanel.tsx`, `src/store/mame/slices/inputSlice.ts`)
- v0.13.2.5: macOS minimap2 is compiled from source in CI (`make arm_neon=on aarch64=on`, pinned v2.30) and bundled into the macOS sidecar, mirroring the Windows MinGW step; previously the macOS build had no minimap2 source and failed at `build_sidecar.py`. (`.github/workflows/build.yml`)

---

## v0.12.1.0 – v0.12.3.4 (minimap2 CLI cross-platform)

In-process `mappy` 정렬기를 사이드카에 번들된 `minimap2` CLI 로 교체. mappy 는 Windows wheel 이 없어 MAME `raw_run` 이 Windows 에서 실패했음.

### Changed
- `kuma_core/mame/ingest/align.py`: `align_reads`/`align_reads_multi` 가 `minimap2` 바이너리를 subprocess 로 호출하고 SAM 을 파싱, 동일한 `Alignment` dataclass 반환. 바이너리는 `KURO_MINIMAP2` → 사이드카 `_MEIPASS/bin` → PATH 순으로 해석.
- reverse-strand `q_st`/`q_en` 를 원본 read 좌표로 환산, soft/hard clip 을 `Alignment.cigar` 에서 제거하여 mappy 와 일치(실 ONT 데이터에서 consensus byte-identical 검증).
- `build_sidecar.py` / `mame-sidecar.spec`: PyInstaller `--add-binary` 로 플랫폼별 `minimap2` 를 `_MEIPASS/bin/` 에 번들.
- `.github/workflows/build.yml`: 사이드카 빌드 전 vendor 채우기. Linux/macOS 는 `scripts/vendor-minimap2.py` 로 공식 바이너리 다운로드, Windows 는 MSYS2/MinGW 정적 빌드(`make LIBS="-Wl,-Bstatic -lm -lz -lpthread -Wl,-Bdynamic"`) + `ldd` 가드로 비정적 바이너리 거부.
- `.github/workflows/ci.yml`: `python-tests` 에 minimap2 제공(Linux/macOS). `tests/mame/conftest.py` 는 바이너리 부재 시 MAME 테스트 skip(Windows leg).

### Removed
- `pyproject.toml` 의 `mappy` 의존(main + `mame-raw` extra).

### Added
- `NOTICE-bundled.md`: minimap2(MIT)·zlib 서드파티 고지, 번들 `NOTICE.md` 에 병합.

---

## v0.11.0.0 (PR-B: Legacy cleanup)

Remove legacy sort_barcode pipeline and Trim Adapters UI fields.
Aporva-style alignment-based combinatorial demux becomes canonical.

### Removed
- `kuma_core.mame.ingest.sort_barcode`: sliding/edlib read-sorting algorithm
  (`sort_barcode_run`, `_sort_one_nb`, `_hamming_prefix_window_in_head`,
  `_hamming_suffix_window_in_tail`, `_FWD_SEARCH_WINDOW_BP`, `_EDIT_DIST_RATIO`,
  `SortBarcodeResult`, `_hamming_suffix_window`)
- `python-core/sidecar_mame/handlers/sort_barcode.py`: RPC handler
- `sort_barcode_run` method from dispatcher `_METHODS` and `_ASYNC_METHODS`
- `src/types/mame/sort_barcode.ts`: TypeScript type file
- `RawRunParams.minBarcodeScore`, `linkedTrim`, `revPrimerUniversal` state fields
- Trim Adapters, Universal Rev Primer, Min Barcode Score UI fields (9 keys x 10 locales)

### Changed
- `sort_barcode.py` retained as barcode xlsx parser module only
  (`parse_combinatorial_barcodes`, `parse_sample_map`, `_make_well_filename`,
  `_nb_to_sort_barcode_name`)
- `models.py`: removed `_check_pr_b_fields_deferred` validator;
  `sample_map_xlsx` and `kuro_xlsx` params now accepted without error
- `.cross-layer-sync.json`: removed `mame-sort-barcode` and
  `mame-dispatcher-sort-barcode` groups

---

## v0.10.3.0 (PR-A: combinatorial demux frontend)

Add combinatorial demux RPC and UI.

- ParameterPanel Advanced section (coverageFraction, editDistRatio, chimeraSplit)
- `mame.run_combinatorial_demux` RPC wired to `runAnalysis` in `inputSlice`
- `selectCanRun` updated for raw_run mode validation

---

## v0.10.2.0

Chimera-aware demux for concatenated nanopore reads.

---

## v0.10.1.0

Add combinatorial_demux pipeline for 96-well amplicon screening.
