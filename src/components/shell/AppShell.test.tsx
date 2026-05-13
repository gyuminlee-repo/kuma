// Tests for AppShell sidebar width integration
// Run: npx vitest run src/components/shell/AppShell.test.tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render } from "@testing-library/react";
import { AppShell } from "./AppShell";
import { useLayoutStore } from "@/store/layoutStore";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}));

beforeEach(() => {
  localStorage.clear();
  // Reset store to initial state
  useLayoutStore.setState({ sidebarWidth: null, computedDefault: 240 });
});

describe("AppShell sidebar width", () => {
  it("aside has inline width from store when sidebarWidth is set", () => {
    useLayoutStore.setState({ sidebarWidth: 320 });
    const { getByTestId } = render(
      <AppShell
        tool="kuro"
        titlebar={<div />}
        sidebar={<div>nav</div>}
        main={<div />}
        statusbar={<div />}
      />,
    );
    const aside = getByTestId("sidebar");
    expect(aside).toHaveStyle({ width: "320px" });
  });

  it("aside uses computedDefault when sidebarWidth is null", () => {
    useLayoutStore.setState({ sidebarWidth: null, computedDefault: 250 });
    const { getByTestId } = render(
      <AppShell
        tool="kuro"
        titlebar={<div />}
        sidebar={<div>nav</div>}
        main={<div />}
        statusbar={<div />}
      />,
    );
    const aside = getByTestId("sidebar");
    expect(aside).toHaveStyle({ width: "250px" });
  });

  it("renders ResizeHandle inside aside", () => {
    const { getByRole } = render(
      <AppShell
        tool="kuro"
        titlebar={<div />}
        sidebar={<div>nav</div>}
        main={<div />}
        statusbar={<div />}
      />,
    );
    expect(getByRole("separator")).toBeInTheDocument();
  });

  it("does not render aside when sidebar is null", () => {
    const { queryByTestId, queryByRole } = render(
      <AppShell
        tool="kuro"
        titlebar={<div />}
        sidebar={null}
        main={<div />}
        statusbar={<div />}
      />,
    );
    expect(queryByTestId("sidebar")).toBeNull();
    expect(queryByRole("separator")).toBeNull();
  });

  it("does not render ResizeHandle when disableResize is true", () => {
    const { queryByRole } = render(
      <AppShell
        tool="kuro"
        titlebar={<div />}
        sidebar={<div>nav</div>}
        main={<div />}
        statusbar={<div />}
        disableResize
      />,
    );
    expect(queryByRole("separator")).toBeNull();
  });
});
