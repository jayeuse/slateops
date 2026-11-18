"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { SignedOutFrame } from "@/components/signed-out/signed-out-frame";
import { SignedOutPanel } from "@/components/signed-out/signed-out-panel";
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
import { apiErrorReference } from "@/lib/api-errors";
import { completeRecovery, requestRecovery } from "@/lib/auth-api";
import { recoveryRequestFailureMessage } from "@/lib/email-setup";
import {
  consumeRecoveryToken,
  hasValidRecoveryPasswordLength,
  passwordsMatch,
  retainRecoveryToken,
} from "@/lib/recovery-token";

type RequestState = "idle" | "sent" | "error";
type CompletionState = "idle" | "error";

export default function RecoveryPage() {
  const router = useRouter();
  const [recoveryToken, setRecoveryToken] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [passwordLengthInvalid, setPasswordLengthInvalid] = useState(false);
  const [mismatch, setMismatch] = useState(false);
  const [requestState, setRequestState] = useState<RequestState>("idle");
  const [requestFailure, setRequestFailure] = useState("");
  const [completionState, setCompletionState] =
    useState<CompletionState>("idle");
  const [pending, setPending] = useState(false);
  // The failed request behind either error alert (D1.6); each alert shows
  // only after its own failure set it.
  const [failureReference, setFailureReference] = useState<string>();

  useEffect(() => {
    function captureInitialLink() {
      const captured = consumeRecoveryToken(window.location, window.history);
      setRecoveryToken((current) => retainRecoveryToken(current, captured));
    }
    function captureNewLink() {
      setRecoveryToken(consumeRecoveryToken(window.location, window.history));
    }
    captureInitialLink();
    setHydrated(true);
    window.addEventListener("hashchange", captureNewLink);
    return () => {
      window.removeEventListener("hashchange", captureNewLink);
    };
  }, []);

  async function submitRequest(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    setRequestState("idle");
    setPending(true);
    try {
      await requestRecovery(email);
      setRequestState("sent");
    } catch (failure) {
      setRequestState("error");
      setRequestFailure(recoveryRequestFailureMessage(failure));
      setFailureReference(apiErrorReference(failure));
    } finally {
      setPending(false);
    }
  }

  async function submitCompletion(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending || !recoveryToken) return;
    const validPasswordLength = hasValidRecoveryPasswordLength(password);
    setPasswordLengthInvalid(!validPasswordLength);
    if (!validPasswordLength) {
      document.getElementById("password")?.focus();
      return;
    }
    const matches = passwordsMatch(password, confirmation);
    setMismatch(!matches);
    if (!matches) {
      document.getElementById("confirmation")?.focus();
      return;
    }
    setCompletionState("idle");
    setPending(true);
    try {
      await completeRecovery(recoveryToken, password);
      router.replace("/login?completed=password");
    } catch (failure) {
      setCompletionState("error");
      setFailureReference(apiErrorReference(failure));
    } finally {
      setPending(false);
    }
  }

  const completingRecovery = recoveryToken !== null;

  return (
    <SignedOutFrame>
      <SignedOutPanel
        title={completingRecovery ? "Choose a new password" : "Reset password"}
        description={
          completingRecovery
            ? "Choose a strong password for your Slate Operations account."
            : "Enter your email to get recovery instructions."
        }
        footer={
          <>
            Remembered your password?{" "}
            <a
              className="text-action-text rounded-sm font-medium underline-offset-4 hover:underline"
              href="/login"
            >
              Return to sign in
            </a>
          </>
        }
      >
        {!hydrated ? (
          <p className="text-muted-foreground text-sm" role="status">
            Preparing password recovery…
          </p>
        ) : completingRecovery ? (
          <>
            {completionState === "error" ? (
              <Alert
                role="alert"
                variant="destructive"
                reference={failureReference}
              >
                We could not reset your password. Check the requirements and try
                again.
              </Alert>
            ) : null}
            <form className="flex flex-col gap-4" onSubmit={submitCompletion}>
              <Field invalid={passwordLengthInvalid}>
                <FieldLabel htmlFor="password">New password</FieldLabel>
                <FieldControl
                  render={
                    <Input
                      className="min-h-11"
                      id="password"
                      autoFocus
                      aria-invalid={passwordLengthInvalid}
                      aria-describedby={
                        passwordLengthInvalid
                          ? "password-requirements password-error"
                          : "password-requirements"
                      }
                      autoComplete="new-password"
                      type="password"
                      minLength={12}
                      maxLength={128}
                      required
                      disabled={pending}
                      value={password}
                      onChange={(event) => {
                        setPassword(event.target.value);
                        setPasswordLengthInvalid(false);
                      }}
                    />
                  }
                />
                <FieldDescription id="password-requirements">
                  Use 12 to 128 characters and avoid a common password.
                </FieldDescription>
                {passwordLengthInvalid ? (
                  <FieldError match id="password-error">
                    Use a password between 12 and 128 characters.
                  </FieldError>
                ) : null}
              </Field>
              <Field invalid={mismatch}>
                <FieldLabel htmlFor="confirmation">
                  Confirm new password
                </FieldLabel>
                <FieldControl
                  render={
                    <Input
                      className="min-h-11"
                      id="confirmation"
                      aria-invalid={mismatch}
                      aria-describedby={
                        mismatch ? "confirmation-error" : undefined
                      }
                      autoComplete="new-password"
                      type="password"
                      minLength={12}
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
                Reset password
              </Button>
            </form>
          </>
        ) : (
          <>
            {requestState === "sent" ? (
              <Alert role="status" variant="success">
                If an account matches that email, we will send recovery
                instructions.
              </Alert>
            ) : null}
            {requestState === "error" ? (
              <Alert
                role="alert"
                variant="destructive"
                reference={failureReference}
              >
                {requestFailure}
              </Alert>
            ) : null}
            <form className="flex flex-col gap-4" onSubmit={submitRequest}>
              <Field>
                <FieldLabel htmlFor="email">Email</FieldLabel>
                <FieldControl
                  render={
                    <Input
                      className="min-h-11"
                      id="email"
                      type="email"
                      autoFocus
                      autoComplete="email"
                      required
                      disabled={pending}
                      value={email}
                      onChange={(event) => setEmail(event.target.value)}
                    />
                  }
                />
              </Field>
              <Button
                className="min-h-11 w-full"
                pending={pending}
                pendingLabel="Requesting…"
              >
                Request recovery
              </Button>
            </form>
          </>
        )}
      </SignedOutPanel>
    </SignedOutFrame>
  );
}
