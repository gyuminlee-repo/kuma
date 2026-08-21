import { describe, it, expect } from "vitest";
import { autoDetectCds, autoDetectCdsCandidates } from "./autoDetectCds";

// ─── autoDetectCds backward-compat tests ─────────────────────────────────────

describe("autoDetectCds (backward-compat)", () => {
  it("FASTA 단순 ORF 추출", () => {
    // ATG + 9 codons (3 aa) + stop = 12 nt = 3 aa excluding stop → below MIN_AA_LENGTH(30)
    // Use a long enough ORF: 30aa * 3 = 90nt + 3nt stop = 93nt
    const orf = "ATG" + "AAA".repeat(30) + "TAA"; // 30 aa + stop
    const result = autoDetectCds(`>test\n${orf}`);
    expect(result).toEqual({ start: 0, end: orf.length, source: "fasta-orf" });
  });

  it("GenBank CDS 우선", () => {
    const result = autoDetectCds("LOCUS test\n     CDS             100..500\n");
    expect(result).toEqual({ start: 99, end: 500, source: "genbank-cds" });
  });

  it("ORF 없는 FASTA → null", () => {
    const result = autoDetectCds(">empty\nAATT");
    expect(result).toBeNull();
  });

  it("GenBank와 FASTA 둘 다 있어도 GenBank 우선", () => {
    const orf = "ATG" + "AAA".repeat(30) + "TAA";
    const content = "     CDS             10..30\n>seq\n" + orf;
    const result = autoDetectCds(content);
    expect(result).toEqual({ start: 9, end: 30, source: "genbank-cds" });
  });

  it("줄바꿈·공백 처리 (FASTA 다중 라인 시퀀스)", () => {
    // 30 aa ORF split across lines
    const half1 = "ATG" + "AAA".repeat(15); // 15 codons
    const half2 = "AAA".repeat(15) + "TAA"; // 15 codons + stop
    const result = autoDetectCds(`>multiline\n${half1}\n${half2}`);
    expect(result?.source).toBe("fasta-orf");
    expect(result?.start).toBe(0);
  });

  it("frame이 stop으로 끝나지 않으면 null (short seq)", () => {
    // ATG로 시작하지만 stop codon 없이 서열이 끝남 (too short for MIN_AA_LENGTH)
    const result = autoDetectCds(">nonstop\nATGAAAGGG");
    expect(result).toBeNull();
  });
});

// ─── autoDetectCdsCandidates tests ───────────────────────────────────────────

describe("autoDetectCdsCandidates — GenBank multi-CDS", () => {
  it("단일 CDS 추출", () => {
    const content = "LOCUS test\n     CDS             100..400\n                     /gene=\"ispS\"\n";
    const results = autoDetectCdsCandidates(content);
    expect(results).toHaveLength(1);
    expect(results[0]).toMatchObject({ start: 99, end: 400, source: "genbank-cds", label: "ispS" });
  });

  it("다중 CDS 추출 (label 포함)", () => {
    const content = [
      "LOCUS test",
      "     CDS             100..400",
      '                     /gene="geneA"',
      '                     /product="Protein A"',
      "     CDS             500..800",
      '                     /gene="geneB"',
    ].join("\n");
    const results = autoDetectCdsCandidates(content);
    expect(results).toHaveLength(2);
    expect(results[0]).toMatchObject({ start: 99, end: 400, label: "geneA" });
    expect(results[1]).toMatchObject({ start: 499, end: 800, label: "geneB" });
  });

  it("uses locus_tag when gene is unavailable", () => {
    const content = [
      "LOCUS test",
      "     CDS             100..400",
      '                     /gene="unknown"',
      '                     /locus_tag="LT_001"',
      '                     /product="Target protein"',
    ].join("\n");

    expect(autoDetectCdsCandidates(content)[0]).toMatchObject({
      label: "LT_001",
      gene_name: "LT_001",
    });
  });

  it("aa_length 계산 (stop codon 제외)", () => {
    // 100..400 → end-start = 301 nt → (301 - 3) / 3 = 99 aa (excluding stop)
    const content = "     CDS             100..400\n";
    const results = autoDetectCdsCandidates(content);
    expect(results[0].aa_length).toBe(99);
  });

  it("complement CDS는 후보에서 제외된다", () => {
    // 이전에는 start:199, end:600 을 그대로 돌려줬다. 그 좌표는 정가닥
    // 좌표이고, CdsCoords 에는 strand 를 담을 필드가 없으며 번역기는
    // reference_seq[cds_start:cds_end] 를 정방향으로 자른다
    // (kuma_core/mame/translate/aa_translator.py:211). 즉 그 후보를 고르면
    // 역가닥 유전자를 정가닥으로 읽어 모든 AA 콜과 변이 위치가 틀리는데
    // 어디에서도 strand 를 무시했다고 말하지 않는다. join() 과 같이 건너뛴다.
    const content = "     CDS             complement(200..600)\n                     /gene=\"revGene\"\n";
    const results = autoDetectCdsCandidates(content);
    expect(results).toHaveLength(0);
  });

  it("정가닥 CDS는 그대로 파싱된다", () => {
    // 위 테스트의 대조군. 이게 없으면 모든 CDS 를 버리는 구현도 통과한다.
    const content = "     CDS             200..600\n                     /gene=\"fwdGene\"\n";
    const results = autoDetectCdsCandidates(content);
    expect(results).toHaveLength(1);
    expect(results[0]).toMatchObject({ start: 199, end: 600, label: "fwdGene" });
  });

  it("complement CDS 다음의 정가닥 CDS는 계속 읽힌다", () => {
    // 건너뛰기가 파싱 루프를 망가뜨리지 않는지 본다. i 를 진행시키지 않고
    // continue 하면 무한 루프가 되고, 너무 많이 건너뛰면 뒤 항목을 잃는다.
    const content =
      "     CDS             complement(200..600)\n" +
      "                     /gene=\"revGene\"\n" +
      "     CDS             700..900\n" +
      "                     /gene=\"fwdGene\"\n";
    const results = autoDetectCdsCandidates(content);
    expect(results).toHaveLength(1);
    expect(results[0]).toMatchObject({ start: 699, end: 900, label: "fwdGene" });
  });

  it("label 없는 CDS → label undefined", () => {
    const content = "     CDS             50..200\n";
    const results = autoDetectCdsCandidates(content);
    expect(results).toHaveLength(1);
    expect(results[0].label).toBeUndefined();
  });
});

