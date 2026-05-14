import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { useAppStore } from "../../../../store/appStore";
import { SourceInspector } from "../SourceInspector";

describe("SourceInspector", () => {
  afterEach(() => {
    useAppStore.setState({
      evolveproCsvPath: "",
      evolveproTotalCount: 0,
      evolveproRound: 0,
    });
  });

  it("renders empty state when no artifact is loaded", () => {
    useAppStore.setState({
      evolveproCsvPath: "",
      evolveproTotalCount: 0,
      evolveproRound: 0,
    });
    render(<SourceInspector />);
    expect(screen.getAllByText(/No artifact loaded/i).length).toBeGreaterThan(0);
  });

  it("renders artifact filename and counts when loaded", () => {
    useAppStore.setState({
      evolveproCsvPath: "/tmp/round3/variants.csv",
      evolveproTotalCount: 128,
      evolveproRound: 3,
    });
    render(<SourceInspector />);
    expect(screen.getByText("variants.csv")).toBeTruthy();
    expect(screen.getByText("128")).toBeTruthy();
    expect(screen.getByText("3")).toBeTruthy();
    expect(screen.getByText("EVOLVEpro CSV")).toBeTruthy();
  });
});
