/**
 * ReferenceResolutionNotice, the run analysed a slice, and said so.
 *
 * Three store states, three outcomes, and the two silent ones are silent for
 * different reasons: null is "no run reported a resolution", `extracted: false`
 * is a run that measured and cut nothing. They are kept apart in the store even
 * though both render nothing, so a later reader is never left guessing which
 * one it is looking at.
 *
 * On wording vs numbers. The prose lives in the locale files and is edited
 * independently, so nothing here pins a sentence. The NUMBERS are pinned,
 * because they are the whole content of the notice and nothing else in the
 * repo checks them: `i18n-lint` proves a key exists and `i18n-parity` compares
 * key SETS, so a placeholder renamed on one side of `t(...)` and not the other
 * ships a literal `{{spanStart}}` to the operator with every gate green. Two
 * copy-edit-proof guards below cover that class (no `{{` survives, no raw
 * `mame.qc.` key echoes back), and the fixture is built so the arithmetic
 * cannot pass by coincidence.
 */
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/ipc-mame", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

import type { ReferenceResolution } from "@/store/mame/slice-interfaces";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { ReferenceResolutionNotice } from "./ReferenceResolutionNotice";

/**
 * A 1620 bp construct cut down to the amplicon at positions 451-1170.
 *
 * Every number is chosen to discriminate, because a fixture whose candidate
 * answers coincide proves nothing:
 *   720  the closed-interval slice length, `span_end - span_start + 1`
 *   719  what a half-open (off-by-one) count would print, appears nowhere else
 *   599  what `cds_end - cds_start` would print, so reading the length off the
 *        CDS coordinates instead of the span shows up as a missing 720
 * The CDS pair is deliberately NOT 0..720 for that last reason.
 */
const EXTRACTED: ReferenceResolution = {
  path: "/proj/out/demux_filtered/construct.amplicon.fa",
  extracted: true,
  span_start: 451,
  span_end: 1170,
  original_length: 1620,
  cds_start: 61,
  cds_end: 660,
  note: "Amplicon extracted from reference positions 451-1170 (720 bp).",
};

describe("ReferenceResolutionNotice", () => {
  beforeEach(() => {
    useMameAppStore.setState({ referenceResolution: null });
  });

  it("renders nothing before a run has reported a resolution", () => {
    const { container } = render(<ReferenceResolutionNotice />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when the run used the whole file unmodified", () => {
    // Measured, not missing: the run looked for the primer tails and did not
    // cut. There is no substitution to report, so the screen stays quiet -- but
    // the store still holds the resolution rather than a null.
    useMameAppStore.setState({
      referenceResolution: {
        path: "/proj/ref/construct.fa",
        extracted: false,
        span_start: null,
        span_end: null,
        original_length: 1620,
        cds_start: 0,
        cds_end: 0,
        note: "Amplicon extraction skipped because the primer tail sequence was not found in the reference.",
      },
    });

    const { container } = render(<ReferenceResolutionNotice />);
    expect(container).toBeEmptyDOMElement();
    // The distinction the store exists to keep: silent on screen, but NOT the
    // same value as "no run reported one". Collapsing these to a single null
    // would make a measured whole-file run indistinguishable from a snapshot
    // written before the field existed.
    expect(useMameAppStore.getState().referenceResolution).not.toBeNull();
  });

  it("renders nothing when a resolution claims extraction but carries no span", () => {
    // Defensive, and reachable only if the sidecar contract shifts: `extracted`
    // is set on the one branch that has a span. Naming the region is the whole
    // point of the notice, so with no region there is nothing to say -- and a
    // half-rendered "positions null-null" would be worse than silence.
    useMameAppStore.setState({
      referenceResolution: { ...EXTRACTED, span_start: null, span_end: null },
    });

    const { container } = render(<ReferenceResolutionNotice />);
    expect(container).toBeEmptyDOMElement();
  });

  it("states the region the run actually analysed", () => {
    useMameAppStore.setState({ referenceResolution: EXTRACTED });

    render(<ReferenceResolutionNotice />);

    const notice = screen.getByTestId("reference-resolution-notice");
    // A statement about a finished run, not a failure: `status`, never `alert`.
    expect(notice).toHaveAttribute("role", "status");

    const text = notice.textContent ?? "";
    // i18next echoes the key back when it cannot resolve one, so a renamed or
    // dropped key surfaces here rather than as a blank line on screen.
    expect(text).not.toContain("mame.qc.");
    // An interpolation name that disagrees with the locale placeholder leaves
    // the placeholder in the output verbatim. Nothing else in the repo checks
    // this: i18n-lint checks key existence, parity checks key sets.
    expect(text).not.toContain("{{");

    // The numbers come from the store field, not from a hardcoded string.
    expect(notice).toHaveTextContent("1620");
    expect(notice).toHaveTextContent("451");
    expect(notice).toHaveTextContent("1170");
    // Closed interval: both bounds are inclusive 1-based positions, as the
    // handler sends them (`span.start + 1` .. `span.end`).
    expect(notice).toHaveTextContent("720");
    expect(notice).not.toHaveTextContent("719");
  });
});
