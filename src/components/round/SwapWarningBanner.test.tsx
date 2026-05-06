/**
 * SwapWarningBanner & ReplicateMergeStats 단위 테스트
 *
 * 대상:
 *  - SwapWarningBanner: severity 배지 카운트, error 시 alert 렌더, 경고만 있을 때 alert 없음
 *  - ReplicateMergeStats: 4개 카운트 표시, mismatched > 0 시 amber accent + tooltip
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SwapWarningBanner, ReplicateMergeStats } from "./RoundSummaryPanel";
import type { SwapWarning, MergeReplicatesStats } from "@/types/mame/activity";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const warningOnly: SwapWarning[] = [
  {
    severity: "warning",
    code: "value_collision",
    variants: ["A45V", "T89S"],
    wells: ["A01", "B02"],
    values: [1.2, 1.2],
    message: "동일 활성값이 다른 변이에서 감지되었습니다.",
  },
];

const errorAndWarning: SwapWarning[] = [
  {
    severity: "error",
    code: "label_swap_cycle",
    variants: ["G12D", "R34K"],
    wells: ["C03", "D04"],
    values: [2.5, 2.5],
    message: "라벨 교체 사이클이 감지되었습니다.",
  },
  {
    severity: "warning",
    code: "layout_orphan",
    variants: ["P56L"],
    wells: ["E05"],
    values: [0.8],
    message: "레이아웃 고아 변이입니다.",
  },
];

const twoErrors: SwapWarning[] = [
  {
    severity: "error",
    code: "label_swap_cycle",
    variants: ["G12D"],
    wells: ["C03"],
    values: [2.5],
    message: "첫 번째 에러",
  },
  {
    severity: "error",
    code: "value_collision",
    variants: ["R34K"],
    wells: ["D04"],
    values: [2.5],
    message: "두 번째 에러",
  },
];

const replicateStatsNoMismatch: MergeReplicatesStats = {
  authoritative_count: 34,
  fallback_count: 58,
  merged_count: 92,
  mismatched: [],
};

const replicateStatsWithMismatch: MergeReplicatesStats = {
  authoritative_count: 20,
  fallback_count: 60,
  merged_count: 80,
  mismatched: ["A45V", "G12D"],
};

// ---------------------------------------------------------------------------
// SwapWarningBanner tests
// ---------------------------------------------------------------------------

describe("SwapWarningBanner", () => {
  it("경고 배열이 비어있으면 아무것도 렌더하지 않는다", () => {
    const { container } = render(<SwapWarningBanner warnings={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("warning만 있으면 경고 배지를 표시한다", () => {
    render(<SwapWarningBanner warnings={warningOnly} />);
    expect(screen.getByText("경고 1건")).toBeTruthy();
  });

  it("warning만 있을 때 role=alert이 렌더되지 않는다", () => {
    render(<SwapWarningBanner warnings={warningOnly} />);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("error가 있으면 오류 배지를 표시한다", () => {
    render(<SwapWarningBanner warnings={errorAndWarning} />);
    expect(screen.getByText("오류 1건")).toBeTruthy();
  });

  it("error가 있으면 role=alert이 렌더된다", () => {
    render(<SwapWarningBanner warnings={errorAndWarning} />);
    expect(screen.getByRole("alert")).toBeTruthy();
  });

  it("error와 warning이 함께 있으면 두 배지 모두 표시된다", () => {
    render(<SwapWarningBanner warnings={errorAndWarning} />);
    expect(screen.getByText("오류 1건")).toBeTruthy();
    expect(screen.getByText("경고 1건")).toBeTruthy();
  });

  it("error 2건 시 오류 2건 배지를 표시한다", () => {
    render(<SwapWarningBanner warnings={twoErrors} />);
    expect(screen.getByText("오류 2건")).toBeTruthy();
  });

  it("각 경고 항목의 메시지가 렌더된다", () => {
    render(<SwapWarningBanner warnings={warningOnly} />);
    expect(screen.getByText(/동일 활성값이/)).toBeTruthy();
  });

  it("경고 항목 title에 variants와 wells가 포함된다", () => {
    render(<SwapWarningBanner warnings={warningOnly} />);
    const item = screen.getByText(/동일 활성값이/).closest("li");
    expect(item).not.toBeNull();
    expect(item?.getAttribute("title")).toContain("A45V");
    expect(item?.getAttribute("title")).toContain("A01");
  });

  it("접근성: 경고 목록 영역에 aria-label이 있다", () => {
    render(<SwapWarningBanner warnings={warningOnly} />);
    expect(screen.getByLabelText("경고 상세")).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// ReplicateMergeStats tests
// ---------------------------------------------------------------------------

describe("ReplicateMergeStats", () => {
  it("4개 레이블(재측정, 1차측정, 병합, 불일치)이 표시된다", () => {
    render(<ReplicateMergeStats replicateStats={replicateStatsNoMismatch} />);
    expect(screen.getByText("재측정")).toBeTruthy();
    expect(screen.getByText("1차측정")).toBeTruthy();
    expect(screen.getByText("병합")).toBeTruthy();
    expect(screen.getByText("불일치")).toBeTruthy();
  });

  it("props 값이 하드코딩 없이 그대로 표시된다", () => {
    render(<ReplicateMergeStats replicateStats={replicateStatsNoMismatch} />);
    expect(screen.getByText("34")).toBeTruthy();
    expect(screen.getByText("58")).toBeTruthy();
    expect(screen.getByText("92")).toBeTruthy();
    // mismatched.length = 0
    expect(screen.getByText("0")).toBeTruthy();
  });

  it("mismatched가 비어있으면 amber accent 배지가 없다", () => {
    render(<ReplicateMergeStats replicateStats={replicateStatsNoMismatch} />);
    // '!' 배지는 없어야 함
    expect(screen.queryByText("!")).toBeNull();
  });

  it("mismatched > 0이면 amber accent 배지(!)가 표시된다", () => {
    render(<ReplicateMergeStats replicateStats={replicateStatsWithMismatch} />);
    expect(screen.getByText("!")).toBeTruthy();
  });

  it("mismatched > 0이면 title tooltip에 변이 목록이 포함된다", () => {
    render(<ReplicateMergeStats replicateStats={replicateStatsWithMismatch} />);
    const badge = screen.getByText("!");
    expect(badge.getAttribute("aria-label")).toContain("A45V");
    expect(badge.getAttribute("aria-label")).toContain("G12D");
  });

  it("접근성: 섹션에 aria-label이 있다", () => {
    render(
      <ReplicateMergeStats replicateStats={replicateStatsNoMismatch} />
    );
    expect(screen.getByLabelText("Replicate merge 통계")).toBeTruthy();
  });

  it("다른 수치가 주어지면 그 수치를 표시한다", () => {
    const stats: MergeReplicatesStats = {
      authoritative_count: 5,
      fallback_count: 10,
      merged_count: 15,
      mismatched: [],
    };
    render(<ReplicateMergeStats replicateStats={stats} />);
    expect(screen.getByText("5")).toBeTruthy();
    expect(screen.getByText("10")).toBeTruthy();
    expect(screen.getByText("15")).toBeTruthy();
  });
});
