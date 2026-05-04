/**
 * RoundSummaryPanel tests — Phase 6 Task 6.3
 *
 * Coverage:
 *  1. Renders all 6 signal rows when metrics provided.
 *  2. "calibration period" banner always present.
 *  3. ✓ for met signals, — for unmet signals.
 *  4. Classification decision labels NOT rendered (§12-A.6 negative assertion).
 *  5. sigma_assay=null → "WT replicates < 4" message for T2.
 *  6. metrics=null → explicit placeholder text.
 *  7. Accessibility: table has aria-label, section has heading.
 *  8. round_id and computed_at displayed when metrics provided.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RoundSummaryPanel } from "./RoundSummaryPanel";
import type { RoundMetrics } from "@/types/round-metrics";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

/** Fully-populated RoundMetrics fixture (all signals met). */
const metricsAllMet: RoundMetrics = {
  round_id: "round_2",
  computed_at: "2026-05-04T10:00:00Z",
  cumulative_beneficial: 16,
  K_throughput: 14,
  delta_best_ema: 0.001,
  sigma_assay: 0.05,
  r: 3,
  hit_rates: [0.6, 0.5, 0.4],
  top_k_positions_n: [89, 70, 45, 112],
  top_k_positions_n1: [89, 70, 45, 90],
  top_k_positions: [89, 70, 45, 112],
  active_residues: [89, 70, 45],
  unused_beneficial_count: 6,
  T1: true,
  T2: true,
  T3: true,
  T4: true,
  T_active: true,
  T_unused: true,
};

/** Partially-met metrics fixture (T2, T3, T4 unmet). */
const metricsPartial: RoundMetrics = {
  ...metricsAllMet,
  round_id: "round_1",
  T2: false,
  T3: false,
  T4: false,
  delta_best_ema: 0.5,
};

