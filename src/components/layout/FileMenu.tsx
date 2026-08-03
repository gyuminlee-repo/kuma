/**
 * FileMenu.tsx, the File menu both app menubars render.
 *
 * v0.13.35.1 renamed the two app-name triggers to `File` so the menubars had the
 * same shape. The contents stayed in two files and drifted anyway: KURO carried
 * project zip import and export while MAME did not, and the two menus reached for
 * different label keys for the same words. A project holds the work of both apps,
 * so a project-level action that exists in one and not the other is a gap rather
 * than a difference of opinion.
 *
 * Everything project-level lives here. What stays with the caller is what only that
 * app can do, passed as `extraItems` and rendered in its own group.
 *
 * Menu entries that a button already performs during normal work are deliberately
 * absent. A second path to the same action is a second place for behaviour to
 * diverge, and the panel versions carry guards the menu ones did not: the sequence
 * Browse button in `SequenceInput` rejects a FASTA with an explanation where
 * `handleOpenSequence` accepted it, and `MameAppLayout` already opens the JANUS
 * export dialog from the pane that has the data in front of the operator.
 */

import { getCurrentWindow } from "@tauri-apps/api/window";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const MOD_KEY = navigator.platform.toLowerCase().includes("mac") ? "⌘" : "Ctrl+";

export interface FileMenuProps {
  /** Trigger styling, owned by each menubar so the bars stay visually identical. */
  triggerClassName: string;
  /** True once a project folder is open. Exporting an archive needs one. */
  hasProject: boolean;
  /** Which sidecar the restart item kills. */
  sidecar: "kuro" | "mame";
  /**
   * Confirmation text when work is in flight, or null to restart without asking.
   * Each app decides what counts as busy, so it decides when to ask.
   */
  restartConfirmMessage: string | null;
  onExportProjectZip: () => void;
  onImportProjectZip: () => void;
  onRestartSidecar: () => void;
  /** App-specific entries, rendered in their own group above the sidecar item. */
  extraItems?: ReactNode;
}

export function FileMenu({
  triggerClassName,
  hasProject,
  restartConfirmMessage,
  onExportProjectZip,
  onImportProjectZip,
  onRestartSidecar,
  extraItems,
}: FileMenuProps) {
  const { t } = useTranslation();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button className={triggerClassName}>{t("menu.file")}</button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        {/*
          프로젝트 선택으로 돌아가는 유일한 경로다. 작업 화면에는 대응하는 버튼이
          없으므로 중복이 아니다.
        */}
        <DropdownMenuItem
          onClick={() => window.dispatchEvent(new CustomEvent("kuma:return-to-home"))}
        >
          <span className="flex-1">{t("file.openProject")}</span>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        {/*
          프로젝트 이식. 아카이브는 프로젝트 폴더 전체를 담으므로 두 앱의 자동 저장과
          산출물이 함께 들어간다(src-tauri/src/project_archive.rs). 그래서 두 메뉴바가
          같은 항목을 보여야 한다.
        */}
        <DropdownMenuItem onClick={onImportProjectZip}>
          <span className="flex-1">{t("file.importProjectZip")}</span>
        </DropdownMenuItem>
        <DropdownMenuItem onClick={onExportProjectZip} disabled={!hasProject}>
          <span className="flex-1">{t("file.exportProjectZip")}</span>
        </DropdownMenuItem>
        {extraItems ? (
          <>
            <DropdownMenuSeparator />
            {extraItems}
          </>
        ) : null}
        <DropdownMenuSeparator />
        {/* §1 Recovery: UI 상태 보존 sidecar 재시작. Zustand 스토어는 메모리에 유지됨 */}
        <DropdownMenuItem
          onClick={() => {
            if (restartConfirmMessage && !window.confirm(restartConfirmMessage)) return;
            onRestartSidecar();
          }}
        >
          <span className="flex-1">{t("file.restartSidecar")}</span>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        {/* close() 는 close 핸들러를 타므로 autosave 가 실행된다. destroy() 는 건너뛴다. */}
        <DropdownMenuItem onClick={() => { void getCurrentWindow().close(); }}>
          <span className="flex-1">{t("menuBar.appMenu.quit")}</span>
          <kbd className="ml-4 text-caption text-muted-foreground">{MOD_KEY}Q</kbd>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
