"use client";

import { useId, useState } from "react";
import type { Route } from "next";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";

import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useWorkspaceNavigationRequest } from "@/components/workspace-navigation-guard";
import { ApiError } from "@/lib/api";
import { reportDone } from "@/lib/feedback";

import { worksheetKeys } from "../adapters/worksheet-queries";
import {
  deleteWorksheet,
  renameWorksheet,
  type WorksheetDetail,
} from "../adapters/worksheets-api";

// Rename and Delete sheet, the owner's More actions (docs/specs/sheets.md
// V5, L7, F3; D10 routes 5 and 7). Both send the sheet's version; a sheet
// that changed meanwhile, or that is open now, says so and changes nothing.

function refusal(error: unknown, action: "renamed" | "deleted"): string {
  if (error instanceof ApiError) {
    if (error.status === 412)
      return "Someone changed this sheet since you opened it. It now shows the newer version. Try again.";
    if (error.code === "worksheet_open")
      return `This sheet is open now, so it cannot be ${action}.`;
    if (error.status === 403) return `Only the owner can do this.`;
    if (error.status === 422 && action === "renamed")
      return "Use a name of 1 to 200 characters.";
  }
  return `The sheet could not be ${action}. Try again.`;
}

type Props = {
  sheet: WorksheetDetail;
  onClose: () => void;
  onGone: () => void;
};

export function SheetRenameDialog({ sheet, onClose, onGone }: Props) {
  const id = useId();
  const client = useQueryClient();
  const [name, setName] = useState(sheet.title);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submit = async () => {
    if (pending) return;
    const title = name.trim();
    if (!title) {
      setError("Enter a name.");
      return;
    }
    if (title === sheet.title) {
      onClose();
      return;
    }
    setPending(true);
    setError(null);
    try {
      const renamed = await renameWorksheet(sheet.id, sheet.etag, title);
      client.setQueryData(worksheetKeys.detail(sheet.id), renamed);
      void client.invalidateQueries({
        queryKey: worksheetKeys.place(sheet.id),
      });
      void client.invalidateQueries({
        queryKey: worksheetKeys.all,
        refetchType: "none",
      });
      onClose();
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 404) {
        onGone();
        return;
      }
      setError(refusal(failure, "renamed"));
      void client.invalidateQueries({
        queryKey: worksheetKeys.detail(sheet.id),
      });
    } finally {
      setPending(false);
    }
  };
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !pending) onClose();
      }}
    >
      <DialogContent>
        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <DialogHeader>
            <DialogTitle>Rename sheet</DialogTitle>
          </DialogHeader>
          <div className="flex flex-col gap-1.5">
            <label htmlFor={`${id}-name`} className="text-sm font-medium">
              Name
            </label>
            <Input
              id={`${id}-name`}
              autoFocus
              maxLength={200}
              className="min-h-11 xl:h-8 xl:min-h-8"
              value={name}
              aria-invalid={Boolean(error) || undefined}
              aria-describedby={error ? `${id}-error` : undefined}
              onChange={(event) => setName(event.target.value)}
            />
            {error ? (
              <p
                id={`${id}-error`}
                role="alert"
                className="text-danger-text text-sm"
              >
                {error}
              </p>
            ) : null}
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              className="min-h-11 xl:h-8 xl:min-h-8"
              disabled={pending}
              onClick={onClose}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              className="min-h-11 xl:h-8 xl:min-h-8"
              pending={pending}
              pendingLabel="Saving…"
            >
              Save
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function SheetDeleteDialog({ sheet, onClose, onGone }: Props) {
  const client = useQueryClient();
  const router = useRouter();
  const requestNavigation = useWorkspaceNavigationRequest();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const confirm = async () => {
    if (pending) return;
    setPending(true);
    setError(null);
    try {
      await deleteWorksheet(sheet.id, sheet.etag);
      void client.invalidateQueries({
        queryKey: worksheetKeys.all,
        refetchType: "none",
      });
      reportDone(`${sheet.title} deleted`);
      onClose();
      // My sheets offers Restore in its Deleted list (F3).
      const href = "/openview?section=sheets";
      const go = () => router.push(href as Route);
      if (requestNavigation(href, go)) go();
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 404) {
        onGone();
        return;
      }
      setError(refusal(failure, "deleted"));
      void client.invalidateQueries({
        queryKey: worksheetKeys.detail(sheet.id),
      });
    } finally {
      setPending(false);
    }
  };
  return (
    <AlertDialog
      open
      onOpenChange={(open) => {
        if (!open && !pending) onClose();
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete {sheet.title}?</AlertDialogTitle>
          <AlertDialogDescription>
            It disappears for everyone it is shared with. You can restore it
            from My sheets.
          </AlertDialogDescription>
        </AlertDialogHeader>
        {error ? (
          <p role="alert" className="text-danger-text text-sm">
            {error}
          </p>
        ) : null}
        <AlertDialogFooter>
          <Button
            variant="ghost"
            className="min-h-11 xl:h-8 xl:min-h-8"
            disabled={pending}
            onClick={onClose}
          >
            Cancel
          </Button>
          <Button
            variant="destructive"
            className="min-h-11 xl:h-8 xl:min-h-8"
            pending={pending}
            pendingLabel="Deleting…"
            onClick={() => void confirm()}
          >
            Delete sheet
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
