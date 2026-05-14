import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { DrawerStrip } from "./DrawerStrip";

describe("DrawerStrip", () => {
  it("renders without crashing", () => {
    render(<DrawerStrip />);
    expect(screen.getByRole("region", { name: "action-drawer" })).toBeInTheDocument();
  });

  it("renders left slot title and content", () => {
    render(
      <DrawerStrip
        left={{ title: "Recent artifacts", children: <span>artifact row</span> }}
      />,
    );
    expect(screen.getByText("Recent artifacts")).toBeInTheDocument();
    expect(screen.getByText("artifact row")).toBeInTheDocument();
  });

  it("renders center slot title and content", () => {
    render(
      <DrawerStrip
        center={{ title: "Sidecar log", children: <pre>log line</pre> }}
      />,
    );
    expect(screen.getByText("Sidecar log")).toBeInTheDocument();
    expect(screen.getByText("log line")).toBeInTheDocument();
  });

  it("renders right slot title and content", () => {
    render(
      <DrawerStrip
        right={{ title: "Autosave", children: <span>saved 2m ago</span> }}
      />,
    );
    expect(screen.getByText("Autosave")).toBeInTheDocument();
    expect(screen.getByText("saved 2m ago")).toBeInTheDocument();
  });

  it("renders all three slots together", () => {
    render(
      <DrawerStrip
        left={{ title: "Left", children: <span>L</span> }}
        center={{ title: "Center", children: <span>C</span> }}
        right={{ title: "Right", children: <span>R</span> }}
      />,
    );
    expect(screen.getByText("Left")).toBeInTheDocument();
    expect(screen.getByText("Center")).toBeInTheDocument();
    expect(screen.getByText("Right")).toBeInTheDocument();
  });
});
