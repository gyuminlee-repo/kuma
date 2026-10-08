/**
 * MappingIntegrityAlert, whole-run well/variant mapping sanity warning.
 *
 * The 2026-08 incident this covers: 288 wells, PASS 2 / WRONG_AA 239, but the
 * screen looked ordinary. 244 wells had an observed AA change; 0 matched
 * their own well's expected mutation and 241 matched a DIFFERENT well's
 * expected mutation. `mapping_integrity.suspect` is the backend's post-hoc
 * signal for exactly that shape, and this component must not stay quiet
 * about it.
 */
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/ipc-mame", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

import { useMameAppStore } from "@/store/mame/mameAppStore";
import { MappingIntegrityAlert } from "./MappingIntegrityAlert";

describe("MappingIntegrityAlert", () => {
  beforeEach(() => {
    useMameAppStore.setState({ mappingIntegrity: null });
  });

  it("renders nothing before a run has reported mapping_integrity", () => {
    const { container } = render(<MappingIntegrityAlert />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when the mapping check found nothing suspect", () => {
    useMameAppStore.setState({
      mappingIntegrity: {
        wells_considered: 244,
        self_match: 240,
        cross_match: 2,
        self_rate: 0.984,
        cross_rate: 0.008,
        suspect: false,
      },
    });

    const { container } = render(<MappingIntegrityAlert />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders a loud, non-collapsible alert with the actual reported numbers when suspect", () => {
    useMameAppStore.setState({
      mappingIntegrity: {
        wells_considered: 244,
        self_match: 0,
        cross_match: 241,
        self_rate: 0,
        cross_rate: 0.9877,
        suspect: true,
      },
    });

    render(<MappingIntegrityAlert />);

    const alert = screen.getByTestId("mapping-integrity-alert");
    expect(alert).toHaveAttribute("role", "alert");
    // Values come from the store field, not a hardcoded string.
    expect(alert).toHaveTextContent("244");
    expect(alert).toHaveTextContent("0.0%");
    expect(alert).toHaveTextContent("98.8%");
  });
});
