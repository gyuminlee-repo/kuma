export const ESMFOLD_KEY_PREFIX = "ESMFOLD:";
export const ESMFOLD_MIN_RESIDUES = 10;
export const ESMFOLD_MAX_RESIDUES = 400;

export function isEsmfoldKey(structureAccession: string): boolean {
  return structureAccession.toUpperCase().startsWith(ESMFOLD_KEY_PREFIX);
}

export type FrameRecovery = "none" | "esmfold" | "alphafold_server" | "structure_file";

export interface FrameRecoveryInput {
  /** The structure found for the accession does not exactly cover the reference. */
  frameMismatch: boolean;
  /** Reference length without a trailing stop. */
  refLength: number;
  /** The user declined the ESMFold network consent (or switched the service off). */
  esmfoldRefused: boolean;
}

/**
 * What to do when the accession structure does not match the reference:
 * predict the reference with ESMFold when its size allows and consent is given,
 * send a longer sequence to AlphaFold Server, otherwise ask for a structure file.
 * Never returns a silent 1-D fallback: every non-"none" outcome is shown to the user.
 */
export function decideFrameRecovery({ frameMismatch, refLength, esmfoldRefused }: FrameRecoveryInput): FrameRecovery {
  if (!frameMismatch) return "none";
  if (refLength > ESMFOLD_MAX_RESIDUES) return "alphafold_server";
  if (refLength < ESMFOLD_MIN_RESIDUES || esmfoldRefused) return "structure_file";
  return "esmfold";
}
