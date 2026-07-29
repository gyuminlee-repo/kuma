// Matches a single substitution token such as "L59M" (an uppercase letter,
// digits, an uppercase letter). Mirrors kuma_core/kuro/evolvepro.py _POS_RE,
// used there to enumerate substituted positions in colon-separated combo
// variant IDs like "L59M:W60T:K64W".
const SUBSTITUTION_TOKEN_RE = /[A-Z]\d+[A-Z]/g;

/**
 * Count the substituted positions referenced in a variant ID by counting
 * matches of the single-substitution token pattern. A variant with more than
 * one match is a multi-substitution ("combinatorial") variant.
 */
export function countSubstitutionTokens(variant: string): number {
  const matches = variant.match(SUBSTITUTION_TOKEN_RE);
  return matches ? matches.length : 0;
}

/**
 * Fraction of poolVariants that are multi-substitution (combinatorial)
 * variants, i.e. variant IDs referencing more than one substituted position.
 * Returns 0 for an empty pool (no division by zero).
 */
export function combinatorialFraction(poolVariants: string[]): number {
  if (poolVariants.length === 0) return 0;
  const comboCount = poolVariants.filter((v) => countSubstitutionTokens(v) > 1).length;
  return comboCount / poolVariants.length;
}
