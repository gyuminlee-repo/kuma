import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

// twMerge가 커스텀 fontSize 토큰을 색상 클래스(text-*)와 같은 그룹으로 오인해
// `text-body`/`text-caption` 등이 `text-primary-foreground` 같은 색을 지우는 문제를
// 막기 위해 fontSize 그룹에 명시 등록한다.
const twMergeWithTokens = extendTailwindMerge({
  extend: {
    classGroups: {
      "font-size": [
        { text: ["title", "body", "caption", "plate", "plate-tiny"] },
      ],
    },
  },
});

export function cn(...inputs: ClassValue[]) {
  return twMergeWithTokens(clsx(inputs));
}

export function basename(filepath: string): string {
  return filepath.split(/[\\/]/).pop() ?? filepath;
}

export function formatError(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}
