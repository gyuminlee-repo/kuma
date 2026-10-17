import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ReRunManifestDialog } from "./ReRunManifestDialog";
import type { RunManifest } from "@/lib/runManifest";

vi.mock("@/lib/reRun", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/reRun")>()),
  reRunFromManifest: vi.fn(),
}));

const manifest: RunManifest = {
  schema_version: "1.0",
  method: "design_sdm_primers",
  kuma_version: "0.13.3",
  python_version: "3.12.0",
  platform: "linux",
  started_at: "2026-06-10T00:00:00Z",
  finished_at: "2026-06-10T00:00:01Z",
  duration_seconds: 1,
  inputs: {
    sequence: {
      path: "/tmp/sequence.gb",
      sha256: "abc123",
      size_bytes: 12,
    },
  },
  params: { mutation: "A1V" },
  seed: null,
};

function renderDialog(
  verifyResult:
    | { missing: string[]; mismatched: string[]; unverifiable: string[] }
    | null,
) {
  return render(
    <ReRunManifestDialog
      open
      manifest={manifest}
      verifyResult={verifyResult}
      onClose={vi.fn()}
      onStatusMessage={vi.fn()}
    />,
  );
}

describe("ReRunManifestDialog input verification warning", () => {
  it("does not render a warning when verification is pending or clean", () => {
    const { rerender } = renderDialog(null);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    rerender(
      <ReRunManifestDialog
        open
        manifest={manifest}
        verifyResult={{ missing: [], mismatched: [], unverifiable: [] }}
        onClose={vi.fn()}
        onStatusMessage={vi.fn()}
      />,
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("renders missing and mismatched input details", () => {
    renderDialog({ missing: ["sequence"], mismatched: ["activity"], unverifiable: [] });

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Input files have changed.");
    expect(alert).toHaveTextContent("Missing paths: sequence");
    expect(alert).toHaveTextContent("Hash mismatch: activity");
  });
  it("names an input whose digest was never recorded, apart from a mismatch", () => {
    renderDialog({ missing: [], mismatched: [], unverifiable: ["layout"] });

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent(
      "Recorded without a digest, so the file cannot be checked against the run: layout",
    );
    // The two states are separate claims: the file is not being called changed.
    expect(alert).not.toHaveTextContent("Hash mismatch");
  });
});

// A replay applies only some of what a manifest records and runs the rest with
// the open session's values. It used to do that silently, so a partial replay
// passed for the recorded run. The dialog now names what it will not apply and
// still lets the operator run it.
describe("ReRunManifestDialog recorded conditions the replay does not apply", () => {
  function show(params: Record<string, unknown>, seed: number | null) {
    return render(
      <ReRunManifestDialog
        open
        manifest={{ ...manifest, params, seed }}
        verifyResult={null}
        onClose={vi.fn()}
        onStatusMessage={vi.fn()}
      />,
    );
  }

  it("names the recorded params and seed it leaves to the session", () => {
    show({ mutation_text: "A1V", tm_fwd_target: 68 }, 7);
    const notice = screen.getByRole("status");
    expect(notice).toHaveTextContent("tm_fwd_target, seed");
    expect(notice).not.toHaveTextContent("mutation_text");
    expect(screen.getByRole("button", { name: "Re-run" })).toBeEnabled();
  });

  it("says nothing when everything recorded is applied", () => {
    show({ mutation_text: "A1V" }, null);
    expect(screen.queryByRole("status")).toBeNull();
  });
});
