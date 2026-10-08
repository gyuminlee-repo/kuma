/**
 * HydrationOverlay, 자동 저장 복원 중 화면 전체를 덮는 차단 오버레이.
 *
 * 복원 구간(resetAll → readAutosave → applyKuroSnapshot → MAME 복원 → auto-detect)
 * 동안 사용자가 입력한 값을 applyKuroSnapshot이 조용히 덮어쓰는 문제를 막는다.
 * 버튼뿐 아니라 입력 필드까지 포인터 접근을 차단하고, 잘못 연 프로젝트에서
 * 빠져나갈 취소 경로를 제공한다.
 *
 * 차단과 표시를 분리한다. 차단 레이어는 open과 동시에(t=0) 깔리고 스피너 카드만
 * DELAY_MS 뒤에 나타난다. 로컬 파일 읽기로 끝나는 빠른 경로에서 모달이 번쩍이지
 * 않으면서도 resetAll 직후 구간이 무방비로 열리지 않는다. 둘은 마운트 시점이 다르고
 * 역할도 다르므로(투명 차단막 vs 흐림 배경 + 카드) 형제로 렌더한다. open이 내려가면
 * 둘 다 같은 프레임에 함께 걷힌다.
 *
 * document.body로 portal한다. GuidedTour가 #root에 inert=true를 걸기 때문에
 * MainShell 서브트리에 그대로 렌더하면 취소 버튼이 포커스·클릭 불가가 된다.
 *
 * ESC는 즉시 취소가 아니라 확인 단계를 띄우고, 백드롭 클릭은 무시한다(오조작 방지).
 * 헌장 §7이 진행 중 작업 모달을 ESC/backdrop 닫기 [필수]의 예외로 두므로 이 조합이 규정에 맞다.
 */

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { Spinner } from "@/components/ui/Spinner";
import type { HydrationPhase } from "@/hooks/useAutosaveHydration";

/** 지연 표시 임계값. 이보다 빨리 끝나는 복원에는 카드를 띄우지 않는다(차단은 t=0). */
const DELAY_MS = 400;

/**
 * 카드가 떠 있던 상태로 닫힌 뒤 이 시간 안에 다시 열리면 DELAY_MS를 건너뛰고 즉시 띄우는 유예.
 * 유예는 표시 타이밍에만 관여한다. 차단 레이어, 카드, 확인 단계, 키 트랩은 open이 내려가는
 * 즉시 걷힌다(복원이 끝난 뒤에도 입력을 먹는 구간을 만들지 않는다).
 *
 * 왕복이 실제로 일어나는 근거: App.tsx handleOpenWorkspace는 비-scratch 경로에서
 * await loadProject(path)를 먼저 기다린 뒤 setProject를 부른다. 그 await 구간에 이전 프로젝트
 * 복원 run의 finally가 setHydrating(false)를 실행하므로 open이 false→true로 왕복한다.
 * 그때 DELAY_MS를 다시 기다리면 새 프로젝트의 resetAll 구간이 시각적으로 비어 카드가 깜빡인다.
 */
const GRACE_MS = 150;

/**
 * 복원 단계 → locale 키. 문자열 조합("hydrationOverlay.phase" + phase)이 아니라 명시적 맵이라
 * satisfies가 키 누락과 오타를 컴파일 타임에 잡는다.
 */
const PHASE_KEYS = {
  reset: "hydrationOverlay.phaseReset",
  workspace: "hydrationOverlay.phaseWorkspace",
  kuro: "hydrationOverlay.phaseKuro",
  mame: "hydrationOverlay.phaseMame",
  detect: "hydrationOverlay.phaseDetect",
} as const satisfies Record<HydrationPhase, string>;

/**
 * 오버레이 카드 안의 버튼들 사이로만 포커스를 순환시킨다.
 * 기본 화면은 버튼 1개, 확인 단계는 2개라 두 버튼 모두 키보드로 닿아야 한다.
 */
function cycleFocus(card: HTMLElement | null, backwards: boolean): void {
  if (!card) return;
  const buttons = Array.from(card.querySelectorAll<HTMLButtonElement>("button"));
  if (buttons.length === 0) {
    card.focus();
    return;
  }
  const current = buttons.findIndex((button) => button === document.activeElement);
  const next =
    current === -1
      ? backwards
        ? buttons.length - 1
        : 0
      : (current + (backwards ? -1 : 1) + buttons.length) % buttons.length;
  buttons[next]?.focus();
}

