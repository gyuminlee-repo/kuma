import type { StateCreator } from "zustand";
import i18next from "i18next";
import { sendRequest } from "../../lib/ipc-kuro";
import { buildKuroDesignInputPatch, buildKuroResultResetPatch } from "../../lib/kuroResultReset";
import { formatError } from "../../lib/utils";
import type { AppState } from "../types";
import type {
  ComputeCodonTableParams,
  ComputeCodonTableResult,
  ImportCodonTableParams,
  ImportCodonTableResult,
} from "../../types/models";
import { useMameAppStore } from "../mame/mameAppStore";

import type { SequenceSlice } from "../slice-interfaces";
export type { SequenceSlice };

// Only domain/pareto/structural diversity actually consume uniprotAccession
// (reference-domain fetch, pareto 3D distance, structural diversity, 3D view).
// Top-N-only workflows never touch it, so BLAST-backed auto-search (slow, no
// known accession) is gated on at least one of these being enabled.
function diversityConsumersEnabled(state: AppState): boolean {
  return state.domainDiversityEnabled || state.paretoDiversityEnabled || state.structuralDiversityEnabled;
}

/**
 * 결과물을 비웠으면 상태 메시지에 재설계 안내를 덧붙인다.
 * 기존 영어 리터럴 메시지는 그대로 두고 덧붙이는 문장만 i18n 키로 처리한다.
 */
function withClearedNotice(message: string, cleared: boolean): string {
  if (!cleared) return message;
  return `${message} | ${i18next.t("sequenceSlice.resultsClearedOnTemplateChange")}`;
}

// Ten minutes. The default 60 s covers the measured cases (0.5 s on a Linux
// filesystem, 4.2 s over drvfs, for 6,000 coding sequences) with room to
// spare, and would still cut off a large eukaryotic genome on a network
// drive -- where the user would read the timeout as a crash rather than as
// a slow file. Nothing here polls, so a longer ceiling costs nothing.
const COMPUTE_TIMEOUT_MS = 600_000;

const UNIPROT_AUTO_SEARCH_SKIPPED_MESSAGE =
  "UniProt auto-search skipped (domain/pareto/structural diversity disabled), "
  + "use the Step 1 search button if you need it later.";

/**
 * The one place the import payload is built.
 *
 * `dryRun` is a parameter rather than a literal in each caller. Two reasons,
 * and the second is a gate: preview and install must differ in exactly this
 * flag and nothing else, which is easier to keep true when one function writes
 * the payload; and tests/test_request_flags_come_from_controls.py rejects a
 * snake_case boolean pinned to a literal inside a request, because that is the
 * shape of a flag a control claims to own while the wire says otherwise. Here
 * the value genuinely comes from the caller, so writing it as a variable states
 * that rather than asserting it in an allow-list.
 */
async function sendCodonImport(
  params: ImportCodonTableParams,
  dryRun: boolean,
): Promise<ImportCodonTableResult> {
  return await sendRequest("import_codon_table", { ...params, dry_run: dryRun });
}

/** The compute counterpart of `sendCodonImport`. See that function's note. */
async function sendCompute(
  params: ComputeCodonTableParams,
  dryRun: boolean,
): Promise<ComputeCodonTableResult> {
  return await sendRequest(
    "compute_codon_table",
    { ...params, dry_run: dryRun },
    COMPUTE_TIMEOUT_MS,
  );
}

