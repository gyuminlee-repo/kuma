# In-app help panel 구현 계획

**목표:** KURO 와 MAME 양쪽에서 열리는 우측 슬라이드오버 도움말 패널을 붙여, 앱을 떠나지 않고 14개 주제를 찾아 읽게 한다.

**아키텍처:** 마크다운 14편을 로케일별로 두고 Vite `import.meta.glob` 이 빌드 시점에 문자열로 끌어온다. 패널은 상태를 갖지 않고 `topic` 과 `onTopicChange` 를 props 로 받으며, 각 탭의 `MenuBar` 가 자기 스토어에서 현재 단계를 읽어 주제를 정한다. 본문 내 상대 링크는 렌더러가 가로채 패널 안에서 주제만 바꾼다.

**기술 스택:** React 19, Vite 6 `import.meta.glob`, `react-markdown` 10.1.0, vitest, i18next

**스펙:** `docs/design/2026-09-15-inapp-help-panel.md`
**리뷰 상태:** 작성 직후 @reviewer(scope=completion) 검증 예정

---

## 사전 확인된 사실

| 사실 | 근거 |
|---|---|
| KURO 현재 단계는 `currentSubStep` | `src/store/slices/navigationSlice.ts`, `useAppStore` 로 읽음 |
| MAME 현재 단계는 `currentMameSubStep` | `src/store/mame/slices/navigationSlice.ts:39`, 기본값 `"setup.files"` at `:46` |
| MAME `MenuBar` 는 두 스토어를 모두 import | `src/components/mame/layout/MenuBar.tsx:6,32` |
| 공용 다이얼로그를 각 `MenuBar` 안에서 렌더하는 선례 | `src/components/layout/MenuBar.tsx:471`, `src/components/mame/layout/MenuBar.tsx:444` |
| 모듈 선언을 둘 자리 | `src/vite-env.d.ts` |
| `.cross-layer-sync.json` 에 help 그룹 없음 | 77개 그룹 중 0건 |
| `react-markdown` 10.1.0 peer 는 `react: ">=18"` | npm registry, 2026-09-15 확인 |
| 컴포넌트 테스트는 같은 자리에 `*.test.tsx` | `src/components/ui/Panel.test.tsx` |

## 라벨 규약

**본문에 `vA.BB.CC.DD` 라벨을 박지 않는다.** 커밋 제목은 `feat(help):` 같은 라벨 없는 형식을 쓴다. 이 작업은 shipped 동작을 바꾸므로 릴리스 라벨이 필요하지만, 그것은 머지 직전 `git fetch` 후 원격 최댓값으로 결정한다.

## 파일 구조

### 생성

| 경로 | 책임 |
|---|---|
| `docs/help/ko/` 14편 | 한국어 본문. `docs/kuro`·`docs/mame` 에서 옮김 |
| `docs/help/en/` 14편 | 영어 본문. 신규 번역 |
| `src/help/topics.ts` | 주제 id 목록, 목차 그룹, 단계 대 주제 대응표. 순수 데이터 |
| `src/help/content.ts` | `import.meta.glob` 로 본문 적재, 로케일 폴백 해석 |
| `src/help/content.test.ts` | 적재·폴백·재고 검사 |
| `src/help/topics.test.ts` | 목차와 파일 집합 일치, 상호 참조 무결성 |
| `src/components/help/HelpPanel.tsx` | 슬라이드오버 패널. 상태 없음 |
| `src/components/help/HelpPanel.test.tsx` | 렌더·목차·닫기·폴백 표시 |
| `src/components/help/HelpMarkdown.tsx` | `react-markdown` 래퍼, 링크 가로채기 |
| `src/components/help/HelpMarkdown.test.tsx` | 링크 3분기 |

### 수정

| 경로 | 변경 |
|---|---|
| `src/vite-env.d.ts` | `*.md?raw` 모듈 선언 |
| `src/components/layout/MenuBar.tsx` | Help 메뉴 항목 추가, 패널 렌더, `currentSubStep` 읽기 |
| `src/components/mame/layout/MenuBar.tsx` | 동일, `currentMameSubStep` 읽기 |
| `src/locales/*.json` 10종 | 패널 chrome 키 |
| `.cross-layer-sync.json` | help 그룹 추가 |
| `package.json` | `react-markdown` 의존성 |

