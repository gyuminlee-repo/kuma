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

export async function open(
  _options?: OpenDialogOptions,
): Promise<string | string[] | null> {
  return null;
}

export async function save(_options?: SaveDialogOptions): Promise<string | null> {
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
