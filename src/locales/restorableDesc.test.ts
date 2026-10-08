/**
 * `home.restorableDesc` promises only what `collect_restorable` delivers.
 *
 * The sentence used to read "Removed from the recent list but still present on
 * disk", which claims every project that still exists anywhere. The Rust side
 * does a single `read_dir(projects_root)` over direct entries
 * (`src-tauri/src/config.rs:244-262`), so changing the projects root from
 * Onboarding re-entry (`src/screens/Onboarding.tsx:70`) makes every earlier
 * project invisible while the old sentence still promised to list it.
 *
 * The scoping has to hold in all ten locales, or nine users read the old claim.
 */

import { describe, expect, it } from "vitest";

import de from "./de.json";
import en from "./en.json";
import es from "./es.json";
import fr from "./fr.json";
import ja from "./ja.json";
import ko from "./ko.json";
import ptBR from "./pt-BR.json";
import ru from "./ru.json";
import zhCN from "./zh-CN.json";
import zhTW from "./zh-TW.json";

/**
 * A phrase naming the folder restriction, per locale. Deliberately a substring
 * of the real sentence and not the whole thing: this asserts the CLAIM is
 * scoped, not that the wording never gets polished.
 */
const FOLDER_PHRASE: Record<string, [{ home: { restorableDesc: string } }, string]> = {
  en: [en, "current projects folder"],
  de: [de, "aktuellen Projektordner"],
  es: [es, "carpeta de proyectos actual"],
  fr: [fr, "dossier de projets actuel"],
  ja: [ja, "現在のプロジェクトフォルダー"],
  ko: [ko, "현재 프로젝트 폴더"],
  "pt-BR": [ptBR, "pasta de projetos atual"],
  ru: [ru, "текущей папке проектов"],
  "zh-CN": [zhCN, "当前项目文件夹"],
  "zh-TW": [zhTW, "目前專案資料夾"],
};

describe("home.restorableDesc is scoped to the current projects folder", () => {
  it("covers all ten shipped locales", () => {
    expect(Object.keys(FOLDER_PHRASE)).toHaveLength(10);
  });

  for (const [locale, [bundle, phrase]] of Object.entries(FOLDER_PHRASE)) {
    it(`${locale} names the folder restriction`, () => {
      expect(bundle.home.restorableDesc).toContain(phrase);
    });

    it(`${locale} no longer claims everything still on disk`, () => {
      // The English original and each translation of it said "on disk" with no
      // qualifier. Nothing that reads that way may remain.
      const sentence = bundle.home.restorableDesc;
      for (const overclaim of [
        "still present on disk",
        "auf der Festplatte vorhanden",
        "presentes en el disco",
        "présents sur le disque",
        "ディスクには残っている",
        "디스크에 그대로 남아",
        "presentes no disco",
        "есть на диске",
        "保留在磁盘上",
        "保留在磁碟上",
      ]) {
        expect(sentence).not.toContain(overclaim);
      }
    });
  }
});