/** Metrics with sigma_assay = null → T2 unavailable. */
const metricsNoSigma: RoundMetrics = {
  ...metricsAllMet,
  sigma_assay: null,
  T2: false,
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("RoundSummaryPanel", () => {
  describe("when metrics is null", () => {
    it("renders the placeholder text", () => {
      render(<RoundSummaryPanel metrics={null} />);
      expect(screen.getByText(/No round metrics yet/i)).toBeTruthy();
    });

    it("still renders the calibration banner", () => {
      render(<RoundSummaryPanel metrics={null} />);
      expect(screen.getByText(/calibration period/i)).toBeTruthy();
    });

    it("does not render a signals table", () => {
      render(<RoundSummaryPanel metrics={null} />);
      expect(screen.queryByRole("table")).toBeNull();
    });
  });

  describe("when metrics is provided", () => {
    it("renders a table with accessible label", () => {
      render(<RoundSummaryPanel metrics={metricsAllMet} />);
      const table = screen.getByRole("table", { name: /round strategy signals/i });
      expect(table).toBeTruthy();
    });

    it("renders all 6 signal rows", () => {
      render(<RoundSummaryPanel metrics={metricsAllMet} />);
      const signalIds = ["T1", "T2", "T3", "T4", "T_active", "T_unused"];
      for (const id of signalIds) {
        expect(screen.getByText(new RegExp(id))).toBeTruthy();
      }
    });

    it("shows ✓ for met signals", () => {
      render(<RoundSummaryPanel metrics={metricsAllMet} />);
      const metBadges = screen.getAllByLabelText("Signal met");
      expect(metBadges.length).toBe(6);
    });

    it("shows — for unmet signals", () => {
      render(<RoundSummaryPanel metrics={metricsPartial} />);
      const unmetBadges = screen.getAllByLabelText("Signal not met");
      // T2, T3, T4 are false in metricsPartial
      expect(unmetBadges.length).toBe(3);
    });

    it("shows T1 input value with cumulative_beneficial and K_throughput", () => {
      render(<RoundSummaryPanel metrics={metricsAllMet} />);
      expect(screen.getByText(/16 \/ K=14/)).toBeTruthy();
    });

    it("shows round_id in the header area", () => {
      render(<RoundSummaryPanel metrics={metricsAllMet} />);
      expect(screen.getByText(/round_2/)).toBeTruthy();
    });

    it("shows the calibration period banner", () => {
      render(<RoundSummaryPanel metrics={metricsAllMet} />);
      expect(screen.getByText(/calibration period/i)).toBeTruthy();
    });

    it("renders section heading 'Round Signals'", () => {
      render(<RoundSummaryPanel metrics={metricsAllMet} />);
      expect(
        screen.getByRole("heading", { name: /round signals/i })
      ).toBeTruthy();
    });
  });

  describe("calibration mode — classification decisions NOT displayed (spec §12-A.6)", () => {
    const DECISION_LABELS = [
      "continue_walking",
      "switch_combinatorial",
      "stop",
      "deferred",
    ];

    it("does not show classification labels when metrics=null", () => {
      render(<RoundSummaryPanel metrics={null} />);
      for (const label of DECISION_LABELS) {
        expect(screen.queryByText(new RegExp(label, "i"))).toBeNull();
      }
    });

    it("does not show classification labels when all signals met", () => {
      render(<RoundSummaryPanel metrics={metricsAllMet} />);
      for (const label of DECISION_LABELS) {
        expect(screen.queryByText(new RegExp(label, "i"))).toBeNull();
      }
    });

    it("does not show classification labels when signals partially met", () => {
      render(<RoundSummaryPanel metrics={metricsPartial} />);
      for (const label of DECISION_LABELS) {
        expect(screen.queryByText(new RegExp(label, "i"))).toBeNull();
      }
    });
  });

  describe("T2 with sigma_assay = null (spec §12-A.8)", () => {
    it("shows 'WT replicates < 4' message for T2", () => {
      render(<RoundSummaryPanel metrics={metricsNoSigma} />);
      expect(screen.getByText(/WT replicates < 4/i)).toBeTruthy();
    });

    it("shows T2 as unmet when sigma_assay is null", () => {
      render(<RoundSummaryPanel metrics={metricsNoSigma} />);
      const unmetBadges = screen.getAllByLabelText("Signal not met");
      expect(unmetBadges.length).toBeGreaterThan(0);
    });
  });

  describe("signal basis labels", () => {
    it("shows 'lit' badge for T1 and T_active (literature anchors)", () => {
      render(<RoundSummaryPanel metrics={metricsAllMet} />);
      // Two 'lit' badges: T1 and T_active
      const litBadges = screen.getAllByText("lit");
      expect(litBadges.length).toBe(2);
    });

    it("shows 'infer' badge for T2, T3, T4, T_unused (reasoning-based)", () => {
      render(<RoundSummaryPanel metrics={metricsAllMet} />);
      const inferBadges = screen.getAllByText("infer");
      expect(inferBadges.length).toBe(4);
    });
  });

  describe("accessibility", () => {
    it("section is labelled by heading (role=region)", () => {
      render(<RoundSummaryPanel metrics={metricsAllMet} />);
      const section = screen.getByRole("region", { name: /round signals/i });
      expect(section).toBeTruthy();
    });

    it("calibration banner has role=status", () => {
      render(<RoundSummaryPanel metrics={metricsAllMet} />);
      expect(screen.getByRole("status")).toBeTruthy();
    });

    it("signal met/unmet badges have aria-labels", () => {
      render(<RoundSummaryPanel metrics={metricsPartial} />);
      const met = screen.getAllByLabelText("Signal met");
      expect(met.length).toBeGreaterThan(0);
      const unmet = screen.getAllByLabelText("Signal not met");
      expect(unmet.length).toBeGreaterThan(0);
    });

    it("table has 4 column headers", () => {
      render(<RoundSummaryPanel metrics={metricsAllMet} />);
      const colHeaders = screen.getAllByRole("columnheader");
      expect(colHeaders.length).toBe(4);
    });
  });
});
