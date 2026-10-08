import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { InspectorPanel } from "./InspectorPanel";

describe("InspectorPanel", () => {
  it("renders without crashing", () => {
    render(<InspectorPanel title="Source Inspector"><p>body</p></InspectorPanel>);
    expect(screen.getByRole("heading", { name: "Source Inspector" })).toBeInTheDocument();
  });

  it("section is labelled by heading", () => {
    render(<InspectorPanel title="Source Inspector"><p>body</p></InspectorPanel>);
    const section = screen.getByRole("region", { name: "Source Inspector" });
    expect(section).toBeInTheDocument();
  });

  it("renders subtitle when provided", () => {
    render(
      <InspectorPanel title="Source Inspector" subtitle="MAME artifact">
        <p>body</p>
      </InspectorPanel>,
    );
    expect(screen.getByText("MAME artifact")).toBeInTheDocument();
  });

  it("does not render subtitle when omitted", () => {
    render(<InspectorPanel title="Source Inspector"><p>body</p></InspectorPanel>);
    expect(screen.queryByText("MAME artifact")).toBeNull();
  });

  it("renders children in scroll area", () => {
    render(
      <InspectorPanel title="Source Inspector">
        <div data-testid="child-content">KV rows here</div>
      </InspectorPanel>,
    );
    expect(screen.getByTestId("child-content")).toBeInTheDocument();
  });
});
