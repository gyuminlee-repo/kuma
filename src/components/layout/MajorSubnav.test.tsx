/**
 * MajorSubnav.test.tsx — 4탭 렌더링 + 클릭 시 setMajor 호출 + active 표시 (Phase F: shadcn TabsList)
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
  { id: "design", labelKey: "phaseC.majors.design" },
  { id: "report", labelKey: "phaseC.majors.report" },
  { id: "plate",  labelKey: "phaseC.majors.plate" },
  { id: "export", labelKey: "phaseC.majors.export" },
];

describe("MajorSubnav (shadcn TabsList, 4-major)", () => {
  beforeEach(() => {
    useAppStore.setState({
      currentMajor: "design",
      currentSubStep: "design.load",
    });
  });

  it("renders all 4 tabs", () => {
    render(<MajorSubnav majors={MAJORS} />);
    const tabs = screen.getAllByRole("tab");
    expect(tabs).toHaveLength(4);
  });

  it("first tab is aria-selected when currentMajor=design", () => {
    render(<MajorSubnav majors={MAJORS} />);
    const tabs = screen.getAllByRole("tab");
    expect(tabs[0].getAttribute("aria-selected")).toBe("true");
    expect(tabs[1].getAttribute("aria-selected")).toBe("false");
    expect(tabs[2].getAttribute("aria-selected")).toBe("false");
    expect(tabs[3].getAttribute("aria-selected")).toBe("false");
  });

  it("clicking report tab updates currentMajor to report", async () => {
    const user = userEvent.setup();
    render(<MajorSubnav majors={MAJORS} />);
    const tabs = screen.getAllByRole("tab");
    await user.click(tabs[1]); // report
    expect(useAppStore.getState().currentMajor).toBe("report");
  });

  it("clicking plate tab calls setMajor('plate') and updates currentMajor", async () => {
    const user = userEvent.setup();
    render(<MajorSubnav majors={MAJORS} />);
    const tabs = screen.getAllByRole("tab");
    await user.click(tabs[2]); // plate
    expect(useAppStore.getState().currentMajor).toBe("plate");
  });

  it("clicking export tab calls setMajor('export')", async () => {
    const user = userEvent.setup();
    render(<MajorSubnav majors={MAJORS} />);
    const tabs = screen.getAllByRole("tab");
    await user.click(tabs[3]); // export
    expect(useAppStore.getState().currentMajor).toBe("export");
  });

  it("count badge is hidden when countBadge prop is undefined", () => {
    const { container } = render(<MajorSubnav majors={MAJORS} />);
    const badges = container.querySelectorAll(".bg-muted.text-muted-foreground.rounded-full");
    expect(badges.length).toBe(0);
  });

  it("count badge is visible when countBadge prop is provided", () => {
    const majorsWithBadge: MajorNavItem[] = [
      { id: "design", labelKey: "phaseC.majors.design", countBadge: 5 },
      ...MAJORS.slice(1),
    ];
    render(<MajorSubnav majors={majorsWithBadge} />);
    expect(screen.getByText("5")).toBeTruthy();
  });
});
