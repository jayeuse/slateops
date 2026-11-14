"use client";

import { useEffect, useId, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type {
  LifecycleDerivedChange,
  LifecycleMutationResponse,
  LifecyclePreviewResponse,
} from "@/lib/api";
import { workspaceCalendarQueryOptions } from "../../manage/adapters/workspace-api";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DisabledReason } from "@/components/ui/disabled-reason";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { LifecyclePurgeReview } from "@/components/systems/shared/lifecycle-purge-review";
import {
  DialogFrameFooter,
  DialogFrameHeader,
  dialogFrameContentClass,
} from "@/components/ui/dialog-frame";
import {
  structuralLifecycleErrorMessage,
  type LifecyclePurgeInput,
  type LifecyclePurgePreview,
} from "@/lib/lifecycle";
import {
  previewSandboxLifecycle,
  type SandboxLifecycleRequest,
} from "../state/lifecycle-api";
import { useErrorText } from "@/lib/use-error-text";
import { ChangeGroup } from "./publish-change-groups";

const CHANNEL_NOUNS = ["channel", "channels"] as const;

/**
 * What a department close does to its channels (BE-SD7, SD17): the setup
 * channel is archived, and the department's other channels stay open for
 * administrators and people given access.
 */
export function LifecycleChannelChanges({
  changes,
}: {
  changes: readonly LifecycleDerivedChange[];
}) {
  const channels = changes.filter((change) => change.role === "channel");
  const rows = [
    ...channels.filter((change) => change.action === "close"),
    ...channels.filter((change) => change.action === "keep"),
  ];
  return (
    <ChangeGroup
      title="Channels"
      note={
        rows.some((change) => change.action === "keep")
          ? "Administrators and people given access can still post in open channels."
          : undefined
      }
      noun={CHANNEL_NOUNS}
      items={rows}
      itemKey={(change) => `${change.action}-${change.target_id}`}
      render={(change) => (
        <div className="flex items-start gap-2">
          <Badge
            variant={change.action === "close" ? "warning" : "outline"}
            className="w-24 shrink-0 justify-center whitespace-nowrap"
          >
            {change.action === "close" ? "Archived" : "Stays open"}
          </Badge>
          <span className="min-w-0 wrap-anywhere">{change.name}</span>
        </div>
      )}
    />
  );
}

/** The page notice after a confirmed change; a reopen names its channel. */
export function lifecycleDoneNotice(result: LifecycleMutationResponse): string {
  const restored =
    result.impact.operation === "reopen"
      ? result.impact.derived_changes.find(
          (change) => change.role === "channel" && change.action === "reopen",
        )
      : undefined;
  return restored
    ? `Live change confirmed · Channel ${restored.name} restored`
    : "Live change confirmed";
}

type Props = {
  request: SandboxLifecycleRequest | null;
  onCancel: () => void;
  onConfirm: (input?: LifecyclePurgeInput) => Promise<void>;
};

