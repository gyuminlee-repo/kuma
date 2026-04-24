import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function basename(filepath: string): string {
  return filepath.split(/[\\/]/).pop() ?? filepath;
}

export function formatError(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}
