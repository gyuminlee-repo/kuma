/** MOCK_MODE shims for screenshot/tutorial automation. */

export interface OpenDialogOptions {
  multiple?: boolean;
  filters?: Array<{ name: string; extensions: string[] }>;
  defaultPath?: string;
  directory?: boolean;
  recursive?: boolean;
  title?: string;
}

export interface SaveDialogOptions {
  filters?: Array<{ name: string; extensions: string[] }>;
  defaultPath?: string;
  title?: string;
}

/**
 * Paths the next picker calls should answer with, seeded by the capture driver.
 *
 * MAME input rows are `FileField`, whose text input is unconditionally
 * readOnly, so the Browse button is the only way a path reaches the store. The
 * capture run therefore queues the real lab paths here and clicks Browse,
 * which keeps the app on its own code path: the store is filled by the same
 * handler an operator triggers, not by injection.
 *
 * An empty queue answers null, which is a cancelled dialog and the previous
 * behaviour for every other MOCK_MODE consumer.
 */
declare global {
  interface Window {
    __mockDialogQueue?: {
      open?: Array<string | string[] | null>;
      save?: Array<string | null>;
    };
  }
}

export async function open(
  _options?: OpenDialogOptions,
): Promise<string | string[] | null> {
  const queue = globalThis.window?.__mockDialogQueue?.open;
  if (queue && queue.length > 0) {
    return queue.shift() ?? null;
  }
  return null;
}

export async function save(_options?: SaveDialogOptions): Promise<string | null> {
  const queue = globalThis.window?.__mockDialogQueue?.save;
  if (queue && queue.length > 0) {
    return queue.shift() ?? null;
  }
  return null;
}

export async function message(
  _message: string,
  _options?: { title?: string; kind?: "info" | "warning" | "error" },
): Promise<void> {
}

export async function ask(
  _message: string,
  _options?: { title?: string; kind?: "info" | "warning" | "error" },
): Promise<boolean> {
  return false;
}

export async function confirm(
  _message: string,
  _options?: { title?: string; kind?: "info" | "warning" | "error" },
): Promise<boolean> {
  return false;
}