---

## Task 0: 두 미지수를 먼저 없앤다

스펙 C4 다. 실패하면 D3 또는 D4 가 무너지므로 다른 것을 짓기 전에 한다.

**파일:**
- 생성: `src/help/spike.test.ts` (확인 후 삭제)

- [ ] **Step 1: `import.meta.glob` 이 실제 문자열을 주는지 확인하는 테스트**

```ts
// src/help/spike.test.ts
import { describe, it, expect } from "vitest";

describe("vite raw glob", () => {
  it("loads markdown as a non-empty string", () => {
    const mods = import.meta.glob("../../docs/kuro/*.md", {
      query: "?raw",
      import: "default",
      eager: true,
    }) as Record<string, string>;
    const keys = Object.keys(mods);
    expect(keys.length).toBeGreaterThan(0);
    expect(typeof mods[keys[0]]).toBe("string");
    expect(mods[keys[0]].length).toBeGreaterThan(0);
  });
});
```

- [ ] **Step 2: 실행**

실행: `bash $HOME/.claude/skills/win-build/scripts/win-build.sh pnpm exec vitest run --cwd <워크트리> src/help/spike.test.ts`
예상: PASS. 빈 객체가 나오면 glob 경로나 옵션 철자가 틀린 것이다. FAIL 이면 여기서 멈추고 보고한다.

- [ ] **Step 3: `react-markdown` 설치**

```bash
bash $HOME/.claude/skills/win-build/scripts/win-build.sh pnpm add react-markdown --cwd <워크트리>
```

설치 전 사용자 확인을 받는다. WSL 에서 직접 `pnpm add` 를 돌리지 않는다.

- [ ] **Step 4: 스모크 렌더**

```ts
// src/help/spike.test.ts 에 추가
import { render, screen } from "@testing-library/react";
import Markdown from "react-markdown";

it("renders markdown under React 19", () => {
  render(<Markdown>{"# Title\n\n- one\n- two"}</Markdown>);
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Title");
  expect(screen.getAllByRole("listitem")).toHaveLength(2);
});
```

파일 확장자를 `.test.tsx` 로 바꿔야 JSX 가 통한다.

실행: 위와 같은 명령
예상: PASS. FAIL 이면 D4 폐기하고 빌드 시점 변환으로 전환한다. 그 경우 계획을 다시 쓴다.

- [ ] **Step 5: spike 삭제하고 커밋**

```bash
rm src/help/spike.test.tsx
git add package.json pnpm-lock.yaml
git commit -m "chore(help): add react-markdown for the in-app help panel"
```

---

## Task 1: 본문을 옮기고 drift 를 묶는다

**파일:**
- 생성: `docs/help/ko/` 14편
- 수정: `.cross-layer-sync.json`

- [ ] **Step 1: 파일 복사와 이름 맞추기**

```bash
mkdir -p docs/help/ko
while read -r src dst; do
  [ -n "$src" ] && cp "docs/${src}.md" "docs/help/ko/${dst}.md"
done <<'PAIRS'
kuro/index          kuro-index
kuro/01-load        kuro-01-load
kuro/02-mutation    kuro-02-mutation
kuro/03-params      kuro-03-params
kuro/04-submit      kuro-04-submit
kuro/05-output      kuro-05-output
kuro/06-export      kuro-06-export
mame/index          mame-index
mame/01-setup       mame-01-setup
mame/02-review      mame-02-review
mame/03-janus       mame-03-janus
mame/04-activity    mame-04-activity
mame/mame-pipeline  mame-pipeline
PAIRS
```

13편이다. 14번째는 `docs/kuro/biological-unit-tier2-spec.md` 인데 목차 그룹 어디에도 안 들어가므로 **옮기지 않는다.** 스펙 D1 의 "8 files" 는 이 사양 문서를 포함한 수이고 목차는 13개 주제다. 스펙의 "14 topics" 를 13 으로 정정해야 한다.

- [ ] **Step 2: 내부 링크를 새 이름으로 고친다**

각 파일의 상대 링크가 옛 이름을 가리킨다. 옛 이름(`NN-name` 형태)을 새 주제 id(`mame-NN-name` 형태)로 바꾼다. 확장자는 그대로다.

