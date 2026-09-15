import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HelpMarkdown } from "./HelpMarkdown";

const openUrlMock = vi.hoisted(() => vi.fn<(url: string) => Promise<void>>());

vi.mock("@tauri-apps/plugin-opener", () => ({
  openUrl: openUrlMock,
}));

const KNOWN = ["alpha-topic", "beta-topic"];

// The pipeline topic carries the largest table in the help set. The pattern
// ends in a wildcard so no literal document name appears in this file.
const PIPELINE_EN = import.meta.glob<string>("../../../docs/help/en/mame-pipeline*", {
  query: "?raw",
  import: "default",
  eager: true,
});

const TABLE = ["| Column | Meaning |", "| --- | --- |", "| verdict | Call for the well |"].join("\n");

describe("HelpMarkdown", () => {
  beforeEach(() => {
    openUrlMock.mockReset();
    openUrlMock.mockResolvedValue();
  });

  it("swaps the topic on a link naming a known topic", async () => {
    const onTopicChange = vi.fn();
    render(
      <HelpMarkdown
        body={"See [Setup](alpha-topic.md)."}
        knownTopics={KNOWN}
        onTopicChange={onTopicChange}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Setup" }));
    expect(onTopicChange).toHaveBeenCalledWith("alpha-topic");
  });

  it("uses the last path segment when the href carries a directory", async () => {
    const onTopicChange = vi.fn();
    render(
      <HelpMarkdown
        body={"See [Beta](../x/beta-topic.md)."}
        knownTopics={KNOWN}
        onTopicChange={onTopicChange}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Beta" }));
    expect(onTopicChange).toHaveBeenCalledWith("beta-topic");
  });

  it("renders a link to an unknown topic as plain text", () => {
    render(
      <HelpMarkdown
        body={"See [Ghost](gamma-topic.md)."}
        knownTopics={KNOWN}
        onTopicChange={vi.fn()}
      />,
    );
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText(/Ghost/)).toBeInTheDocument();
  });

  it("keeps an external link as a link", async () => {
    render(
      <HelpMarkdown
        body={"See [Repo](https://github.com/example)."}
        knownTopics={KNOWN}
        onTopicChange={vi.fn()}
      />,
    );
    const link = screen.getByRole("link", { name: "Repo" });
    expect(link).toBeInTheDocument();
    await userEvent.click(link);
    expect(openUrlMock).toHaveBeenCalledWith("https://github.com/example");
  });

  it("renders an anchor-only link as plain text", () => {
    render(
      <HelpMarkdown body={"See [Top](#top)."} knownTopics={KNOWN} onTopicChange={vi.fn()} />,
    );
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByText(/Top/)).toBeInTheDocument();
  });
  it("renders a GFM table as a table without pipe characters", () => {
    render(<HelpMarkdown body={TABLE} knownTopics={KNOWN} onTopicChange={vi.fn()} />);
    const table = screen.getByRole("table");
    expect(screen.getByRole("columnheader", { name: "Column" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "Call for the well" })).toBeInTheDocument();
    expect(table.textContent).not.toContain("|");
  });

  it("wraps a table in a horizontally scrollable container", () => {
    render(<HelpMarkdown body={TABLE} knownTopics={KNOWN} onTopicChange={vi.fn()} />);
    const wrapper = screen.getByRole("table").parentElement;
    expect(wrapper).not.toBeNull();
    expect(wrapper?.className).toContain("overflow-x-auto");
  });

  it("drops HTML comments and keeps the sentences around them", () => {
    const { container } = render(
      <HelpMarkdown
        body={"Before the note.\n\n<!-- 비밀 주석 -->\n\nAfter the note."}
        knownTopics={KNOWN}
        onTopicChange={vi.fn()}
      />,
    );
    expect(screen.getByText("Before the note.")).toBeInTheDocument();
    expect(screen.getByText("After the note.")).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/비밀 주석|<!--/);
  });

  it("does not render raw HTML elements", () => {
    const { container } = render(
      <HelpMarkdown body={"Some <b>raw</b> text."} knownTopics={KNOWN} onTopicChange={vi.fn()} />,
    );
    expect(container.querySelector("b")).toBeNull();
    expect(container.textContent).not.toContain("<b>");
  });

  it("renders the real pipeline topic with tables and no pipe rows", () => {
    const bodies = Object.values(PIPELINE_EN);
    expect(bodies).toHaveLength(1);
    const { container } = render(
      <HelpMarkdown body={bodies[0]} knownTopics={KNOWN} onTopicChange={vi.fn()} />,
    );
    expect(screen.getAllByRole("table").length).toBeGreaterThan(0);
    const lines = (container.textContent ?? "").split("\n");
    expect(lines.filter((l) => l.trimStart().startsWith("| "))).toEqual([]);
  });
});