/**
 * 이 키 이벤트가 오버레이보다 위층 모달의 것인가. true면 오버레이는 손대지 않고 넘긴다.
 *
 * 오버레이는 z-[45]라 z-50 모달(ui/dialog.tsx의 overlay·content, MainShell.tsx의 메모리
 * 초과 alertdialog)보다 아래에 깔린다. 그 모달들은 복원 중에도 오버레이 위에 그려지고
 * 마우스로 조작 가능하다. 그런데 아래 window capture 트랩이 화면에 무엇이 있든 Tab을
 * preventDefault하고 포커스를 자기 카드로 되돌리며 ESC를 자기 확인 단계로 소비하면,
 * 키보드만 쓰는 사용자에게는 그 모달을 해제할 방법이 남지 않는다(8초짜리 복원 중
 * 메모리 감시가 block 레벨을 발화하는 경로가 실제로 있다). 위층 모달은 자체 포커스
 * 트랩과 ESC 처리를 가지므로 그 몫의 키는 그대로 흘려보내는 것이 안전하다.
 *
 * 카드 밖이면서 모달 조상도 없으면 배경 앱이다. 그때는 기존 트랩을 유지한다.
 * 그것이 이 오버레이의 원래 목적인 "복원 중 배경 조작 차단"이다.
 */
function isFromLayeredModal(ev: KeyboardEvent, card: HTMLElement | null): boolean {
  // 타깃과 activeElement를 함께 본다. Radix FocusScope가 포커스를 가져가면 이벤트 타깃이
  // body가 아니라 그 모달 내부 요소가 되고, 반대로 타깃은 body인데 포커스만 모달 안에
  // 들어가 있는 조합도 나온다.
  const target = ev.target instanceof Node ? ev.target : null;
  const active = document.activeElement instanceof Node ? document.activeElement : null;
  for (const node of [target, active]) {
    if (node === null) continue;
    // 카드 안이면 트랩 대상이다. 카드 자체가 role="dialog"라 이 검사가 closest보다 앞서야
    // 한다. 순서가 뒤집히면 카드가 자기 셀렉터에 걸려 트랩이 통째로 죽는다.
    if (card?.contains(node)) return false;
    const element = node instanceof Element ? node : node.parentElement;
    if (element?.closest('[role="dialog"], [role="alertdialog"]')) return true;
  }
  return false;
}

export interface HydrationOverlayProps {
  open: boolean;
  onCancel: () => void;
  /**
   * 현재 복원 단계. useAutosaveHydration이 돌려주는 값을 그대로 받는다.
   *
   * 범용 statusMessage를 받던 자리다. 그 prop은 두 가지로 죽어 있었다. MainShell 상태바가
   * 같은 문자열을 role="status" aria-live="polite"로 이미 렌더해 중복 announce가 됐고,
   * 그 state는 4초 자동 소멸이라 주 복원 메시지가 인디케이터 라벨로만 흘러 8초짜리 복원 내내
   * 빈 문자열이었다. 단계 채널은 훅이 직접 올려 주므로 두 문제가 함께 사라진다.
   */
  phase?: HydrationPhase | null;
  /** 프로젝트 없이 시작한 scratch 세션. 열지도 않은 프로젝트를 가리키는 문구를 피한다. */
  scratch?: boolean;
}

