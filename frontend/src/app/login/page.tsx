"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { SignedOutFrame } from "@/components/signed-out/signed-out-frame";
import { SignedOutPanel } from "@/components/signed-out/signed-out-panel";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { workspaceStartRoute } from "@/components/workspace-start";
import {
  Field as FormField,
  FieldControl,
  FieldLabel,
} from "@/components/ui/field";
import { getSessionStatus, signIn } from "@/lib/auth-api";
import { loginFailureCause, loginFailureMessage } from "@/lib/login-failure";
import { useErrorText } from "@/lib/use-error-text";

/** After a recovery ("password") or an accepted invitation ("invitation"). */
const completedNotices = new Map([
  ["password", "Password set. Sign in."],
  [
    "invitation",
    "Your password is set. Sign in with the email or username from your invitation message.",
  ],
]);

function PasswordSetNotice() {
  const search = useSearchParams();
  const notice = completedNotices.get(search.get("completed") ?? "");
  return notice ? <Alert variant="success">{notice}</Alert> : null;
}

export default function LoginPage() {
  const router = useRouter();
  // An email address or a username, sent as typed (REQ-0024 addition 6).
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [errorFailure, setError] = useErrorText();
  const error = errorFailure?.message ?? "";
  const [pending, setPending] = useState(false);
  const [checkingSession, setCheckingSession] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    async function checkSession() {
      try {
        const session = await getSessionStatus(controller.signal);
        if (session.authenticated) {
          const destination = await workspaceStartRoute();
          if (!controller.signal.aborted) router.replace(destination);
        } else if (!controller.signal.aborted) {
          setCheckingSession(false);
        }
      } catch {
        if (!controller.signal.aborted) setCheckingSession(false);
      }
    }
    void checkSession();
    return () => controller.abort();
  }, [router]);
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setPending(true);
    try {
      const session = await signIn(login, password);
      if (session.setup_required) {
        setError("Finish setup using the link in your invitation email.");
        return;
      }
      router.push(await workspaceStartRoute());
    } catch (error) {
      setError(loginFailureMessage(error), loginFailureCause(error));
    } finally {
      setPending(false);
    }
  }
  return (
    <SignedOutFrame busy={checkingSession}>
      <SignedOutPanel
        title="Welcome back"
        description="Sign in to continue to your workspace."
        contentHidden={checkingSession}
        footer={
          <>
            First deployment?{" "}
            <a
              className="text-action-text rounded-sm font-medium underline-offset-4 hover:underline"
              href="/setup"
            >
              Read the setup guide
            </a>
          </>
        }
      >
        <Suspense fallback={null}>
          <PasswordSetNotice />
        </Suspense>
        {error && (
          <Alert
            role="alert"
            variant="destructive"
            reference={errorFailure?.reference}
          >
            {error}
          </Alert>
        )}
        <form className="flex flex-col gap-4" onSubmit={submit}>
          <FormField>
            <FieldLabel htmlFor="login">Email or username</FieldLabel>
            <FieldControl
              render={
                <Input
                  id="login"
                  type="text"
                  autoComplete="username"
                  autoCapitalize="none"
                  autoCorrect="off"
                  spellCheck={false}
                  required
                  className="min-h-11"
                  value={login}
                  onChange={(event) => setLogin(event.target.value)}
                />
              }
            />
          </FormField>
          <FormField>
            <FieldLabel htmlFor="password">Password</FieldLabel>
            <FieldControl
              render={
                <Input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  minLength={12}
                  required
                  className="min-h-11"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                />
              }
            />
            <a
              className="text-action-text inline-flex min-h-11 items-center self-start rounded-sm text-sm font-medium underline-offset-4 hover:underline xl:min-h-6"
              href="/auth/recovery"
            >
              Forgot password?
            </a>
          </FormField>
          <Button
            className="min-h-11 w-full"
            pending={pending}
            pendingLabel="Signing in…"
          >
            Sign in
          </Button>
        </form>
      </SignedOutPanel>
    </SignedOutFrame>
  );
}
