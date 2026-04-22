import { open } from "@tauri-apps/plugin-dialog";

export async function browseFile(
  filters: { name: string; extensions: string[] }[],
  onSelect: (path: string) => Promise<void> | void,
) {
  const path = await open({ filters, multiple: false });
  if (typeof path === "string") {
    await onSelect(path);
  }
}
