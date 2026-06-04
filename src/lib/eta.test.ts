import { describe, it, expect, vi } from "vitest";
import { computeEtaFromElapsed } from "./eta";

const t = (key: string, vars?: Record<string, number>) => {
  if (key === "mame.progressModal.eta.calculating") return "Calculating…";
  if (key === "mame.progressModal.eta.lessThanMinute") return "1분 미만";
  if (key === "mame.progressModal.eta.remaining") return `약 ${vars?.min}분 ${vars?.sec}초 남음`;
  return key;
};

describe("computeEtaFromElapsed", () => {
  it("returns 'Calculating…' when progress < 5%", () => {
    vi.setSystemTime(100_000);
    expect(computeEtaFromElapsed(0, 99_000, t)).toBe("Calculating…");
    expect(computeEtaFromElapsed(4.9, 99_000, t)).toBe("Calculating…");
  });
  it("returns '1분 미만' when remaining < 60s", () => {
    vi.setSystemTime(100_000);
    expect(computeEtaFromElapsed(50, 50_000, t)).toBe("1분 미만");
  });
  it("returns 'X분 Y초 남음' for >= 60s remaining", () => {
    vi.setSystemTime(100_000);
    expect(computeEtaFromElapsed(25, 70_000, t)).toBe("약 1분 30초 남음");
  });
});
