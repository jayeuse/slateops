"use client";

import { useEffect, useId, useRef, useState } from "react";
import type { Route } from "next";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { DepartmentMark } from "@/components/sandbox/department-mark";
import { moduleHref } from "@/components/department-navigation-model";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { DisabledReason } from "@/components/ui/disabled-reason";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
} from "@/components/ui/dialog";
import { useSkeletonVisible } from "@/components/ui/loading-region";
import { cn } from "@/lib/utils";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  DialogFrameFooter,
  DialogFrameHeader,
  dialogFrameContentClass,
} from "@/components/ui/dialog-frame";
import {
  PublishChangeGroups,
  type PublishReviewDesign,
} from "./publish-change-groups";
import { SetupControl } from "./setup-popover";
import { departmentSetup } from "../domain/department-setup";
import type { DepartmentSetup } from "../domain/model";
import type { SandboxCommandResult } from "../state/commands";
import {
  publicationRefusalBlockers,
  type SandboxPublication,
  type SandboxPublicationBlocker,
  type SandboxPublicationPreview,
} from "../state/api";
import type { SandboxBinding } from "../state/lifecycle-api";
import { useErrorText } from "@/lib/use-error-text";
import { ErrorReference } from "@/components/ui/error-reference";

type Props = {
  open: boolean;
  expectedRevision: number;
  disabled: boolean;
  /** The draft being reviewed, so field changes can sit under their module. */
  design: PublishReviewDesign;
  /** Trigger settings the server cannot publish, found before the review. */
  localBlockers: readonly SandboxPublicationBlocker[];
  /** Closes the review and opens the thing that blocks publishing. */
  onOpenBlocker: (blocker: SandboxPublicationBlocker) => void;
  onOpenChange: (open: boolean) => void;
  onPendingChange?: (pending: boolean) => void;
  onPreview: () => Promise<SandboxPublicationPreview>;
  onPublish: (input: {
    preview: SandboxPublicationPreview;
    password: string;
    note: string;
    idempotencyKey: string;
  }) => Promise<SandboxPublication>;
  /**
   * Refreshes the page after a publish and gives the bindings read after it
   * (DR-11.5). A failed read rejects, and the Published state has no link.
   */
  onPublished: (
    publication: SandboxPublication,
  ) => Promise<readonly SandboxBinding[]>;
  /**
   * FIT-3 (plan 11.3, DQ4): one Setup toggle of a new department, applied to
   * the draft through the Build save queue. On a conflict or a failed save
   * the page closes the review and shows its alert; the review shows any
   * other refusal itself.
   */
  onSetupChange?: (
    departmentId: string,
    item: keyof DepartmentSetup,
    on: boolean,
  ) => Promise<SandboxCommandResult<unknown>>;
};

/** A module this publish creates, kept for its link once it is live. */
export type PublishedModule = {
  id: string;
  name: string;
  departmentName: string;
  /** The department's position in the draft, for its mark; -1 if none. */
  departmentIndex: number;
};
export type PublishedModuleLink = PublishedModule & { href: string };

/**
 * The open modules a publish creates, with their departments, read from the
 * review and the draft when Publish is pressed (DR-11.4). A module created
 * closed has no records to open.
 */
export function createdModules(
  changes: SandboxPublicationPreview["changes"],
  design: PublishReviewDesign,
): PublishedModule[] {
  return changes.flatMap((change) => {
    if (change.kind !== "module" || change.action !== "create") return [];
    const draft = design.modules.find((item) => item.id === change.sandboxId);
    if (!draft || draft.closed) return [];
    const departmentIndex = design.departments.findIndex(
      (item) => item.id === draft.departmentId,
    );
    return [
      {
        id: change.sandboxId,
        name: change.label,
        departmentName: design.departments[departmentIndex]?.name ?? "",
        departmentIndex,
      },
    ];
  });
}

/**
 * Each created module that the bindings read after the publish names,
 * linked to its records by its live id (DR-11.5). No live module, no link.
 */
