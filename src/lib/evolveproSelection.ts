/**
 * Resize an EVOLVEpro selection to a new design count from the candidates
 * already loaded, without asking the sidecar again.
 *
 * The selection is seeded at CSV load with `topN = maxPrimers`, so a design
 * count raised afterwards used to leave it at the load-time size and Run
 * Design kept designing that many (the design-time reload preserved it).
 *
 * Ordering follows `prepareDesignInput`: the current selection in ranked order
 * (backend score order), unranked entries last. Shrinking keeps the first
 * `target`. Growing appends ranked candidates not yet selected, in rank order.
 *
 * Limit: `ranked` is the selection plus at most `EVOLVEPRO_RANKED_BUFFER` (50)
 * further candidates (`kuma_core/kuro/evolvepro.py`), so growth stops when that
 * buffer runs out, and a refill by score is exact only for plain top-N. The
 * design-time reload asks the sidecar again with the current count and closes
 * both gaps; this function keeps the screen and the count in step until then.
 */
import type { RankedCandidateItem } from "@/types/models.generated";

export function resizeEvolveproSelection(
  current: readonly string[],
  ranked: readonly Pick<RankedCandidateItem, "variant">[],
  target: number,
): string[] {
  const n = Math.max(0, Math.floor(target));
  const rankOf = new Map<string, number>();
  ranked.forEach((c, i) => {
    if (!rankOf.has(c.variant)) rankOf.set(c.variant, i);
  });
  const selected = new Set(current);
  const inRank = [...selected]
    .filter((v) => rankOf.has(v))
    .sort((a, b) => rankOf.get(a)! - rankOf.get(b)!);
  const unranked = [...selected].filter((v) => !rankOf.has(v));
  const ordered = [...inRank, ...unranked];
  if (ordered.length >= n) return ordered.slice(0, n);
  const out = [...ordered];
  for (const c of ranked) {
    if (out.length >= n) break;
    if (!selected.has(c.variant)) {
      selected.add(c.variant);
      out.push(c.variant);
    }
  }
  return out;
}