export function HydrationOverlay({
  open,
  onCancel,
  phase,
  scratch = false,
}: HydrationOverlayProps) {
  const { t } = useTranslation();
  const [visible, setVisible] = useState(false);
  // ESC는 즉시 취소하지 않고 이 확인 단계를 거친다.
  const [confirming, setConfirming] = useState(false);
  const cardRef = useRef<HTMLDivElement | null>(null);
  const keepWaitingRef = useRef<HTMLButtonElement | null>(null);
  // 카드가 떠 있던 상태로 닫혔고 아직 GRACE_MS가 지나지 않았다. 다음 open에서 DELAY_MS를 건너뛴다.
  const recentlyVisibleRef = useRef(false);
  const graceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // 유예 타이머는 언마운트에서만 정리한다. 아래 표시 effect의 cleanup에 매달 수 없다.
  // 그 effect가 setVisible(false)를 부르는 순간 deps(visible)가 바뀌어 cleanup이 돌고
  // 방금 건 타이머를 스스로 취소해 버린다.
  useEffect(() => {
    return () => {
      if (graceTimerRef.current !== null) clearTimeout(graceTimerRef.current);
    };
  }, []);

  // deps는 open과 visible. onCancel은 넣지 않는다. 호출부가 인라인 화살표를 넘길 때
  // 타이머가 매 렌더 리셋돼 오버레이가 영영 뜨지 않는다.
  useEffect(() => {
    if (!open) {
      if (!visible) return;
      // 닫히면 카드와 확인 단계를 즉시 걷는다. 복원이 끝난 뒤에도 카드를 띄워 두면
      // fixed inset-0 래퍼가 포인터를 계속 먹고, 아래 키 트랩이 Tab·ESC를 가로채
      // 곧바로 마운트되는 ProjectTourCoordinator 조작이 죽는다.
      setVisible(false);
      setConfirming(false);
      // 남기는 것은 "곧 다시 열리면 DELAY_MS를 건너뛴다"는 표시뿐이다.
      recentlyVisibleRef.current = true;
      if (graceTimerRef.current !== null) clearTimeout(graceTimerRef.current);
      graceTimerRef.current = setTimeout(() => {
        graceTimerRef.current = null;
        recentlyVisibleRef.current = false;
      }, GRACE_MS);
      return;
    }
    // 이미 떠 있으면 지연 타이머를 다시 걸지 않는다.
    if (visible) return;
    if (recentlyVisibleRef.current) {
      // 유예 안에 돌아온 프로젝트 전환. 400ms를 다시 기다리면 새 프로젝트의 resetAll 구간이
      // 시각적으로 비어 카드가 깜빡인다. 차단 자체는 blocker가 t=0에 붙어 이와 무관하다.
      if (graceTimerRef.current !== null) clearTimeout(graceTimerRef.current);
      graceTimerRef.current = null;
      recentlyVisibleRef.current = false;
      setVisible(true);
      return;
    }
    const timer: ReturnType<typeof setTimeout> = setTimeout(() => setVisible(true), DELAY_MS);
    return () => clearTimeout(timer);
  }, [open, visible]);

  // capture 단계로 window에 등록한다. 버블 단계 document 리스너는 Cmd/Ctrl+D 같은
  // 전역 단축키가 AppLayout까지 올라가 복원 중 설계를 실행시키는 구멍을 남긴다.
  useEffect(() => {
    // open이 내려가면 트랩도 같은 프레임에 해제한다. 유예 동안 리스너를 살려 두면
    // 복원이 끝난 화면에서 Tab·ESC가 150ms 동안 먹히지 않는다.
    if (!open) return;
    const onKeyDown = (ev: KeyboardEvent) => {
      // 오버레이 위에 뜬 모달의 키는 그 모달 몫이다. preventDefault도 stopPropagation도
      // 하지 않고 즉시 물러난다(근거는 isFromLayeredModal 주석).
      if (isFromLayeredModal(ev, cardRef.current)) return;
      if (ev.key === "Escape") {
        ev.stopPropagation();
        if (!visible) return;
        ev.preventDefault();
        // false→true는 확인 요청, true→false는 물러나기. ESC 연타로 튕겨나가지 않는다.
        setConfirming((previous) => !previous);
        return;
      }
      if (ev.key === "Tab") {
        if (!visible) return;
        ev.preventDefault();
        ev.stopPropagation();
        cycleFocus(cardRef.current, ev.shiftKey);
        return;
      }
      // preventDefault는 하지 않는다. Cmd+C/Cmd+V와 Tauri 메뉴 accelerator를 깨지 않기 위해서다.
      if (ev.metaKey || ev.ctrlKey) {
        ev.stopPropagation();
      }
    };
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, [open, visible]);

  // deps는 visible만. confirming을 넣으면 토글마다 cleanup이 돌아
  // 포커스가 오버레이 밖으로 되돌아간다.
  useEffect(() => {
    if (!visible) return;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    cardRef.current?.focus();
    return () => {
      previous?.focus();
    };
  }, [visible]);

  // 확인 단계에서는 안전한 쪽(계속 기다리기)에 포커스를 둔다.
  useEffect(() => {
    if (!visible || !confirming) return;
    keepWaitingRef.current?.focus();
  }, [visible, confirming]);

  if (!open) return null;

  const buttonClass =
    "w-full rounded-control border border-border px-4 py-2 text-sm font-medium text-foreground hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

  // scratch 세션은 열어둔 프로젝트가 없다. "프로젝트 복원 중" 문구를 그대로 쓰면
  // 존재하지 않는 프로젝트를 가리키게 되므로 제목·설명 4키만 갈아끼운다.
  // cancel / keepWaiting / confirmLeave는 두 모드가 공유한다.
  const titleKey = scratch ? "hydrationOverlay.titleScratch" : "hydrationOverlay.title";
  const descriptionKey = scratch
    ? "hydrationOverlay.descriptionScratch"
    : "hydrationOverlay.description";
  const confirmTitleKey = scratch
    ? "hydrationOverlay.confirmTitleScratch"
    : "hydrationOverlay.confirmTitle";
  const confirmDescriptionKey = scratch
    ? "hydrationOverlay.confirmDescriptionScratch"
    : "hydrationOverlay.confirmDescription";

  // 복원 단계 문구. 정적 문구만으로는 얼마나 남았는지 알 수 없어 취소를 누르게 된다.
  const phaseText = phase ? t(PHASE_KEYS[phase]) : "";

  return createPortal(
    // z-[45]는 "모든 모달 아래, 모든 콘텐츠 위" 한 층이다.
    // 아래에 두는 것: 콘텐츠·플로팅 패널 최고층인 z-40(JobQueuePanel, LogPanel,
    // AnalyzeStepView 전체화면 플레이트). 복원 중에는 이들이 차단돼야 한다.
    // 위에 두는 것: 모달 계층 최저값 z-50(ui/dialog.tsx overlay·content, dropdown-menu,
    // popover, select, MainShell 메모리 초과 alertdialog, MAME 토스트, 결과 popover 4종).
    // 이전 근거였던 "portal이라 DOM 뒤에 붙어 위에 그려진다"는 거짓이다. MainShell의
    // 메모리 초과 모달(MainShell.tsx의 role="alertdialog")은 portal을 쓰지 않고 #root 안에
    // 인라인 렌더된다. #root와 body 사이에 stacking context를 만드는 요소가 없어 두 층이
    // 루트 stacking context에서 직접 겨루는데, z가 동률이면 나중에 append된 이 portal이
    // 이겨 경고가 백드롭에 가리고 유일한 확인 버튼이 차단 레이어에 먹혔다.
    // GuidedTour(z-[80])와의 충돌은 MainShell의 !hydrating 투어 게이트가 담당한다.
    <>
      {/* 차단 레이어는 open과 동시에 깔리고 open과 동시에 걷힌다. */}
      <div className="fixed inset-0 z-[45]" data-testid="hydration-blocker" aria-hidden="true" />
      {/* 카드는 형제로 둔다. 마운트 시점(t=0 vs DELAY_MS)과 역할이 다르다.
          백드롭 클릭은 무시한다(핸들러 없음). */}
      {visible && (
        <div className="fixed inset-0 z-[45] flex items-center justify-center bg-background/80 backdrop-blur-sm">
          <div
            ref={cardRef}
            tabIndex={-1}
            role="dialog"
            aria-modal="true"
            aria-busy="true"
            aria-labelledby="hydration-overlay-title"
            aria-describedby="hydration-overlay-desc"
            className="w-full max-w-sm rounded-lg border border-border bg-card p-6 shadow-lg focus:outline-none"
          >
            {/* 제목·설명·진행 문구는 확인 단계 토글에도 같은 노드를 유지하고 키만 갈아끼운다.
                두 화면을 통째로 배타 렌더하면 아래 live region이 토글마다 언마운트돼
                스크린리더가 갱신으로 인식하지 못한다. */}
            <div className="flex items-center gap-3">
              {!confirming && <Spinner size="md" />}
              <h2 id="hydration-overlay-title" className="text-sm font-medium text-foreground">
                {t(confirming ? confirmTitleKey : titleKey)}
              </h2>
            </div>
            <p id="hydration-overlay-desc" className="mt-3 text-caption text-muted-foreground">
              {t(confirming ? confirmDescriptionKey : descriptionKey)}
            </p>
            {/* 컨테이너는 항상 마운트하고 내부 텍스트만 비운다. 여백만 문구 유무로 갈린다. */}
            <p
              aria-live="polite"
              data-testid="hydration-status"
              className={`text-caption text-muted-foreground${phaseText ? " mt-2" : ""}`}
            >
              {phaseText}
            </p>
            {confirming ? (
              <div className="mt-4 flex gap-2">
                <button
                  ref={keepWaitingRef}
                  type="button"
                  className={buttonClass}
                  onClick={() => setConfirming(false)}
                >
                  {t("hydrationOverlay.keepWaiting")}
                </button>
                <button type="button" className={buttonClass} onClick={onCancel}>
                  {t("hydrationOverlay.confirmLeave")}
                </button>
              </div>
            ) : (
              <button type="button" className={`mt-4 ${buttonClass}`} onClick={onCancel}>
                {t("hydrationOverlay.cancel")}
              </button>
            )}
          </div>
        </div>
      )}
    </>,
    document.body,
  );
}
