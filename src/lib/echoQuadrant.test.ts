import { describe, expect, it } from "vitest";
import {
  ECHO_QUADRANTS,
  echoPlacementIssue,
  foldPersistedPlacement,
  HALF_LAYOUT_VERSION,
  QUADRANT_RESTORE_VERSION,
  savedUnderHalfLayout,
  isColumnInQuadrant,
  isForwardRow,
  otherQuadrants,
  quadrantColumnOffset,
  quadrantFirstColumn,
  quadrantLastColumn,
  quadrantsFilledAfterRun,
} from "./echoQuadrant";

describe("Echo source plate column parities", () => {
  it("offers exactly the two rounds the core does", () => {
    // kuma_core/kuro/plate_quadrant.QUADRANTS. A third entry here would put an
    // option in the picker the sidecar rejects. The v0.14.0 picker had four,
    // with a row axis that duplicated this one.
    expect([...ECHO_QUADRANTS]).toEqual(["A1", "A2"]);
  });

  it("puts one round on the odd columns and the other on the even ones", () => {
    expect(quadrantColumnOffset("A1")).toBe(0);
    expect(quadrantColumnOffset("A2")).toBe(1);
    expect([quadrantFirstColumn("A1"), quadrantLastColumn("A1")]).toEqual([1, 23]);
    expect([quadrantFirstColumn("A2"), quadrantLastColumn("A2")]).toEqual([2, 24]);
  });

  it("decides membership by column parity, not by a contiguous range", () => {
    // 절반 배치에서는 1~12 가 전부 A1 이고 13 이 아니었다. 이 네 줄이 판별점이다.
    expect(isColumnInQuadrant(1, "A1")).toBe(true);
    expect(isColumnInQuadrant(2, "A1")).toBe(false);
    expect(isColumnInQuadrant(13, "A1")).toBe(true);
    expect(isColumnInQuadrant(2, "A2")).toBe(true);
    expect(isColumnInQuadrant(24, "A2")).toBe(true);
    expect(isColumnInQuadrant(23, "A2")).toBe(false);
  });

  it("names the round a run leaves untouched", () => {
    expect(otherQuadrants("A1")).toEqual(["A2"]);
    expect(otherQuadrants("A2")).toEqual(["A1"]);
  });

  it("counts a run as spending one of the two rounds", () => {
    expect(quadrantsFilledAfterRun("A1", [])).toBe(1);
    expect(quadrantsFilledAfterRun("A1", ["A2"])).toBe(2);
    expect(quadrantsFilledAfterRun("A1", ["A1"])).toBe(1);
  });

  it("reads direction from row parity alone, in either round", () => {
    // 행 축은 선택지가 아니므로 round 를 인자로 받지 않는다.
    expect(isForwardRow(0)).toBe(true);
    expect(isForwardRow(1)).toBe(false);
    expect(isForwardRow(14)).toBe(true);
    expect(isForwardRow(15)).toBe(false);
  });
});

describe("dating a saved file against the half layout", () => {
  it("calls the releases that wrote contiguous-half names half-era", () => {
    expect(savedUnderHalfLayout(HALF_LAYOUT_VERSION)).toBe(true);
    expect(savedUnderHalfLayout("0.16.61")).toBe(true);
    expect(savedUnderHalfLayout("0.16.61.1")).toBe(true);
    expect(savedUnderHalfLayout("0.16.65")).toBe(true);
    expect(savedUnderHalfLayout("v0.16.63")).toBe(true);
  });

  it("calls anything before 0.16.61 an interleaved-era file", () => {
    expect(savedUnderHalfLayout("0.16.60.3")).toBe(false);
    expect(savedUnderHalfLayout("0.16.9")).toBe(false);
    expect(savedUnderHalfLayout("0.9.99")).toBe(false);
  });

  it("calls this release and later current", () => {
    expect(savedUnderHalfLayout(QUADRANT_RESTORE_VERSION)).toBe(false);
    expect(savedUnderHalfLayout("0.17.0")).toBe(false);
    expect(savedUnderHalfLayout("1.0.0")).toBe(false);
  });

  it("treats an absent or unparseable version as not half-era", () => {
    // 이 방향이어야 하는 이유: half 이름을 쓴 릴리스는 전부 이 스탬프도 함께
    // 썼다. 스탬프가 없다는 것은 0.16.61 이전이라는 뜻이고 그 시절 값은 이미
    // 열 패리티를 뜻한다. 반대로 읽으면 0.16.61 이전 프로젝트의 선택이 전부
    // 이유 없이 떨어진다.
    expect(savedUnderHalfLayout("")).toBe(false);
    expect(savedUnderHalfLayout(undefined)).toBe(false);
    expect(savedUnderHalfLayout(null)).toBe(false);
    expect(savedUnderHalfLayout("0.0.0-test")).toBe(false);
    expect(savedUnderHalfLayout("latest")).toBe(false);
    expect(savedUnderHalfLayout(16.61)).toBe(false);
  });
});

