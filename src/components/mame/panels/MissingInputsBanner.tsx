/**
 * MissingInputsBanner, 복원 후 되찾지 못한 MAME 입력을 다시 지정받는 배너.
 *
 * 프로젝트 폴더 안의 입력은 복원 때 자동 감지가 되찾는다. 여기 남는 것은 폴더
 * 밖에 있던 원천 입력, 실질적으로 raw MinKNOW run 폴더다. 수 GB라 프로젝트에
 * 담기지 않으므로 옮긴 환경에서는 사용자가 다시 골라야 한다.
 *
 * 이전에는 4초짜리 상태 메시지로만 지나가 사라진 줄 모르고 분석을 돌리다
 * 실패했다. 이 배너는 해소될 때까지 남는다.
 *
 * 다시 고른 대상이 원래 것과 크기가 다르면 경고만 하고 값은 받아들인다. 같은
 * 이름의 다른 run 을 붙이는 사고를 막되, 사용자가 의도적으로 교체하는 경우를
 * 차단하지는 않는다.
 */

import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import { open } from "@tauri-apps/plugin-dialog";
import { stat } from "@tauri-apps/plugin-fs";
import { AlertTriangle, FolderOpen } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import {
  formatSize,
  looksLikeSameTarget,
  useMissingInputs,
  type MissingInput,
} from "@/lib/mame/missingInputs";
import { baseName } from "@/lib/pathRef";
import { MAME_PATH_LABEL_KEYS, type MamePathField } from "@/lib/mame/stalePaths";

/** run 폴더만 디렉토리 선택이고 나머지는 파일 선택이다. */
const DIRECTORY_FIELDS = new Set<MamePathField>(["inputDir"]);

const FILTERS: Partial<Record<MamePathField, { name: string; extensions: string[] }>> = {
  expectedPath: { name: "Excel", extensions: ["xlsx"] },
  sampleMapPath: { name: "Excel", extensions: ["xlsx"] },
  referencePath: { name: "Sequence", extensions: ["fa", "fasta", "fna"] },
  customBarcodesPath: { name: "Table", extensions: ["xlsx", "csv"] },
  sequencingSummaryPath: { name: "Summary", extensions: ["txt", "tsv"] },
};

export function MissingInputsBanner() {
  const { t } = useTranslation();
  const items = useMissingInputs((s) => s.items);
  const resolve = useMissingInputs((s) => s.resolve);

  const applyPath = useCallback(
    (field: MamePathField, path: string) => {
      const store = useMameAppStore.getState();
      switch (field) {
        case "inputDir":
          store.setInputDir(path);
          break;
        case "expectedPath":
          store.setExpectedPath(path);
          break;
        case "referencePath":
          store.setReferencePath(path);
          break;
        case "sampleMapPath":
          store.setSampleMapPath(path);
          break;
        case "customBarcodesPath":
          store.setParams({ rawRunParams: { customBarcodesPath: path } });
          break;
        case "sequencingSummaryPath":
          store.setParams({ rawRunParams: { sequencingSummaryPath: path } });
          break;
      }
    },
    [],
  );

  const relocate = useCallback(
    async (item: MissingInput) => {
      const isDir = DIRECTORY_FIELDS.has(item.field);
      const filter = FILTERS[item.field];
      const selected = await open({
        directory: isDir,
        multiple: false,
        title: t("mame.missingInputs.chooseTitle", { name: item.name }),
        ...(!isDir && filter ? { filters: [filter] } : {}),
      });
      if (typeof selected !== "string") return;

      // 크기 대조는 파일에만 의미가 있다. 폴더는 stat 이 크기를 주지 않는다.
      let actualSize: number | undefined;
      if (!isDir) {
        try {
          actualSize = (await stat(selected)).size;
        } catch {
          // 크기를 못 읽으면 대조를 생략한다. 읽기 실패가 불일치의 근거는 아니다.
          actualSize = undefined;
        }
      }
      if (!looksLikeSameTarget(item, { name: baseName(selected), size: actualSize })) {
        toast.warning(t("mame.missingInputs.mismatchTitle"), {
          description: t("mame.missingInputs.mismatchBody", {
            expected: item.name,
            actual: baseName(selected),
          }),
          duration: 8000,
        });
      }
      applyPath(item.field, selected);
      resolve(item.field);
    },
    [applyPath, resolve, t],
  );

  if (items.length === 0) return null;

  return (
    <section
      role="status"
      aria-labelledby="missing-inputs-heading"
      className="rounded-md border border-amber-500/40 bg-amber-500/10 p-4"
    >
      <div className="flex items-start gap-2">
        <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-600" aria-hidden />
        <div className="min-w-0 flex-1">
          <h3 id="missing-inputs-heading" className="text-sm font-medium">
            {t("mame.missingInputs.title")}
          </h3>
          <p className="mt-1 text-xs text-muted-foreground">
            {t("mame.missingInputs.description")}
          </p>
          <ul className="mt-3 space-y-2">
            {items.map((item) => {
              const size = formatSize(item.size);
              return (
                <li
                  key={item.field}
                  className="flex flex-wrap items-center justify-between gap-2"
                >
                  <div className="min-w-0">
                    <span className="text-xs font-medium">
                      {t(MAME_PATH_LABEL_KEYS[item.field])}
                    </span>
                    <span className="ml-2 truncate text-xs text-muted-foreground">
                      {item.name}
                      {size ? ` (${size})` : ""}
                    </span>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => void relocate(item)}
                  >
                    <FolderOpen className="mr-1 size-3.5" aria-hidden />
                    {t("mame.missingInputs.browse")}
                  </Button>
                </li>
              );
            })}
          </ul>
        </div>
      </div>
    </section>
  );
}
