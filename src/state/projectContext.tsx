import { createContext, useContext, type ReactNode } from "react";

export type KumaProject = {
  path: string;
  name: string;
  scratch: boolean;
  stage?: string;
  project_id?: string;
  newlyCreated?: boolean;
} | null;

const ProjectContext = createContext<KumaProject>(null);

export function ProjectProvider({ value, children }: { value: KumaProject; children: ReactNode }) {
  return <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>;
}

export function useKumaProject(): KumaProject {
  return useContext(ProjectContext);
}