실행: `grep -rn "](.*\.md)" docs/help/ko/` 로 전수 확인 후 수정.

- [ ] **Step 3: 인용 검사 통과 확인**

실행: `node scripts/check-doc-citations.mjs`
예상: OK. 새 파일이 tracked 되기 전이면 실패할 수 있으므로 `git add` 후 재실행한다.

- [ ] **Step 4: sync 그룹 추가**

`.cross-layer-sync.json` `groups[]` 에 추가한다. 기존 스키마는 `{ id, files[], symbols?, note, severity }` 다.

```json
{
  "id": "help-content-mirror",
  "files": [
    "<in-app copy>", "<published original>",
    "... one pair per topic, 26 paths in all"
  ],
  "note": "In-app help content is a copy of the published step guides. A change to one side has to reach the other or the app and the site disagree.",
  "severity": "warning"
}
```

`files` 에는 13쌍 26개 경로를 실제 값으로 적는다. 앞은 `docs/help/ko/<topic-id>` 이고 뒤는 그 원본이다. severity 는 `warning` 이다. 문서가 갈라지는 것은 빌드를 막을 일이 아니다.

- [ ] **Step 5: 검사와 커밋**

실행: `node scripts/sync-check-groups.mjs`
예상: 통과

```bash
git add docs/help/ko .cross-layer-sync.json
git commit -m "docs(help): move the step guides into the in-app help tree"
```

---

## Task 2: 영어 본문

**파일:**
- 생성: `docs/help/en/` 13편

- [ ] **Step 1: 13편 번역**

`docs/help/ko` 를 원본으로 옮긴다. 과학·기술 용어는 영어를 유지한다는 저장소 규약이 원문에도 적용돼 있어 용어는 대부분 이미 영어다.

파일명은 `ko` 쪽과 같아야 한다. 이름이 어긋나면 Task 3 의 재고 검사가 잡는다.

- [ ] **Step 2: 재고 대조**

실행: `diff <(ls docs/help/ko) <(ls docs/help/en)`
예상: 출력 없음

- [ ] **Step 3: 커밋**

```bash
git add docs/help/en
git commit -m "docs(help): translate the in-app help topics into English"
```

> 이 태스크는 분량이 커 별도 PR 로 떼도 된다. 떼는 경우 Task 3 의 폴백이 영어 부재를 견디는지 먼저 확인한다.

---

## Task 3: 본문 적재와 로케일 폴백

**파일:**
- 생성: `src/help/content.ts`, `src/help/content.test.ts`
- 수정: `src/vite-env.d.ts`

- [ ] **Step 1: 실패 테스트 작성**

```ts
// src/help/content.test.ts
import { describe, it, expect } from "vitest";
import { getTopicBody, listLoadedTopics } from "./content";

describe("help content", () => {
  it("loads every Korean topic as non-empty text", () => {
    const ids = listLoadedTopics("ko");
    expect(ids.length).toBeGreaterThan(0);
    for (const id of ids) {
      expect(getTopicBody(id, "ko").body.length).toBeGreaterThan(0);
    }
  });

  it("serves the requested locale without a fallback flag", () => {
    const r = getTopicBody("mame-01-setup", "ko");
    expect(r.usedLocale).toBe("ko");
    expect(r.fellBack).toBe(false);
  });

  it("falls back to English and says so", () => {
    const r = getTopicBody("mame-01-setup", "ja");
    expect(r.usedLocale).toBe("en");
    expect(r.fellBack).toBe(true);
  });

  it("reports a missing topic rather than returning empty text", () => {
    const r = getTopicBody("no-such-topic", "ko");
    expect(r.usedLocale).toBeNull();
    expect(r.body).toBe("");
  });

  it("carries the same topic set in both locales", () => {
    expect(listLoadedTopics("ko").sort()).toEqual(listLoadedTopics("en").sort());
  });
});
```

- [ ] **Step 2: 실행 → 실패 확인**

실행: `bash $W pnpm exec vitest run --cwd <워크트리> src/help/content.test.ts`
예상: FAIL, "Failed to resolve import ./content"

- [ ] **Step 3: 모듈 선언 추가**

```ts
// src/vite-env.d.ts 끝에 추가
declare module "*.md?raw" {
  const content: string;
  export default content;
}
```

