import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { useAppStore } from "../../../../store/appStore";
import { CurrentMutationInspector } from "../CurrentMutationInspector";

describe("CurrentMutationInspector", () => {
  afterEach(() => {
    useAppStore.setState({
      isDesigning: false,
      statusMessage: "",
      successCount: 0,
      totalCount: 0,
    });
  });

  it("renders idle/empty placeholders when nothing is running", () => {
    useAppStore.setState({
      isDesigning: false,
      statusMessage: "",
      successCount: 0,
      totalCount: 0,
    });
    render(<CurrentMutationInspector />);
    expect(screen.getByText(/Current Mutation/i)).toBeTruthy();
    expect(screen.getAllByText("--").length).toBeGreaterThan(0);
  });

  it("renders progress and status when designing", () => {
    useAppStore.setState({
      isDesigning: true,
      statusMessage: "Designing M42A",
      successCount: 3,
      totalCount: 10,
    });
    render(<CurrentMutationInspector />);
    expect(screen.getByText("Designing M42A")).toBeTruthy();
    expect(screen.getByText("3 / 10")).toBeTruthy();
  });
});
