/**
 * MOCK_MODE shim for `@tauri-apps/api/event`.
 *
 * The real module routes `listen` and its unlisten callback through
 * `invoke("plugin:event|listen")` and `invoke("unregisterListener")`. Neither
 * command has a stub in core.ts, so both threw and every screen that registers
 * an event listener painted a page error during capture. MainShell registers
 * one for `second-instance-attempted`, which is why the error showed up before
 * any interaction.
 *
 * Nothing in MOCK_MODE emits events, so the listeners only have to register,
 * stay registered, and unregister without throwing. `emit` is kept so a capture
 * script can drive a listener by hand if it ever needs to.
 */

export interface Event<T> {
  event: string;
  id: number;
  payload: T;
}

export type EventCallback<T> = (event: Event<T>) => void;
export type UnlistenFn = () => void;

let nextId = 1;
const listeners = new Map<string, Map<number, EventCallback<never>>>();

function register<T>(event: string, handler: EventCallback<T>): UnlistenFn {
  const id = nextId++;
  let forEvent = listeners.get(event);
  if (!forEvent) {
    forEvent = new Map();
    listeners.set(event, forEvent);
  }
  forEvent.set(id, handler as EventCallback<never>);
  return () => {
    listeners.get(event)?.delete(id);
  };
}

export async function listen<T>(
  event: string,
  handler: EventCallback<T>,
): Promise<UnlistenFn> {
  return register(event, handler);
}

export async function once<T>(
  event: string,
  handler: EventCallback<T>,
): Promise<UnlistenFn> {
  const unlisten = register<T>(event, (payload) => {
    unlisten();
    handler(payload);
  });
  return unlisten;
}

export async function emit<T>(event: string, payload?: T): Promise<void> {
  const forEvent = listeners.get(event);
  if (!forEvent) return;
  for (const [id, handler] of [...forEvent]) {
    (handler as EventCallback<T>)({ event, id, payload: payload as T });
  }
}

export async function emitTo<T>(
  _target: unknown,
  event: string,
  payload?: T,
): Promise<void> {
  await emit(event, payload);
}

export const TauriEvent = {
  WINDOW_CLOSE_REQUESTED: "tauri://close-requested",
  DRAG_DROP: "tauri://drag-drop",
  DRAG_ENTER: "tauri://drag-enter",
  DRAG_LEAVE: "tauri://drag-leave",
  DRAG_OVER: "tauri://drag-over",
} as const;