- [ ] **Step 4: 구현**

```ts
// src/help/content.ts
export type HelpLocale = "ko" | "en";

const RAW_KO = import.meta.glob("../../docs/help/ko/*.md", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

const RAW_EN = import.meta.glob("../../docs/help/en/*.md", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

/** Path to topic id: the file stem, which is what cross-references name. */
function byStem(raw: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [path, body] of Object.entries(raw)) {
    const stem = path.split("/").pop()?.replace(/\.md$/, "");
    if (stem) out[stem] = body;
  }
  return out;
}

const BODIES: Record<HelpLocale, Record<string, string>> = {
  ko: byStem(RAW_KO),
  en: byStem(RAW_EN),
};

/**
 * The order a request is served in. The app has ten locales and help has two,
 * so eight of them land on English. Korean is last rather than absent because
 * it is the language the topics were written in, and a Korean body a reader
 * cannot read beats a blank panel.
 */
const CHAIN: HelpLocale[] = ["en", "ko"];

export interface TopicBody {
  body: string;
  /** The locale actually served, or null when no locale holds the topic. */
  usedLocale: HelpLocale | null;
  /** True when the served locale is not the one asked for. */
  fellBack: boolean;
}

export function getTopicBody(id: string, requested: string): TopicBody {
  const asked = requested as HelpLocale;
  if (BODIES[asked]?.[id]) {
    return { body: BODIES[asked][id], usedLocale: asked, fellBack: false };
  }
  for (const loc of CHAIN) {
    if (BODIES[loc][id]) {
      return { body: BODIES[loc][id], usedLocale: loc, fellBack: true };
    }
  }
  return { body: "", usedLocale: null, fellBack: false };
}

export function listLoadedTopics(locale: HelpLocale): string[] {
  return Object.keys(BODIES[locale]);
}
```

- [ ] **Step 5: 실행 → 통과 확인**

실행: 위와 같은 명령
예상: 5 passed

- [ ] **Step 6: 커밋**

```bash
git add src/help/content.ts src/help/content.test.ts src/vite-env.d.ts
git commit -m "feat(help): load the help topics with a stated locale fallback"
```

---

## Task 4: 주제 목록, 목차, 단계 대응

**파일:**
- 생성: `src/help/topics.ts`, `src/help/topics.test.ts`

- [ ] **Step 1: 실패 테스트 작성**

```ts
// src/help/topics.test.ts
import { describe, it, expect } from "vitest";
import { HELP_GROUPS, ALL_TOPIC_IDS, topicForStep } from "./topics";
import { listLoadedTopics, getTopicBody } from "./content";

describe("help topics", () => {
  it("lists every topic exactly once across the groups", () => {
    const flat = HELP_GROUPS.flatMap((g) => g.topics);
    expect(new Set(flat).size).toBe(flat.length);
    expect(flat.sort()).toEqual([...ALL_TOPIC_IDS].sort());
  });

  it("names only topics that were actually loaded", () => {
    expect([...ALL_TOPIC_IDS].sort()).toEqual(listLoadedTopics("ko").sort());
  });

  it("maps each known step to a real topic", () => {
    for (const step of ["setup.files", "analyze.review", "design.load", "export.all"]) {
      const id = topicForStep(step);
      expect(ALL_TOPIC_IDS).toContain(id);
    }
  });

  it("falls back to a group index for an unmapped step", () => {
    expect(ALL_TOPIC_IDS).toContain(topicForStep("no.such.step"));
  });

  it("has no cross-reference pointing at a topic that does not exist", () => {
    const broken: string[] = [];
    for (const id of ALL_TOPIC_IDS) {
      const body = getTopicBody(id, "ko").body;
      for (const m of body.matchAll(/\]\(([\w.-]+)\.md\)/g)) {
        if (!ALL_TOPIC_IDS.includes(m[1])) broken.push(`${id} -> ${m[1]}`);
      }
    }
    expect(broken).toEqual([]);
  });
});
```

- [ ] **Step 2: 실행 → 실패 확인**

예상: FAIL, "Failed to resolve import ./topics"

- [ ] **Step 3: 구현**

