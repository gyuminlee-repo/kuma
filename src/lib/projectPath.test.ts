import { describe, it, expect } from "vitest";
import {
  PROJECT_PATH_PREFIX,
  isPortablePath,
  isExternalPath,
  toPortablePath,
  fromPortablePath,
} from "./projectPath";

// 합성 경로. 실제 머신 경로를 쓰지 않는다.
const PROJECT = "/srv/proj/run7";
const MOVED = "/srv/other/run7";
const OUTSIDE = "/srv/ngs/run_20260730/fastq_pass";

describe("toPortablePath", () => {
  it("프로젝트 폴더 안 경로를 접두사 + 상대 경로로 바꾼다", () => {
    expect(toPortablePath(PROJECT, `${PROJECT}/barcodes/plate1.xlsx`)).toBe(
      `${PROJECT_PATH_PREFIX}barcodes/plate1.xlsx`,
    );
  });

  it("프로젝트 폴더 자신은 접두사만 남긴다", () => {
    expect(toPortablePath(PROJECT, PROJECT)).toBe(PROJECT_PATH_PREFIX);
  });

  it("프로젝트 폴더 밖 경로는 절대 경로 그대로 둔다", () => {
    expect(toPortablePath(PROJECT, OUTSIDE)).toBe(OUTSIDE);
  });

  it("이름이 접두사처럼 겹치는 형제 폴더를 안쪽으로 오인하지 않는다", () => {
    const sibling = `${PROJECT}-backup/x.xlsx`;
    expect(toPortablePath(PROJECT, sibling)).toBe(sibling);
  });

  it("Windows 역슬래시 경로도 안쪽으로 인식한다", () => {
    expect(toPortablePath("C:\\work\\run7", "C:\\work\\run7\\ref.fasta")).toBe(
      `${PROJECT_PATH_PREFIX}ref.fasta`,
    );
  });

  it("프로젝트 폴더 끝에 구분자가 붙어 있어도 같게 처리한다", () => {
    expect(toPortablePath(`${PROJECT}/`, `${PROJECT}/a.txt`)).toBe(
      `${PROJECT_PATH_PREFIX}a.txt`,
    );
  });

  it("scratch 세션(projectPath 없음)에서는 변환하지 않는다", () => {
    const abs = "/srv/tmp/a.fasta";
    expect(toPortablePath(null, abs)).toBe(abs);
  });

  it("빈 값은 미지정이므로 그대로 둔다", () => {
    expect(toPortablePath(PROJECT, "")).toBe("");
  });
});

describe("fromPortablePath", () => {
  it("접두사가 붙은 값을 현재 프로젝트 폴더 기준으로 되살린다", () => {
    expect(
      fromPortablePath(PROJECT, `${PROJECT_PATH_PREFIX}barcodes/plate1.xlsx`),
    ).toBe(`${PROJECT}/barcodes/plate1.xlsx`);
  });

  it("옮긴 뒤 새 폴더 기준으로 되살린다", () => {
    expect(fromPortablePath(MOVED, `${PROJECT_PATH_PREFIX}ref.fasta`)).toBe(
      `${MOVED}/ref.fasta`,
    );
  });

  it("접두사만 있으면 프로젝트 폴더 자신을 준다", () => {
    expect(fromPortablePath(PROJECT, PROJECT_PATH_PREFIX)).toBe(PROJECT);
  });

  it("구 스냅샷의 절대 경로는 그대로 통과시킨다", () => {
    const legacy = "/srv/old/run7/ref.fasta";
    expect(fromPortablePath(PROJECT, legacy)).toBe(legacy);
  });

  it("프로젝트 폴더를 모르면 상대 조각을 흘리지 않고 빈 값을 준다", () => {
    expect(fromPortablePath(null, `${PROJECT_PATH_PREFIX}ref.fasta`)).toBe("");
  });

  it("빈 값은 그대로 둔다", () => {
    expect(fromPortablePath(PROJECT, "")).toBe("");
  });
});

describe("왕복", () => {
  it("안쪽 경로는 같은 폴더에서 원래 값으로 돌아온다", () => {
    const abs = `${PROJECT}/activity/evolvepro_input.xlsx`;
    expect(fromPortablePath(PROJECT, toPortablePath(PROJECT, abs))).toBe(abs);
  });

  it("바깥 경로는 폴더를 옮겨도 원래 절대 경로를 유지한다", () => {
    const stored = toPortablePath(PROJECT, OUTSIDE);
    expect(fromPortablePath(MOVED, stored)).toBe(OUTSIDE);
  });

  it("안쪽 경로는 폴더를 옮기면 새 폴더를 따라간다", () => {
    const stored = toPortablePath(PROJECT, `${PROJECT}/ref.fasta`);
    expect(fromPortablePath(MOVED, stored)).toBe(`${MOVED}/ref.fasta`);
  });
});

describe("분류 술어", () => {
  it("isPortablePath는 접두사 유무로 판정한다", () => {
    expect(isPortablePath(`${PROJECT_PATH_PREFIX}a`)).toBe(true);
    expect(isPortablePath("/abs/a")).toBe(false);
  });

  it("isExternalPath는 값이 있고 접두사가 없을 때만 참이다", () => {
    expect(isExternalPath(OUTSIDE)).toBe(true);
    expect(isExternalPath(`${PROJECT_PATH_PREFIX}a`)).toBe(false);
    expect(isExternalPath("")).toBe(false);
  });
});
