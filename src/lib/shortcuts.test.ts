import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { SHORTCUTS } from "./shortcuts";

describe("keyboard shortcut docs", () => {
  it("keeps shortcut references aligned with the registry", () => {
    const docs = [
      readFileSync(join(process.cwd(), "docs/en/keyboard-shortcuts.md"), "utf8"),
      readFileSync(join(process.cwd(), "docs/ko/keyboard-shortcuts.md"), "utf8"),
      readFileSync(join(process.cwd(), "docs/reference/keybindings.md"), "utf8"),
    ].join("\n");

    for (const shortcut of SHORTCUTS) {
      expect(docs).toContain(shortcut.keys);
      expect(docs).toContain(shortcut.action);
    }
  });

  it("keeps the frontend shortcut standard aligned with the active run key", () => {
    const standard = readFileSync(
      join(process.cwd(), "docs/standards/common-frontend-standards.md"),
      "utf8",
    );

    expect(standard).toContain("Ctrl/Cmd+D");
    expect(standard).not.toContain("Ctrl/Cmd+R, Ctrl/Cmd+S");
  });
});
