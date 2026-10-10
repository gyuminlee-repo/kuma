import type { AppState } from "@/store/types";
import type { DomainAnnotationBinding, DomainAnnotationResult, DomainAnnotationSource } from "@/types/domainAnnotation";

export function domainReferenceSequence(state: AppState): string {
  return ((state.seqInfo?.genes.find((g) => String(g.cds_start) === state.selectedGene) ?? state.seqInfo?.genes[0])?.translation ?? "").trim().replace(/\*+$/, "");
}

/** Session identity includes the inspection revision, so same-path reimports invalidate old work. */
export function domainAnnotationContextKey(state: AppState): string {
  return JSON.stringify([state.strictStructureSource, state.predictionBundleRevision, state.predictionBundlePath,
    state.predictionBundleInventory?.bundle_sha256, state.predictionBundleModelId, state.predictionBundleChainId,
    state.fastaPath, state.seqInfo?.header, state.selectedGene, domainReferenceSequence(state)]);
}

export function domainAnnotationSource(state: AppState): DomainAnnotationSource | null {
  const inventory = state.predictionBundleInventory;
  const model = inventory?.models.find((item) => item.model_id === state.predictionBundleModelId);
  const chain = model?.chains.find((item) => item.chain_id === state.predictionBundleChainId);
  const refSeq = domainReferenceSequence(state);
  if (state.strictStructureSource !== "prediction_bundle" || (inventory?.format !== "colabfold" && inventory?.format !== "af3_server")
    || state.predictionBundleLoading || !state.predictionBundlePath || !model || !chain || !refSeq) return null;
  return { prediction_bundle_path: state.predictionBundlePath, prediction_bundle_sha256: inventory.bundle_sha256,
    prediction_model_id: model.model_id, prediction_chain_id: chain.chain_id, ref_seq: refSeq };
}

export async function hashDomainReference(reference: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(reference));
  return Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, "0")).join("");
}

export function bindingMatchesSource(binding: DomainAnnotationBinding, source: DomainAnnotationSource, referenceSha256: string): boolean {
  return binding.bundle_sha256 === source.prediction_bundle_sha256 && binding.model_id === source.prediction_model_id
    && binding.chain_id === source.prediction_chain_id && binding.reference_sha256 === referenceSha256;
}

export function sameDomainBinding(a: DomainAnnotationBinding, b: DomainAnnotationBinding): boolean {
  return a.bundle_sha256 === b.bundle_sha256 && a.source_sha256 === b.source_sha256
    && a.reference_sha256 === b.reference_sha256 && a.model_id === b.model_id && a.chain_id === b.chain_id;
}

export function currentDomainAnnotation(state: AppState): DomainAnnotationResult | null {
  return state.domainAnnotationContext === domainAnnotationContextKey(state) ? state.domainAnnotationResult : null;
}

export function domainJobIsActive(state: string | undefined): boolean {
  return state === "queued" || state === "running" || state === "cancelling";
}

/** Pure display summary; never changes variant order, N, scores or selection. */
export function domainSelectionDistribution(result: DomainAnnotationResult, reference: string, variants: string[]) {
  const membership = new Map<number, number>();
  result.domains.forEach((domain, i) => domain.positions.forEach((p) => membership.set(p, i)));
  const buckets = [...result.domains.map((d) => ({ residues: d.positions.length, variants: [] as string[], sites: new Set<number>() })),
    { residues: result.unassigned_positions.length, variants: [] as string[], sites: new Set<number>() }];
  if (reference.length !== result.total_residues) return null;
  const seen = new Set<string>();
  for (const variant of variants) {
    const match = /^([ACDEFGHIKLMNPQRSTVWY])([1-9]\d{0,3})([ACDEFGHIKLMNPQRSTVWY])$/.exec(variant);
    if (!match || seen.has(variant)) return null;
    const position = Number(match[2]);
    if (position > reference.length || reference[position - 1] !== match[1] || match[1] === match[3]) return null;
    seen.add(variant);
    const bucket = buckets[membership.get(position) ?? result.domains.length];
    bucket.variants.push(variant); bucket.sites.add(position);
  }
  return buckets.map((bucket) => ({ residueCount: bucket.residues, variantCount: bucket.variants.length,
    siteCount: bucket.sites.size, variants: bucket.variants, fraction: variants.length ? bucket.variants.length / variants.length : null }));
}

export function formatDomainPositions(positions: number[]): string {
  const segments: string[] = [];
  for (let i = 0; i < positions.length; i++) {
    const start = positions[i];
    let end = start;
    while (i + 1 < positions.length && positions[i + 1] === end + 1) end = positions[++i];
    segments.push(start === end ? String(start) : `${start}–${end}`);
  }
  return segments.join(", ");
}
