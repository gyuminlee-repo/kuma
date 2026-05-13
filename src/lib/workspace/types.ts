export type AppId = "kuro" | "mame" | "primerbench";

export type ArtifactType =
  | "evolvepro_csv"
  | "sdm_primer_xlsx"
  | "mame_consensus_fasta";

export interface ManifestArtifact {
  id: string;
  app: AppId;
  step: string;
  type: ArtifactType;
  path: string;
  producedAt: string;
  mtime: string;
  sizeBytes: number;
}

export interface WorkspaceManifest {
  schemaVersion: 1;
  workspaceId: string;
  createdAt: string;
  updatedAt: string;
  artifacts: ManifestArtifact[];
}

export interface ArtifactRef extends Omit<ManifestArtifact, "path"> {
  path: string;
  stale: boolean;
}

export interface NewArtifact {
  app: AppId;
  step: string;
  type: ArtifactType;
  absolutePath: string;
}

export const SCHEMA_VERSION = 1 as const;
export const MANIFEST_FILENAME = ".kuma-workspace.json";
