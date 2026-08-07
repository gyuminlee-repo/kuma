#!/usr/bin/env node
/**
 * sync-check-mame-extensions.mjs, MAME 입력 확장자 집합, TS vs Python.
 *
 * `python-core/sidecar_mame/core.py` 의 세 집합이 `handle_validate_inputs` 가
 * 실제로 수락/거부하는 경계다. 프런트에는 picker(InputPanel), 배너
 * (MissingInputsBanner), 드롭 핸들러(MameAppLayout) 세 소비자가 있고, 예전에는
 * 셋이 각자 목록을 들고 있어 어느 둘도 일치하지 않았다. 넓은 쪽은 함정이 되어
 * 조작자가 고른 뒤에야 "Unsupported file extension '.csv'" 가 오고, 좁은 쪽은
 * .gb reference 를 배너에서 아예 숨겼다.
 *
 * 이제 사본은 `src/lib/mame/fileExtensions.ts` 하나이고, 이 check 가 그 하나를
 * Python 정본에 묶는다. 소비자들이 모듈에서 import 하는지도 함께 확인한다.
 * `mame-sequence-extensions` 그룹은 파일을 이어 붙여 심볼을 한 번만 찾으므로
 * 한 곳만 맞아도 통과한다. 이 check 가 그 빈틈을 메운다.
 *
 * 값 추출은 ast 다. `sidecar_mame.core` 를 import 하면 RPC 기구까지 끌고 온다.
 *
 * Usage: node scripts/sync-check-mame-extensions.mjs
 */
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const TS_FILE = "src/lib/mame/fileExtensions.ts";
const PY_FILE = "python-core/sidecar_mame/core.py";

/** Python 집합 이름 -> TS export 이름. */
const SET_MAP = {
  _ALLOWED_FASTA_EXTENSIONS: "MAME_FASTA_EXTENSIONS",
  _ALLOWED_SEQUENCE_EXTENSIONS: "MAME_SEQUENCE_EXTENSIONS",
  _ALLOWED_EXCEL_EXTENSIONS: "MAME_EXCEL_EXTENSIONS",
};

/** 소비자가 손으로 다시 적지 않고 모듈에서 가져오는지 확인한다. */
const CONSUMERS = [
  "src/components/mame/panels/InputPanel.tsx",
  "src/components/mame/panels/MissingInputsBanner.tsx",
  "src/components/mame/layout/MameAppLayout.tsx",
];

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

/** 모듈 최상위 set 리터럴을 ast 로 읽는다. 순서가 없으므로 정렬해 돌려준다. */
function pythonSets(file, names) {
  const code = [
    "import ast, json",
    `tree = ast.parse(open(${JSON.stringify(file)}, encoding="utf-8").read())`,
    `want = set(${JSON.stringify(names)})`,
    "out = {}",
    "for node in tree.body:",
    "    if not isinstance(node, ast.Assign):",
    "        continue",
    "    for target in node.targets:",
    "        if isinstance(target, ast.Name) and target.id in want:",
    "            out[target.id] = sorted(ast.literal_eval(node.value))",
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

/** TS 배열 리터럴을 그대로 떼어내 평가한다. `as const` 는 닫는 대괄호 뒤라 걸리지 않는다. */
function tsArray(src, name) {
  const marker = `export const ${name}`;
  const start = src.indexOf(marker);
  if (start === -1) throw new Error(`${TS_FILE}: ${name} not found`);
  const from = src.indexOf("[", start);
  let depth = 0;
  let end = -1;
  for (let i = from; i < src.length; i++) {
    if (src[i] === "[") depth++;
    else if (src[i] === "]") {
      depth--;
      if (depth === 0) {
        end = i;
        break;
      }
    }
  }
  if (end === -1) throw new Error(`${TS_FILE}: unterminated array literal for ${name}`);
  return new Function(`return (${src.slice(from, end + 1)});`)();
}

function main() {
  const py = pythonSets(PY_FILE, Object.keys(SET_MAP));
  const tsSrc = fs.readFileSync(path.join(ROOT, TS_FILE), "utf-8");

  for (const [pyName, tsName] of Object.entries(SET_MAP)) {
    const pySet = py[pyName];
    if (!pySet) {
      problems.push(`${PY_FILE}: ${pyName} not found as a module-level set literal`);
      continue;
    }
    const tsList = [...tsArray(tsSrc, tsName)].sort();
    if (JSON.stringify(pySet) !== JSON.stringify(tsList)) {
      problems.push(
        `${tsName} drift: python ${pyName}=${JSON.stringify(pySet)} ` +
          `ts=${JSON.stringify(tsList)}`,
      );
    }
    for (const ext of tsList) {
      if (!ext.startsWith(".")) {
        problems.push(`${tsName} entry "${ext}" must keep the leading dot, like the Python set`);
      }
      if (ext !== ext.toLowerCase()) {
        problems.push(`${tsName} entry "${ext}" must be lower case; matching lower-cases the path`);
      }
    }
  }

  for (const consumer of CONSUMERS) {
    const src = fs.readFileSync(path.join(ROOT, consumer), "utf-8");
    if (!src.includes("@/lib/mame/fileExtensions")) {
      problems.push(
        `${consumer} no longer imports ${TS_FILE}. A local extension list here is ` +
          "exactly the drift this check exists to stop.",
      );
    }
  }

  if (problems.length > 0) {
    console.error("[mame-extensions] FAIL: MAME input extension sets are out of sync");
    for (const p of problems) console.error(`  - ${p}`);
    console.error(
      `  Fix by editing ${TS_FILE} to match ${PY_FILE}; the sidecar sets are the ` +
        "boundary that actually accepts or refuses the file.",
    );
    process.exit(1);
  }

  console.log(
    `[mame-extensions] OK: ${Object.keys(SET_MAP).length} extension sets aligned between ` +
      `${TS_FILE} and ${PY_FILE}, ${CONSUMERS.length} consumers importing them`,
  );
}

try {
  main();
} catch (err) {
  console.error(`[mame-extensions] FAIL: ${err.message}`);
  process.exit(1);
}
