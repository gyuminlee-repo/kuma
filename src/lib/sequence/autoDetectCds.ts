export interface CdsCoords {
  start: number; // 0-based inclusive
  end: number;   // 0-based exclusive
  source: "genbank-cds" | "fasta-orf";
}

export interface CdsCandidate {
  start: number;     // 0-based inclusive
  end: number;       // 0-based exclusive
  source: "genbank-cds" | "fasta-orf";
  label?: string;    // GenBank: gene/product name; FASTA: "ORF1", "ORF2", ...
  aa_length: number; // (end - start - 3) / 3 (excluding stop codon)
}

// Minimum ORF length in amino acids for FASTA ORF detection
const MIN_AA_LENGTH = 30;

/**
 * Extract all CDS/ORF candidates from a sequence file content.
 *
 * GenBank: parses all CDS features (skips join() constructs) with /gene= and /product= labels.
 * FASTA: searches all 3 forward frames for ATG~stop ORFs, filters by MIN_AA_LENGTH.
 * GenBank candidates are returned first when both types are present.
 */
export function autoDetectCdsCandidates(content: string): CdsCandidate[] {
  // Try GenBank first
  const gbCandidates = parseGenbankCds(content);
  if (gbCandidates.length > 0) return gbCandidates;

  // Fall back to FASTA ORF detection
  return parseFastaOrfs(content);
}

/**
 * Backward-compatible single result. Returns the first candidate or null.
 */
export function autoDetectCds(content: string): CdsCoords | null {
  const candidates = autoDetectCdsCandidates(content);
  if (candidates.length === 0) return null;
  const first = candidates[0];
  return { start: first.start, end: first.end, source: first.source };
}

// ─── GenBank parser ──────────────────────────────────────────────────────────

/**
 * Parse all CDS features from a GenBank flat file.
 * Skips join() constructs (multi-exon). Extracts /gene= and /product= qualifiers.
 */
function parseGenbankCds(content: string): CdsCandidate[] {
  const candidates: CdsCandidate[] = [];
  const lines = content.split(/\r?\n/);

  // Feature table lines have a 5-column indent for feature keys, 21-column for qualifiers.
  // A CDS feature line looks like:
  //   "     CDS             100..500"
  // or with complement:
  //   "     CDS             complement(100..500)"
  const featureLineRe = /^ {5}CDS\s+(?:complement\()?(\d+)\.\.(\d+)\)?/;
  const qualifierRe = /^ {21}\/(\w+)="(.*)"/;
  const contQualifierRe = /^ {21}([^/].*)"/;

  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const featureMatch = featureLineRe.exec(line);
    if (featureMatch) {
      const start = parseInt(featureMatch[1], 10) - 1; // GenBank 1-based → 0-based inclusive
      const end = parseInt(featureMatch[2], 10);       // GenBank 1-based inclusive → 0-based exclusive (end stays same)
      const aaLength = Math.floor((end - start - 3) / 3);

      // Scan forward for qualifiers (stop at next feature)
      let gene: string | undefined;
      let product: string | undefined;
      let j = i + 1;
      let currentQual: string | null = null;
      let currentVal = "";

      while (j < lines.length) {
        const qLine = lines[j];
        // Next feature detected (non-qualifier indent) → stop
        if (/^ {5}\S/.test(qLine)) break;

        const qualMatch = qualifierRe.exec(qLine);
        if (qualMatch) {
          // Save previous accumulated qualifier
          if (currentQual === "gene") gene = currentVal;
          else if (currentQual === "product") product = currentVal;

          currentQual = qualMatch[1];
          currentVal = qualMatch[2];
          // Check if value is complete (ends with ")
          if (qLine.trimEnd().endsWith('"')) {
            if (currentQual === "gene") gene = currentVal;
            else if (currentQual === "product") product = currentVal;
            currentQual = null;
            currentVal = "";
          }
        } else if (currentQual !== null) {
          // Continuation line
          const contMatch = contQualifierRe.exec(qLine);
          if (contMatch) {
            currentVal += " " + contMatch[1].trim().replace(/"$/, "");
            if (qLine.trimEnd().endsWith('"')) {
              if (currentQual === "gene") gene = currentVal;
              else if (currentQual === "product") product = currentVal;
              currentQual = null;
              currentVal = "";
            }
          }
        }
        j++;
      }

      // Flush last qualifier if not closed
      if (currentQual === "gene") gene = currentVal;
      else if (currentQual === "product") product = currentVal;

      const label = gene ?? product;
      candidates.push({ start, end, source: "genbank-cds", label, aa_length: aaLength });
      i = j;
      continue;
    }
    i++;
  }
  return candidates;
}

// ─── FASTA ORF parser ────────────────────────────────────────────────────────

/**
 * Find all ORFs (ATG → stop) in 3 forward reading frames that meet MIN_AA_LENGTH threshold.
 * Stop codon is excluded from aa_length count.
 */
function parseFastaOrfs(content: string): CdsCandidate[] {
  // Strip all FASTA headers and whitespace
  const seq = content
    .replace(/^>.*$/gm, "")
    .replace(/\s/g, "")
    .toUpperCase();

  if (!seq) return [];

  const candidates: CdsCandidate[] = [];
  const stopCodons = new Set(["TAA", "TAG", "TGA"]);
  let orfCounter = 0;

  for (let frame = 0; frame < 3; frame++) {
    let i = frame;
    while (i + 3 <= seq.length) {
      const codon = seq.substring(i, i + 3);
      if (codon === "ATG") {
        const orfStart = i;
        let j = i + 3;
        let found = false;
        while (j + 3 <= seq.length) {
          const stopCodon = seq.substring(j, j + 3);
          if (stopCodons.has(stopCodon)) {
            const orfEnd = j + 3; // 0-based exclusive (includes stop codon)
            const aaLength = Math.floor((orfEnd - orfStart - 3) / 3); // exclude stop
            if (aaLength >= MIN_AA_LENGTH) {
              orfCounter++;
              candidates.push({
                start: orfStart,
                end: orfEnd,
                source: "fasta-orf",
                label: `ORF${orfCounter}`,
                aa_length: aaLength,
              });
            }
            i = j + 3; // advance past stop
            found = true;
            break;
          }
          j += 3;
        }
        if (!found) {
          i = seq.length; // no stop found, skip to end
        }
      } else {
        i += 3;
      }
    }
  }

  // Sort by descending aa_length (longest ORF first = most likely coding)
  candidates.sort((a, b) => b.aa_length - a.aa_length);
  return candidates;
}
