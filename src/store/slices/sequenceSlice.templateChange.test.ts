/**
 * sequenceSlice.templateChange.test.ts
 *
 * loadSequence가 템플릿 변경 시에만 파생 결과물(designResults 등)을 비우는지 본다.
 * 잔기 번호(F385Y 등)는 선택된 CDS 기준이라 템플릿이 바뀌면 이전 결과는 의미가 없다.
 * 같은 파일을 다시 열었을 뿐이면 결과물은 보존해야 한다.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AppState } from "../types";
import { sendRequest } from "../../lib/ipc-kuro";
import { createSequenceSlice } from "./sequenceSlice";

vi.mock("../../lib/ipc-kuro", () => ({
  sendRequest: vi.fn(),
}));

vi.mock("i18next", () => ({
  default: { t: (key: string) => key },
}));

const mockedSendRequest = vi.mocked(sendRequest);

const GENE_A = {
  gene: "ispS",
  cds_start: 1,
  aa_length: 3,
  organism: "e_coli",
  translation: "MKT",
  // 알려진 accession이 있으면 auto-search가 statusMessage를 덮지 않는다
  // (BLAST 게이트의 "skipped" 메시지 경로를 피해 상태 메시지를 단정할 수 있다).
  uniprot_accession: "P0CJ90",
};
const GENE_B = { ...GENE_A, gene: "gapA", translation: "MQQ" };

function seqInfoOf(gene: typeof GENE_A) {
  return { header: "h", seq_length: 9, genes: [gene] };
}

/** 이미 설계가 끝난 상태(결과물 + 카운터가 채워진 store)를 만든다. */
function makeStore(overrides: Record<string, unknown> = {}) {
  const fixture: Record<string, unknown> = {
    fastaPath: "/tmp/a.gb",
    seqInfo: seqInfoOf(GENE_A),
    selectedGene: "1",
    organism: "e_coli",
    // 파생 결과물. 템플릿이 바뀌면 전부 초기값으로 돌아가야 한다.
    designResults: [{ mutation: "F385Y" }],
    successCount: 1,
    totalCount: 2,
    failedMutations: ["Q163W"],
    plateMappings: [{ well: "A1" }],
    dedupInfo: { F385Y: 1 },
    manuallySwapped: { F385Y: "fwd" },
    customCandidates: { F385Y: [] },
    rescuedMutationDetails: [{ mutation: "F385Y" }],
    backendDesignStateSynced: true,
    // 사용자 원본 입력. 어떤 경우에도 보존한다.
    mutationText: "F385Y\nQ163W",
    statusMessage: "",
    domainDiversityEnabled: false,
    paretoDiversityEnabled: false,
    structuralDiversityEnabled: false,
    searchUniprot: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
  const state: Record<string, unknown> = { ...fixture };
  const set = (u: Record<string, unknown> | ((s: typeof state) => Record<string, unknown>)) => {
    Object.assign(state, typeof u === "function" ? u(state) : u);
  };
  const get = () => state as unknown as AppState;
  const slice = createSequenceSlice(
    set as Parameters<typeof createSequenceSlice>[0],
    get as Parameters<typeof createSequenceSlice>[1],
    {} as Parameters<typeof createSequenceSlice>[2],
  );
  // 슬라이스 초기 상태(seqInfo: null 등)가 픽스처를 덮지 않도록 순서를 맞춘다.
  Object.assign(state, slice, fixture);
  return { state, slice };
}

function expectResultsCleared(state: Record<string, unknown>) {
  expect(state.designResults).toEqual([]);
  expect(state.successCount).toBe(0);
  expect(state.totalCount).toBe(0);
  expect(state.failedMutations).toEqual([]);
  expect(state.plateMappings).toEqual([]);
  expect(state.dedupInfo).toEqual({});
  expect(state.manuallySwapped).toEqual({});
  expect(state.customCandidates).toEqual({});
  expect(state.rescuedMutationDetails).toEqual([]);
  expect(state.backendDesignStateSynced).toBe(false);
}

describe("loadSequence derived-result invalidation", () => {
  beforeEach(() => vi.clearAllMocks());

  it("clears design results when a different template file is loaded", async () => {
    mockedSendRequest.mockResolvedValue(seqInfoOf(GENE_B) as never);
    const { state, slice } = makeStore();

    await slice.loadSequence("/tmp/b.gb");

    expectResultsCleared(state);
    // 사용자 원본 입력은 보존한다.
    expect(state.mutationText).toBe("F385Y\nQ163W");
    expect(state.statusMessage).toContain("sequenceSlice.resultsClearedOnTemplateChange");
  });

  it("clears design results when the same path is reloaded but the target translation changed", async () => {
    mockedSendRequest.mockResolvedValue(seqInfoOf(GENE_B) as never);
    const { state, slice } = makeStore();

    await slice.loadSequence("/tmp/a.gb");

    expectResultsCleared(state);
  });

  it("keeps the cleared notice when the UniProt auto-search skip message replaces the load message", async () => {
    // accession 없음 + diversity consumer 전부 off = skip 분기. 이 분기는 로드 성공
    // 메시지를 동기적으로 대체하므로 공지가 함께 실려야 한다.
    const noAccession = { ...GENE_B, uniprot_accession: "" };
    mockedSendRequest.mockResolvedValue(seqInfoOf(noAccession) as never);
    const { state, slice } = makeStore();

    await slice.loadSequence("/tmp/b.gb");

    expect(state.searchUniprot).not.toHaveBeenCalled();
    expect(state.statusMessage).toContain("skipped");
    expect(state.statusMessage).toContain("sequenceSlice.resultsClearedOnTemplateChange");
  });

  it("keeps design results when the same unchanged file is reloaded", async () => {
    mockedSendRequest.mockResolvedValue(seqInfoOf(GENE_A) as never);
    const { state, slice } = makeStore();

    await slice.loadSequence("/tmp/a.gb");

    expect(state.designResults).toEqual([{ mutation: "F385Y" }]);
    expect(state.successCount).toBe(1);
    expect(state.totalCount).toBe(2);
    expect(state.backendDesignStateSynced).toBe(true);
    expect(state.statusMessage).not.toContain("resultsClearedOnTemplateChange");
  });

  it("does not announce a clear on the first load when no results exist yet", async () => {
    mockedSendRequest.mockResolvedValue(seqInfoOf(GENE_A) as never);
    const { state, slice } = makeStore({
      fastaPath: "",
      seqInfo: null,
      selectedGene: "",
      designResults: [],
    });

    await slice.loadSequence("/tmp/a.gb");

    expect(state.statusMessage).not.toContain("resultsClearedOnTemplateChange");
  });
});

describe("setSelectedGene derived-result invalidation", () => {
  beforeEach(() => vi.clearAllMocks());

  it("clears design results when a different CDS is selected", () => {
    const { state, slice } = makeStore({
      seqInfo: { header: "h", seq_length: 9, genes: [GENE_A, { ...GENE_B, cds_start: 2 }] },
    });

    slice.setSelectedGene("2");

    expectResultsCleared(state);
    expect(state.mutationText).toBe("F385Y\nQ163W");
    expect(state.statusMessage).toContain("sequenceSlice.resultsClearedOnTemplateChange");
  });

  it("keeps the cleared notice when the UniProt auto-search skip message replaces it", () => {
    const { state, slice } = makeStore({
      seqInfo: {
        header: "h",
        seq_length: 9,
        genes: [GENE_A, { ...GENE_B, cds_start: 2, uniprot_accession: "" }],
      },
    });

    slice.setSelectedGene("2");

    expect(state.statusMessage).toContain("skipped");
    expect(state.statusMessage).toContain("sequenceSlice.resultsClearedOnTemplateChange");
  });

  it("keeps design results when the already selected CDS is re-selected", () => {
    const { state, slice } = makeStore();

    slice.setSelectedGene("1");

    expect(state.designResults).toEqual([{ mutation: "F385Y" }]);
    expect(state.backendDesignStateSynced).toBe(true);
  });
});
