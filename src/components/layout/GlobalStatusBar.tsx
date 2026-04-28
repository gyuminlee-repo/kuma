import type { ReactNode } from "react";
import { Spinner } from "../ui/Spinner";

/**
 * sidecar 연결 상태.
 * `label`은 컴포넌트 계약상 필수: 색 단독으로 상태를 전달하지 않는다(계획서 §6.2).
 */
export interface SidecarInfo {
  state: "ready" | "connecting" | "error";
  /** 점 옆에 항상 표시되는 텍스트. 빈 문자열 전달 금지. */
  label: string;
  /** error 상태일 때 표시되는 retry 핸들러. */
  onRetry?: () => void;
}

/**
 * autosave 상태 인디케이터.
 * `label`은 색 단독 금지 계약(계획서 §9) 이행용. 빈 문자열 전달 금지.
 */
export interface AutosaveInfo {
  state: "idle" | "saving" | "saved" | "error" | "disabled";
  /** 점 옆에 항상 표시되는 텍스트. */
  label: string;
  /** error 상태일 때 retry 핸들러. */
  onRetry?: () => void;
}

export interface GlobalStatusBarProps {
  /** 좌측 상태 메시지. aria-live="polite" 영역에 표시된다. */
  message: string;
  /** 중앙 슬롯. 서브툴별 요약(수치 등). 생략 가능. */
  centerSlot?: ReactNode;
  /**
   * 우측 sidecar 상태.
   * state별 색:
   *   ready       → bg-success
   *   connecting  → bg-info + Spinner size="sm"
   *   error       → bg-error + retry 버튼
   */
  sidecar: SidecarInfo;
  /**
   * autosave 상태 인디케이터. 생략 또는 state="disabled"이면 렌더하지 않는다.
   * sidecar 인디케이터 좌측에 gap-3으로 배치.
   */
  autosave?: AutosaveInfo;
}

/** sidecar state별 점 색 클래스 */
const SIDECAR_DOT_COLOR: Record<SidecarInfo["state"], string> = {
  ready: "bg-success",
  connecting: "bg-info",
  error: "bg-error",
};

/** autosave state별 점 색 클래스 */
const AUTOSAVE_DOT_COLOR: Record<AutosaveInfo["state"], string> = {
  idle: "bg-success",
  saving: "bg-info",
  saved: "bg-success",
  error: "bg-error",
  disabled: "",
};

/**
 * GlobalStatusBar
 *
 * kuro/mame 양쪽에서 공유하는 하단 상태바 셸.
 * 높이 `h-statusbar`(24px), `text-caption`, 패딩 `px-3`.
 *
 * 계획서 §6.2, §9 준수.
 * - 구형 CSS 변수(verdict/status 계열) 사용 0건 (Phase 3에서 제거 완료)
 * - 색 단독 금지: 점 옆에 항상 label 텍스트 동반
 */
export function GlobalStatusBar({ message, centerSlot, sidecar, autosave }: GlobalStatusBarProps) {
  const sidecarDotClass = SIDECAR_DOT_COLOR[sidecar.state];
  const showAutosave = autosave !== undefined && autosave.state !== "disabled";

  return (
    <footer
      className="h-statusbar px-3 text-caption flex items-center justify-between bg-background border-t border-border"
      role="contentinfo"
      aria-label="Status bar"
    >
      {/* 좌측: 상태 메시지 (aria-live 영역) */}
      <span
        className="flex-1 min-w-0 truncate text-muted-foreground"
        aria-live="polite"
        aria-atomic="true"
      >
        {message}
      </span>

      {/* 중앙: 서브툴별 요약 슬롯 */}
      {centerSlot && (
        <span className="mx-3 shrink-0 text-muted-foreground tabular-nums">
          {centerSlot}
        </span>
      )}

      {/* 우측: autosave + sidecar 인디케이터 묶음 */}
      <span className="flex items-center gap-3 shrink-0">
        {/* autosave 상태 인디케이터 (disabled 또는 미전달 시 숨김) */}
        {showAutosave && (
          <span
            className="flex items-center gap-1.5 text-muted-foreground"
            aria-label={`Autosave: ${autosave.label}`}
          >
            <span
              className={`h-2 w-2 rounded-full shrink-0 ${AUTOSAVE_DOT_COLOR[autosave.state]}`}
              aria-hidden="true"
            />
            <span className="whitespace-nowrap">{autosave.label}</span>
            {autosave.state === "saving" && <Spinner size="sm" />}
            {autosave.state === "error" && autosave.onRetry && (
              <button
                type="button"
                className="text-error underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 transition-colors duration-fast"
                onClick={autosave.onRetry}
                aria-label="Retry autosave"
              >
                retry
              </button>
            )}
          </span>
        )}

        {/* sidecar 상태 표시 */}
        <span className="flex items-center gap-1.5 text-muted-foreground">
          {/* 8px 원형 상태 점 */}
          <span
            className={`h-2 w-2 rounded-full shrink-0 ${sidecarDotClass}`}
            aria-hidden="true"
          />

          {/* 라벨 텍스트 (색 단독 금지 계약 이행) */}
          <span className="whitespace-nowrap">{sidecar.label}</span>

          {/* connecting: Spinner 동반 */}
          {sidecar.state === "connecting" && (
            <Spinner size="sm" />
          )}

          {/* error: retry 링크 */}
          {sidecar.state === "error" && sidecar.onRetry && (
            <button
              type="button"
              className="text-error underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 transition-colors duration-fast"
              onClick={sidecar.onRetry}
              aria-label="Retry sidecar connection"
            >
              retry
            </button>
          )}
        </span>
      </span>
    </footer>
  );
}
