import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { KuroInspector } from "./KuroChrome";
import { useAppStore } from "../../store/appStore";
import { EMPTY_RESCUE_STATS } from "../../store/slices/designSlice.helpers";

describe("KuroInspector switch — output.summary -> DesignReportInspector", () => {
  afterEach(() => {
    useAppStore.setState({
      designResults: [],
      failedMutations: [],
      totalCount: 0,
      rescueStats: EMPTY_RESCUE_STATS,
      rescuedMutationDetails: [],
    });
  });

  it("renders DesignReportInspector empty-state when on output.summary with no results", () => {
    useAppStore.setState({
      currentSubStep: "output.summary",
      designResults: [],
    });
    render(<KuroInspector />);
    // DesignReportInspector empty-state copy from en.json: "Run Design first ..."
    expect(screen.getByText(/Run Design first/i)).toBeTruthy();
  });

  it("does not mount DesignReportInspector on other substeps (e.g. design.load)", () => {
    useAppStore.setState({
      currentSubStep: "design.load",
      designResults: [],
    });
    render(<KuroInspector />);
    expect(screen.queryByText(/Run Design first/i)).toBeNull();
  });
});
