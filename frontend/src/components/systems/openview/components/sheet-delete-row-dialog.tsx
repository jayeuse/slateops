"use client";

import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

/** Delete row's confirmation (F4; no Undo in v1). Loads on first use. */
export default function SheetDeleteRowDialog({
  index,
  onCancel,
  onConfirm,
}: {
  index: number;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <AlertDialog
      open
      onOpenChange={(open) => {
        if (!open) onCancel();
      }}
    >
      <AlertDialogContent>
        <AlertDialogTitle>Delete row {index + 1}?</AlertDialogTitle>
        <AlertDialogDescription>
          It leaves this sheet for everyone who can see it. You cannot undo
          this.
        </AlertDialogDescription>
        <div className="flex justify-end gap-2">
          <AlertDialogCancel
            render={<Button variant="ghost" className="min-h-11" />}
          >
            Cancel
          </AlertDialogCancel>
          <Button
            variant="destructive"
            className="min-h-11"
            onClick={onConfirm}
          >
            Delete row
          </Button>
        </div>
      </AlertDialogContent>
    </AlertDialog>
  );
}
