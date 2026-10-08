/**
 * Type shim for @tauri-apps/plugin-notification.
 * Generated until the package is installed via `pnpm install` (Windows native terminal required).
 * Replace with the actual package once installed.
 */
declare module "@tauri-apps/plugin-notification" {
  export type Permission = "granted" | "denied" | "default";

  export interface Options {
    title: string;
    body?: string;
    icon?: string;
  }

  export function isPermissionGranted(): Promise<boolean>;
  export function requestPermission(): Promise<Permission>;
  export function sendNotification(notification: Options | string): void;
}
