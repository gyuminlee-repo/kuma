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
    <div className="min-h-screen bg-muted px-6 py-12 text-foreground">
      <div className="mx-auto flex w-full max-w-2xl flex-col rounded-container border border-border bg-card p-8">
        <h1 className="text-3xl font-bold tracking-tight">Get started</h1>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">
          Choose a default folder for projects. New projects will be created inside this folder.
        </p>

        <label className="mt-8 text-sm font-medium text-foreground" htmlFor="projects-root">
          Projects folder
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
            Choose folder
          </Button>
          <Button type="button" onClick={() => void handleSubmit()} disabled={!path.trim() || isSaving}>
            Done
          </Button>
        </div>

        {error ? <p className="mt-4 text-sm text-error">{error}</p> : null}
      </div>
    </div>
  );
}
