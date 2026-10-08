import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import i18n from "@/lib/i18n";
import { WhatsNewDialog } from "./WhatsNewDialog";

// vitest.config.ts defines __APP_VERSION__ as "0.0.0-test".
const CURRENT_VERSION = "0.0.0-test";
const STORAGE_KEY = "kuma:lastSeenVersion";

/** Live en.json slice backing i18next; mutated per test and restored after. */
const dialogBundle: Record<string, unknown> =
  i18n.getResourceBundle("en", "translation").whatsNewDialog;
const originalHighlights = dialogBundle.highlights;
const originalReleases = dialogBundle.releases;

/**
 * A per-version archive for the range cases. Those pass `currentVersion`
 * explicitly, because the build constant this modal defaults to is fixed at
 * "0.0.0-test" and no released version sorts below it.
 */
const ARCHIVE = {
  "0.16.9": ["The newest note."],
  "0.16.8": ["A middle note."],
  "0.16.7": ["The oldest note."],
};

function highlightStrings(): string[] {
  return Array.isArray(originalHighlights)
    ? originalHighlights.filter((v): v is string => typeof v === "string")
    : [];
}

describe("WhatsNewDialog", () => {
  beforeEach(() => {
    localStorage.clear();
    // A stored version older than the current one is what opens the dialog.
    localStorage.setItem(STORAGE_KEY, "0.0.0-old");
  });

  afterEach(() => {
    cleanup();
    dialogBundle.highlights = originalHighlights;
    dialogBundle.releases = originalReleases;
    localStorage.clear();
  });

  it("renders one bullet per highlight from the active locale", () => {
    const expected = highlightStrings();
    expect(expected.length).toBeGreaterThan(0);

    render(<WhatsNewDialog />);

    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(expected.length);
    expect(items.map((li) => li.textContent)).toEqual(expected);
  });

  it("renders no bullets and does not crash when highlights is missing", () => {
    delete dialogBundle.highlights;

    render(<WhatsNewDialog />);

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
    // The raw key must never leak into the UI.
    expect(screen.queryByText(/whatsNewDialog\.highlights/)).not.toBeInTheDocument();
  });

  it("renders no bullets and does not crash when highlights is not an array", () => {
    dialogBundle.highlights = "not an array";

    render(<WhatsNewDialog />);

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
  });

  it("still renders the confirm button when the highlights are many and long", () => {
    // The bullets are translated by hand and some languages run 30% longer than
    // the English, so the modal has to stay dismissable past the point where the
    // list would otherwise push the footer off screen. jsdom does no layout, so
    // what is asserted here is that the footer is still rendered and reachable;
    // the bounded height and the scroll live on the list's own classes.
    dialogBundle.highlights = Array.from(
      { length: 40 },
      (_, i) => `Highlight ${i + 1}: ${"a very long release note ".repeat(8)}`,
    );

    render(<WhatsNewDialog />);

    expect(screen.getAllByRole("listitem")).toHaveLength(40);
    const confirm = screen.getByRole("button", { name: "Got it" });
    expect(confirm).toBeInTheDocument();

    fireEvent.click(confirm);
    expect(localStorage.getItem(STORAGE_KEY)).toBe(CURRENT_VERSION);
  });

  it("puts the scrollable highlight list in the tab order so it can be scrolled by keyboard", async () => {
    const user = userEvent.setup();
    render(<WhatsNewDialog />);

    // The scroll container carries overflow-y-auto and holds no focusable
    // descendant, so it needs a tab stop of its own or the overflow is
    // mouse-only (WCAG 2.1.1). It is the wrapper rather than a list because a
    // range of releases is one list per release, and a per-list stop would make
    // the number of tab stops depend on how many releases were skipped.
    const scroller = screen.getByRole("list").parentElement?.parentElement;
    expect(scroller).toHaveAttribute("tabindex", "0");

    // Reachability, not just the attribute. Focus starts on the confirm button
    // (it carries autoFocus), placed here explicitly so the assertion is about
    // the tab order rather than about Radix's open-time focus timing in jsdom.
    const confirm = screen.getByRole("button", { name: "Got it" });
    confirm.focus();
    await user.tab();
    expect(scroller).toHaveFocus();
  });

  it("shows every release between the stored version and the running one, newest first", () => {
    // The point of the archive: an operator who skipped two releases reads all
    // three sets of notes, not only the release they happened to land on.
    dialogBundle.releases = ARCHIVE;
    localStorage.setItem(STORAGE_KEY, "0.16.6");

    render(<WhatsNewDialog currentVersion="0.16.9" />);

    expect(screen.getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "The newest note.",
      "A middle note.",
      "The oldest note.",
    ]);
    // Each release is labelled, or the bullets read as one undated list.
    expect(screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent)).toEqual([
      "v0.16.9",
      "v0.16.8",
      "v0.16.7",
    ]);
    expect(screen.getByText("Highlights from every update since v0.16.6.")).toBeInTheDocument();
  });

  it("excludes releases at or below the stored version and above the running one", () => {
    dialogBundle.releases = ARCHIVE;
    localStorage.setItem(STORAGE_KEY, "0.16.7");

    render(<WhatsNewDialog currentVersion="0.16.8" />);

    expect(screen.getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "A middle note.",
    ]);
    // One release keeps the single-release wording and no version heading: the
    // dialog title already names it.
    expect(screen.queryAllByRole("heading", { level: 3 })).toHaveLength(0);
    expect(screen.getByText("Highlights from the latest update.")).toBeInTheDocument();
  });

  it("shows the whole archive when the stored version predates it", () => {
    // The archive begins at the release that introduced these notes, so a much
    // older build must produce every entry rather than none.
    dialogBundle.releases = ARCHIVE;
    localStorage.setItem(STORAGE_KEY, "0.14.0");

    render(<WhatsNewDialog currentVersion="0.16.9" />);

    expect(screen.getAllByRole("listitem")).toHaveLength(3);
  });

  it("falls back to the current release notes when the stored version is newer", () => {
    // A downgrade: nothing in the archive is in range, and an empty modal would
    // be worse than the notes of the build now running.
    dialogBundle.releases = ARCHIVE;
    localStorage.setItem(STORAGE_KEY, "0.17.0");

    render(<WhatsNewDialog currentVersion="0.16.9" />);

    expect(screen.getAllByRole("listitem").map((li) => li.textContent)).toEqual(
      highlightStrings(),
    );
  });

  it("renders no bullets and does not crash when the archive is not an object", () => {
    dialogBundle.releases = "not an object";
    delete dialogBundle.highlights;

    render(<WhatsNewDialog />);

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
  });

  it("stores the current version and calls onDismiss when confirmed", () => {
    const onDismiss = vi.fn();
    render(<WhatsNewDialog onDismiss={onDismiss} />);

    fireEvent.click(screen.getByRole("button", { name: "Got it" }));

    expect(localStorage.getItem(STORAGE_KEY)).toBe(CURRENT_VERSION);
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });
});
