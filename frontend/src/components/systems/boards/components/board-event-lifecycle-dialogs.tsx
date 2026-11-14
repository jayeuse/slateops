"use client";

import { Alert } from "@/components/ui/alert";
import { ErrorReference } from "@/components/ui/error-reference";
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { DisabledReason } from "@/components/ui/disabled-reason";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import type { WorkspaceRegion } from "@/lib/date-time";
import type { LifecyclePurgePreview } from "@/lib/lifecycle";
import { LifecyclePurgeReview } from "../../shared/lifecycle-purge-review";
import type { BoardEventLifecycleAction } from "./server-backed-board-event-lifecycle";

/** Archive asks once with its consequence; Restore confirms the series. */
export function BoardEventLifecycleDialog({
  open,
  target,
  error,
  reference,
  pending,
  canConfirm,
  onCancel,
  onConfirm,
}: {
  open: boolean;
  target: BoardEventLifecycleAction | null;
  error: string | null;
  /** The failed request's ID, shown under the error (D1.4). */
  reference?: string;
  pending: boolean;
  canConfirm: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        if (!next && !pending) onCancel();
      }}
    >
      <AlertDialogContent className="slim-ui">
        <AlertDialogHeader>
          <AlertDialogTitle>
            {target?.kind === "archive" ? "Archive event?" : "Restore event?"}
          </AlertDialogTitle>
          <AlertDialogDescription>
            {target?.kind === "archive"
              ? `Archive “${target.title}”? It leaves the calendar, and a board manager can restore it.`
              : `Restore “${target?.title ?? "this event"}” to the calendar?`}
          </AlertDialogDescription>
        </AlertDialogHeader>
        {error ? (
          <Alert variant="destructive" reference={reference}>
            {error}
          </Alert>
        ) : null}
        <AlertDialogFooter>
          <Button
            type="button"
            variant="ghost"
            className="min-h-11 xl:min-h-8"
            disabled={pending}
            onClick={onCancel}
          >
            Cancel
          </Button>
          <DisabledReason
            stable
            reason={
              pending || canConfirm
                ? null
                : target?.kind === "archive"
                  ? "This event changed, or you can no longer archive it."
                  : "This event changed, or you can no longer restore it."
            }
          >
            <Button
              type="button"
              variant={target?.kind === "archive" ? "destructive" : "default"}
              className="min-h-11 xl:min-h-8"
              disabled={!canConfirm}
              pending={pending}
              pendingLabel={
                target?.kind === "archive" ? "Archiving…" : "Restoring…"
              }
              onClick={onConfirm}
            >
              {target?.kind === "archive" ? "Archive event" : "Restore event"}
            </Button>
          </DisabledReason>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

/** Delete forever (admins, archived events): the existing guarded review. */
export function BoardEventPurgeDialog({
  open,
  pending,
  enabled,
  preview,
  error,
  reference,
  name,
  password,
  region,
  onName,
  onPassword,
  onConfirm,
  onReviewAgain,
  onClose,
}: {
  open: boolean;
  pending: boolean;
  enabled: boolean;
  preview: LifecyclePurgePreview | null;
  error: string;
  reference?: string;
  name: string;
  password: string;
  region: WorkspaceRegion | undefined;
  onName: (value: string) => void;
  onPassword: (value: string) => void;
  onConfirm: () => void;
  onReviewAgain: () => void;
  onClose: () => void;
}) {
  return (
    <Dialog
      open={open}
      dismissible={!pending}
      onOpenChange={(next) => {
        if (!next && !pending) onClose();
      }}
    >
      <DialogContent className="slim-ui">
        <DialogHeader>
          <DialogTitle>Delete event forever?</DialogTitle>
          <DialogDescription>
            This removes the archived event forever.
          </DialogDescription>
        </DialogHeader>
        {pending && !preview ? <p role="status">Preparing review…</p> : null}
        {error ? (
          <div>
            <p role="alert" className="text-destructive text-sm">
              {error}
            </p>
            <ErrorReference id={reference} />
          </div>
        ) : null}
        {preview ? (
          <div className="mt-4 space-y-4">
            <LifecyclePurgeReview preview={preview} region={region} />
            {preview.impact.blockers.length === 0 ? (
              <form
                className="space-y-4"
                onSubmit={(event) => {
                  event.preventDefault();
                  onConfirm();
                }}
              >
                <p className="text-sm break-words">
                  Event name: <code>{preview.confirmation_name}</code>
                </p>
                <label className="block space-y-2 text-sm">
                  Type the event name
                  <Input
                    autoComplete="off"
                    value={name}
                    disabled={pending}
                    onChange={(event) => onName(event.target.value)}
                  />
                </label>
                <label className="block space-y-2 text-sm">
                  Administrator password
                  <Input
                    type="password"
                    autoComplete="current-password"
                    value={password}
                    disabled={pending}
                    onChange={(event) => onPassword(event.target.value)}
                  />
                </label>
                {/* A plain box: in the space-y form, the reason's text after
                    the button must not give the button a bottom margin. */}
                <div>
                  <DisabledReason
                    stable
                    reason={
                      pending
                        ? null
                        : !enabled
                          ? "Deleting forever is turned off for this workspace."
                          : name !== preview.confirmation_name
                            ? "Type the event name to confirm."
                            : !password
                              ? "Enter your administrator password."
                              : null
                    }
                  >
                    <Button
                      type="submit"
                      variant="destructive"
                      className="min-h-11 xl:min-h-8"
                      pending={pending}
                      pendingLabel="Deleting…"
                    >
                      Delete event forever
                    </Button>
                  </DisabledReason>
                </div>
              </form>
            ) : null}
          </div>
        ) : !pending ? (
          <Button
            className="mt-4 min-h-11 xl:min-h-8"
            variant="outline"
            onClick={onReviewAgain}
          >
            Review again
          </Button>
        ) : null}
        <Button
          className="mt-4 min-h-11 xl:min-h-8"
          variant="ghost"
          disabled={pending}
          onClick={onClose}
        >
          Cancel
        </Button>
      </DialogContent>
    </Dialog>
  );
}
