import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useAppStore } from "../../store/appStore";
import { SequenceViewer } from "./SequenceViewer";

describe("SequenceViewer domain legend", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    useAppStore.setState(useAppStore.getInitialState());
  });

  it("renders repeated domain names at different ranges without duplicate-key warnings", () => {
    // Given
    useAppStore.setState({
      seqInfo: null,
      parsedMutations: [{ raw: "A100V", wt_aa: "A", position: 100, mt_aa: "V" }],
      designResults: [],
      failedMutations: [],
      refDomains: [
        { name: "Repeat", id: "PF00001", start: 10, end: 30, db: "Pfam" },
        { name: "Repeat", id: "PF00001", start: 60, end: 80, db: "Pfam" },
      ],
      disabledDomains: [],
      domainStats: {},
    });
    const consoleError = vi.spyOn(console, "error");

    // When
    render(<SequenceViewer />);

    // Then
    expect(screen.getAllByText("Repeat", { selector: "span" })).toHaveLength(2);
    expect(consoleError.mock.calls.filter(([message]) =>
      typeof message === "string" && message.includes("same key"),
    )).toEqual([]);
  });
});
