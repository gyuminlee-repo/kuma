/**
 * §21 Multi-workspace — compare two workspace snapshots.
 *
 * Works with any JSON-serialisable snapshot shape (kuro WorkspaceV3,
 * mame WorkspaceSnapshot, or future formats). Uses a generic recursive
 * diff to avoid tight coupling to a specific schema version.
 *
 * No external dependencies — pure TypeScript, no `any`.
 */

export interface WorkspaceDiff {
  /** Dot-notation path of the changed field (e.g. "inputs.mutationText"). */
  path: string;
  left: unknown;
  right: unknown;
}

export interface WorkspaceComparison {
  differences: WorkspaceDiff[];
}

type JsonObject = Record<string, unknown>;

function isJsonObject(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Recursively collect leaf-level differences between two JSON-compatible
 * values. Arrays are compared element-by-element at the same indices.
 */
function collectDiffs(
  left: unknown,
  right: unknown,
  path: string,
  out: WorkspaceDiff[],
): void {
  // Both are plain objects → recurse into keys union
  if (isJsonObject(left) && isJsonObject(right)) {
    const keys = new Set([...Object.keys(left), ...Object.keys(right)]);
    for (const key of keys) {
      collectDiffs(left[key], right[key], path ? `${path}.${key}` : key, out);
    }
    return;
  }

  // Both are arrays → compare element by element
  if (Array.isArray(left) && Array.isArray(right)) {
    const len = Math.max(left.length, right.length);
    for (let i = 0; i < len; i++) {
      collectDiffs(left[i], right[i], `${path}[${i}]`, out);
    }
    return;
  }

  // Leaf comparison — use JSON stringify for stable equality on nested values
  const leftStr = JSON.stringify(left);
  const rightStr = JSON.stringify(right);
  if (leftStr !== rightStr) {
    out.push({ path, left, right });
  }
}

/**
 * Compare two workspace snapshots and return the list of field differences.
 *
 * The inputs are typed as `unknown` rather than a specific snapshot interface
 * so the function remains usable across kuro (WorkspaceV3) and mame
 * (WorkspaceSnapshot v1) without requiring a shared base type.
 *
 * @param a - First workspace snapshot (parsed JSON object).
 * @param b - Second workspace snapshot (parsed JSON object).
 * @returns `WorkspaceComparison` with a `differences` array. An empty array
 *   means the two snapshots are identical.
 */
export function compareWorkspaces(a: unknown, b: unknown): WorkspaceComparison {
  const differences: WorkspaceDiff[] = [];
  collectDiffs(a, b, "", differences);
  return { differences };
}