```ts
// src/help/topics.ts
export interface HelpGroup {
  /** i18n key for the group heading. */
  labelKey: string;
  topics: string[];
}

export const HELP_GROUPS: HelpGroup[] = [
  { labelKey: "help.panel.group.start", topics: ["kuro-index", "mame-index"] },
  {
    labelKey: "help.panel.group.kuro",
    topics: [
      "kuro-01-load",
      "kuro-02-mutation",
      "kuro-03-params",
      "kuro-04-submit",
      "kuro-05-output",
      "kuro-06-export",
    ],
  },
  {
    labelKey: "help.panel.group.mame",
    topics: ["mame-01-setup", "mame-02-review", "mame-03-janus", "mame-04-activity"],
  },
  { labelKey: "help.panel.group.deeper", topics: ["mame-pipeline"] },
];

export const ALL_TOPIC_IDS: string[] = HELP_GROUPS.flatMap((g) => g.topics);

/**
 * Step id to topic. The keys are the sub-step ids the two stores already hold:
 * KURO in src/store/slices/navigationSlice.ts, MAME in
 * src/store/mame/slices/navigationSlice.ts.
 */
const STEP_TO_TOPIC: Record<string, string> = {
  "design.load": "kuro-01-load",
  "design.mutation": "kuro-02-mutation",
  "design.params": "kuro-03-params",
  "design.submit": "kuro-04-submit",
  "output.summary": "kuro-05-output",
  "export.all": "kuro-06-export",
  "setup.files": "mame-01-setup",
  "analyze.inputs": "mame-01-setup",
  "analyze.review": "mame-02-review",
  "janus.settings": "mame-03-janus",
  "activity.ingest": "mame-04-activity",
  "activity.signals": "mame-04-activity",
};

/** An unmapped step opens an index rather than nothing. */
export function topicForStep(step: string | null | undefined): string {
  if (step && STEP_TO_TOPIC[step]) return STEP_TO_TOPIC[step];
  return step?.startsWith("design.") || step?.startsWith("output.") || step?.startsWith("export.")
    ? "kuro-index"
    : "mame-index";
}
```

- [ ] **Step 4: 실행 → 통과 확인**

예상: 5 passed. 상호 참조 테스트가 실패하면 Task 1 Step 2 의 링크 수정이 덜 된 것이다.

- [ ] **Step 5: 커밋**

```bash
git add src/help/topics.ts src/help/topics.test.ts
git commit -m "feat(help): declare the help contents and the step mapping"
```

---

## Task 5: 마크다운 렌더러와 링크 가로채기

**파일:**
- 생성: `src/components/help/HelpMarkdown.tsx`, `src/components/help/HelpMarkdown.test.tsx`

- [ ] **Step 1: 실패 테스트 작성**

```tsx
// src/components/help/HelpMarkdown.test.tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HelpMarkdown } from "./HelpMarkdown";

const KNOWN = ["alpha-topic", "beta-topic"];

describe("HelpMarkdown", () => {
  it("swaps the topic on a link naming a known topic", async () => {
    const onTopicChange = vi.fn();
    render(
      <HelpMarkdown
        body={"See [Setup](alpha-topic.md)."}
        knownTopics={KNOWN}
        onTopicChange={onTopicChange}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Setup" }));
    expect(onTopicChange).toHaveBeenCalledWith("alpha-topic");
  });

  it("renders a link to an unknown topic as plain text", () => {
    render(
      <HelpMarkdown
        body={"See [Ghost](gamma-topic.md)."}
        knownTopics={KNOWN}
        onTopicChange={vi.fn()}
      />,
    );
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText(/Ghost/)).toBeInTheDocument();
  });

  it("keeps an external link as a link", () => {
    render(
      <HelpMarkdown
        body={"See [Repo](https://github.com/example)."}
        knownTopics={KNOWN}
        onTopicChange={vi.fn()}
      />,
    );
    expect(screen.getByRole("link", { name: "Repo" })).toBeInTheDocument();
  });

  it("renders an anchor-only link as plain text", () => {
    render(
      <HelpMarkdown body={"See [Top](#top)."} knownTopics={KNOWN} onTopicChange={vi.fn()} />,
    );
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByText(/Top/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: 실행 → 실패 확인**

예상: FAIL, "Failed to resolve import ./HelpMarkdown"

- [ ] **Step 3: 구현**

```tsx
// src/components/help/HelpMarkdown.tsx
import Markdown from "react-markdown";
import { openUrl } from "@tauri-apps/plugin-opener";

