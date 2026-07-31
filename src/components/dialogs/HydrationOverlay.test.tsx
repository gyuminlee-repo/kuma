import { readFileSync } from "node:fs";
import { join } from "node:path";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import en from "@/locales/en.json";
import { HydrationOverlay } from "./HydrationOverlay";

/** 지연 표시 임계값. 컴포넌트의 DELAY_MS와 같아야 한다. */
const DELAY_MS = 400;

/**
 * 카드가 떠 있던 상태로 닫힌 뒤 이 시간 안에 다시 열리면 DELAY_MS를 건너뛰는 유예.
 * 컴포넌트의 GRACE_MS와 같아야 한다. 유예는 표시 타이밍에만 관여한다. 차단 레이어·카드·
 * 확인 단계·키 트랩은 open이 내려가는 즉시 걷힌다(아래 [R7] 5케이스가 고정한다).
 */
const GRACE_MS = 150;

/**
 * test-setup.ts가 initI18n("en")을 돌리므로 t()는 en.json 값을 그대로 돌려준다.
 * 문구를 테스트에 다시 적지 않고 locale 원본을 참조한다.
 */
const L = en.hydrationOverlay;

function advance(ms: number): void {
  act(() => {
    vi.advanceTimersByTime(ms);
  });
}

function noop(): void {}

/**
 * 콘텐츠·플로팅 패널 최고층. JobQueuePanel·LogPanel·AnalyzeStepView 전체화면 플레이트가
 * 쓰는 값이고 HydrationOverlay.tsx의 z 근거 주석과 같은 숫자다. 복원 중 이 층이 차단되려면
 * 오버레이가 이보다 위여야 한다.
 */
const CONTENT_TOP_Z = 40;

/**
 * "z-50", "z-[45]" 형태의 z 클래스를 모두 찾아 숫자만 뽑는다.
 * 끝 경계는 임의값 형태(`z-[45]`)에 걸리지 않도록 맨숫자 가지에만 붙인다.
 */
function zValues(source: string): number[] {
  return Array.from(source.matchAll(/\bz-(?:\[(\d+)\]|(\d+)\b)/g)).map((match) =>
    Number(match[1] ?? match[2]),
  );
}

/**
 * MainShell 메모리 초과 alertdialog의 className. role 마커 뒤 첫 className만 잘라내
 * 같은 파일의 다른 층 z가 섞이지 않게 한다.
 */
function alertDialogClassName(): string {
  const source = readFileSync(join(process.cwd(), "src/screens/MainShell.tsx"), "utf8");
  const start = source.indexOf('role="alertdialog"');
  expect(start).toBeGreaterThan(-1);
  const className = /className="([^"]*)"/.exec(source.slice(start));
  expect(className).not.toBeNull();
  return className?.[1] ?? "";
}

