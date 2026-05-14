import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";
import type { ArtifactRef } from "@/lib/workspace/types";

interface Props {
  artifact: ArtifactRef;
  className?: string;
}

export function ArtifactBadge({ artifact, className }: Props) {
  const { t } = useTranslation();
  const variant = artifact.stale ? "warning" : "secondary";
  const title = artifact.stale
    ? `${artifact.path}\n${t("artifact.badge.staleHint")}`
    : artifact.path;

  return (
    <Badge variant={variant} className={className} title={title}>
      {t("artifact.badge.detected", { step: artifact.step })}
    </Badge>
  );
}
