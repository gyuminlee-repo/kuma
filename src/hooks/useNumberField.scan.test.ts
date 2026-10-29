/**
 * No `type="number"` input commits a draft on blur by hand.
 *
 * Hand-written blur commits over a local string draft were how the KURO
 * fields came to show text the store did not hold: each pushed the store value
 * back only when the store changed, so a commit the setter normalized to the
 * value it already held left the rejected text on screen. `useNumberField`
 * drops the draft on every commit; a field that writes its own `onBlur` has
 * left that path. This repo has no ESLint configuration, so a source scan is
 * the enforcement available (the same reasoning as `src/lib/ipc.bypass.test.ts`).
 *
 * A number input with no `onBlur` is outside the rule: it is either bound to
 * the store directly (`value={store}`, React restores the stored value after
 * each change) or a draft read by a separate button (add-a-domain, add-a-site).
 */

import { readdirSync, readFileSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = resolve(__dirname, "..");

function sourceFiles(dir: string, out: string[] = []): string[] {
  // `withFileTypes` avoids a stat per entry, which is slow on a drvfs mount.
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      sourceFiles(path, out);
    } else if (entry.name.endsWith(".tsx") && !/\.test\.tsx$/.test(entry.name)) {
      out.push(path);
    }
  }
  return out;
}

/** Opening JSX tags of `input`/`Input` elements, braces balanced. */
function openingTags(source: string): string[] {
  const tags: string[] = [];
  const start = /<(input|Input)\b/g;
  let match: RegExpExecArray | null;
  while ((match = start.exec(source)) !== null) {
    let depth = 0;
    let quote: string | null = null;
    let end = match.index + match[0].length;
    for (; end < source.length; end++) {
      const ch = source[end];
      if (quote) {
        if (ch === quote) quote = null;
        continue;
      }
      if (ch === '"' || ch === "'" || ch === "`") quote = ch;
      else if (ch === "{") depth++;
      else if (ch === "}") depth--;
      else if (ch === ">" && depth === 0) break;
    }
    tags.push(source.slice(match.index, end + 1));
  }
  return tags;
}

/** A number input that writes its own blur handler. */
function handWrittenBlurCommits(source: string): string[] {
  return openingTags(source).filter(
    (tag) => /\btype\s*=\s*(?:"number"|\{\s*"number"\s*\})/.test(tag) && /\bonBlur\s*=/.test(tag),
  );
}

describe("number inputs commit through useNumberField", () => {
  it("flags the hand-written pattern and passes the hook spread", () => {
    const old = `<input type="number" value={str} onChange={(e) => setStr(e.target.value)}
      onBlur={() => { const n = parseFloat(str); commit(n); }} />`;
    const viaHook = `<input type="number" className={cls} {...field.inputProps} />`;
    const notNumber = `<input type="text" onBlur={save} />`;
    expect(handWrittenBlurCommits(old)).toHaveLength(1);
    expect(handWrittenBlurCommits(viaHook)).toEqual([]);
    expect(handWrittenBlurCommits(notNumber)).toEqual([]);
  });

  it("finds none in src", () => {
    const offenders = sourceFiles(SRC).flatMap((file) =>
      handWrittenBlurCommits(readFileSync(file, "utf8")).map(
        (tag) => `${relative(SRC, file)}: ${tag.replace(/\s+/g, " ").slice(0, 120)}`,
      ),
    );
    expect(offenders).toEqual([]);
  });
});
