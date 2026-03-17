/**
 * MOCK_MODE stub for @tauri-apps/plugin-dialog
 * No-op implementation used by Playwright capture script.
 */

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
 * open() stub — always returns null (no file selected).
 */
export async function open(
  _options?: OpenDialogOptions,
): Promise<string | string[] | null> {
  return null;
}

/**
 * save() stub — always returns null (dialog cancelled).
 */
export async function save(_options?: SaveDialogOptions): Promise<string | null> {
  return null;
}

export async function message(
  _message: string,
  _options?: { title?: string; kind?: "info" | "warning" | "error" },
): Promise<void> {
  // no-op
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
