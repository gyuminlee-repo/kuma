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

export async function writeFile(
  _path: string,
  _data: Uint8Array,
  _options?: unknown,
): Promise<void> {
}

export async function rename(_oldPath: string, _newPath: string): Promise<void> {
}

// Added when the plugin-fs alias was switched on for the capture run: these
// four are imported by the app and their absence broke the dev bundle before
// a single screen rendered.

export async function stat(_path: string, _options?: unknown): Promise<{
  isFile: boolean;
  isDirectory: boolean;
  size: number;
  mtime: Date | null;
}> {
  return { isFile: false, isDirectory: false, size: 0, mtime: null };
}

export async function remove(_path: string, _options?: unknown): Promise<void> {
}

export async function readDir(
  _path: string,
  _options?: unknown,
): Promise<Array<{ name: string; isFile: boolean; isDirectory: boolean }>> {
  return [];
}

export async function readFile(_path: string): Promise<Uint8Array> {
  throw new Error("MOCK_MODE: readFile not implemented");
}
