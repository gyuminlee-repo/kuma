import { create } from "zustand";
import { createContext, useContext } from "react";
import { registerRunStore, type MameRunScope } from "@/lib/mame/runRequests";
import { subscribeWithSelector } from "zustand/middleware";
import { createAnalysisSlice } from "./slices/analysisSlice";
import { createExportSlice } from "./slices/exportSlice";
import { createInputSlice } from "./slices/inputSlice";
import { createNavigationSlice } from "./slices/navigationSlice";
import { createPhaseSlice } from "./slices/phaseSlice";
import type { AppState } from "./types";
export type { AppState };

export const createMameStore = (runScope: MameRunScope = "primary") => create<AppState>()(
  subscribeWithSelector((...args) => ({
    ...createInputSlice(...args),
    ...createAnalysisSlice(...args),
    ...createExportSlice(...args),
    ...createPhaseSlice(...args),
    ...createNavigationSlice(...args),
    runScope,
    janusRunScope: "primary",
    analyzeResult: null,
    resequenceSnapshot: null,
    ...(runScope === "resequence" ? { mamePhase: "analyze" as const, currentMameSubStep: "analyze.inputs" as const } : {}),
  })),
);

const primaryStore = createMameStore();
export const resequenceStore = createMameStore("resequence");
export const MameRunStoreContext = createContext<ReturnType<typeof createMameStore> | null>(null);
export function useMameStoreApi() {
  return useContext(MameRunStoreContext) ?? primaryStore;
}
function useScopedStore(): AppState;
function useScopedStore<T>(selector: (state: AppState) => T): T;
function useScopedStore<T>(selector?: (state: AppState) => T): T | AppState {
  const store = useMameStoreApi();
  return store<T | AppState>((state) => selector ? selector(state) : state);
}
export const useMameAppStore = Object.assign(useScopedStore, primaryStore);
registerRunStore("primary", primaryStore.getState);
registerRunStore("resequence", resequenceStore.getState);