export function publishedModuleLinks(
  modules: readonly PublishedModule[],
  bindings: readonly SandboxBinding[],
): PublishedModuleLink[] {
  return modules.flatMap((item) => {
    const binding = bindings.find(
      (candidate) =>
        candidate.kind === "module" &&
        candidate.sandbox_id === item.id &&
        !candidate.is_deleted,
    );
    return binding ? [{ ...item, href: moduleHref(binding.live_id) }] : [];
  });
}

/**
 * The record links of the Published state: a skeleton row after 300 ms
 * while the bindings read runs, then one link per live module, or nothing
 * (DR-11.6). Each row is 44 px below 1280 px and 32 px from there (G5).
 */
function PublishedRecords({
  links,
}: {
  links: "reading" | readonly PublishedModuleLink[];
}) {
  const headingId = useId();
  const reading = links === "reading";
  const skeletonVisible = useSkeletonVisible(reading);
  if (reading || skeletonVisible)
    return (
      <div className={cn("grid gap-2", !skeletonVisible && "invisible")}>
        {skeletonVisible ? (
          <span role="status" className="sr-only">
            Finding the new records…
          </span>
        ) : null}
        <Skeleton className="h-5 w-28" />
        <Skeleton className="h-11 w-full xl:h-8" />
      </div>
    );
  if (!links.length) return null;
  return (
    <section aria-labelledby={headingId}>
      <h3 id={headingId} data-slot="section-title" className="font-medium">
        Open records
      </h3>
      <ul className="mt-2 grid gap-1.5">
        {links.map((link) => (
          <li key={link.id}>
            <Link
              href={link.href as Route}
              className="border-border hover:bg-muted focus-visible:outline-ring grid min-h-11 grid-cols-[0.5rem_minmax(0,1fr)_auto] items-center gap-2.5 rounded-md border px-2.5 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 xl:min-h-8"
            >
              {link.departmentIndex >= 0 ? (
                <DepartmentMark departmentIndex={link.departmentIndex} />
              ) : (
                <span aria-hidden="true" />
              )}
              <span className="min-w-0 wrap-anywhere">
                <span className="font-medium">{link.name}</span>
                {link.departmentName ? (
                  <span className="text-muted-foreground">
                    {" "}
                    · {link.departmentName}
                  </span>
                ) : null}
              </span>
              {/* The row names the module; "Open" only shows where it goes. */}
              <span
                aria-hidden="true"
                className="text-action-text inline-flex items-center gap-1 font-medium"
              >
                Open
                <ArrowRight className="size-4" />
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function publicationIdempotencyKey(
  current: string,
  create: () => string,
): string {
  return current || create();
}

function errorCode(error: unknown): string {
  return typeof error === "object" && error !== null && "code" in error
    ? String(error.code)
    : "";
}

/**
 * A publish refused because something blocks it now (SD-C7) turns the
 * review into a blocked review, so the blockers show as they would at
 * review time. Null for any other failure.
 */
export function blockedReview(
  preview: SandboxPublicationPreview,
  reason: unknown,
): SandboxPublicationPreview | null {
  const blockers = publicationRefusalBlockers(reason);
  return blockers ? { ...preview, blockers } : null;
}

function errorMessage(error: unknown): string {
  const code = errorCode(error);
  if (code === "stale_revision" || code === "live_state_changed")
    return "The draft changed while you were reviewing it. Close this window, refresh the review, and try again.";
  if (code === "preview_expired" || code === "preview_mismatch")
    return "This review has expired. Refresh the review and confirm again.";
  if (code === "invalid_password")
    return "That password was not accepted. Check it and try again.";
  if (code === "idempotency_mismatch")
    return "This publish attempt no longer matches the original request. Refresh the review and try again.";
  return "We could not confirm this change. Your password and note are still here so you can try again.";
}

export function ReviewPublishDialog({
  open,
  expectedRevision,
  disabled,
  design,
  localBlockers,
  onOpenBlocker,
  onOpenChange,
  onPendingChange,
  onPreview,
  onPublish,
  onPublished,
  onSetupChange,
}: Props) {
  const [preview, setPreview] = useState<SandboxPublicationPreview | null>(
    null,
  );
  // The draft revision the shown review was made from. A newer revision
  // keeps the list on screen until the next review replaces it.
  const [previewRevision, setPreviewRevision] = useState<number | null>(null);
  const stale = preview !== null && previewRevision !== expectedRevision;
  // Setup toggles on their way to the draft; the last one shows at once
  // (FIT-3). Each leaves the list when its own change settles.
  const [pendingSetups, setPendingSetups] = useState<
    ReadonlyArray<{ departmentId: string; setup: DepartmentSetup }>
  >([]);
  const pendingSetup = pendingSetups.at(-1) ?? null;
  const [password, setPassword] = useState("");
  const [note, setNote] = useState("");
  // One request at a time: loading the review, or publishing it.
  const [busy, setBusy] = useState<"review" | "publish" | null>(null);
  const pending = busy !== null;
  const [idempotencyKey, setIdempotencyKey] = useState("");
  // Review errors show above the list; publish errors show in the footer,
  // next to the password and Publish that caused them.
  const [errorFailure, setError] = useErrorText();
  const error = errorFailure?.message ?? "";
  // A refused Setup toggle (NB-5) shows in the same place. It stays until
  // the next toggle or the next open, so the save it waited for and the
  // review after it do not clear it at once.
  const [setupError, setSetupError] = useState("");
  const [publishErrorFailure, setPublishError] = useErrorText();
  const publishError = publishErrorFailure?.message ?? "";
  const [passwordRejected, setPasswordRejected] = useState(false);
  const passwordId = useId();
  const passwordHintId = useId();
  const teamHintId = useId();
  const noteId = useId();
  const blockerId = useId();
  // Each open (and each new draft revision) gets one automatic review. The
  // round number also drops a review that finishes after the dialog closed.
  const round = useRef(0);
  const autoReviewed = useRef<number | null>(null);
  const wasOpen = useRef(false);
  // The end state after a successful publish (DR-11.4). It stays while the
  // page refreshes the draft, and only a new open clears it. `opens` counts
  // opens and closes, so a bindings read that ends after a close is dropped.
  const [published, setPublished] = useState<{
    links: "reading" | readonly PublishedModuleLink[];
  } | null>(null);
  const opens = useRef(0);
  const backRef = useRef<HTMLButtonElement>(null);
  const focusBack = useRef(false);

  useEffect(() => {
    round.current += 1;
    autoReviewed.current = null;
    const opened = open && !wasOpen.current;
    if (open !== wasOpen.current) opens.current += 1;
    wasOpen.current = open;
    if (!open) return;
    // Only an open starts empty; a new revision during an open review keeps
    // the list until the next review replaces it in place (plan 11.3).
    if (opened) {
      setPreview(null);
      setSetupError("");
      setPublished(null);
    }
    setError("");
    setPublishError("");
    setPasswordRejected(false);
    setIdempotencyKey("");
  }, [open, expectedRevision]);
  useEffect(() => onPendingChange?.(pending), [onPendingChange, pending]);
  useEffect(() => () => onPendingChange?.(false), [onPendingChange]);

  // A failed second review removes the list and the Setup control that had
  // focus; focus then moves to Try again, not to the page (CI run
  // 43029850886).
  const retryRef = useRef<HTMLButtonElement>(null);
  const focusRetry = useRef(false);
  useEffect(() => {
    if (!focusRetry.current || busy !== null || preview !== null) return;
    focusRetry.current = false;
    retryRef.current?.focus();
  }, [busy, preview]);
  async function review() {
    const current = round.current;
    const kept = preview !== null;
    const revision = expectedRevision;
    setBusy("review");
    setError("");
    try {
      const next = await onPreview();
      if (round.current === current) {
        setPreview(next);
        setPreviewRevision(revision);
      }
    } catch (reason) {
      if (round.current === current) {
        // A failed second review drops the kept list, so the footer offers
        // today's "Try again" (plan 11.3, "Second review fails").
        setPreview(null);
        setPreviewRevision(null);
        setError(errorMessage(reason), reason);
        focusRetry.current = kept;
      }
    } finally {
      setBusy(null);
    }
  }
  useEffect(() => {
    // The Published state reads nothing more: the refresh after a publish
    // gives a new revision, which must not start another review.
    if (!open || disabled || pending || published) return;
    if (autoReviewed.current === round.current) return;
    autoReviewed.current = round.current;
    void review();
  }, [open, expectedRevision, disabled, pending, published]);
  // The password and Publish leave with the review, so focus moves to the
  // one action of the Published state, not to the page.
  useEffect(() => {
    if (!published || !focusBack.current) return;
    focusBack.current = false;
    backRef.current?.focus();
  }, [published]);
  async function publish() {
    if (!preview || stale || !password || blockers.length) return;
    // What this publish creates, as reviewed; the refresh after it replaces
    // the draft that the page passes in.
    const created = createdModules(preview.changes, shownDesign);
    setBusy("publish");
    setPublishError("");
    setPasswordRejected(false);
    let publication: SandboxPublication;
    try {
      const key = publicationIdempotencyKey(idempotencyKey, () =>
        crypto.randomUUID(),
      );
      setIdempotencyKey(key);
      publication = await onPublish({
        preview,
        password,
        note,
        idempotencyKey: key,
      });
    } catch (reason) {
      const refused = blockedReview(preview, reason);
      if (refused) setPreview(refused);
      else {
        setPublishError(errorMessage(reason), reason);
        setPasswordRejected(errorCode(reason) === "invalid_password");
      }
      return;
    } finally {
      setBusy(null);
    }
    // Published (DR-11.4). The read after it is not part of the publish: a
    // failed read only leaves the state without links (DR-11.6).
    setPassword("");
    setNote("");
    focusBack.current = true;
    setPublished({ links: created.length ? "reading" : [] });
    const current = opens.current;
    try {
      const bindings = await onPublished(publication);
      if (opens.current === current && created.length)
        setPublished({ links: publishedModuleLinks(created, bindings) });
    } catch {
      if (opens.current === current) setPublished({ links: [] });
    }
  }
  // The local check names the trigger, so it replaces the server's
  // message for the same trigger.
  const locallyBlocked = new Set(
    localBlockers.map((blocker) => blocker.targetId),
  );
  const blockers = [
    ...localBlockers,
    ...(preview?.blockers ?? []).filter(
      (blocker) => !blocker.targetId || !locallyBlocked.has(blocker.targetId),
    ),
  ];
  const blocked = blockers.length > 0;
  // The password's hint is the team line; a refusal or a blocked review
  // adds its reason beside it.
  const footerHint = publishError
    ? publishError
    : blocked
      ? "Fix the blocked items, then reopen this review."
      : "";
  // FIT-3: one toggle saves through the queue, then the review runs again by
  // itself. The control waits while a save or a review holds the draft.
  const setupSaving = pendingSetup !== null;
  const setupHeld = disabled || pending || setupSaving;
  async function changeSetup(
    departmentId: string,
    setup: DepartmentSetup | undefined,
    item: keyof DepartmentSetup,
    on: boolean,
  ) {
    if (!onSetupChange || setupHeld) return;
    const toggle = {
      departmentId,
      setup: { ...departmentSetup({ setup }), [item]: on },
    };
    setSetupError("");
    setPendingSetups((current) => [...current, toggle]);
    try {
      const result = await onSetupChange(departmentId, item, on);
      // A conflict or a failed save closes the review in the page, which
      // shows its alert (N1 rule 3, B5c). Any other refusal is a hold: the
      // review stays and says why where it shows its errors (NB-5).
      if (!result.ok) setSetupError(result.error);
    } finally {
      setPendingSetups((current) =>
        current.filter((entry) => entry !== toggle),
      );
    }
  }
  const shownDesign: PublishReviewDesign = pendingSetup
    ? {
        ...design,
        departments: design.departments.map((item) =>
          item.id === pendingSetup.departmentId
            ? { ...item, setup: pendingSetup.setup }
            : item,
        ),
      }
    : design;
  const reviewing = busy === "review" || stale;
  // Why Publish waits: the setup save, then the review it starts, then the
  // password (DESIGN.md Sandbox "Dialogs").
  const publishReason = setupSaving
    ? "Saving…"
    : preview && reviewing
      ? "Preparing your review…"
      : !password && !(disabled || pending || blocked)
        ? "Enter your password to publish."
        : null;
  // Cancel stays available while the review loads; only a publish in flight
  // holds the dialog open.
  const cancel = (
    <Button
      variant="outline"
      className="min-h-11"
      disabled={busy === "publish"}
      onClick={() => onOpenChange(false)}
    >
      Cancel
    </Button>
  );
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => busy !== "publish" && onOpenChange(next)}
    >
      {/* One scroller: the header and footer stay in view (Dialogs in
          Access), so focused controls are never hidden behind them. */}
      <DialogContent className={`${dialogFrameContentClass} sm:max-w-2xl`}>
        <DialogFrameHeader
          title={
            <DialogTitle>
              {published ? "Published" : <>Review &amp; Publish</>}
            </DialogTitle>
          }
          description={
            published ? (
              <DialogDescription>
                Your team sees these changes now.
              </DialogDescription>
            ) : undefined
          }
          closeLabel={published ? "Close" : "Close review"}
          closeDisabled={busy === "publish"}
          onClose={() => onOpenChange(false)}
        />
        {!published && (error || setupError) ? (
          <Alert
            role="alert"
            variant="destructive"
            reference={error ? errorFailure?.reference : undefined}
          >
            {error || setupError}
          </Alert>
        ) : null}
        {!published && blocked ? (
          <Alert role="alert" variant="destructive">
            <p className="font-medium">Publishing is blocked</p>
            <ul className="mt-2 grid gap-2">
              {blockers.map((blocker, index) => (
                <li
                  key={`${blocker.code}:${blocker.targetId ?? ""}:${blocker.message}`}
                  className="flex flex-wrap items-center gap-x-3 gap-y-1"
                >
                  <span id={`${blockerId}-${index}`}>{blocker.message}</span>
                  {blocker.targetId ? (
                    <Button
                      variant="outline"
                      size="sm"
                      aria-describedby={`${blockerId}-${index}`}
                      onClick={() => onOpenBlocker(blocker)}
                    >
                      {blocker.code.startsWith("trigger")
                        ? "Open trigger"
                        : "Show in Build"}
                    </Button>
                  ) : null}
                </li>
              ))}
            </ul>
          </Alert>
        ) : null}
        {published ? (
          <PublishedRecords links={published.links} />
        ) : busy === "review" && !preview ? (
          <div role="status" className="grid gap-3">
            <p className="text-muted-foreground text-sm">
              Preparing your review…
            </p>
            <Skeleton className="h-5 w-40" />
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : !preview ? null : (
          <>
            {preview.warnings.length ? (
              <Alert>
                <p className="font-medium">Please note</p>
                <ul className="mt-2 list-inside list-disc">
                  {preview.warnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              </Alert>
            ) : null}
            {reviewing ? (
              // A second review: the list stays, one line says why.
              <p role="status" className="text-muted-foreground text-sm">
                Preparing your review…
              </p>
            ) : null}
            <section aria-busy={reviewing || undefined}>
              <h3 data-slot="section-title" className="font-medium">
                Changes
              </h3>
              {preview.changes.length ? (
                <div className="mt-2">
                  <PublishChangeGroups
                    changes={preview.changes}
                    design={shownDesign}
                    departmentControl={
                      onSetupChange
                        ? (department) => (
                            <SetupControl
                              name={department.name}
                              departmentIndex={department.index}
                              setup={department.setup}
                              held={setupHeld}
                              onToggle={(item, on) =>
                                void changeSetup(
                                  department.id,
                                  department.setup,
                                  item,
                                  on,
                                )
                              }
                            />
                          )
                        : undefined
                    }
                  />
                </div>
              ) : (
                <p className="text-muted-foreground mt-2 text-sm">
                  No structural changes are waiting to be applied.
                </p>
              )}
            </section>
            {blocked ? null : (
              <>
                {/* Label-left, like the password row below. */}
                <Field className="grid gap-1.5 sm:grid-cols-[8rem_minmax(0,1fr)] sm:items-start sm:gap-3">
                  <FieldLabel htmlFor={noteId} className="sm:pt-2">
                    Note (optional)
                  </FieldLabel>
                  <Textarea
                    id={noteId}
                    value={note}
                    maxLength={1000}
                    onChange={(event) => setNote(event.target.value)}
                    disabled={pending || blocked}
                  />
                </Field>
              </>
            )}
          </>
        )}
        <DialogFrameFooter>
          {published ? (
            <DialogFooter className="mt-0 sm:flex-row sm:justify-end">
              <Button
                ref={backRef}
                variant="outline"
                className="min-h-11 w-full sm:w-auto"
                onClick={() => onOpenChange(false)}
              >
                Back to Build
              </Button>
            </DialogFooter>
          ) : preview ? (
            <>
              {/* The password is its own label-left row (stacked on a
                  phone), pinned above Cancel and Publish. */}
              <Field className="grid gap-1.5 sm:grid-cols-[8rem_minmax(0,1fr)] sm:items-center sm:gap-3">
                <FieldLabel htmlFor={passwordId}>Your password</FieldLabel>
                <Input
                  id={passwordId}
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  aria-invalid={passwordRejected || undefined}
                  aria-describedby={
                    footerHint ? `${teamHintId} ${passwordHintId}` : teamHintId
                  }
                  onChange={(event) => {
                    setPassword(event.target.value);
                    setPasswordRejected(false);
                  }}
                  disabled={pending || blocked}
                />
              </Field>
              {/* Hints sit under the field, in its column from 640px. */}
              <div className="-mt-1.5 grid gap-1 text-sm sm:pl-[8.75rem]">
                <p id={teamHintId} className="text-muted-foreground">
                  Your team sees these changes as soon as you publish.
                </p>
                {footerHint ? (
                  <p
                    id={passwordHintId}
                    role={publishError ? "alert" : undefined}
                    className={
                      publishError
                        ? "text-danger-text"
                        : "text-muted-foreground"
                    }
                  >
                    {footerHint}
                  </p>
                ) : null}
                {/* A refused password is a field refusal; other failures
                    keep their request's reference (D1.4). */}
                <ErrorReference
                  id={
                    passwordRejected
                      ? undefined
                      : publishErrorFailure?.reference
                  }
                  className="mt-0"
                />
              </div>
              <DialogFooter className="mt-0 flex-row justify-end">
                {cancel}
                {/* Waiting only for the password, Publish says so (S26). */}
                <DisabledReason stable reason={publishReason}>
                  <Button
                    className="min-h-11"
                    disabled={
                      disabled ||
                      pending ||
                      blocked ||
                      stale ||
                      setupSaving ||
                      !password
                    }
                    onClick={() => void publish()}
                  >
                    {busy === "publish" ? "Publishing…" : "Publish changes"}
                  </Button>
                </DisabledReason>
              </DialogFooter>
            </>
          ) : (
            <DialogFooter className="mt-0 flex-row justify-end">
              {cancel}
              {busy === "review" ? null : (
                <DisabledReason
                  reason={disabled ? "Finish the current change first." : null}
                >
                  <Button
                    ref={retryRef}
                    className="min-h-11"
                    disabled={disabled}
                    onClick={() => void review()}
                  >
                    {error ? "Try again" : "Review changes"}
                  </Button>
                </DisabledReason>
              )}
            </DialogFooter>
          )}
        </DialogFrameFooter>
      </DialogContent>
    </Dialog>
  );
}
