"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { AdvancedSection } from "@/components/ui/advanced-section";
import { Button } from "@/components/ui/button";
import { DisabledReason } from "@/components/ui/disabled-reason";
import { reportDone, reportError, reportUndoable } from "@/lib/feedback";
import { apiErrorReference } from "@/lib/api-errors";

import { afterAccessUserChange } from "../adapters/access-queries";
import { peopleErrorMessage, personName, personState } from "../helpers/people";
import {
  deleteAccessUser,
  getWorksheetImpact,
  newAccessInvitationLink,
  reconcileAccessInvitation,
  resendAccessInvitation,
  restoreAccessUser,
  revokeAccessInvitation,
  updateAccessUser,
  type AccessUser,
} from "../state/api";
import { useAccessVerifying, verifyingReason } from "../state/draft-navigation";
import { ActionError } from "./editor-conflicts";
import { useErrorText } from "@/lib/use-error-text";
import { OneTimeSecret } from "./one-time-secret";
import {
  InvitationMessageCopy,
  useInvitingOrganizationName,
} from "./invitation-message-copy";
import {
  INVITATION_LINK_LIFETIME,
  invitationMessage,
} from "../helpers/invitation-message";

type AccountAction =
  | "reconcile"
  | "resend"
  | "link"
  | "revoke"
  | "disable"
  | "enable"
  | "delete"
  | "restore";

type ActionCopy = {
  button: string;
  title: string;
  description: string;
  confirm: string;
  /** The confirm button's label while the request runs. */
  pending: string;
  done: string;
  destructive: boolean;
};

function actionCopy(action: AccountAction, person: AccessUser): ActionCopy {
  const name = personName(person);
  switch (action) {
    case "reconcile":
      return {
        button: "Finish sending invitation",
        title: "Finish sending the invitation?",
        description: `Complete the pending invitation for ${person.email}. They will receive an invitation email.`,
        confirm: "Send invitation",
        pending: "Sending…",
        done: "Invitation sent",
        destructive: false,
      };
    case "resend":
      return {
        button: "Resend invitation",
        title: "Resend the invitation?",
        description: `Renew the invitation for ${person.email}. Existing accounts accept when signed in; new accounts get an email.`,
        confirm: "Resend invitation",
        pending: "Sending…",
        done: "Invitation sent again",
        destructive: false,
      };
    case "link":
      return {
        button: "Copy a new link",
        title: "Make a new invitation link?",
        description: `The earlier link or invitation email for ${person.email} stops working. The new link works once, for 24 hours.`,
        confirm: "Make new link",
        pending: "Making…",
        done: "New invitation link made",
        destructive: false,
      };
    case "revoke":
      return {
        button: "Revoke invitation",
        title: "Revoke the invitation?",
        description:
          "This invitation can no longer be accepted, in the app or by email link.",
        confirm: "Revoke invitation",
        pending: "Revoking…",
        done: "Invitation revoked",
        destructive: true,
      };
    case "disable":
      return {
        button: "Disable",
        title: `Disable ${name}?`,
        description:
          "They are signed out everywhere and cannot sign in until you enable them again.",
        confirm: "Disable account",
        pending: "Disabling…",
        done: `${name} is disabled`,
        destructive: true,
      };
    case "enable":
      return {
        button: "Enable",
        title: `Enable ${name}?`,
        description: "They can sign in again with the access they had before.",
        confirm: "Enable account",
        pending: "Enabling…",
        done: `${name} is enabled`,
        destructive: false,
      };
    case "delete":
      return {
        button: "Delete",
        title: `Delete ${name}?`,
        description:
          "They are signed out everywhere and leave the directory. You can restore them later.",
        confirm: "Delete account",
        pending: "Deleting…",
        done: `${name} deleted`,
        destructive: true,
      };
    case "restore":
      return {
        button: "Restore",
        title: `Restore ${name}?`,
        description: "They come back to the directory and can sign in again.",
        confirm: "Restore account",
        pending: "Restoring…",
        done: `${name} is restored`,
        destructive: false,
      };
  }
}

