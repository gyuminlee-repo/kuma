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

function renderDialog(verifyResult: { missing: string[]; mismatched: string[] } | null) {
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
        verifyResult={{ missing: [], mismatched: [] }}
        onClose={vi.fn()}
        onStatusMessage={vi.fn()}
      />,
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("renders missing and mismatched input details", () => {
    renderDialog({ missing: ["sequence"], mismatched: ["activity"] });

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Input files have changed.");
    expect(alert).toHaveTextContent("Missing paths: sequence");
    expect(alert).toHaveTextContent("Hash mismatch: activity");
  });
});
