import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ReRunManifestDialog } from "./ReRunManifestDialog";
import type { RunManifest } from "@/lib/runManifest";

vi.mock("@/lib/reRun", () => ({
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
