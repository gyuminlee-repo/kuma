import { describe, it, expect } from "vitest";
import { autoDetectCds } from "./autoDetectCds";

describe("autoDetectCds", () => {
  it("FASTA 단순 ORF 추출", () => {
    const result = autoDetectCds(">test\nATGAAATAA");
    expect(result).toEqual({ start: 0, end: 9, source: "fasta-orf" });
  });

  it("GenBank CDS 우선", () => {
    const result = autoDetectCds("LOCUS test\n     CDS  100..500\n");
    expect(result).toEqual({ start: 99, end: 500, source: "genbank-cds" });
  });

  it("ORF 없는 FASTA → null", () => {
    const result = autoDetectCds(">empty\nAATT");
    expect(result).toBeNull();
  });

  it("GenBank와 FASTA 둘 다 있어도 GenBank 우선", () => {
    const content = "     CDS  10..30\n>seq\nATGAAATAA";
    const result = autoDetectCds(content);
    expect(result).toEqual({ start: 9, end: 30, source: "genbank-cds" });
  });

  it("줄바꿈·공백 처리 (FASTA 다중 라인 시퀀스)", () => {
    const result = autoDetectCds(">multiline\nATGAAA\nAAATAA");
    expect(result).toEqual({ start: 0, end: 12, source: "fasta-orf" });
  });

  it("frame이 stop으로 끝나지 않으면 null", () => {
    // ATG로 시작하지만 stop codon 없이 서열이 끝남
    const result = autoDetectCds(">nonstop\nATGAAAGGG");
    expect(result).toBeNull();
  });
});
