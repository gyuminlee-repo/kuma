export interface CloneEvidenceLink {
  readonly relationship: "same_clone" | "measured_resequence_clone";
  readonly mutant_id: string;
  readonly original_well: string;
  readonly original_plate: string;
  readonly activity_well?: string;
  readonly resequence_well: string;
  readonly resequence_plate: string;
}

export interface ResequenceEvidence {
  readonly original_verdict_xlsx: string;
  readonly verdict_xlsx: string;
  readonly links: CloneEvidenceLink[];
}

export function isResequenceEvidence(value: unknown): value is ResequenceEvidence {
  if (typeof value !== "object" || value === null) return false;
  if (!("original_verdict_xlsx" in value) || typeof value.original_verdict_xlsx !== "string") return false;
  if (!("verdict_xlsx" in value) || typeof value.verdict_xlsx !== "string") return false;
  return "links" in value && Array.isArray(value.links) && value.links.every((link: unknown) => {
    if (typeof link !== "object" || link === null) return false;
    return "relationship" in link && (link.relationship === "same_clone" ||
      (link.relationship === "measured_resequence_clone" && "activity_well" in link && typeof link.activity_well === "string" && link.activity_well.length > 0))
      && "mutant_id" in link && typeof link.mutant_id === "string"
      && "original_well" in link && typeof link.original_well === "string"
      && "original_plate" in link && typeof link.original_plate === "string"
      && "resequence_well" in link && typeof link.resequence_well === "string"
      && "resequence_plate" in link && typeof link.resequence_plate === "string";
  });
}
