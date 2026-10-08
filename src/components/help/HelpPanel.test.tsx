import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import i18n from "@/lib/i18n";
import { ALL_TOPIC_IDS, HELP_GROUPS } from "@/help/topics";
import { HelpPanel } from "./HelpPanel";

vi.mock("@tauri-apps/plugin-opener", () => ({
  openUrl: vi.fn(() => Promise.resolve()),
}));

type Props = Parameters<typeof HelpPanel>[0];

function setup(over: Partial<Props> = {}) {
  const props: Props = {
    open: true,
    topic: "mame-01-setup",
    onTopicChange: vi.fn(),
    onClose: vi.fn(),
    ...over,
  };
  render(<HelpPanel {...props} />);
  return props;
}

/** Labels come from the live en bundle so a copy change does not break a test. */
function en(key: string): string {
  return i18n.t(key, { lng: "en" });
}

function contents() {
  return within(screen.getByRole("navigation"));
}

describe("HelpPanel", () => {
  afterEach(async () => {
    await i18n.changeLanguage("en");
  });

  it("renders nothing when closed", () => {
    setup({ open: false });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("names itself by its heading and focuses the close button on open", () => {
    setup();
    const dialog = screen.getByRole("dialog");
    const heading = screen.getByRole("heading", { name: en("help.panel.title") });
    expect(dialog).toHaveAttribute("aria-labelledby", heading.id);
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: en("help.panel.close") }),
    );
  });

  it("shows every group label and one contents button per topic", () => {
    setup();
    for (const g of HELP_GROUPS) {
      expect(contents().getByText(en(g.labelKey))).toBeInTheDocument();
    }
    expect(contents().getAllByRole("button")).toHaveLength(ALL_TOPIC_IDS.length);
  });

  it("resolves every group and topic label rather than printing the key", () => {
    setup();
    const nav = screen.getByRole("navigation");
    for (const g of HELP_GROUPS) expect(nav.textContent).not.toContain(g.labelKey);
    for (const id of ALL_TOPIC_IDS) {
      expect(nav.textContent).not.toContain(`help.panel.topic.${id}`);
    }
  });

  it("changes topic when a contents entry is clicked", async () => {
    const p = setup();
    await userEvent.click(
      contents().getByRole("button", { name: en("help.panel.topic.mame-02-review") }),
    );
    expect(p.onTopicChange).toHaveBeenCalledWith("mame-02-review");
  });

  it("marks the current topic", () => {
    setup({ topic: "mame-03-janus" });
    const current = contents().getByRole("button", {
      name: en("help.panel.topic.mame-03-janus"),
    });
    expect(current).toHaveAttribute("aria-current", "true");
    const other = contents().getByRole("button", { name: en("help.panel.topic.kuro-01-load") });
    expect(other).not.toHaveAttribute("aria-current");
  });

  it("closes on the close button", async () => {
    const p = setup();
    await userEvent.click(screen.getByRole("button", { name: en("help.panel.close") }));
    expect(p.onClose).toHaveBeenCalledTimes(1);
  });

  it("closes on Escape", async () => {
    const p = setup();
    await userEvent.keyboard("{Escape}");
    expect(p.onClose).toHaveBeenCalledTimes(1);
  });

  it("keeps the contents usable when the topic is missing", () => {
    setup({ topic: "no-such-topic" });
    expect(screen.getByTestId("help-missing-topic")).toBeInTheDocument();
    expect(contents().getAllByRole("button")).toHaveLength(ALL_TOPIC_IDS.length);
  });

  it("says so when the body came from another locale", async () => {
    await i18n.changeLanguage("ja");
    setup({ topic: "mame-01-setup" });
    const notice = screen.getByTestId("help-fallback-notice");
    expect(notice).toHaveTextContent(en("help.panel.shownInEnglish"));
  });

  it("shows no fallback notice when the requested locale holds the topic", async () => {
    await i18n.changeLanguage("ko");
    setup({ topic: "mame-01-setup" });
    expect(screen.queryByTestId("help-fallback-notice")).toBeNull();
  });

  it("does not leak HTML comments in the body as text", () => {
    setup({ topic: "kuro-01-load" });
    // The body must actually be on screen, or the absence below proves nothing.
    // The heading text itself is not pinned: it is prose that the help content
    // is free to reword, and pinning it makes every copy edit fail here.
    expect(
      screen.getByRole("heading", { level: 1 }).textContent?.trim(),
    ).not.toHaveLength(0);
    expect(screen.getByRole("dialog").textContent).not.toMatch(/TODO|insert screenshot|<!--/);
  });
});
