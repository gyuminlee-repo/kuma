/**
 * deadlockCopy.test.ts, 데드락 다이얼로그 문구가 감지기가 아는 것만 말하는지.
 *
 * `deadlockDetector.ts` 는 thresholdMs 동안 progress 알림이 오지 않았다는 사실만
 * 관측한다(startDeadlockWatch 의 `now - lastAt >= thresholdMs`). 작업이 실제로
 * 멈췄는지는 알 수 없고, 다이얼로그도 "계속 기다리기"(deadlockWait) 버튼을 함께
 * 낸다. 그래서 두 문구 모두 단정이 아니라 유보형이어야 한다.
 *
 * KURO 쪽 `appLayout.deadlockDesc` 는 이미 로케일별 유보 표현을 갖고 있으므로,
 * MAME 쪽 `mame.appLayout.deadlockDescription` 은 같은 문장이어야 한다. 두 문구가
 * 같은 감지기의 같은 사건을 설명하기 때문이다. 표현을 정규식으로 채점하지 않고
 * 형제 문자열과 대조하는 이유는, 로케일마다 유보 표현이 달라 패턴으로는 잡히지
 * 않기 때문이다(es "puede estar", fr "peut-être", ja "可能性があります" 등).
 */
import { describe, it, expect } from "vitest";

import de from "@/locales/de.json";
import en from "@/locales/en.json";
import es from "@/locales/es.json";
import fr from "@/locales/fr.json";
import ja from "@/locales/ja.json";
import ko from "@/locales/ko.json";
import ptBR from "@/locales/pt-BR.json";
import ru from "@/locales/ru.json";
import zhCN from "@/locales/zh-CN.json";
import zhTW from "@/locales/zh-TW.json";

const LOCALES = { de, en, es, fr, ja, ko, "pt-BR": ptBR, ru, "zh-CN": zhCN, "zh-TW": zhTW };

describe("deadlock dialog copy", () => {
  for (const [lang, bundle] of Object.entries(LOCALES)) {
    it(`${lang}: mame deadlock description hedges like its KURO sibling`, () => {
      const mame = bundle.mame.appLayout.deadlockDescription;
      const sibling = bundle.appLayout.deadlockDesc;
      expect(mame).toBe(sibling);
    });

    it(`${lang}: mame deadlock description keeps the {{seconds}} placeholder`, () => {
      expect(bundle.mame.appLayout.deadlockDescription).toContain("{{seconds}}");
    });
  }
});
