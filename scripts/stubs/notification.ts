/** Stub for @tauri-apps/plugin-notification in vitest environment. */

export type Permission = "granted" | "denied" | "default";

export async function isPermissionGranted(): Promise<boolean> {
  return false;
}

export async function requestPermission(): Promise<Permission> {
  return "denied";
}

export function sendNotification(_options: { title: string; body?: string }): void {
  // no-op in test environment
}
