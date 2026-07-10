export const UPDATE_CHECK_EVENT = "kuma:check-for-updates";
export const RELEASES_URL = "https://github.com/gyuminlee-repo/kuma/releases";

const LATEST_RELEASE_API =
  "https://api.github.com/repos/gyuminlee-repo/kuma/releases/latest";

interface GitHubReleaseResponse {
  tag_name?: unknown;
}

export interface UpdateCheckResult {
  currentVersion: string;
  latestVersion: string;
  releaseUrl: string;
  updateAvailable: boolean;
}

interface ParsedVersion {
  core: number[];
  prerelease: string[];
}

function parseVersion(value: string): ParsedVersion | null {
  const normalized = value.trim().replace(/^v/i, "").split("+", 1)[0];
  const [corePart, prereleasePart] = normalized.split("-", 2);
  const coreSegments = corePart.split(".");
  if (
    coreSegments.length < 2 ||
    coreSegments.length > 4 ||
    coreSegments.some((segment) => !/^\d+$/.test(segment))
  ) {
    return null;
  }

  return {
    core: coreSegments.map(Number),
    prerelease: prereleasePart ? prereleasePart.split(".") : [],
  };
}

function comparePrerelease(left: string[], right: string[]): number {
  if (left.length === 0 && right.length === 0) return 0;
  if (left.length === 0) return 1;
  if (right.length === 0) return -1;

  const length = Math.max(left.length, right.length);
  for (let index = 0; index < length; index += 1) {
    const leftPart = left[index];
    const rightPart = right[index];
    if (leftPart === undefined) return -1;
    if (rightPart === undefined) return 1;
    if (leftPart === rightPart) continue;

    const leftNumeric = /^\d+$/.test(leftPart);
    const rightNumeric = /^\d+$/.test(rightPart);
    if (leftNumeric && rightNumeric) {
      return Number(leftPart) > Number(rightPart) ? 1 : -1;
    }
    if (leftNumeric !== rightNumeric) return leftNumeric ? -1 : 1;
    return leftPart > rightPart ? 1 : -1;
  }
  return 0;
}

export function compareVersions(left: string, right: string): number {
  const parsedLeft = parseVersion(left);
  const parsedRight = parseVersion(right);
  if (!parsedLeft || !parsedRight) {
    throw new Error("Invalid release version returned by GitHub.");
  }

  const length = Math.max(parsedLeft.core.length, parsedRight.core.length);
  for (let index = 0; index < length; index += 1) {
    const leftPart = parsedLeft.core[index] ?? 0;
    const rightPart = parsedRight.core[index] ?? 0;
    if (leftPart !== rightPart) return leftPart > rightPart ? 1 : -1;
  }

  return comparePrerelease(parsedLeft.prerelease, parsedRight.prerelease);
}

export async function checkForLatestRelease(
  currentVersion: string,
  fetchImpl: typeof fetch = fetch,
): Promise<UpdateCheckResult> {
  const response = await fetchImpl(LATEST_RELEASE_API, {
    headers: {
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
    },
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`GitHub returned HTTP ${response.status}.`);
  }

  const payload = (await response.json()) as GitHubReleaseResponse;
  if (typeof payload.tag_name !== "string") {
    throw new Error("GitHub release response has no valid tag.");
  }

  const latestVersion = payload.tag_name.replace(/^v/i, "");
  const updateAvailable = compareVersions(latestVersion, currentVersion) > 0;
  return {
    currentVersion,
    latestVersion,
    releaseUrl: `${RELEASES_URL}/tag/v${latestVersion}`,
    updateAvailable,
  };
}
