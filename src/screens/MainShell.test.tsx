import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MainShell } from "./MainShell";
import { ProjectProvider } from "@/state/projectContext";
import type { HydrationPhase } from "@/hooks/useAutosaveHydration";
import {
  __emitCloseRequestedForTest,
  __getWindowMockState,
  __resetWindowMock,
} from "../../scripts/stubs/webview";

vi.mock("@/lib/ipc", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/ipc")>();
  return {
    ...actual,
    killSidecar: vi.fn().mockResolvedValue(undefined),
    rawSidecarRpc: vi.fn().mockResolvedValue({}),
  };
});
vi.mock("@/lib/autosave", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/autosave")>();
  return {
    ...actual,
    flushAutosave: vi.fn().mockResolvedValue(undefined),
  };
});
// 복원 훅은 프로젝트 진입마다 사이드카 RPC 왕복을 돌리고 그동안 HydrationOverlay 가
// 화면 전체를 덮는다. 훅 자체는 useAutosaveHydration.test.tsx 가 검증하므로 여기서는
// 반환값만 갈아끼우고, MainShell 이 그 값을 오버레이·투어 게이트로 올바로 배선하는지 본다.
//
// 가변 객체로 두는 이유: 훅을 { hydrating: false } 로 못박으면 open={hydrating} 을
// open={false} 로 하드코딩해도 전 테스트가 통과한다(jsdom 은 레이아웃·hit-testing 이
// 없어 fixed inset-0 오버레이가 클릭을 가로채지 못하므로 다른 테스트도 눈치채지 못한다).
// 테스트마다 값을 바꿔 양방향으로 관측해야 배선이 실제로 고정된다.
const hydrationState = vi.hoisted(() => ({
  hydrating: false,
  // 유니온을 여기에 베껴 적지 않는다. 훅에 단계가 추가되면 조용히 낡는다.
  // 타입 전용 import 는 컴파일 시 지워지므로 vi.hoisted 가 import 위로 올라가도 안전하다.
  phase: null as HydrationPhase | null,
  cancel: vi.fn(),
}));

vi.mock("@/hooks/useAutosaveHydration", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/hooks/useAutosaveHydration")>();
  return {
    ...actual,
    // 매 렌더 hydrationState 를 다시 읽는다. 객체를 그대로 돌려주면 렌더 시점이 아니라
    // mock 팩토리 실행 시점의 값에 고정된다.
    useAutosaveHydration: () => ({
      hydrating: hydrationState.hydrating,
      phase: hydrationState.phase,
      cancel: hydrationState.cancel,
    }),
  };
});

// 탭 본문은 셸 배선과 무관하므로 스텁으로 대체한다(MainShell.integration.test.tsx 와 같은 패턴).
// 성능뿐 아니라 정확성 문제이기도 하다. 두 lazy 청크는 Selection3DPanel 의 `import("3dmol")`
// 과 MenuBar 경유 updateCheck 의 `import("@tauri-apps/plugin-process")` 를 끌고 오는데, 두
// 패키지 모두 package.json 에 선언돼 있으나 이 머신 node_modules 에는 없어서 vite import-analysis
// 가 변환 단계에서 실패한다. 청크가 reject 되면 Suspense 가 던져 셸 트리 전체가 언마운트된다.
// 기존 3개 테스트는 그 reject 가 착지하기 전에 끝나 우연히 지나갔을 뿐이고, 400ms 를 기다리는
// 아래 (c)·(d) 가 처음으로 밟는다.
//
// 트레이드오프를 명시한다. 단언 손실은 없지만(어느 테스트도 탭 본문을 단언하지 않는다)
// 커버리지 손실은 있다. 기존 3개 테스트는 실물 탭 트리를 마운트해 mount-time 크래시 회귀를
// 잡을 여지가 있었고 이제는 못 잡는다. 두 패키지가 설치되면 이 스텁 2개를 되돌릴 수 있다.
vi.mock("./KuroTab", () => ({
  KuroTab: () => <div data-testid="kuro-tab-stub" />,
}));
vi.mock("./MameTab", () => ({
  MameTab: () => <div data-testid="mame-tab-stub" />,
}));

// 투어 코디네이터는 localStorage enabled 키가 있어야 카드를 띄우므로 실물로는
// 마운트 여부를 관측할 수 없다. 렌더 여부만 보이는 스텁으로 갈아끼운다.
// START_GUIDED_TOUR_EVENT 등 다른 export 는 spread 로 살려 둔다.
vi.mock("@/components/dialogs/ProjectTourCoordinator", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("@/components/dialogs/ProjectTourCoordinator")>();
  return {
    ...actual,
    ProjectTourCoordinator: () => <div data-testid="tour-coordinator-stub" />,
  };
});

import { killSidecar, rawSidecarRpc } from "@/lib/ipc";

const killSidecarMock = vi.mocked(killSidecar);
const rpcMock = vi.mocked(rawSidecarRpc);

