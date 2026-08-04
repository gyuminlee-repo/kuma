/**
 * FileMenu: the project-level items both menubars must show, and the ones they must not.
 *
 * The point of the component is that the two menus cannot drift again, so the tests
 * pin the shared set and pin the absence of the two entries a button already performs.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

vi.mock("@tauri-apps/api/window", () => ({
  getCurrentWindow: () => ({ close: vi.fn() }),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

import { FileMenu } from "./FileMenu";

const BASE = {
  triggerClassName: "trigger",
  hasProject: true,
  sidecar: "kuro" as const,
  restartConfirmMessage: null,
  onExportProjectZip: () => {},
  onImportProjectZip: () => {},
  onRestartSidecar: () => {},
};

async function openMenu(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByText("menu.file"));
  await waitFor(() => expect(screen.getByText("file.openProject")).toBeInTheDocument());
}

describe("FileMenu shared items", () => {
  it("offers project open, both archive directions, restart and quit", async () => {
    const user = userEvent.setup();
    render(<FileMenu {...BASE} />);

    await openMenu(user);

    for (const key of [
      "file.openProject",
      "file.importProjectZip",
      "file.exportProjectZip",
      "file.restartSidecar",
      "menuBar.appMenu.quit",
    ]) {
      expect(screen.getByText(key)).toBeInTheDocument();
    }
  });

  it("does not offer what a button already does", async () => {
    const user = userEvent.setup();
    render(<FileMenu {...BASE} />);

    await openMenu(user);

    // 시퀀스 열기는 SequenceInput 의 Browse, JANUS 는 MameAppLayout 의 버튼이 담당한다.
    expect(screen.queryByText("file.openSequence")).not.toBeInTheDocument();
    expect(screen.queryByText("export.janusMapping")).not.toBeInTheDocument();
  });

  it("renders app-specific entries the caller passes", async () => {
    const user = userEvent.setup();
    render(<FileMenu {...BASE} extraItems={<div>export.runReport</div>} />);

    await openMenu(user);

    expect(screen.getByText("export.runReport")).toBeInTheDocument();
  });

  it("disables the archive export without a project", async () => {
    const user = userEvent.setup();
    render(<FileMenu {...BASE} hasProject={false} />);

    await openMenu(user);

    // 프로젝트 폴더가 없으면 담을 것이 없다.
    expect(screen.getByText("file.exportProjectZip").closest("[role='menuitem']"))
      .toHaveAttribute("data-disabled");
  });
});

describe("FileMenu sidecar restart", () => {
  it("restarts without asking when nothing is in flight", async () => {
    const user = userEvent.setup();
    const onRestartSidecar = vi.fn();
    render(<FileMenu {...BASE} onRestartSidecar={onRestartSidecar} />);

    await openMenu(user);
    await user.click(screen.getByText("file.restartSidecar"));

    expect(onRestartSidecar).toHaveBeenCalledOnce();
  });

  it("asks first when the app says it is busy, and obeys a refusal", async () => {
    const user = userEvent.setup();
    const onRestartSidecar = vi.fn();
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    render(
      <FileMenu {...BASE} restartConfirmMessage="busy?" onRestartSidecar={onRestartSidecar} />,
    );

    await openMenu(user);
    await user.click(screen.getByText("file.restartSidecar"));

    expect(confirm).toHaveBeenCalledWith("busy?");
    expect(onRestartSidecar).not.toHaveBeenCalled();
    confirm.mockRestore();
  });
});