function run(action: AccountAction, person: AccessUser): Promise<unknown> {
  switch (action) {
    case "reconcile":
      return reconcileAccessInvitation(person.id);
    case "resend":
      return resendAccessInvitation(person.id);
    case "link":
      return newAccessInvitationLink(person.id);
    case "revoke":
      return revokeAccessInvitation(person.id);
    case "disable":
      return updateAccessUser(person.id, { status: "disabled" });
    case "enable":
      return updateAccessUser(person.id, { status: "active" });
    case "delete":
      return deleteAccessUser(person.id);
    case "restore":
      return restoreAccessUser(person.id);
  }
}

/** The account actions the backend accepts for a person in this state. */
function availableActions(person: AccessUser, self: boolean): AccountAction[] {
  if (person.is_deleted) return person.status === "pending" ? [] : ["restore"];
  if (person.status === "pending")
    return person.invitation_sent_at === null
      ? ["reconcile"]
      : ["resend", "link", "revoke"];
  if (self) return [];
  return person.status === "disabled"
    ? ["enable", "delete"]
    : ["disable", "delete"];
}

/**
 * How many of the person's private sheets a disable or a removal opens to
 * their records' readers (sheets spec L5, SH-15): read when the confirmation
 * opens, a count only. A failed read shows nothing and never blocks.
 */
function useOpeningSheets(
  userId: string,
  action: AccountAction | null,
  opening: number,
) {
  const asks = action === "disable" || action === "delete";
  const [count, setCount] = useState<{ key: string; value: number } | null>(
    null,
  );
  // Each opening of a confirmation reads again.
  const key = `${userId}:${action ?? ""}:${opening}`;
  useEffect(() => {
    if (!asks) return;
    const controller = new AbortController();
    getWorksheetImpact(userId, { signal: controller.signal }).then(
      (value) => setCount({ key, value }),
      () => undefined,
    );
    return () => controller.abort();
  }, [asks, userId, key]);
  // A count from an earlier dialog never shows in this one.
  return asks && count?.key === key ? count.value : 0;
}

function openingSheetsLine(count: number) {
  return count === 1
    ? "1 private sheet will open read-only to everyone who can read its record or module."
    : `${count} private sheets will open read-only to everyone who can read their records or modules.`;
}

/** Sending an invitation is the pending person's next step, so it stays in view. */
const inviteActions: readonly AccountAction[] = ["reconcile", "resend", "link"];

type FocusTarget = readonly (AccountAction | "invitation")[];

/** Where focus goes once an action has run and its button may be gone. */
const focusAfter: Record<AccountAction, FocusTarget> = {
  reconcile: ["resend"],
  resend: ["resend"],
  link: ["link"],
  revoke: ["invitation"],
  disable: ["enable"],
  enable: ["disable"],
  // A deleted person leaves the directory and the sheet closes.
  delete: [],
  restore: ["enable", "disable"],
};

/**
 * A person's account: a pending invitation's next step in view, then the
 * person's recorded facts (`children`), then the lifecycle actions in one
 * closed Advanced block, last in Details (the Advanced Last Rule). Deleting
 * closes the sheet and offers Undo, which restores the person.
 */
