// Tests for AppShell sidebar width integration
// Run: npx vitest run src/components/shell/AppShell.test.tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

describe("AppShell inspector slot", () => {
  it("does not render inspector aside when inspector prop is omitted", () => {
    const { queryByTestId } = render(
      <AppShell
        tool="kuro"
        titlebar={<div />}
        main={<div />}
        statusbar={<div />}
      />,
    );
    expect(queryByTestId("inspector")).toBeNull();
  });

  it("renders inspector aside when inspector prop is provided (default open)", () => {
    const { getByTestId } = render(
      <AppShell
        tool="kuro"
        titlebar={<div />}
        main={<div />}
        statusbar={<div />}
        inspector={<div>inspect content</div>}
      />,
    );
    expect(getByTestId("inspector")).toBeInTheDocument();
  });

  it("does not render inspector aside when inspectorOpen=false, shows toggle button", () => {
    const { queryByTestId, getByRole } = render(
      <AppShell
        tool="kuro"
        titlebar={<div />}
        main={<div />}
        statusbar={<div />}
        inspector={<div>inspect content</div>}
        inspectorOpen={false}
      />,
    );
    expect(queryByTestId("inspector")).toBeNull();
    expect(getByRole("button", { name: /open inspector/i })).toBeInTheDocument();
  });

  it("calls onInspectorToggle when toggle button is clicked", async () => {
    const onToggle = vi.fn();
    const { getByRole } = render(
      <AppShell
        tool="kuro"
        titlebar={<div />}
        main={<div />}
        statusbar={<div />}
        inspector={<div>inspect content</div>}
        inspectorOpen={false}
        onInspectorToggle={onToggle}
      />,
    );
    await userEvent.setup().click(getByRole("button", { name: /open inspector/i }));
    expect(onToggle).toHaveBeenCalledOnce();
  });
});
