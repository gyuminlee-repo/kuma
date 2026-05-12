import { useTranslation } from "react-i18next";
import { SequenceInput } from "./SequenceInput";
import { MutationInput } from "./MutationInput";

export function InputPanel() {
  const { t } = useTranslation("inputPanel");
  return (
    <section className="space-y-3 rounded-container border bg-card p-3">
      <div>
        <div className="text-caption font-semibold uppercase tracking-wide text-muted-foreground">{t("sectionLabel")}</div>
        <h3 className="text-sm font-semibold text-foreground">{t("title")}</h3>
      </div>

      <SequenceInput />
      <MutationInput />
    </section>
  );
}
