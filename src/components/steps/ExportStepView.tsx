/**
 * ExportStepView — "export" major step 단일 페이지.
 *
 * [source: spec §1 — Export major, 1 sub-step (D2.3)]
 *
 * Sub-step switch 제거 (export.all 단일 sub-step). 전체 export UI를 단일 페이지로 통합.
 */

import { ExportFormatSelector } from "./ExportFormatSelector";
import { OrderSummary } from "./OrderSummary";
import { WorkspaceSaveLoad } from "./WorkspaceSaveLoad";

export function ExportStepView() {
  return (
    <div className="content-card space-y-6">
      <ExportFormatSelector />
      <OrderSummary />
      <WorkspaceSaveLoad />
    </div>
  );
}
