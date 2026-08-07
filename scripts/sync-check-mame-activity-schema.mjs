#!/usr/bin/env node
/**
 * sync-check-mame-activity-schema.mjs, activity long-CSV 헤더 계약, TS vs Python.
 *
 * `MAME_ACTIVITY_CSV_SCHEMA` (src/lib/schemaValidator.ts) 는
 * `kuma_core/mame/activity/ingest_long_csv.py` 의 헤더 수용 규칙을 손으로 옮긴
 * 사본이다. 이 게이트는 `src/store/mame/activitySlice.ts` 가 sendRequest 이전에
 * 돌리므로, 프런트가 좁으면 Python 별칭 로직이 GUI 에서 도달 불가능해진다.
 * 실제로 required 가 [plate_id, well_id, value] 로 굳어 있어 raw GC-FID export
 * ("Sample Name"/"Area") 가 csv 로는 거부되고 xlsx 로는 통과하는 상태였다.
 *
 * 비교 대상은 세 가지다.
 *   1. WELL_COL_ALIASES / VALUE_COL_ALIASES 튜플 == TS alternatives 배열 (순서 포함)
 *   2. TS required == ["well_id", "value"]. plate_id 가 required 로 돌아오면 실패
 *   3. Python 이 여전히 plate_id 를 plate_meta 에서 유도하는지 (그 분기가 사라지면
 *      plate_id 는 다시 필수가 되어야 하고, 이 check 가 그 순간을 잡는다)
 *
 * 값 추출은 import 가 아니라 `ast` 다. 대상이 순수 리터럴이고, ingest 모듈을
 * import 하면 pandas 까지 끌고 온다.
 *
 * `.cross-layer-sync.json` 의 `checks[]` 에 `command` 로 배선되어
 * `node scripts/sync-check-all.mjs` 가 함께 돌린다.
 *
 * Usage: node scripts/sync-check-mame-activity-schema.mjs
 */
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const TS_FILE = "src/lib/schemaValidator.ts";
const PY_FILE = "kuma_core/mame/activity/ingest_long_csv.py";

/** required 는 이 둘이어야 한다. plate_id 는 Python 이 유도하므로 optional 이다. */
const EXPECTED_REQUIRED = ["well_id", "value"];
/** Python 튜플 이름 -> TS alternatives 의 canonical 키. */
const ALIAS_TUPLES = {
  WELL_COL_ALIASES: "well_id",
  VALUE_COL_ALIASES: "value",
};

const problems = [];

function pythonBin() {
  if (process.env.PYTHON_BIN) return process.env.PYTHON_BIN;
  const venv = path.join(
    ROOT,
    process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python",
  );
  if (fs.existsSync(venv)) return venv;
  return process.platform === "win32" ? "python" : "python3";
}

/** 모듈 최상위 튜플/리스트 리터럴을 ast 로 읽는다. import 하지 않는다. */
function pythonLiterals(file, names) {
  const code = [
    "import ast, json, sys",
    `tree = ast.parse(open(${JSON.stringify(file)}, encoding="utf-8").read())`,
    `want = set(${JSON.stringify(names)})`,
    "out = {}",
    "for node in tree.body:",
    "    if not isinstance(node, ast.Assign):",
    "        continue",
    "    for target in node.targets:",
    "        if isinstance(target, ast.Name) and target.id in want:",
    "            out[target.id] = list(ast.literal_eval(node.value))",
    "print(json.dumps(out))",
  ].join("\n");
  const res = spawnSync(pythonBin(), ["-c", code], { cwd: ROOT, encoding: "utf-8" });
  if (res.status !== 0) {
    throw new Error(
      `python could not read ${file} (${pythonBin()}): ` +
        (res.stderr || res.error?.message || "unknown error").trim(),
    );
  }
  return JSON.parse(res.stdout);
}

/**
 * TS 소스에서 객체 리터럴을 그대로 떼어내 평가한다.
 * janus-defaults check 와 같은 방식. 순수 데이터라 트랜스파일러가 필요 없다.
 */