describe("MainShell", () => {
  beforeEach(() => {
    __resetWindowMock();
    vi.clearAllMocks();
    // clearAllMocks 는 평범한 객체를 되돌리지 않는다. 명시적으로 리셋하지 않으면
    // 아래 hydrating=true 케이스가 나머지 테스트를 순서 의존으로 만든다.
    hydrationState.hydrating = false;
    hydrationState.phase = null;
  });

  it("renders the shell header", () => {
    render(
      <ProjectProvider value={{ path: "/tmp/x", name: "Demo", scratch: false }}>
        <MainShell />
      </ProjectProvider>,
    );

    expect(screen.getByText("Demo")).toBeTruthy();
  });

  it("does not block the final native close emitted by destroy", async () => {
    render(
      <ProjectProvider value={{ path: "/tmp/x", name: "Demo", scratch: false }}>
        <MainShell />
      </ProjectProvider>,
    );

    await waitFor(() => {
      expect(__getWindowMockState().hasCloseRequestedHandler).toBe(true);
    });

    await __emitCloseRequestedForTest();

    await waitFor(() => {
      expect(__getWindowMockState().destroyCount).toBe(1);
    });
    expect(killSidecarMock).toHaveBeenCalledWith("kuro");
    expect(killSidecarMock).toHaveBeenCalledWith("mame");
    expect(__getWindowMockState().preventDefaultCount).toBe(1);
  });

  it("pings sidecars when tabs change", async () => {
    const user = userEvent.setup();
    render(
      <ProjectProvider value={{ path: "/tmp/x", name: "Demo", scratch: false }}>
        <MainShell />
      </ProjectProvider>,
    );

    await user.click(screen.getByRole("tab", { name: "Mame" }));
    await waitFor(() => {
      expect(rpcMock).toHaveBeenCalledWith("mame", "ping", {});
    });

    await user.click(screen.getByRole("tab", { name: "Kuro" }));
    await waitFor(() => {
      expect(rpcMock).toHaveBeenCalledWith("kuro", "ping", {});
    });
  });

  // ── 복원 훅 ↔ HydrationOverlay / 투어 게이트 배선
  //
  // 각 케이스는 렌더 전에 hydrationState 를 세팅한다. 가변 객체를 바꾸는 것만으로는
  // 리렌더가 일어나지 않으므로 rerender 가 아니라 set-then-render 형태로 둔다.
  describe("hydration wiring", () => {
    const project = { path: "/tmp/x", name: "Demo", scratch: false };

    it("(a) mounts the blocking layer while hydrating", () => {
      hydrationState.hydrating = true;
      render(
        <ProjectProvider value={project}>
          <MainShell />
        </ProjectProvider>,
      );

      // 차단 레이어는 DELAY_MS 없이 t=0 에 깔린다.
      expect(screen.getByTestId("hydration-blocker")).toBeTruthy();
    });

    it("(a') leaves no blocking layer once hydration finished", () => {
      hydrationState.hydrating = false;
      render(
        <ProjectProvider value={project}>
          <MainShell />
        </ProjectProvider>,
      );

      // 양방향으로 봐야 open={hydrating} 이 실제로 고정된다. jsdom 은 hit-testing 이
      // 없어 오버레이가 남아 있어도 다른 테스트의 클릭을 막지 않는다.
      expect(screen.queryByTestId("hydration-blocker")).toBeNull();
    });

    it("(b) withholds the tour coordinator while hydrating", () => {
      hydrationState.hydrating = true;
      render(
        <ProjectProvider value={project}>
          <MainShell />
        </ProjectProvider>,
      );

      expect(screen.queryByTestId("tour-coordinator-stub")).toBeNull();
    });

    it("(b') mounts the tour coordinator once hydration finished", () => {
      hydrationState.hydrating = false;
      render(
        <ProjectProvider value={project}>
          <MainShell />
        </ProjectProvider>,
      );

      expect(screen.getByTestId("tour-coordinator-stub")).toBeTruthy();
    });

    it("(c) surfaces the phase text the hook reports", async () => {
      hydrationState.hydrating = true;
      hydrationState.phase = "kuro";
      render(
        <ProjectProvider value={project}>
          <MainShell />
        </ProjectProvider>,
      );

      // 카드는 DELAY_MS(400ms) 뒤에 나타난다. 실제 타이머로 기다린다. fake timer 를
      // 쓰면 이 파일의 나머지 케이스가 쓰는 userEvent 와 얽힌다.
      const status = await screen.findByTestId("hydration-status", undefined, { timeout: 2000 });
      // 문구까지 못박아 phase → locale 키 매핑이 함께 고정되게 한다.
      expect(status.textContent).toBe("Loading your primer design work");
    });

    it("(d) passes the scratch flag through to the overlay copy", async () => {
      hydrationState.hydrating = true;
      render(
        <ProjectProvider value={{ path: "/tmp/scratch", name: "Scratch", scratch: true }}>
          <MainShell />
        </ProjectProvider>,
      );

      // scratch 세션은 열어둔 프로젝트가 없어 제목이 갈린다.
      expect(await screen.findByText("Restoring your work", undefined, { timeout: 2000 })).toBeTruthy();
      expect(screen.queryByText("Restoring your project")).toBeNull();
    });
  });
});
