/**
 * Both menu bars put "User guide" first in Help and ask the shell to open the
 * panel at the topic of their own store's current step.
 */
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ProjectProvider } from "@/state/projectContext";
import { MenuBar as KuroMenuBar } from "@/components/layout/MenuBar";
import { MenuBar as MameMenuBar } from "@/components/mame/layout/MenuBar";
import { useAppStore } from "@/store/appStore";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { OPEN_HELP_EVENT, type OpenHelpDetail } from "./events";

vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
  spawnSidecar: vi.fn(() => Promise.resolve()),
  getLastProgressAt: vi.fn(() => Date.now()),
}));

afterEach(() => cleanup());

async function clickFirstHelpItem() {
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Help" }));
  const menu = await waitFor(() => screen.getByRole("menu"));
  const first = within(menu).getAllByRole("menuitem")[0];
  expect(first).toHaveTextContent("User guide");
  const topics: string[] = [];
  const onOpen = (e: Event) => topics.push((e as CustomEvent<OpenHelpDetail>).detail.topic);
  window.addEventListener(OPEN_HELP_EVENT, onOpen);
  await user.click(first);
  window.removeEventListener(OPEN_HELP_EVENT, onOpen);
  return topics;
}

const project = { path: "/tmp/proj", name: "proj", scratch: false };

describe("Help > User guide", () => {
  it("KURO asks for the topic of design.params", async () => {
    useAppStore.setState({ currentSubStep: "design.params" });
    render(
      <ProjectProvider value={project}>
        <KuroMenuBar />
      </ProjectProvider>,
    );
    expect(await clickFirstHelpItem()).toEqual(["kuro-03-params"]);
  });

  it("MAME asks for the topic of analyze.review", async () => {
    useMameAppStore.setState({ currentMameSubStep: "analyze.review" });
    render(
      <ProjectProvider value={project}>
        <MameMenuBar onClearRequest={() => {}} />
      </ProjectProvider>,
    );
    expect(await clickFirstHelpItem()).toEqual(["mame-02-review"]);
  });
});