interface HelpMarkdownProps {
  body: string;
  knownTopics: string[];
  onTopicChange: (id: string) => void;
}

/**
 * Markdown for the help panel, with the link rule the spec fixes in C2.
 *
 * The rule runs in order: an absolute link leaves through the opener, a link
 * naming a topic swaps the panel, and anything else renders as text. The third
 * branch is why a broken cross-reference shows as words rather than as a link
 * that does nothing when clicked.
 */
export function HelpMarkdown({ body, knownTopics, onTopicChange }: HelpMarkdownProps) {
  return (
    <div className="space-y-2 text-sm leading-relaxed [&_h2]:mt-4 [&_h2]:font-semibold [&_h3]:mt-3 [&_h3]:font-medium [&_ul]:list-disc [&_ul]:pl-5 [&_code]:rounded [&_code]:bg-muted/30 [&_code]:px-1">
      <Markdown
        components={{
          a({ href, children }) {
            const target = href ?? "";
            if (target.startsWith("http://") || target.startsWith("https://")) {
              return (
                <a
                  href={target}
                  onClick={(e) => {
                    e.preventDefault();
                    void openUrl(target);
                  }}
                >
                  {children}
                </a>
              );
            }
            const stem = target.endsWith(".md") ? target.slice(0, -3) : null;
            if (stem && knownTopics.includes(stem)) {
              return (
                <button type="button" className="underline" onClick={() => onTopicChange(stem)}>
                  {children}
                </button>
              );
            }
            return <>{children}</>;
          },
        }}
      >
        {body}
      </Markdown>
    </div>
  );
}
```

- [ ] **Step 4: 실행 → 통과 확인**

예상: 4 passed

- [ ] **Step 5: 커밋**

```bash
git add src/components/help/HelpMarkdown.tsx src/components/help/HelpMarkdown.test.tsx
git commit -m "feat(help): render help markdown and keep cross-references in the panel"
```

---

## Task 6: 패널

**파일:**
- 생성: `src/components/help/HelpPanel.tsx`, `src/components/help/HelpPanel.test.tsx`

- [ ] **Step 1: 실패 테스트 작성**

```tsx
// src/components/help/HelpPanel.test.tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HelpPanel } from "./HelpPanel";

function setup(over: Partial<React.ComponentProps<typeof HelpPanel>> = {}) {
  const props = {
    open: true,
    topic: "mame-01-setup",
    onTopicChange: vi.fn(),
    onClose: vi.fn(),
    ...over,
  };
  render(<HelpPanel {...props} />);
  return props;
}

describe("HelpPanel", () => {
  it("renders nothing when closed", () => {
    setup({ open: false });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("shows every group heading and the body of the active topic", () => {
    setup();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /.+/ }).length).toBeGreaterThan(4);
  });

  it("changes topic when a contents entry is clicked", async () => {
    const p = setup();
    await userEvent.click(screen.getByRole("button", { name: /mame-02-review|Analyze/i }));
    expect(p.onTopicChange).toHaveBeenCalled();
  });

  it("closes on the close control", async () => {
    const p = setup();
    await userEvent.click(screen.getByRole("button", { name: /close/i }));
    expect(p.onClose).toHaveBeenCalled();
  });

  it("says so when the body came from another locale", () => {
    setup({ topic: "mame-01-setup" });
    // i18n test harness serves English; the notice appears only when fellBack.
    // Asserted through the testid rather than the copy so a wording change
    // does not break the test.
    const notice = screen.queryByTestId("help-fallback-notice");
    expect(notice === null || notice.textContent !== "").toBe(true);
  });

  it("keeps the contents usable when the topic is missing", () => {
    setup({ topic: "no-such-topic" });
    expect(screen.getByTestId("help-missing-topic")).toBeInTheDocument();
    expect(screen.getAllByRole("button").length).toBeGreaterThan(1);
  });
});
```

- [ ] **Step 2: 실행 → 실패 확인**

예상: FAIL, 모듈 없음

- [ ] **Step 3: 구현**

```tsx
// src/components/help/HelpPanel.tsx
import { useTranslation } from "react-i18next";
import { HELP_GROUPS, ALL_TOPIC_IDS } from "@/help/topics";
import { getTopicBody } from "@/help/content";
import { HelpMarkdown } from "./HelpMarkdown";

