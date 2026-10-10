import { describe, expect, it } from "vitest";
import { getRpcResultValidator } from "./validators";
import { domainJobFixture, domainResultFixture, domainRuntimeFixture } from "@/test-utils/domainAnnotationFixture";
const validate = getRpcResultValidator("import_domain_annotation_file");
describe("domain annotation boundary validators", () => {
  it("accepts bounded discontinuous reference segments", () => expect(validate(domainResultFixture())).toBe(true));
  it.each([
    { coverage: 0.7 }, { confidence: NaN }, { assigned_residues: 4 }, { unassigned_positions: [3] },
    { unassigned_positions: [3, 4, 5] }, { coordinate_frame: "source" }, { total_residues: 10001 },
    { domains: [{ segments: [{ start: 1, end: 4 }], positions: [1, 2, 4] }] },
    { domains: [{ segments: [{ start: 1, end: 2 }, { start: 2, end: 4 }], positions: [1, 2, 4] }] },
    { domains: [domainResultFixture().domains[0], domainResultFixture().domains[0]] },
    { provenance: "managed", job_id: null },
  ])("rejects malformed or inconsistent result %j", (patch) => expect(validate({ ...domainResultFixture(), ...patch })).toBe(false));
  it("does not represent a licensing-blocked runtime as installable", () => {
    expect(getRpcResultValidator("domain_runtime_status")(domainRuntimeFixture({ state: "licensing_blocked", install_available: true }))).toBe(false);
  });
  it("validates exact-attempt recovery and rejects contradictory terminal snapshots", () => {
    const attempt = getRpcResultValidator("get_domain_annotation_attempt");
    expect(attempt({ attempt_id: "e".repeat(32), state: "job", message: "Stopping", job: domainJobFixture("cancelling") })).toBe(true);
    expect(attempt({ attempt_id: "e".repeat(32), state: "cancelled", message: "No active process", job: null })).toBe(true);
    expect(attempt({ attempt_id: "latest", state: "cancelled", message: "No active process", job: null })).toBe(false);
    expect(attempt({ attempt_id: "e".repeat(32), state: "cancelled", message: "Not stopped", job: domainJobFixture("running") })).toBe(false);
  });

});
