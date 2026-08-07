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
  basename,
  filterStillMissing,
  formatSize,
  looksLikeSameTarget,
  useMissingInputs,
  type MissingInput,
} from "@/lib/mame/missingInputs";

import {
  MAME_EXCEL_EXTENSIONS,
  MAME_SEQUENCE_EXTENSIONS,
  toDialogExtensions,
} from "@/lib/mame/fileExtensions";

import {
  MAME_PATH_LABEL_KEYS,
  type MamePathField,
  type RestoredMamePaths,
} from "@/lib/mame/stalePaths";

/** run 폴더만 디렉토리 선택이고 나머지는 파일 선택이다. */
const DIRECTORY_FIELDS = new Set<MamePathField>(["inputDir"]);

/**
 * 필터는 사이드카가 실제로 받는 집합이어야 한다. 넓으면 고른 뒤에야 거부가
 * 오고(csv), 좁으면 되찾을 방법이 사라진다. 복원 직후 reference 가 .gb 였던
 * 조작자는 fa/fasta/fna 필터로는 자기 파일을 볼 수조차 없었다.
 * sequencingSummaryPath 는 3집합에 대응하는 정본이 없어 그대로 둔다.
 */
const FILTERS: Partial<Record<MamePathField, { name: string; extensions: string[] }>> = {
  expectedPath: { name: "Excel", extensions: toDialogExtensions(MAME_EXCEL_EXTENSIONS) },
  referencePath: { name: "Sequence", extensions: toDialogExtensions(MAME_SEQUENCE_EXTENSIONS) },
  customBarcodesPath: { name: "Excel", extensions: toDialogExtensions(MAME_EXCEL_EXTENSIONS) },
  sequencingSummaryPath: { name: "Summary", extensions: ["txt", "tsv"] },
};

export function MissingInputsBanner() {
  const { t } = useTranslation();
  const rawItems = useMissingInputs((s) => s.items);
  const resolve = useMissingInputs((s) => s.resolve);

  // 배너에 남은 항목이라도 해당 필드가 지금 채워져 있으면 표에서 뺀다. 사용자가
  // 배너의 "찾아보기"가 아니라 평소 MAME 입력 패널에서 경로를 다시 잡아도
  // 배너가 사라져야 한다. `resolve()` 호출부는 이 배너 안 하나뿐이라, 그 경로만
  // 믿으면 store 값이 이미 유효해도 항목이 그대로 남는다. 필드별로 나눠 구독해
  // 매 렌더 새 객체를 돌려주는 selector가 불필요한 리렌더를 만들지 않게 한다.
  const inputDir = useMameAppStore((s) => s.inputDir);
  const expectedPath = useMameAppStore((s) => s.expectedPath);
  const referencePath = useMameAppStore((s) => s.referencePath);
  const customBarcodesPath = useMameAppStore((s) => s.rawRunParams.customBarcodesPath);
  const sequencingSummaryPath = useMameAppStore((s) => s.rawRunParams.sequencingSummaryPath);
  const currentPaths: Partial<RestoredMamePaths> = {
    inputDir,
    expectedPath,
    referencePath,
    customBarcodesPath: customBarcodesPath ?? "",
    sequencingSummaryPath: sequencingSummaryPath ?? "",
  };
  const stillMissingFields = new Set(
    filterStillMissing(rawItems.map((i) => i.field), currentPaths),
  );
  const items = rawItems.filter((i) => stillMissingFields.has(i.field));

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
      if (!looksLikeSameTarget(item, { name: basename(selected), size: actualSize })) {
        toast.warning(t("mame.missingInputs.mismatchTitle"), {
          description: t("mame.missingInputs.mismatchBody", {
            expected: item.name,
            actual: basename(selected),
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
