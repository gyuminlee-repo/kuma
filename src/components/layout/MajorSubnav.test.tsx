/**
 * MajorSubnav.test.tsx — 4탭 렌더링 + 클릭 시 setMajor 호출 + active 표시
 */

import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

// ipc-kuro dependency 차단
vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

import { MajorSubnav } from "./MajorSubnav";
import { useAppStore } from "@/store/appStore";
import type { MajorNavItem } from "./MajorSubnav";

const MAJORS: MajorNavItem[] = [
  { id: "variant", labelKey: "phaseC.majors.variant" },
  { id: "sdm",     labelKey: "phaseC.majors.sdm" },
  { id: "plate",   labelKey: "phaseC.majors.plate" },
  { id: "export",  labelKey: "phaseC.majors.export" },
];

describe("MajorSubnav", () => {
  beforeEach(() => {
    useAppStore.setState({
      currentMajor: "variant",
      currentSubStep: "variant.load",
    });
  });

  it("renders all 4 tabs", () => {
    render(<MajorSubnav majors={MAJORS} />);
    // i18n falls back to the key in test env
    const tabs = screen.getAllByRole("tab");
    expect(tabs).toHaveLength(4);
  });

  it("first tab is aria-selected when currentMajor=variant", () => {
    render(<MajorSubnav majors={MAJORS} />);
    const tabs = screen.getAllByRole("tab");
    expect(tabs[0].getAttribute("aria-selected")).toBe("true");
    expect(tabs[1].getAttribute("aria-selected")).toBe("false");
    expect(tabs[2].getAttribute("aria-selected")).toBe("false");
    expect(tabs[3].getAttribute("aria-selected")).toBe("false");
  });

  it("clicking sdm tab calls setMajor('sdm') and updates currentMajor", () => {
    render(<MajorSubnav majors={MAJORS} />);
    const tabs = screen.getAllByRole("tab");
    fireEvent.click(tabs[1]); // sdm
    expect(useAppStore.getState().currentMajor).toBe("sdm");
  });

  it("clicking plate tab calls setMajor('plate')", () => {
    render(<MajorSubnav majors={MAJORS} />);
    const tabs = screen.getAllByRole("tab");
    fireEvent.click(tabs[2]); // plate
    expect(useAppStore.getState().currentMajor).toBe("plate");
  });

  it("count badge is hidden when countBadge prop is undefined", () => {
    const { container } = render(<MajorSubnav majors={MAJORS} />);
    // No count badge elements should exist
    const badges = container.querySelectorAll(".bg-muted.text-muted-foreground.rounded-full");
    expect(badges.length).toBe(0);
  });

  it("count badge is visible when countBadge prop is provided", () => {
    const majorsWithBadge: MajorNavItem[] = [
      { id: "variant", labelKey: "phaseC.majors.variant", countBadge: 5 },
      ...MAJORS.slice(1),
    ];
    render(<MajorSubnav majors={majorsWithBadge} />);
    expect(screen.getByText("5")).toBeTruthy();
  });
});
