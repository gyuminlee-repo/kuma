type Listener = () => void;

const listeners = new Map<string, Set<Listener>>();

export function subscribe(event: string, fn: Listener): () => void {
  let set = listeners.get(event);
  if (!set) {
    set = new Set();
    listeners.set(event, set);
  }
  set.add(fn);
  return () => {
    set!.delete(fn);
  };
}

export function emit(event: string): void {
  const set = listeners.get(event);
  if (!set) return;
  for (const fn of set) {
    try {
      fn();
    } catch {
      // ignore listener errors
    }
  }
}

export function _resetListenersForTest(): void {
  listeners.clear();
}