export function PersonAccount({
  person,
  self,
  onDeleted,
  children,
}: {
  person: AccessUser;
  self: boolean;
  /** The person left the directory; the sheet closes. */
  onDeleted: () => void;
  children?: ReactNode;
}) {
  const client = useQueryClient();
  const verifying = useAccessVerifying();
  const [action, setAction] = useState<AccountAction | null>(null);
  const [pending, setPending] = useState(false);
  const [errorFailure, setError] = useErrorText();
  const error = errorFailure?.message ?? "";
  const [now] = useState(() => Date.now());
  // The new invitation link, shown once in the dialog until it closes.
  const [link, setLink] = useState<string | null>(null);
  const organizationName = useInvitingOrganizationName();
  const mounted = useRef(false);
  const pendingRef = useRef(false);
  const buttons = useRef(new Map<AccountAction, HTMLButtonElement>());
  const invitationTitle = useRef<HTMLHeadingElement>(null);
  // Set when an action has run; the effect below moves focus to the
  // control that replaced the one that started it.
  const focusTarget = useRef<FocusTarget | null>(null);
  const actions = availableActions(person, self);
  const copy = action ? actionCopy(action, person) : null;
  const [opening, setOpening] = useState(0);
  const openingSheets = useOpeningSheets(person.id, action, opening);
  const state = personState(person, now);
  const invitation = actions.filter((item) => inviteActions.includes(item));
  const lifecycle = actions.filter((item) => !inviteActions.includes(item));

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  // After every render: once the replacing control exists, focus it.
  useEffect(() => {
    const target = focusTarget.current;
    if (!target || action !== null) return;
    const element = target
      .map((item) =>
        item === "invitation"
          ? invitationTitle.current
          : (buttons.current.get(item) ?? null),
      )
      .find((candidate) => candidate?.isConnected);
    if (!element) return;
    focusTarget.current = null;
    element.focus();
  });

  function bindButton(item: AccountAction) {
    return (element: HTMLButtonElement | null) => {
      if (element) buttons.current.set(item, element);
      else buttons.current.delete(item);
    };
  }

  async function undoDelete(name: string) {
    try {
      await restoreAccessUser(person.id);
      reportDone(`${name} is restored`);
    } catch (caught) {
      reportError(
        peopleErrorMessage(caught, `${name} could not be restored. Try again.`),
        apiErrorReference(caught),
      );
    } finally {
      void afterAccessUserChange(client);
    }
  }

  async function confirm() {
    if (
      !action ||
      !copy ||
      pending ||
      pendingRef.current ||
      verifying ||
      !actions.includes(action)
    )
      return;
    const selected = action;
    pendingRef.current = true;
    setPending(true);
    setError("");
    try {
      const result = await run(selected, person);
      if (
        selected === "link" &&
        typeof result === "object" &&
        result !== null &&
        "invitation_url" in result &&
        typeof result.invitation_url === "string"
      ) {
        await afterAccessUserChange(client);
        if (!mounted.current) return;
        // The dialog stays open on the link; Done puts focus back here.
        setLink(result.invitation_url);
        focusTarget.current = focusAfter[selected];
        return;
      }
      if (selected === "delete") {
        // The person leaves the directory, so the sheet closes and the
        // notice carries Undo (the Four Moments Rule).
        const name = personName(person);
        reportUndoable(copy.done, () => void undoDelete(name));
        void afterAccessUserChange(client);
        if (!mounted.current) return;
        setAction(null);
        onDeleted();
        return;
      }
      // The sheet shows the new state before the dialog closes, so focus
      // lands on the control that replaced this one.
      await afterAccessUserChange(client);
      if (!mounted.current) return;
      reportDone(copy.done);
      focusTarget.current = focusAfter[selected];
      setAction(null);
    } catch (caught) {
      if (!mounted.current) return;
      setError(
        peopleErrorMessage(caught, "The change could not be made. Try again."),
        caught,
      );
      // A refused change may mean this person changed elsewhere.
      void afterAccessUserChange(client);
    } finally {
      pendingRef.current = false;
      if (mounted.current) setPending(false);
    }
  }

  function open(item: AccountAction) {
    setOpening((value) => value + 1);
    focusTarget.current = null;
    setError("");
    setLink(null);
    setAction(item);
  }

  function closeDialog() {
    setLink(null);
    setAction(null);
  }

  const summary = person.is_deleted
    ? "This account is deleted."
    : state.id === "expired"
      ? "This guest's access has ended. Set a later end date to let them sign in again."
      : person.status === "disabled"
        ? "This account cannot sign in."
        : "This account can sign in.";

  return (
    <>
      {person.status === "pending" ? (
        <section
          aria-labelledby="person-invitation-title"
          className="space-y-2"
        >
          <h3
            id="person-invitation-title"
            ref={invitationTitle}
            tabIndex={-1}
            className="font-semibold outline-none"
          >
            Invitation
          </h3>
          <p className="text-muted-foreground text-sm">
            {person.is_deleted
              ? "This invitation was revoked. Invite this email address again to give them access."
              : person.invitation_sent_at === null
                ? "The invitation has not been sent yet. Finish sending it to give this person their invitation link."
                : "The invitation has not been accepted yet."}
          </p>
          {invitation.map((item) => (
            <Button
              key={item}
              ref={bindButton(item)}
              variant="secondary"
              className="min-h-11 w-full sm:w-auto"
              onClick={() => open(item)}
            >
              {actionCopy(item, person).button}
            </Button>
          ))}
        </section>
      ) : null}

      {children}

      {self && person.status !== "pending" ? (
        <p className="text-muted-foreground text-sm">
          This is your account. Another administrator can disable or delete it.
        </p>
      ) : null}

      {lifecycle.length ? (
        <AdvancedSection
          storageKey="access.person"
          summary={lifecycle
            .map((item) => actionCopy(item, person).button)
            .join(", ")}
        >
          {person.status === "pending" ? null : (
            <p className="text-muted-foreground text-sm">{summary}</p>
          )}
          {/* Ghost buttons start at their text, in line with the sentence. */}
          <div className="flex flex-col gap-2 sm:-ml-3 sm:flex-row sm:flex-wrap">
            {lifecycle.map((item) => {
              const itemCopy = actionCopy(item, person);
              return (
                <Button
                  key={item}
                  ref={bindButton(item)}
                  variant="ghost"
                  className={
                    itemCopy.destructive
                      ? "text-danger-text min-h-11 w-full sm:w-auto"
                      : "min-h-11 w-full sm:w-auto"
                  }
                  onClick={() => open(item)}
                >
                  {itemCopy.button}
                </Button>
              );
            })}
          </div>
        </AdvancedSection>
      ) : null}

      <AlertDialog
        open={action !== null}
        onOpenChange={(next) => !next && !pending && closeDialog()}
      >
        <AlertDialogContent
          className="access-ui slim-ui"
          finalFocus={() => focusTarget.current === null}
        >
          {link ? (
            <>
              <AlertDialogHeader>
                <AlertDialogTitle>Send this invitation link</AlertDialogTitle>
                <AlertDialogDescription>
                  The earlier link or invitation email no longer works.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <InvitationMessageCopy
                message={invitationMessage({
                  organization: organizationName,
                  link,
                  email: person.email,
                  username: person.username,
                })}
              />
              <OneTimeSecret
                label={`Invitation link for ${person.email}`}
                value={link}
                copyLabel="Copy link"
              >
                It works once, for {INVITATION_LINK_LIFETIME}, and shows only
                now. Send it to them by any channel.
              </OneTimeSecret>
              <AlertDialogFooter>
                {/* The copy above is the one filled button (parent D4). */}
                <Button
                  variant="secondary"
                  className="min-h-11"
                  onClick={closeDialog}
                >
                  Close
                </Button>
              </AlertDialogFooter>
            </>
          ) : (
            <>
              <AlertDialogHeader>
                <AlertDialogTitle>{copy?.title}</AlertDialogTitle>
                <AlertDialogDescription>
                  {copy?.description}
                </AlertDialogDescription>
                {openingSheets > 0 ? (
                  <p className="text-sm">{openingSheetsLine(openingSheets)}</p>
                ) : null}
              </AlertDialogHeader>
              <ActionError
                message={error}
                reference={errorFailure?.reference}
              />
              <AlertDialogFooter>
                <Button
                  variant="ghost"
                  className="min-h-11"
                  disabled={pending}
                  onClick={() => setAction(null)}
                >
                  Cancel
                </Button>
                <DisabledReason reason={verifying ? verifyingReason : null}>
                  <Button
                    variant={copy?.destructive ? "destructive" : "default"}
                    className="min-h-11"
                    pending={pending}
                    pendingLabel={copy?.pending}
                    onClick={() => void confirm()}
                  >
                    {copy?.confirm}
                  </Button>
                </DisabledReason>
              </AlertDialogFooter>
            </>
          )}
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