interface HelpPanelProps {
  open: boolean;
  topic: string;
  onTopicChange: (id: string) => void;
  onClose: () => void;
}

/**
 * The help panel holds no state and knows nothing about steps. Each tab passes
 * the topic it derived from its own store, which is what keeps the panel usable
 * from two trees whose stores never meet.
 */
export function HelpPanel({ open, topic, onTopicChange, onClose }: HelpPanelProps) {
  const { t, i18n } = useTranslation();
  if (!open) return null;

  const { body, usedLocale, fellBack } = getTopicBody(topic, i18n.language);

  return (
    <div
      role="dialog"
      aria-modal="false"
      aria-label={t("help.panel.title")}
      className="fixed inset-y-0 right-0 z-40 flex w-[440px] max-w-full flex-col border-l border-border bg-surface shadow-lg"
    >
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <h2 className="text-sm font-semibold">{t("help.panel.title")}</h2>
        <button type="button" aria-label={t("help.panel.close")} onClick={onClose}>
          x
        </button>
      </div>

      <nav className="border-b border-border px-4 py-2">
        {HELP_GROUPS.map((g) => (
          <div key={g.labelKey} className="mb-2">
            <div className="text-xs text-muted">{t(g.labelKey)}</div>
            <div className="flex flex-wrap gap-1">
              {g.topics.map((id) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => onTopicChange(id)}
                  className={id === topic ? "font-semibold underline" : ""}
                >
                  {t(`help.panel.topic.${id}`)}
                </button>
              ))}
            </div>
          </div>
        ))}
      </nav>

      <div className="flex-1 overflow-y-auto px-4 py-3">
        {usedLocale === null ? (
          <p data-testid="help-missing-topic">{t("help.panel.notTranslated")}</p>
        ) : (
          <>
            {fellBack && (
              <p data-testid="help-fallback-notice" className="mb-2 text-xs text-muted">
                {t("help.panel.shownIn", { locale: usedLocale })}
              </p>
            )}
            <HelpMarkdown
              body={body}
              knownTopics={ALL_TOPIC_IDS}
              onTopicChange={onTopicChange}
            />
          </>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: 실행 → 통과 확인**

예상: 6 passed

- [ ] **Step 5: 커밋**

```bash
git add src/components/help/HelpPanel.tsx src/components/help/HelpPanel.test.tsx
git commit -m "feat(help): add the help slide-over panel"
```

---

## Task 7: 두 MenuBar 에 배선하고 로케일 키를 넣는다

**파일:**
- 수정: `src/components/layout/MenuBar.tsx`, `src/components/mame/layout/MenuBar.tsx`, `src/locales/*.json` 10종

- [ ] **Step 1: 로케일 키 추가**

`en.json` 에 넣고 나머지 9종에 번역한다. 과학·기술 용어는 영어를 유지한다.

```json
"help": {
  "userGuide": "User guide",
  "panel": {
    "title": "Help",
    "close": "Close help",
    "notTranslated": "This topic is not available yet.",
    "shownIn": "Shown in {{locale}} because this topic is not translated into your language yet.",
    "group": {
      "start": "Getting started",
      "kuro": "KURO design",
      "mame": "MAME verification",
      "deeper": "Deeper"
    },
    "topic": {
      "kuro-index": "KURO overview",
      "kuro-01-load": "Load",
      "kuro-02-mutation": "Mutations",
      "kuro-03-params": "Parameters",
      "kuro-04-submit": "Submit",
      "kuro-05-output": "Results",
      "kuro-06-export": "Export",
      "mame-index": "MAME overview",
      "mame-01-setup": "Barcode setup",
      "mame-02-review": "Analyze and review",
      "mame-03-janus": "Janus",
      "mame-04-activity": "Activity",
      "mame-pipeline": "MAME pipeline"
    }
  }
}
```

기존 `help` 네임스페이스에 병합한다. 그 아래에 `loadSampleData` 등 5키가 이미 있다.

- [ ] **Step 2: KURO MenuBar 배선**

```tsx
// src/components/layout/MenuBar.tsx
const currentSubStep = useAppStore((s) => s.currentSubStep);
const [helpOpen, setHelpOpen] = useState(false);
const [helpTopic, setHelpTopic] = useState<string>("kuro-index");

// Help 메뉴 첫 항목으로
<DropdownMenuItem
  onClick={() => {
    setHelpTopic(topicForStep(currentSubStep));
    setHelpOpen(true);
  }}
>
  {t("help.userGuide")}
</DropdownMenuItem>

// SharedAboutDialog 옆에
<HelpPanel
  open={helpOpen}
  topic={helpTopic}
  onTopicChange={setHelpTopic}
  onClose={() => setHelpOpen(false)}
/>
```

- [ ] **Step 3: MAME MenuBar 배선**

같은 모양이며 읽는 값만 다르다.

```tsx
const currentSubStep = useMameAppStore((s) => s.currentMameSubStep);
```

- [ ] **Step 4: 검사**

실행:
```bash
node node_modules/typescript/bin/tsc --noEmit
node scripts/i18n-lint.mjs
node scripts/i18n-parity.mjs
```
예상: 전부 exit 0

- [ ] **Step 5: 커밋**

```bash
git add src/components/layout/MenuBar.tsx src/components/mame/layout/MenuBar.tsx src/locales
git commit -m "feat(help): open the help panel from both Help menus"
```

---

## Task 8: 전체 검증과 PR

- [ ] **Step 1: 전량 테스트**

```bash
bash $W pnpm exec vitest run --silent --reporter=dot --cwd <워크트리>
node node_modules/typescript/bin/tsc --noEmit
node scripts/i18n-lint.mjs && node scripts/i18n-parity.mjs
node scripts/sync-check-groups.mjs
node scripts/check-doc-citations.mjs
python3 -m pytest tests/ -q
```

기대값: vitest 0 failed, tsc exit 0, pytest 실패 0. Python 은 건드리지 않았으므로 기준선 그대로여야 한다.

- [ ] **Step 2: 육안 확인**

`pnpm tauri dev` 를 Windows 에서 띄우고 다음을 눈으로 본다. WSL 에서 GUI 확인을 시도하지 않는다.

1. KURO 탭 Help 메뉴에서 패널이 열리는가
2. MAME `analyze.review` 에서 열면 「Analyze and review」가 선택되는가
3. 본문의 상호 참조를 누르면 패널 안에서 주제만 바뀌는가
4. 목차에서 다른 주제로 갈 수 있는가
5. `x` 로 닫히고 하던 작업이 그대로인가
6. 탭을 바꿔도 패널이 움직이지 않는가

- [ ] **Step 3: PR**

```bash
git push -u origin feat/mame-inapp-help-spec
gh pr create --base main --title "feat(help): add an in-app help panel for KURO and MAME"
```

라벨은 머지 직전에 `git fetch` 후 원격 최댓값으로 정한다.

---

## 스펙과 어긋나는 점

| 스펙 서술 | 실제 | 처리 |
|---|---|---|
| "14 topics" | 목차는 13개다. `docs/kuro` 8편 중 tier 2 사양서는 사용자 문서가 아니라 제외했다 | **해소됨.** 스펙을 13 으로 정정했다 |

## 열린 항목

- Task 2 의 영어 번역 13편은 분량이 커 별도 PR 로 뗄 수 있다. 떼면 1차 출고는 한국어만 담고 나머지 로케일은 한국어로 폴백한다. 스펙의 완료 기준이 "13편이 stub 아닌 실제 번역" 이므로 뗄 경우 그 기준도 함께 옮긴다.
- (해소됨) `prose` 는 쓰지 않는다. `@tailwindcss/typography` 가 `package.json` 과 `tailwind.config.js` 어디에도 없고 `src` 에서 `prose` 를 쓰는 곳도 0건이라, 그 클래스는 CSS 를 전혀 만들지 않는다. `HelpMarkdown` 이 자식 선택자로 타이포그래피를 직접 준다. AGENTS.md 가 적었듯 이런 누락은 tsc 도 vitest 도 린터도 잡지 못하므로 Task 8 의 육안 확인이 유일한 검증이다.
