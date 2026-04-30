/** MOCK_MODE shims for fs access in Vitest and screenshot automation. */

export async function exists(_path: string): Promise<boolean> {
  return false;
}

export async function mkdir(_path: string, _options?: unknown): Promise<void> {
}

export async function readTextFile(_path: string): Promise<string> {
  throw new Error("MOCK_MODE: readTextFile not implemented");
}

export async function writeTextFile(
  _path: string,
  _contents: string,
  _options?: unknown,
): Promise<void> {
}
