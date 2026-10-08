/**
 * The consent dialog must name every recipient a granted call can reach.
 *
 * ESMFold sends the protein sequence to Meta (api.esmatlas.com). It used to
 * ride on the AlphaFold entry, so the dialog listed only EBI hosts and the user
 * was never told the sequence left for Meta.
 */
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { useAppStore } from "../../../store/appStore";
import { NetworkConsentDialog } from "../NetworkConsentDialog";

describe("NetworkConsentDialog", () => {
  afterEach(() => {
    useAppStore.setState({ networkConsentPending: false });
  });

  it("lists ESMFold with its Meta endpoint", () => {
    useAppStore.setState({ networkConsentPending: true });
    render(<NetworkConsentDialog />);

    expect(screen.getByText("ESMFold (Meta)")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: "api.esmatlas.com" });
    expect(link).toBeInTheDocument();
    // The EBI entries are still there; ESMFold is added, not swapped in.
    expect(screen.getByRole("link", { name: "alphafold.ebi.ac.uk" })).toBeInTheDocument();
  });
});
