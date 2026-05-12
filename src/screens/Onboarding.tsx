import { useState } from "react";
import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation();
  const [path, setPath] = useState(initialPath ?? "");
  const [error, setError] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  const isReentry = Boolean(initialPath);

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
        <h1 className="text-3xl font-bold tracking-tight">
          {isReentry ? t("onboarding.titleChange") : t("onboarding.titleNew")}
        </h1>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">
          {isReentry
            ? t("onboarding.descChange")
            : t("onboarding.descNew")}
        </p>

        <label className="mt-8 text-sm font-medium text-foreground" htmlFor="projects-root">
          {t("onboarding.projectsFolder")}
        </label>
        <Input
          id="projects-root"
          value={path}
          onChange={(event) => setPath(event.target.value)}
          placeholder={initialPath ? undefined : t("onboarding.folderPlaceholder")}
          className="mt-2"
        />

        <div className="mt-4 flex flex-wrap gap-3">
          <Button type="button" variant="outline" onClick={() => void handlePickFolder()}>
            {t("onboarding.chooseFolder")}
          </Button>
          <Button type="button" onClick={() => void handleSubmit()} disabled={!path.trim() || isSaving}>
            {t("onboarding.done")}
          </Button>
        </div>

        {error ? <p className="mt-4 text-sm text-error">{error}</p> : null}

        <div className="mt-8 border-t border-border pt-6">
          <p className="text-sm font-medium text-foreground">{t("onboarding.insideProject")}</p>
          <dl className="mt-3 space-y-2">
            <div className="flex gap-2 text-sm text-muted-foreground">
              <dt className="font-semibold text-foreground">Kuro</dt>
              <dd>{t("onboarding.kuroDesc")}</dd>
            </div>
            <div className="flex gap-2 text-sm text-muted-foreground">
              <dt className="font-semibold text-foreground">Mame</dt>
              <dd>{t("onboarding.mameDesc")}</dd>
            </div>
            <div className="mt-3 text-sm text-muted-foreground">
              {t("onboarding.autosaveNote")}
            </div>
          </dl>
        </div>
      </div>
    </div>
  );
}