function tsObjectLiteral(file, marker, open = "{", close = "}") {
  const src = fs.readFileSync(path.join(ROOT, file), "utf-8");
  const start = src.indexOf(marker);
  if (start === -1) throw new Error(`${file}: ${marker} not found`);
  const from = src.indexOf(open, start);
  let depth = 0;
  let end = -1;
  for (let i = from; i < src.length; i++) {
    if (src[i] === open) depth++;
    else if (src[i] === close) {
      depth--;
      if (depth === 0) {
        end = i;
        break;
      }
    }
  }
  if (end === -1) throw new Error(`${file}: unterminated literal after ${marker}`);
  return new Function(`return (${src.slice(from, end + 1)});`)();
}

function main() {
  const py = pythonLiterals(PY_FILE, Object.keys(ALIAS_TUPLES));
  const ts = tsObjectLiteral(TS_FILE, "export const MAME_ACTIVITY_CSV_SCHEMA");

  const required = [...(ts.required ?? [])].sort();
  if (required.join(",") !== [...EXPECTED_REQUIRED].sort().join(",")) {
    problems.push(
      `required is [${ts.required}] but the backend only insists on ` +
        `[${EXPECTED_REQUIRED}]. plate_id is derived from plate_meta ` +
        `(${PY_FILE}), so requiring it blocks files the sidecar accepts.`,
    );
  }

  for (const [tupleName, canonical] of Object.entries(ALIAS_TUPLES)) {
    const pyAliases = py[tupleName];
    if (!pyAliases) {
      problems.push(`${PY_FILE}: ${tupleName} not found as a module-level literal`);
      continue;
    }
    const tsAliases = ts.alternatives?.[canonical];
    if (!tsAliases) {
      problems.push(
        `${TS_FILE}: alternatives.${canonical} missing; ${tupleName} lists [${pyAliases}]`,
      );
      continue;
    }
    if (JSON.stringify(pyAliases) !== JSON.stringify(tsAliases)) {
      problems.push(
        `${canonical} alias drift: python ${tupleName}=${JSON.stringify(pyAliases)} ` +
          `ts alternatives.${canonical}=${JSON.stringify(tsAliases)}`,
      );
    }
    // 별칭이 unknown 으로 찍히지 않으려면 optional 에도 못 들어가야 한다는 뜻은
    // 아니다. validateCsvHeader 가 alternatives 를 allowed 집합에 넣는다.
  }

  // plate_id 유도 분기가 살아 있는지. 사라지면 plate_id 는 다시 필수가 된다.
  const pySrc = fs.readFileSync(path.join(ROOT, PY_FILE), "utf-8");
  if (!/if\s+"plate_id"\s+not\s+in\s+df\.columns:/.test(pySrc)) {
    problems.push(
      `${PY_FILE}: the plate_id derivation branch is gone. plate_id may be ` +
        `required again, in which case ${TS_FILE} must move it back into required.`,
    );
  }
  if ((ts.optional ?? []).includes("plate_id") === false) {
    problems.push(
      `${TS_FILE}: plate_id must stay in optional, otherwise a file that carries ` +
        `it is reported as an unknown column.`,
    );
  }

  if (problems.length > 0) {
    console.error("[mame-activity-csv-schema] FAIL: activity CSV header contract is out of sync");
    for (const p of problems) console.error(`  - ${p}`);
    console.error(
      `  Fix by editing ${TS_FILE} to match ${PY_FILE}; the Python module is the ` +
        "canon because it is what actually parses the upload.",
    );
    process.exit(1);
  }

  const aliasCount = Object.values(ALIAS_TUPLES).reduce(
    (n, canonical) => n + (ts.alternatives?.[canonical]?.length ?? 0),
    0,
  );
  console.log(
    `[mame-activity-csv-schema] OK: required [${ts.required}] and ${aliasCount} ` +
      `column aliases aligned between ${TS_FILE} and ${PY_FILE}`,
  );
}

try {
  main();
} catch (err) {
  console.error(`[mame-activity-csv-schema] FAIL: ${err.message}`);
  process.exit(1);
}
