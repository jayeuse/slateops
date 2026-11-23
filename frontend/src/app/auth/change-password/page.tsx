"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { SignedOutFrame } from "@/components/signed-out/signed-out-frame";
import { SignedOutPanel } from "@/components/signed-out/signed-out-panel";
import { workspaceStartRoute } from "@/components/workspace-start";
import { changeAccountPassword } from "@/components/systems/platform/adapters/account-api";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Field,
  FieldControl,
  FieldDescription,
  FieldError,
  FieldLabel,
} from "@/components/ui/field";
import { ApiError } from "@/lib/api";
import { apiErrorReference } from "@/lib/api-errors";
import { getAuthMe, signOut } from "@/lib/auth-api";
import { passwordChangeErrorMessage } from "@/lib/password-change";
import {
  hasValidRecoveryPasswordLength,
  passwordsMatch,
} from "@/lib/recovery-token";

// A person with two-step verification completes it first: the password
// change needs a two-step session. Any workspace page runs the two-step gate,
// and after it the shell sends the person back here.
const MFA_GATE_ROUTE = "/openview";
function mfaFirst(caught: unknown): boolean {
  return (
    caught instanceof ApiError &&
    caught.status === 403 &&
    (caught.code as string | undefined) === "mfa_required"
  );
}

/**
 * Choose a new password (DEC-0042, AC-F-UI). After an administrator sets a
 * temporary password, the server refuses everything else until the person
 * chooses their own here, with the existing password change. Then the normal
 * app opens. A person who has nothing to change goes to the app; a signed-out
 * person goes to sign-in.
 */
export default function ChangePasswordPage() {
  const router = useRouter();
  const [checking, setChecking] = useState(true);
  const [current, setCurrent] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [lengthInvalid, setLengthInvalid] = useState(false);
  const [mismatch, setMismatch] = useState(false);
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<{
    message: string;
    reference: string | undefined;
  } | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      try {
        const me = await getAuthMe(controller.signal);
        if (controller.signal.aborted) return;
        if (!me.passwordChangeRequired) {
          router.replace(await workspaceStartRoute());
          return;
        }
        setChecking(false);
      } catch (caught) {
        if (controller.signal.aborted) return;
        if (caught instanceof ApiError && caught.status === 401)
          router.replace("/login");
        else if (mfaFirst(caught)) router.replace(MFA_GATE_ROUTE);
        else setChecking(false);
      }
    })();
    return () => controller.abort();
  }, [router]);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    const validLength = hasValidRecoveryPasswordLength(password);
    setLengthInvalid(!validLength);
    if (!validLength) {
      document.getElementById("password")?.focus();
      return;
    }
    const matches = passwordsMatch(password, confirmation);
    setMismatch(!matches);
    if (!matches) {
      document.getElementById("confirmation")?.focus();
      return;
    }
    setPending(true);
    setFailure(null);
    try {
      await changeAccountPassword(current, password);
      router.replace(await workspaceStartRoute());
    } catch (caught) {
      if (mfaFirst(caught)) {
        router.replace(MFA_GATE_ROUTE);
        return;
      }
      setFailure({
        message: passwordChangeErrorMessage(caught),
        reference: apiErrorReference(caught),
      });
      setPending(false);
    }
  }

  async function leave() {
    try {
      await signOut();
    } finally {
      router.replace("/login");
    }
  }

  return (
    <SignedOutFrame busy={checking}>
      <SignedOutPanel
        title="Choose a new password"
        description="An administrator set a temporary password for you. Choose your own to continue."
        contentHidden={checking}
        footer={
          <button
            type="button"
            className="text-action-text inline-flex min-h-11 items-center underline underline-offset-4"
            disabled={pending}
            onClick={() => void leave()}
          >
            Sign out
          </button>
        }
      >
        {failure ? (
          <Alert
            role="alert"
            variant="destructive"
            reference={failure.reference}
          >
            {failure.message}
          </Alert>
        ) : null}
        <form className="flex flex-col gap-4" onSubmit={submit}>
          <Field>
            <FieldLabel htmlFor="current">Temporary password</FieldLabel>
            <FieldControl
              render={
                <Input
                  className="min-h-11"
                  id="current"
                  autoFocus
                  autoComplete="current-password"
                  type="password"
                  maxLength={128}
                  required
                  disabled={pending}
                  value={current}
                  onChange={(event) => setCurrent(event.target.value)}
                />
              }
            />
          </Field>
          <Field invalid={lengthInvalid}>
            <FieldLabel htmlFor="password">New password</FieldLabel>
            <FieldControl
              render={
                <Input
                  className="min-h-11"
                  id="password"
                  aria-invalid={lengthInvalid}
                  aria-describedby={
                    lengthInvalid
                      ? "password-requirements password-error"
                      : "password-requirements"
                  }
                  autoComplete="new-password"
                  type="password"
                  maxLength={128}
                  required
                  disabled={pending}
                  value={password}
                  onChange={(event) => {
                    setPassword(event.target.value);
                    setLengthInvalid(false);
                  }}
                />
              }
            />
            <FieldDescription id="password-requirements">
              Use 12 to 128 characters and avoid a common password.
            </FieldDescription>
            {lengthInvalid ? (
              <FieldError match id="password-error">
                Use a password between 12 and 128 characters.
              </FieldError>
            ) : null}
          </Field>
          <Field invalid={mismatch}>
            <FieldLabel htmlFor="confirmation">Confirm new password</FieldLabel>
            <FieldControl
              render={
                <Input
                  className="min-h-11"
                  id="confirmation"
                  aria-invalid={mismatch}
                  aria-describedby={mismatch ? "confirmation-error" : undefined}
                  autoComplete="new-password"
                  type="password"
                  maxLength={128}
                  required
                  disabled={pending}
                  value={confirmation}
                  onChange={(event) => setConfirmation(event.target.value)}
                />
              }
            />
            {mismatch ? (
              <FieldError match id="confirmation-error">
                Passwords must match.
              </FieldError>
            ) : null}
          </Field>
          <Button
            className="min-h-11 w-full"
            pending={pending}
            pendingLabel="Saving…"
          >
            Save new password
          </Button>
        </form>
      </SignedOutPanel>
    </SignedOutFrame>
  );
}
