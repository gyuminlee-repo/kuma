/**
 * Whether an autosave restore is in progress, as a value React can subscribe
 * to. `autosave.ts` owns the gate (`beginHydration`/`endHydration`) and
 * reports its transitions here; this module has no other state.
 *
 * It is separate from `autosave.ts` so a component can read it without
 * pulling that module in: several tests replace `@/lib/autosave` wholesale
 * and would otherwise have to add these exports to every mock.
 */

import { useSyncExternalStore } from "react";

let active = false;
const listeners = new Set<() => void>();

/** Called by autosave.ts whenever its hydration depth crosses zero. */
export function setHydrationActive(next: boolean): void {
  if (next === active) return;
  active = next;
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function getSnapshot(): boolean {
  return active;
}

/** True while a project or scratch restore is being applied. */
export function useHydrationActive(): boolean {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}