export const createSequenceSlice: StateCreator<AppState, [], [], SequenceSlice> = (set, get) => ({
  fastaPath: "",
  seqInfo: null,
  selectedGene: "",
  organism: "ecoli",
  organisms: [],
  restoredCodonTable: null,
  codonTableFailures: [],
  codonTableDir: null,

  loadSequence: async (filepath: string) => {
    // 판정에 쓸 직전 상태는 set()이 덮어쓰기 전에 잡아 둔다.
    const prev = get();
    const prevSeqInfo = prev.seqInfo;
    const prevHadResults = prev.designResults.length > 0 || prev.failedMutations.length > 0;

    try {
      set({ statusMessage: "Loading sequence file..." });
      const info = await sendRequest("load_fasta", { filepath });

      let bestGene = info.genes.length > 0 ? info.genes[0] : null;
      if (info.genes.length > 1) {
        for (const g of info.genes) {
          if (!bestGene || g.aa_length > bestGene.aa_length) {
            bestGene = g;
          }
        }
      }

      const selectedKey = bestGene ? String(bestGene.cds_start) : "";

      // The response carries no nucleotide identity; unchanged translation
      // cannot establish that primers still match a reloaded DNA template.
      const invalidateResults = prevSeqInfo !== null && prevHadResults;

      const loadedMessage =
        `Loaded: ${info.header} (${info.seq_length} bp) | ${info.genes.length} gene(s) `
        + `| Target: ${bestGene?.gene ?? "none"}`;

      set({
        ...buildKuroResultResetPatch(),
        ...(bestGene?.organism_key ? { organism: bestGene.organism_key } : {}),
        fastaPath: filepath,
        seqInfo: info,
        selectedGene: selectedKey,
        domains: [],
        refDomains: [],
        refDomainHash: "",
        refDomainsLoading: false,
        disabledDomains: [],
        domainStats: {},
        domainLoading: false,
        poolVariants: [],
        benchmarkResults: null,
        showBenchmark: false,
        uniprotCandidates: [],
        uniprotSearching: false,
        uniprotAccession: "",
        structureAccession: "",
        structureLoaded: false,
        structureLoading: false,
        statusMessage: withClearedNotice(loadedMessage, invalidateResults),
      });

      // Dual-write to MAME shared store so BarcodeSetupPanel can auto-fill.
      try {
        useMameAppStore.getState().setSharedFastaPath(filepath);
      } catch {
        // Defensive: never let the cross-store hand-off break sequence load.
      }

      // Auto-trigger UniProt search if gene has db_xref or translation.
      // Known-accession lookups are cheap (backend skips BLAST at >=95%
      // identity), so those always run. BLAST-only lookups (no known
      // accession) are gated on an actual accession consumer being enabled.
      if (bestGene) {
        const knownAcc = bestGene.uniprot_accession ?? "";
        const translation = bestGene.translation ?? "";
        const organism = bestGene.organism ?? "";
        if (knownAcc) {
          get().searchUniprot(bestGene.gene, organism, translation, knownAcc);
        } else if (translation) {
          if (diversityConsumersEnabled(get())) {
            get().searchUniprot(bestGene.gene, organism, translation, knownAcc);
          } else {
            // 이 분기는 위 set()의 statusMessage를 동기적으로 대체한다.
            // 결과물을 비웠으면 그 공지가 렌더 전에 사라지지 않게 함께 실어 보낸다.
            set({ statusMessage: withClearedNotice(UNIPROT_AUTO_SEARCH_SKIPPED_MESSAGE, invalidateResults) });
          }
        }

        // Domain allocation reads refDomains only (inputSlice.helpers
        // resolveSelectionDomains returns refDomains ?? []), and refDomains come
        // from the InterProScan scan, not from the UniProt accession. Auto-running
        // only the accession search left the one input allocation needs empty, so
        // the scan runs too whenever domain allocation is on. Concurrent consent
        // requests share one modal (networkConsentSlice requireNetworkConsent),
        // so this cannot double-prompt.
        if (translation && get().domainDiversityEnabled) {
          void get().annotateReferenceDomains();
        }
      }
    } catch (err) {
      set({ statusMessage: `Sequence file load failed: ${formatError(err)}` });
    }
  },

  setSelectedGene: (gene: string) => {
    // 대상 CDS가 바뀌면 잔기 번호 기준이 바뀌므로 loadSequence와 같은 이유로
    // 파생 결과물을 비운다. 같은 gene 재선택이거나 결과물이 없으면 건너뛴다.
    // mutationText는 사용자 원본이라 여기서도 보존한다.
    const prevState = get();
    const invalidateResults = gene !== prevState.selectedGene && prevState.designResults.length > 0;

    set({
      ...(invalidateResults ? buildKuroResultResetPatch() : {}),
      ...(invalidateResults
        ? { statusMessage: i18next.t("sequenceSlice.resultsClearedOnTemplateChange") }
        : {}),
      // 아래 uniprot 블록이 statusMessage를 동기적으로 덮을 수 있어
      // skip 분기에서 같은 공지를 다시 실어 보낸다(withClearedNotice).
      selectedGene: gene,
      domains: [],
      refDomains: [],
      refDomainHash: "",
      refDomainsLoading: false,
      disabledDomains: [],
      domainStats: {},
      domainLoading: false,
      poolVariants: [],
      benchmarkResults: null,
      showBenchmark: false,
      uniprotCandidates: [],
      uniprotSearching: false,
      uniprotAccession: "",
      structureAccession: "",
      structureLoaded: false,
      structureLoading: false,
    });
    const { seqInfo, organism } = get();
    const g = seqInfo?.genes.find((g) => String(g.cds_start) === gene);
    if (g) {
      if (g.organism_key) {
        set({ organism: g.organism_key });
      }
      const knownAcc = g.uniprot_accession ?? "";
      const translation = g.translation ?? "";
      if (knownAcc) {
        get().searchUniprot(g.gene, g.organism ?? organism, translation, knownAcc);
      } else if (translation) {
        if (diversityConsumersEnabled(get())) {
          get().searchUniprot(g.gene, g.organism ?? organism, translation, knownAcc);
        } else {
          set({ statusMessage: withClearedNotice(UNIPROT_AUTO_SEARCH_SKIPPED_MESSAGE, invalidateResults) });
        }
      }
      // The set() above cleared refDomains because the CDS changed. Domain
      // allocation reads refDomains only, so rescan for the same reason
      // loadSequence does.
      if (translation && get().domainDiversityEnabled) {
        void get().annotateReferenceDomains();
      }
    }
  },

  setOrganism: (organism: string) => set(buildKuroDesignInputPatch(get(), { organism })),

  /**
   * Fill the organism dropdown from the codon tables the sidecar actually has.
   *
   * The backend globs its resources directory, so the shipped set is whatever
   * is on disk and a hardcoded list in the UI goes stale every time a table is
   * added. Mirrors loadPolymerases in designSlice, minus its retired-profile
   * migration: a saved `organism` is never remapped or reset here, because a
   * key that is missing on this machine (a renamed or deleted table) must
   * survive a workspace restore rather than be silently switched to another
   * organism. SequenceInput keeps such a key selectable.
   */
  setRestoredCodonTable: (expected) => set({ restoredCodonTable: expected }),

  /**
   * Install the project's copy of the codon table into the user folder.
   *
   * Written straight to the drop-in folder rather than through an RPC, because
   * that folder IS the install interface Phase 1 shipped: the next
   * `list_organisms` validates the file exactly as it validates one a user
   * copied there by hand, so a bad embed lands in `failed[]` and never in the
   * dropdown. No new RPC, no dispatcher or generated-model change.
   *
   * The file is named after the key, which is what rule V8 checks the stem
   * against, and an existing file of that name is replaced - that replacement
   * is the explicit overwrite the caller has already confirmed.
   */
  installRestoredCodonTable: async () => {
    const expected = get().restoredCodonTable;
    const dir = get().codonTableDir;
    if (!expected?.document || !dir) {
      return i18next.t("codonTable.restore.installUnavailable");
    }
    try {
      const { writeTextFile } = await import("@tauri-apps/plugin-fs");
      const separator = dir.includes("\\") && !dir.includes("/") ? "\\" : "/";
      const target = `${dir.replace(/[/\\]$/, "")}${separator}${expected.key}.json`;
      await writeTextFile(target, JSON.stringify(expected.document, null, 2));
    } catch (err) {
      return formatError(err);
    }
    await get().loadOrganisms();
    // Whatever the listing now says is the answer; the resolver re-runs against
    // it. Dropping the expectation here instead would hide a write that landed
    // but did not validate.
    return null;
  },

  /**
   * Validate without installing. The dialog's preview.
   *
   * `dry_run` is the only difference from importCodonTable, so preview and
   * import cannot disagree about what a file gets wrong. A rejection is a
   * normal result here rather than a throw: the user picked a file and the
   * answer is the list of rules it broke, which the dialog renders through
   * formatCodonTableMessage. Only a transport failure throws.
   */
  previewCodonTable: async (params) => await sendCodonImport(params, true),

  /**
   * Install a codon table, re-list, and select it.
   *
   * The send -> relist -> select order is saveCustomPolymerase's, deliberately
   * copied rather than reinvented (designSlice.ts). The relist is what puts the
   * key in the dropdown and the select is what the user came for.
   *
   * A rejected import returns its result without touching the selection: the
   * sidecar wrote nothing, so switching the organism would name a table that
   * does not exist.
   */
  importCodonTable: async (params) => {
    try {
      const result = await sendCodonImport(params, false);
      if (!result.installed) return result;
      await get().loadOrganisms();
      get().setOrganism(result.key);
      set({
        statusMessage: i18next.t("codonTable.manager.installed", {
          key: result.key,
        }),
      });
      return result;
    } catch (err) {
      set({
        statusMessage: i18next.t("codonTable.manager.importFailed", {
          reason: formatError(err),
        }),
      });
      throw err;
    }
  },

  /**
   * The one place the compute payload is built, for the same reason
   * sendCodonImport exists: preview and install must differ in `dry_run` and
   * in nothing else.
   *
   * The timeout is raised from the 60 s default because the scan is the work.
   * Measured on this branch, 6,000 coding sequences take 0.5 s on a Linux
   * filesystem and 4.2 s over a Windows drvfs mount; a large eukaryotic
   * genome on a network drive is the case the default would cut off mid-scan,
   * and a timeout there reads as a crash rather than as a slow file.
   */
  previewComputedCodonTable: async (params) =>
    await sendCompute(params, true),

  /**
   * Count a genome, install the table and select it.
   *
   * Same send -> relist -> select as importCodonTable, and it delegates the
   * failure sentences to the same locale keys: from the user's side a table
   * that would not install is one situation, not two.
   */
  computeCodonTable: async (params) => {
    try {
      const result = await sendCompute(params, false);
      if (!result.installed) return result;
      await get().loadOrganisms();
      get().setOrganism(result.key);
      set({
        statusMessage: i18next.t("codonTable.manager.installed", {
          key: result.key,
        }),
      });
      return result;
    } catch (err) {
      set({
        statusMessage: i18next.t("codonTable.manager.importFailed", {
          reason: formatError(err),
        }),
      });
      throw err;
    }
  },

  exportCodonTable: async (params) => {
    try {
      const result = await sendRequest("export_codon_table", { ...params });
      set({
        statusMessage: i18next.t("codonTable.manager.exported", {
          path: result.path,
        }),
      });
      return result.path;
    } catch (err) {
      set({
        statusMessage: i18next.t("codonTable.manager.exportFailed", {
          reason: formatError(err),
        }),
      });
      throw err;
    }
  },

  loadOrganisms: async () => {
    try {
      // This call IS the refresh: the handler drops the registry caches, seeds
      // the user folder and re-reads both directories before answering, so the
      // Settings "Refresh" button needs no RPC of its own.
      const result = await sendRequest("list_organisms", {});
      // sendRequest validates and throws on a bad payload, so a malformed
      // envelope only reaches here from a stubbed transport. Guard anyway:
      // assigning undefined would break every reader of these lists.
      if (result && Array.isArray(result.organisms)) {
        set({
          organisms: result.organisms,
          codonTableFailures: Array.isArray(result.failed) ? result.failed : [],
          codonTableDir: typeof result.user_dir === "string" ? result.user_dir : null,
        });
      }
    } catch (err) {
      set({ statusMessage: `Organism list load failed: ${formatError(err)}` });
    }
  },
});