describe("autoDetectCdsCandidates — FASTA multi-ORF", () => {
  function makeOrf(aa: number): string {
    return "ATG" + "AAA".repeat(aa) + "TAA";
  }

  it("단일 ORF (≥30 aa)", () => {
    const orf = makeOrf(30);
    // makeOrf(30) = ATG + 30×AAA + TAA = 32 codons total (ATG counts as 1 aa)
    // aa_length = (end - start - 3) / 3 = (96 - 3) / 3 = 31
    const results = autoDetectCdsCandidates(`>test\n${orf}`);
    expect(results).toHaveLength(1);
    expect(results[0]).toMatchObject({ start: 0, end: orf.length, source: "fasta-orf", label: "ORF1" });
    expect(results[0].aa_length).toBe(31);
  });

  it("30aa 미만 ORF 필터링", () => {
    const shortOrf = makeOrf(10); // 10 aa → filtered out
    const results = autoDetectCdsCandidates(`>test\n${shortOrf}`);
    expect(results).toHaveLength(0);
  });

  it("다중 ORF 추출 및 길이 기준 정렬", () => {
    // Two ORFs in same frame separated by stop codon (using non-ATG spacer to avoid overlap)
    const orf1 = makeOrf(50); // 50 aa (longer)
    const spacer = "GGG".repeat(5); // non-ATG spacer, stays in frame 0
    const orf2 = makeOrf(30); // 30 aa (shorter)
    const seq = orf1 + spacer + orf2;
    const results = autoDetectCdsCandidates(`>test\n${seq}`);
    expect(results.length).toBeGreaterThanOrEqual(2);
    // Results sorted by descending aa_length
    expect(results[0].aa_length).toBeGreaterThanOrEqual(results[1].aa_length);
  });

  it("FASTA 다중 frame ORF 감지", () => {
    // Frame 0: ATG...TAA starting at 0
    // Frame 1: ATG...TAA starting at 1
    const f0Orf = makeOrf(30); // starts at 0
    const frame1Prefix = "T";  // offset by 1
    const f1Orf = makeOrf(35); // starts at offset 1
    const seq = `${frame1Prefix}${f1Orf}TTTTT${f0Orf}`;
    // f0 ORF in frame 1 (offset 1), f1 is actually in frame 0 of the concatenated seq
    // Just verify that multi-frame search is attempted and at least one ORF found
    const results = autoDetectCdsCandidates(`>test\n${seq}`);
    expect(results.length).toBeGreaterThan(0);
    expect(results[0].source).toBe("fasta-orf");
  });

  it("GenBank content이면 FASTA ORF 무시", () => {
    const orf = makeOrf(30);
    const content = `     CDS             1..90\n>seq\n${orf}`;
    const results = autoDetectCdsCandidates(content);
    expect(results.every((r) => r.source === "genbank-cds")).toBe(true);
  });

  it("binary-looking content (SnapGene .dna read as text) yields [] instead of junk ORFs", () => {
    // A real SnapGene .dna file is a binary container: length-prefixed blocks,
    // arbitrary byte values. Reading it as text produces a mojibake string
    // that nonetheless contains ATG..stop runs in some frame, which previously
    // fired parseFastaOrfs and filled the dropdown with dozens of fake "ORF" entries.
    // Simulate that by embedding an ORF-shaped run inside high-byte garbage.
    const orf = makeOrf(30);
    const garbage = Array.from({ length: 200 }, (_, i) =>
      String.fromCharCode(1 + (i % 254)),
    ).join("");
    const content = `${garbage}${orf}${garbage}`;
    const results = autoDetectCdsCandidates(content);
    expect(results).toEqual([]);
  });
});
