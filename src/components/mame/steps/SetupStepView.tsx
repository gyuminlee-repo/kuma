/**
 * SetupStepView — "setup" mame phase sub-step 디스패처.
 *
 * [source: spec §D2.4 — mame StepView 신규]
 *
 * Sub-step 매핑:
 *   setup.files  → BarcodeSetupPanel(group="files")  — 입력 파일 + 유전자 좌표 + 프로젝트 메타
 *   setup.design → BarcodeSetupPanel(group="design") — 플랭크 + 바인딩 파라미터
 *   setup.output → BarcodeSetupPanel(group="output") — 생성 버튼 + 출력 파일
 */

import { useMameAppStore } from "@/store/mame/mameAppStore";
import { BarcodeSetupPanel } from "@/components/mame/panels/BarcodeSetupPanel";

export function SetupStepView() {
  const subStep = useMameAppStore((s) => s.currentMameSubStep);

  return (
    <div className="content-card">
      {(() => {
        switch (subStep) {
          case "setup.files":
            return <BarcodeSetupPanel group="files" />;
          case "setup.design":
            return <BarcodeSetupPanel group="design" />;
          case "setup.output":
            return <BarcodeSetupPanel group="output" />;
          default:
            return null;
        }
      })()}
    </div>
  );
}
