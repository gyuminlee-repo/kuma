import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { SHORTCUTS } from "./shortcuts";

describe("keyboard shortcut docs", () => {
  it("keeps the English shortcut reference aligned with the registry", () => {
    const doc = readFileSync(
      join(process.cwd(), "docs/en/keyboard-shortcuts.md"),
      "utf8",
    );

    for (const shortcut of SHORTCUTS) {
      expect(doc).toContain(shortcut.keys);
      expect(doc).toContain(shortcut.action);
    }
  });
});
