import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HelpMarkdown } from "./HelpMarkdown";

const openUrlMock = vi.hoisted(() => vi.fn<(url: string) => Promise<void>>());

vi.mock("@tauri-apps/plugin-opener", () => ({
  openUrl: openUrlMock,
}));

const KNOWN = ["alpha-topic", "beta-topic"];

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
});