export function SandboxLifecycleDialog({
  request,
  onCancel,
  onConfirm,
}: Props) {
  const [preview, setPreview] = useState<
    LifecyclePreviewResponse | LifecyclePurgePreview | null
  >(null);
  const [confirmation, setConfirmation] = useState("");
  const [password, setPassword] = useState("");
  const [errorFailure, setError] = useErrorText();
  const error = errorFailure?.message ?? "";
  const [busy, setBusy] = useState<"review" | "command" | null>(null);
  const generation = useRef(0);
  const confirming = useRef(false);
  const id = useId();
  const region = useQuery({
    ...workspaceCalendarQueryOptions(),
    enabled: request?.operation === "purge",
  });

  function clear() {
    setPreview(null);
    setConfirmation("");
    setPassword("");
    setError("");
  }
  async function review(current: number, target: SandboxLifecycleRequest) {
    clear();
    setBusy("review");
    try {
      const result = await previewSandboxLifecycle(target);
      if (generation.current === current) setPreview(result);
    } catch (reason) {
      if (generation.current === current)
        setError(
          structuralLifecycleErrorMessage(reason, target.operation),
          reason,
        );
    } finally {
      if (generation.current === current) setBusy(null);
    }
  }
  useEffect(() => {
    const current = ++generation.current;
    confirming.current = false;
    clear();
    setBusy(null);
    if (request && request.operation !== "reopen")
      void review(current, request);
    return () => {
      generation.current += 1;
    };
  }, [request]);

  if (!request) return null;
  const { operation, binding } = request;
  const title =
    operation === "purge"
      ? `Delete ${binding.kind} forever`
      : `${operation === "close" ? "Close" : "Reopen"} ${binding.kind}`;
  const recordLinkCount = preview
    ? new Set(
        preview.impact.external_impacts
          .map((impact) => impact.edge_id)
          .filter((id) => id !== null),
      ).size
    : 0;
  const blocked = Boolean(preview?.impact.blockers.length);
  const cancel = () => {
    if (confirming.current) return;
    generation.current += 1;
    clear();
    setBusy(null);
    onCancel();
  };
  async function confirm() {
    if (!request || confirming.current || busy || blocked) return;
    if (
      request.operation !== "reopen" &&
      (!preview || confirmation !== preview.confirmation_name || !password)
    )
      return;
    confirming.current = true;
    setBusy("command");
    setError("");
    const current = generation.current;
    try {
      await onConfirm(
        request.operation === "reopen"
          ? undefined
          : {
              token: preview!.token,
              confirmationName: preview!.confirmation_name,
              password,
            },
      );
      if (generation.current === current) {
        clear();
      }
    } catch (reason) {
      if (generation.current === current) {
        clear();
        setError(
          structuralLifecycleErrorMessage(reason, request.operation),
          reason,
        );
      }
    } finally {
      if (generation.current === current) {
        setPassword("");
        setBusy(null);
        confirming.current = false;
      }
    }
  }
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) cancel();
      }}
    >
      <DialogContent className={`${dialogFrameContentClass} sm:max-w-xl`}>
        <DialogFrameHeader
          title={<DialogTitle>{title}</DialogTitle>}
          description={
            <DialogDescription>
              {operation === "purge"
                ? `This removes the live ${binding.kind} forever, with its current design structure${binding.kind === "department" ? ", including draft modules and fields" : ""}.`
                : operation === "close"
                  ? "Review the effect on the live workspace before closing this item."
                  : "Reopens this and everything its close included."}
            </DialogDescription>
          }
          closeLabel="Close review"
          closeDisabled={busy === "command"}
          onClose={cancel}
        />
        {error ? (
          <Alert
            role="alert"
            variant="destructive"
            reference={errorFailure?.reference}
          >
            {error}
          </Alert>
        ) : null}
        {busy === "review" ? <p role="status">Preparing review…</p> : null}
        {preview &&
        operation === "purge" &&
        "last_successful_backup_at" in preview ? (
          <LifecyclePurgeReview preview={preview} region={region.data} />
        ) : null}
        {preview && operation === "close" ? (
          <div className="space-y-3 text-sm">
            <p role="status">
              This close affects {preview.impact.rows.length} items. Existing
              records are kept.
            </p>
            <LifecycleChannelChanges changes={preview.impact.derived_changes} />
            {binding.kind === "relationship" ? (
              <p>
                {recordLinkCount} record link
                {recordLinkCount === 1 ? "" : "s"} will be closed. Existing
                records are kept.
              </p>
            ) : null}
            {binding.kind === "field" ? (
              <p>
                Closing this field removes its linked fields from the current
                design.
              </p>
            ) : null}
            {blocked ? (
              <Alert role="alert" variant="warning">
                <p>Closing is blocked</p>
                <ul className="list-disc space-y-2 pl-5">
                  {preview.impact.blockers.map((blocker) => (
                    <li key={`${blocker.code}-${blocker.entity_id}`}>
                      {blocker.detail}
                    </li>
                  ))}
                </ul>
              </Alert>
            ) : null}
          </div>
        ) : null}
        {preview ? (
          <>
            <p className="text-sm">
              Confirm the live name:{" "}
              <strong className="break-words">
                {preview.confirmation_name}
              </strong>
              .
            </p>
            <Field>
              <FieldLabel htmlFor={`${id}-name`}>
                Type the {binding.kind} name
              </FieldLabel>
              <Input
                id={`${id}-name`}
                value={confirmation}
                disabled={busy !== null || blocked}
                onChange={(event) => setConfirmation(event.target.value)}
                autoComplete="off"
              />
            </Field>
            <Field>
              <FieldLabel htmlFor={`${id}-password`}>
                Administrator password
              </FieldLabel>
              <Input
                id={`${id}-password`}
                type="password"
                value={password}
                disabled={busy !== null || blocked}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="current-password"
              />
            </Field>
          </>
        ) : null}
        <DialogFrameFooter className="flex flex-wrap justify-end gap-2">
          <Button
            variant="ghost"
            disabled={busy === "command"}
            onClick={cancel}
          >
            Cancel
          </Button>
          {operation !== "reopen" && !preview && busy === null ? (
            <Button
              variant="outline"
              onClick={() => void review(++generation.current, request)}
            >
              Review again
            </Button>
          ) : null}
          {/* TASK-0061 rules 4 and 6: the command is its busy state; the
              review and each missing step are its reasons. */}
          <DisabledReason
            stable
            reason={
              busy === "command"
                ? null
                : busy === "review"
                  ? "Wait for the review to finish."
                  : blocked
                    ? "Fix the blocked items first."
                    : operation === "reopen"
                      ? null
                      : !preview
                        ? "Review the change again first."
                        : confirmation !== preview.confirmation_name
                          ? `Type the ${binding.kind} name to confirm.`
                          : !password
                            ? "Enter your administrator password."
                            : null
            }
          >
            <Button
              variant={operation === "purge" ? "destructive" : "default"}
              pending={busy === "command"}
              pendingLabel="Confirming…"
              disabled={
                busy === "review" ||
                blocked ||
                (operation !== "reopen" &&
                  (!preview ||
                    confirmation !== preview.confirmation_name ||
                    !password))
              }
              onClick={() => void confirm()}
            >
              {title}
            </Button>
          </DisabledReason>
        </DialogFrameFooter>
      </DialogContent>
    </Dialog>
  );
}