describe("HydrationOverlay", () => {
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("open과 동시에 차단 레이어가 깔리고 카드는 400ms 전까지 뜨지 않는다", () => {
    vi.useFakeTimers();
    render(<HydrationOverlay open onCancel={noop} />);

    // 시간 진행 없이(t=0) 차단만 먼저 걸린다. resetAll 직후 구간이 무방비로
    // 열리지 않는 것이 이 오버레이의 존재 이유다.
    expect(screen.getByTestId("hydration-blocker")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).toBeNull();

    advance(DELAY_MS - 1);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("400ms 후 카드가 뜨고 포커스가 다이얼로그 컨테이너로 옮겨간다", () => {
    vi.useFakeTimers();
    render(<HydrationOverlay open onCancel={noop} />);

    advance(DELAY_MS);
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAttribute("aria-busy", "true");
    expect(dialog).toHaveAttribute("tabindex", "-1");
    expect(document.activeElement).toBe(dialog);
  });

  it("Tab이 오버레이 안에 갇힌다", () => {
    vi.useFakeTimers();
    // 오버레이 바깥의 포커스 가능한 요소. 트랩이 깨지면 여기로 새어 나간다.
    const outside = document.createElement("button");
    outside.textContent = "outside";
    document.body.appendChild(outside);
    try {
      render(<HydrationOverlay open onCancel={noop} />);
      advance(DELAY_MS);

      const dialog = screen.getByRole("dialog");
      const cancelButton = screen.getByRole("button", { name: L.cancel });

      fireEvent.keyDown(document.body, { key: "Tab" });
      expect(document.activeElement).toBe(cancelButton);

      // 버튼이 하나뿐인 기본 화면에서는 같은 버튼으로 되돌아온다.
      fireEvent.keyDown(document.body, { key: "Tab" });
      expect(document.activeElement).toBe(cancelButton);
      expect(dialog.contains(document.activeElement)).toBe(true);

      fireEvent.keyDown(document.body, { key: "Tab", shiftKey: true });
      expect(dialog.contains(document.activeElement)).toBe(true);
      expect(document.activeElement).not.toBe(outside);
    } finally {
      outside.remove();
    }
  });

  it("[R5] 오버레이 위에 뜬 모달의 Tab·ESC는 가로채지 않는다", () => {
    vi.useFakeTimers();
    const onCancel = vi.fn();
    // 오버레이(z-[45]) 위에 그려지는 z-50 모달. 8초짜리 복원 도중 메모리 감시가 block
    // 레벨을 발화해 MainShell의 alertdialog가 뜨는 경로를 최소 형태로 재현한다.
    const modal = document.createElement("div");
    modal.setAttribute("role", "alertdialog");
    const modalButton = document.createElement("button");
    modalButton.textContent = "dismiss";
    modal.appendChild(modalButton);
    document.body.appendChild(modal);
    // window 버블 스파이. 오버레이는 window capture에서 stopPropagation하므로 여기까지
    // 올라왔다면 가로채지 않은 것이다.
    const appKeys = vi.fn();
    window.addEventListener("keydown", appKeys);
    try {
      render(<HydrationOverlay open onCancel={onCancel} />);
      // 카드가 뜬 뒤에 포커스를 옮긴다. 표시 effect가 cardRef로 포커스를 가져가므로
      // 순서가 뒤바뀌면 오버레이가 포커스를 되찾아 이 케이스가 아무것도 검증하지 못한다.
      advance(DELAY_MS);
      modalButton.focus();
      expect(document.activeElement).toBe(modalButton);

      fireEvent.keyDown(modalButton, { key: "Tab" });
      fireEvent.keyDown(modalButton, { key: "Escape" });

      // 두 키 모두 오버레이를 통과했다. 막히면 키보드 사용자에게 경고를 해제할 방법이 없다.
      expect(appKeys).toHaveBeenCalledTimes(2);
      // Tab이 포커스를 오버레이 카드로 끌어가지 않았다.
      expect(document.activeElement).toBe(modalButton);
      // ESC를 오버레이가 소비하지 않았다(확인 단계가 뜨지 않고 기본 화면 그대로다).
      expect(screen.queryByText(L.confirmTitle)).toBeNull();
      expect(screen.getByText(L.title)).toBeInTheDocument();
      expect(onCancel).not.toHaveBeenCalled();
    } finally {
      window.removeEventListener("keydown", appKeys);
      modal.remove();
    }
  });

  it("[R5] 카드가 뜨기 전 차단막만 깔린 구간에서도 위층 모달의 ESC는 통과한다", () => {
    vi.useFakeTimers();
    const onCancel = vi.fn();
    // 차단막은 t=0에 깔리고 카드는 400ms 뒤에 뜬다. 그 사이 구간은 cardRef가 아직 null이라
    // 판정이 closest만으로 갈리고, ESC 분기는 visible 검사보다 stopPropagation이 앞서
    // 무조건 삼켜지던 자리다. 빠른 복원 중에 발화한 경고도 해제 가능해야 한다.
    const modal = document.createElement("div");
    modal.setAttribute("role", "alertdialog");
    const modalButton = document.createElement("button");
    modalButton.textContent = "dismiss";
    modal.appendChild(modalButton);
    document.body.appendChild(modal);
    const appKeys = vi.fn();
    window.addEventListener("keydown", appKeys);
    try {
      render(<HydrationOverlay open onCancel={onCancel} />);
      // 시간 전진 없이 확인한다. 차단막은 있고 카드는 아직 없다.
      expect(screen.getByTestId("hydration-blocker")).toBeInTheDocument();
      expect(screen.queryByRole("dialog")).toBeNull();
      modalButton.focus();

      fireEvent.keyDown(modalButton, { key: "Escape" });
      expect(appKeys).toHaveBeenCalledTimes(1);
      expect(onCancel).not.toHaveBeenCalled();
    } finally {
      window.removeEventListener("keydown", appKeys);
      modal.remove();
    }
  });

  it("복원 중에는 수식키 단축키가 앱 핸들러까지 올라가지 않는다", () => {
    vi.useFakeTimers();
    // AppLayout.tsx의 등록과 같은 대상·같은 단계(window, 버블)로 스파이를 건다.
    // document 버블에 걸면 window capture의 stopPropagation과 무관하게
    // 통과해 버려 테스트가 늘 통과한다.
    const appShortcut = vi.fn();
    window.addEventListener("keydown", appShortcut);
    try {
      const { rerender } = render(<HydrationOverlay open onCancel={noop} />);
      advance(DELAY_MS);

      // Cmd/Ctrl+D는 AppLayout에서 design run을 띄운다. 복원 중에는 막혀야 한다.
      fireEvent.keyDown(document.body, { key: "d", ctrlKey: true });
      fireEvent.keyDown(document.body, { key: "d", metaKey: true });
      expect(appShortcut).not.toHaveBeenCalled();

      // 오버레이가 걷히면 같은 키가 다시 앱까지 도달한다(스파이 자체가 죽어
      // 있어서 통과한 것이 아님을 확인).
      rerender(<HydrationOverlay open={false} onCancel={noop} />);
      advance(GRACE_MS);
      fireEvent.keyDown(document.body, { key: "d", ctrlKey: true });
      expect(appShortcut).toHaveBeenCalledTimes(1);
    } finally {
      window.removeEventListener("keydown", appShortcut);
    }
  });

  it("ESC는 즉시 취소하지 않고 확인 단계를 띄운다", () => {
    vi.useFakeTimers();
    const onCancel = vi.fn();
    render(<HydrationOverlay open onCancel={onCancel} />);

    advance(DELAY_MS);
    fireEvent.keyDown(document.body, { key: "Escape" });

    expect(onCancel).not.toHaveBeenCalled();
    expect(screen.getByText(L.confirmTitle)).toBeInTheDocument();
    expect(screen.getAllByRole("button")).toHaveLength(2);
  });

  it("확인 단계에서 나가기를 누르면 onCancel을 호출한다", () => {
    vi.useFakeTimers();
    const onCancel = vi.fn();
    render(<HydrationOverlay open onCancel={onCancel} />);

    advance(DELAY_MS);
    fireEvent.keyDown(document.body, { key: "Escape" });
    fireEvent.click(screen.getByRole("button", { name: L.confirmLeave }));

    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("확인 단계에서 ESC를 한 번 더 누르면 기본 화면으로 후퇴한다", () => {
    vi.useFakeTimers();
    const onCancel = vi.fn();
    render(<HydrationOverlay open onCancel={onCancel} />);

    advance(DELAY_MS);
    fireEvent.keyDown(document.body, { key: "Escape" });
    fireEvent.keyDown(document.body, { key: "Escape" });

    expect(onCancel).not.toHaveBeenCalled();
    expect(screen.queryByText(L.confirmTitle)).toBeNull();
    expect(screen.getByText(L.title)).toBeInTheDocument();
    expect(screen.getAllByRole("button")).toHaveLength(1);
  });

  it("기본 화면 취소 버튼은 확인 단계 없이 onCancel을 호출한다", () => {
    vi.useFakeTimers();
    const onCancel = vi.fn();
    render(<HydrationOverlay open onCancel={onCancel} />);

    advance(DELAY_MS);
    fireEvent.click(screen.getByRole("button", { name: L.cancel }));

    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("[R7] open이 내려가면 차단 레이어와 카드가 같은 프레임에 걷힌다", () => {
    vi.useFakeTimers();
    const { rerender } = render(<HydrationOverlay open onCancel={noop} />);

    advance(DELAY_MS);
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    rerender(<HydrationOverlay open={false} onCancel={noop} />);
    // 시간 전진 없이 확인한다. 복원이 끝난 뒤에도 카드를 남기면 fixed inset-0 래퍼가
    // 포인터를 계속 먹어, 곧바로 마운트되는 투어 조작이 유예 동안 죽는다.
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.queryByTestId("hydration-blocker")).toBeNull();
  });

  it("[R7] 유예 안에 다시 열리면 DELAY_MS 없이 카드가 즉시 돌아온다", () => {
    vi.useFakeTimers();
    const { rerender } = render(<HydrationOverlay open onCancel={noop} />);

    advance(DELAY_MS);
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    // 프로젝트 A→B 전환은 open을 false→true로 왕복시킨다(App.tsx handleOpenWorkspace가
    // await loadProject를 먼저 기다리는 동안 A의 finally가 hydrating을 내린다).
    rerender(<HydrationOverlay open={false} onCancel={noop} />);
    advance(GRACE_MS - 1);

    rerender(<HydrationOverlay open onCancel={noop} />);
    // DELAY_MS를 다시 기다리지 않는다. 시간 전진 없이 그대로 떠 있어야 한다.
    // 여기서 400ms를 다시 채우면 B의 resetAll 구간에 카드가 깜빡인다.
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByTestId("hydration-blocker")).toBeInTheDocument();

    // 유예 타이머가 setVisible(false)를 거는 구현으로 회귀하면 여기서 카드가 사라진다.
    // 현재 구현의 타이머는 "다음 open에서 지연을 건너뛴다"는 ref만 내린다.
    advance(GRACE_MS + DELAY_MS);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("[R7] 유예를 넘겨 다시 열면 DELAY_MS를 처음부터 다시 기다린다", () => {
    vi.useFakeTimers();
    const { rerender } = render(<HydrationOverlay open onCancel={noop} />);

    advance(DELAY_MS);
    fireEvent.keyDown(document.body, { key: "Escape" });
    expect(screen.getByText(L.confirmTitle)).toBeInTheDocument();

    rerender(<HydrationOverlay open={false} onCancel={noop} />);
    advance(GRACE_MS);

    rerender(<HydrationOverlay open onCancel={noop} />);
    // 차단은 t=0에 다시 깔리지만 카드는 지연을 다시 채워야 뜬다.
    expect(screen.getByTestId("hydration-blocker")).toBeInTheDocument();
    advance(DELAY_MS - 1);
    expect(screen.queryByRole("dialog")).toBeNull();

    advance(1);
    // 확인 단계는 open이 내려갈 때 초기화됐으므로 기본 화면에서 시작한다.
    expect(screen.getByText(L.title)).toBeInTheDocument();
    expect(screen.queryByText(L.confirmTitle)).toBeNull();
    expect(screen.getAllByRole("button")).toHaveLength(1);
  });

  it("[R7] 카드가 뜨기 전에 닫혔으면 유예가 서지 않아 다시 DELAY_MS를 채운다", () => {
    vi.useFakeTimers();
    const { rerender } = render(<HydrationOverlay open onCancel={noop} />);

    // 카드가 뜨기 직전에 끝난 빠른 복원. 유예 표시는 카드가 떠 있던 경우에만 선다.
    advance(DELAY_MS - 1);
    rerender(<HydrationOverlay open={false} onCancel={noop} />);
    rerender(<HydrationOverlay open onCancel={noop} />);

    advance(DELAY_MS - 1);
    expect(screen.queryByRole("dialog")).toBeNull();
    advance(1);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("[R7] 유예 중에는 ESC·Tab 트랩이 이미 해제돼 있다", () => {
    vi.useFakeTimers();
    // 오버레이는 window capture 단계에서 stopPropagation한다. 같은 대상의 버블 리스너가
    // 이벤트를 받았다면 트랩이 풀린 것이다.
    const appKeys = vi.fn();
    window.addEventListener("keydown", appKeys);
    try {
      const { rerender } = render(<HydrationOverlay open onCancel={noop} />);
      advance(DELAY_MS);

      fireEvent.keyDown(document.body, { key: "Escape" });
      fireEvent.keyDown(document.body, { key: "Tab" });
      expect(appKeys).not.toHaveBeenCalled();

      rerender(<HydrationOverlay open={false} onCancel={noop} />);
      // 시간 전진 없이 유예 한복판에서 확인한다. 여기서 막히면 복원이 끝난 화면에서
      // 150ms 동안 투어의 Tab·ESC가 먹히지 않는다.
      fireEvent.keyDown(document.body, { key: "Escape" });
      fireEvent.keyDown(document.body, { key: "Tab" });
      expect(appKeys).toHaveBeenCalledTimes(2);
    } finally {
      window.removeEventListener("keydown", appKeys);
    }
  });

  it("[R8] scratch 세션은 프로젝트를 가리키지 않는 문구를 쓴다", () => {
    vi.useFakeTimers();
    render(<HydrationOverlay open scratch onCancel={noop} />);

    advance(DELAY_MS);
    expect(screen.getByText(L.titleScratch)).toBeInTheDocument();
    expect(screen.queryByText(L.title)).toBeNull();

    fireEvent.keyDown(document.body, { key: "Escape" });
    expect(screen.getByText(L.confirmTitleScratch)).toBeInTheDocument();
    expect(screen.queryByText(L.confirmTitle)).toBeNull();
  });

  it("[R6] phase 문구가 aria-live 영역에 뜨고, phase가 없으면 같은 영역이 비어 있다", () => {
    vi.useFakeTimers();
    const { rerender } = render(<HydrationOverlay open onCancel={noop} />);

    advance(DELAY_MS);
    // 컨테이너는 phase 없이도 마운트된다. 문구 유무로 언마운트하면 스크린리더가
    // 첫 문구를 새 영역의 초기값으로 보고 갱신으로 읽지 않는다.
    const status = screen.getByTestId("hydration-status");
    expect(status).toHaveAttribute("aria-live", "polite");
    expect(status.textContent).toBe("");

    rerender(<HydrationOverlay open onCancel={noop} phase="kuro" />);
    expect(status.textContent).toBe(L.phaseKuro);

    // 단계가 바뀌면 같은 노드의 문구만 갈린다(PHASE_KEYS 매핑도 함께 고정한다).
    rerender(<HydrationOverlay open onCancel={noop} phase="detect" />);
    expect(status.textContent).toBe(L.phaseDetect);

    // 확인 단계로 넘어가도 live region은 새로 마운트되지 않고 그 노드 그대로다.
    fireEvent.keyDown(document.body, { key: "Escape" });
    expect(screen.getAllByTestId("hydration-status")).toHaveLength(1);
    expect(screen.getByTestId("hydration-status")).toBe(status);
  });

  it("[R5] 오버레이 z가 모달 계층 아래·콘텐츠 계층 위에 놓인다", () => {
    vi.useFakeTimers();
    render(<HydrationOverlay open onCancel={noop} />);

    advance(DELAY_MS);
    const blocker = screen.getByTestId("hydration-blocker");
    const cardWrapper = screen.getByRole("dialog").parentElement;
    expect(cardWrapper).not.toBeNull();
    // 두 층이 같은 값을 써야 한다. 갈리면 차단막과 카드가 서로 다른 이웃과 겨룬다.
    const blockerZ = zValues(blocker.className);
    expect(blockerZ).toEqual([45]);
    expect(zValues(cardWrapper?.className ?? "")).toEqual(blockerZ);

    // 상대편 값은 테스트에 다시 적지 않고 소스에서 읽는다. 숫자를 여기 박아 두면 저쪽이
    // 내려가도 이 테스트는 계속 통과한다. 여러 z 중 최소값이 곧 "모달 계층 최저층"이다.
    const modalZ = zValues(
      readFileSync(join(process.cwd(), "src/components/ui/dialog.tsx"), "utf8"),
    );
    const alertZ = zValues(alertDialogClassName());
    // 추출 실패가 NaN 비교로 조용히 통과하지 않도록 값 자체를 먼저 못박는다.
    expect(modalZ).toEqual([50, 50]);
    expect(alertZ).toEqual([50]);

    // jsdom에는 레이아웃·stacking 엔진이 없어 실제 겹침 순서는 여기서 재현할 수 없다.
    // 대신 "누가 위인가"를 결정하는 숫자 관계를 고정한다. 오버레이가 모달과 동률이 되면
    // 나중에 append된 이 portal이 이겨 경고 모달이 백드롭에 가리고 유일한 확인 버튼이
    // 차단 레이어에 먹힌다(그래서 z-[45]로 내렸다).
    expect(blockerZ[0]).toBeLessThan(Math.min(...modalZ, ...alertZ));
    // 반대로 콘텐츠 최고층보다 낮아지면 복원 중 그 패널들이 열린 채로 조작 가능해진다.
    expect(blockerZ[0]).toBeGreaterThan(CONTENT_TOP_Z);
  });
});
