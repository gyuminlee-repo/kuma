export interface CdsCoords {
  start: number; // 0-based inclusive
  end: number;   // 0-based exclusive
  source: "genbank-cds" | "fasta-orf";
}

export function autoDetectCds(content: string): CdsCoords | null {
  // GenBank CDS feature 우선
  const cdsMatch = content.match(/CDS\s+(\d+)\.\.(\d+)/);
  if (cdsMatch) {
    return {
      start: parseInt(cdsMatch[1]) - 1, // GenBank 1-based → 0-based inclusive
      end: parseInt(cdsMatch[2]),       // GenBank 1-based inclusive -> 0-based exclusive (no conversion needed)
      source: "genbank-cds",
    };
  }
  // FASTA 첫 ORF (ATG~stop)
  const seq = content.replace(/^>.*\n/m, "").replace(/\s/g, "").toUpperCase();
  const startIdx = seq.indexOf("ATG");
  if (startIdx < 0) return null;
  for (let i = startIdx; i + 3 <= seq.length; i += 3) {
    const codon = seq.substring(i, i + 3);
    if (codon === "TAA" || codon === "TAG" || codon === "TGA") {
      return { start: startIdx, end: i + 3, source: "fasta-orf" };
    }
  }
  return null;
}
