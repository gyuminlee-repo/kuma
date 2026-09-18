/**
 * codonTableRestore.ts, which codon table a restored project is entitled to.
 *
 * Section 8.3 of the design note is a table of five situations and it is the
 * substance of that section, because the two restore paths store different
 * things about the same fact. A workspace embeds the whole table (it travels to
 * machines that never had the file); an autosave snapshot embeds only the key
 * and the digest (it stays on one machine and is rewritten on every organism
 * change). So the same "the numbers moved" event arrives with a body on one
 * path and with a digest alone on the other, and the two cannot say the same
 * sentence: only the path that carries a body can name the amino acids.
 *
 * WHAT THIS FILE WILL NOT DO. There is no branch that quietly falls back to
 * `ecoli`, and no branch that merges the two tables. A key that this machine
 * cannot satisfy is preserved and reported; a table that disagrees blocks the
 * design until a human picks a side. `loadPolymerases` already set that
 * precedent for retired profiles (designSlice.ts), and the A1-versus-A01 well
 * ordering incident is what the silent-merge alternative looks like later.
 *
 * WHY A PURE FUNCTION AND NOT A HYDRATION ONE-SHOT. `useAutosaveHydration` can
 * resolve before `AppLayout`'s `loadOrganisms` does, so at hydration time the
 * organism list is still empty and every key reads as "not installed here".
 * The expectation is therefore stored as state and this resolver runs against
 * whatever the listing currently says, which also makes Refresh and a fresh
 * install re-answer the question with no extra wiring.
 */
import type { CodonTableDocument, OrganismSummary } from "@/types/models";

/**
 * What the restored project says its codon table was.
 *
 * `document` is present only when the expectation came from a workspace file.
 * An autosave snapshot supplies `key` and `tableSha256` alone, which is enough
 * to detect a disagreement and not enough to describe one.
 */
export interface ExpectedCodonTable {
  key: string;
  tableSha256: string;
  document?: CodonTableDocument | null;
}

export type CodonTableRestore =
  /** The organism listing has not arrived yet; ask again when it does. */
  | { kind: "pending" }
  /** Row 1: installed here and byte-for-byte the table the project used. */
  | { kind: "ok" }
  /** Row 2: not installed here, but the project carries its own copy. */
  | { kind: "installable"; key: string; name: string }
  /**
   * Row 4: not installed here and no copy to install (autosave restore).
   * The key is kept as selected and the design is refused by the backend.
   */
  | { kind: "absent"; key: string }
  /**
   * Row 3, digest-only form: installed here and different, restored from an
   * autosave snapshot that carries no body. Blocks the design; cannot name the
   * amino acids, so it points at the project file instead.
   */
  | { kind: "mismatchUnexplained"; key: string; name: string }
  /**
   * Rows 3 and 5: installed here, different, and the project's copy is at
   * hand. Blocks the design, names the amino acids that differ, and offers the
   * project's copy - which is the authoritative one - as an explicit
   * overwrite. `canInstall` is false when the local table is a bundled one,
   * where a user file of the same stem would be shadowed (R5) rather than take
   * effect.
   */
  | {
      kind: "mismatch";
      key: string;
      name: string;
      differingAminoAcids: string[];
      canInstall: boolean;
    };

/** Kinds that must stop a design from starting. */
export function blocksDesign(state: CodonTableRestore): boolean {
  return (
    state.kind === "installable" ||
    state.kind === "absent" ||
    state.kind === "mismatch" ||
    state.kind === "mismatchUnexplained"
  );
}

function serializeAminoAcid(pairs: [string, number][] | undefined): string {
  if (!pairs) return "";
  return pairs.map(([codon, freq]) => `${codon}:${freq}`).join(",");
}

/**
 * Amino acids whose codon assignment or frequencies differ between two tables.
 *
 * Compared in the order the backend normalised them into, so a table that only
 * re-sorted its codons does not read as changed; the canonical digest is taken
 * over the same normalised form, which is why "digests differ" and "this list
 * is non-empty" cannot disagree.
 */
export function differingAminoAcids(
  a: CodonTableDocument,
  b: CodonTableDocument,
): string[] {
  const names = new Set([...Object.keys(a.codons), ...Object.keys(b.codons)]);
  const differing: string[] = [];
  for (const aa of names) {
    if (serializeAminoAcid(a.codons[aa]) !== serializeAminoAcid(b.codons[aa])) {
      differing.push(aa);
    }
  }
  return differing.sort();
}

/**
 * Decide what a restored project may do with its codon table.
 *
 * @param expected What the project recorded, or null when it recorded nothing
 *   (a pre-Phase-2 file, or a session that never restored anything).
 * @param organisms The tables this machine currently offers, straight from
 *   `list_organisms`. An empty list means "not listed yet", not "none".
 */
export function resolveCodonTableRestore(
  expected: ExpectedCodonTable | null,
  organisms: OrganismSummary[],
): CodonTableRestore {
  if (!expected) return { kind: "ok" };
  if (organisms.length === 0) return { kind: "pending" };

  const local = organisms.find((o) => o.key === expected.key);
  if (!local) {
    return expected.document
      ? { kind: "installable", key: expected.key, name: expected.document.name }
      : { kind: "absent", key: expected.key };
  }
  if (local.table_sha256 === expected.tableSha256) return { kind: "ok" };
  if (!expected.document) {
    return { kind: "mismatchUnexplained", key: expected.key, name: local.name };
  }
  return {
    kind: "mismatch",
    key: expected.key,
    name: local.name,
    differingAminoAcids: local.document
      ? differingAminoAcids(local.document, expected.document)
      : [],
    canInstall: local.source === "user",
  };
}
