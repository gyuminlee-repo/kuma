const VALID_BASES = /^[ATGCatgc]*$/;

export function validateSeq(seq: string): string | null {
  if (!seq) return null;
  if (!VALID_BASES.test(seq)) {
    const invalid = seq.replace(/[ATGCatgc]/g, "");
    return `Invalid characters: ${[...new Set(invalid)].join(", ")}`;
  }
  return null;
}
