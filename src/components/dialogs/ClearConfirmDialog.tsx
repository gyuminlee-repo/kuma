import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

interface ClearConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
}

export function ClearConfirmDialog({ open, onOpenChange, onConfirm }: ClearConfirmDialogProps) {
  const { t } = useTranslation();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>{t("clearConfirmDialog.title")}</DialogTitle>
          <DialogDescription>
            {t("clearConfirmDialog.description")}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
            {t("clearConfirmDialog.cancelBtn")}
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="text-error border-error/40 hover:bg-error/8"
            onClick={() => {
              onConfirm();
              onOpenChange(false);
            }}
          >
            {t("clearConfirmDialog.clearBtn")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
