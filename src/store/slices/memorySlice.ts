import type { StateCreator } from "zustand";
import type { AppState } from "../types";
import type { MemorySlice, MemoryWarning } from "../slice-interfaces";
export type { MemorySlice };

export const createMemorySlice: StateCreator<AppState, [], [], MemorySlice> = (
  set,
) => ({
  memoryWarning: null,

  setMemoryWarning: (w: MemoryWarning | null) => {
    set({ memoryWarning: w });
  },
});