describe("reading a persisted placement", () => {
  const CURRENT = QUADRANT_RESTORE_VERSION;

  it("passes a placement this version wrote through unchanged", () => {
    expect(foldPersistedPlacement("A2", ["A1"], CURRENT)).toEqual({
      quadrant: "A2",
      usedQuadrants: ["A1"],
      legacySeen: [],
    });
  });

  it("normalises case and padding, and orders used rounds canonically", () => {
    expect(foldPersistedPlacement(" a1 ", ["a2", "A1", "A2"], CURRENT)).toEqual({
      quadrant: "A1",
      usedQuadrants: ["A1", "A2"],
      legacySeen: [],
    });
  });

  it("drops entries the app never wrote instead of failing the load", () => {
    expect(foldPersistedPlacement("C3", ["A1", "C3", 7, null], CURRENT)).toEqual({
      quadrant: null,
      usedQuadrants: ["A1"],
      legacySeen: [],
    });
  });

  it("folds an interleaved-era B1 or B2 without calling it legacy", () => {
    // (a) 그 이름들은 이 라운드들을 reverse 쪽에서 부른 것이다. 접어도 좌표가
    // 하나도 움직이지 않으므로 작업자가 할 일이 없고, 경고를 띄울 이유도 없다.
    expect(foldPersistedPlacement("B1", [], "0.16.60")).toEqual({
      quadrant: "A1",
      usedQuadrants: [],
      legacySeen: [],
    });
    expect(foldPersistedPlacement("B2", ["B1"], "0.16.60")).toEqual({
      quadrant: "A2",
      usedQuadrants: ["A1"],
      legacySeen: [],
    });
    expect(foldPersistedPlacement("A2", ["B2", "A2"], "0.16.58")).toEqual({
      quadrant: "A2",
      usedQuadrants: ["A2"],
      legacySeen: [],
    });
  });

  it("spends both rounds when a stored name is a half name", () => {
    // (b) 12 연속 열은 어느 열 패리티에도 대응되지 않고 두 라운드 각각의 192 웰
    // 중 96 웰 위에 앉는다. 한쪽으로 접으면 모든 소스 웰이 말없이 옮겨진다.
    expect(foldPersistedPlacement("A13", [], CURRENT)).toEqual({
      quadrant: null,
      usedQuadrants: ["A1", "A2"],
      legacySeen: ["A13"],
    });
    expect(foldPersistedPlacement(null, ["A13"], CURRENT)).toEqual({
      quadrant: null,
      usedQuadrants: ["A1", "A2"],
      legacySeen: ["A13"],
    });
  });

  it("dates the whole placement from one half name, quadrant or used", () => {
    // The "A1" beside "A13" is columns 1-12 too, so it is reported rather than
    // read as the odd columns.
    expect(foldPersistedPlacement("A13", ["A1"], CURRENT)).toEqual({
      quadrant: null,
      usedQuadrants: ["A1", "A2"],
      legacySeen: ["A13", "A1"],
    });
  });

  it("refuses a lone A1 saved inside the half-layout range", () => {
    // (c) 이 입력은 저장값만으로는 판별되지 않는다. 두 어휘가 "A1" 을 같은 글자로
    // 쓰기 때문이다. 버전 판별이 없으면 half 시절의 1~12 열 블록이 홀수 열로
    // 읽히고, 프라이머가 든 짝수 열 라운드가 비어 있다고 선언된다.
    expect(foldPersistedPlacement("A1", [], HALF_LAYOUT_VERSION)).toEqual({
      quadrant: null,
      usedQuadrants: ["A1", "A2"],
      legacySeen: ["A1"],
    });
    expect(foldPersistedPlacement("A1", [], "0.16.65")).toEqual({
      quadrant: null,
      usedQuadrants: ["A1", "A2"],
      legacySeen: ["A1"],
    });
    expect(foldPersistedPlacement("A1", [], QUADRANT_RESTORE_VERSION).quadrant).toBe("A1");
  });

  it("leaves an empty placement empty however the file is dated", () => {
    // A project that never picked a round states nothing about the plate, so
    // there is nothing to re-date. Reporting both rounds spent here would
    // invent a plate state and make the operator clear a claim nobody made.
    expect(foldPersistedPlacement(null, [], HALF_LAYOUT_VERSION)).toEqual({
      quadrant: null,
      usedQuadrants: [],
      legacySeen: [],
    });
    expect(foldPersistedPlacement(null, [], "0.1.0")).toEqual({
      quadrant: null,
      usedQuadrants: [],
      legacySeen: [],
    });
  });
});

describe("refusing a placement the sidecar would reject", () => {
  it("passes a round that is not marked spent", () => {
    expect(echoPlacementIssue("A1", [])).toBeNull();
    expect(echoPlacementIssue("A1", ["A2"])).toBeNull();
  });

  it("refuses spent rounds with none chosen", () => {
    // This is what a half-era placement folds to, and it is the combination
    // the mapper raises on rather than quietly drawing columns 1-12.
    expect(echoPlacementIssue(null, ["A1", "A2"])).toBe("noQuadrantSelected");
    expect(echoPlacementIssue(null, ["A1"])).toBe("noQuadrantSelected");
  });

  it("passes an empty placement, which is the untouched-plate default", () => {
    expect(echoPlacementIssue(null, [])).toBeNull();
  });

  it("refuses dispensing on top of a round the operator marked spent", () => {
    expect(echoPlacementIssue("A2", ["A2"])).toBe("quadrantAlreadyUsed");
  });
});
