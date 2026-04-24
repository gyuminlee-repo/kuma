import { useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { setProjectsRoot, type Config } from "../lib/project";
import { formatError } from "../lib/utils";

type OnboardingProps = {
  initialPath?: string;
  onDone: (cfg: Config) => void;
};

export function Onboarding({ initialPath, onDone }: OnboardingProps) {
  const [path, setPath] = useState(initialPath ?? "");
  const [error, setError] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  async function handlePickFolder() {
    setError("");
    try {
      const selected = await open({ directory: true });
      if (typeof selected === "string") {
        setPath(selected);
      }
    } catch (err) {
      setError(formatError(err));
    }
  }

  async function handleSubmit() {
    if (!path.trim()) {
      return;
    }

    setIsSaving(true);
    setError("");
    try {
      const cfg = await setProjectsRoot(path.trim());
      onDone(cfg);
    } catch (err) {
      setError(formatError(err));
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-100 px-6 py-12 text-slate-900">
      <div className="mx-auto flex w-full max-w-2xl flex-col rounded-3xl border border-slate-200 bg-white/90 p-8 shadow-sm">
        <h1 className="text-3xl font-bold tracking-tight">시작하기</h1>
        <p className="mt-3 text-sm leading-6 text-slate-600">
          프로젝트가 저장될 기본 폴더를 정해 주세요. 이후 새 프로젝트는 이 경로 아래에 만들어집니다.
        </p>

        <label className="mt-8 text-sm font-medium text-slate-700" htmlFor="projects-root">
          프로젝트 폴더
        </label>
        <Input
          id="projects-root"
          value={path}
          onChange={(event) => setPath(event.target.value)}
          placeholder={initialPath ? undefined : "~/Documents/kuma/"}
          className="mt-2 bg-white"
        />

        <div className="mt-4 flex flex-wrap gap-3">
          <Button type="button" variant="outline" className="bg-white" onClick={() => void handlePickFolder()}>
            폴더 선택
          </Button>
          <Button type="button" onClick={() => void handleSubmit()} disabled={!path.trim() || isSaving}>
            완료
          </Button>
        </div>

        {error ? <p className="mt-4 text-sm text-red-600">{error}</p> : null}
      </div>
    </div>
  );
}
