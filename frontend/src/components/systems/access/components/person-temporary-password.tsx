"use client";

import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { KeyRound } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { DisabledReason } from "@/components/ui/disabled-reason";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { ApiError } from "@/lib/api";
import { requestSessionRecheck } from "@/lib/auth-api";
import { useErrorText } from "@/lib/use-error-text";

import { afterPersonSecurityChange } from "../adapters/access-queries";
import { setPersonTemporaryPassword } from "../adapters/security-api";
import { temporaryPasswordFailure } from "../helpers/person-security-outcome";
import { personName } from "../helpers/people";
import type { AccessUser } from "../state/api";
import { OneTimeSecret } from "./one-time-secret";
import { TextField } from "./people-fields";

type Source = "generated" | "typed";

const sources: readonly { value: Source; label: string; line: string }[] = [
  {
    value: "generated",
    label: "Make one for me",
    line: "Slate Operations makes a strong password and shows it once.",
  },
  {
    value: "typed",
    label: "Type one",
    line: "Use 12 to 128 characters.",
  },
];

/**
 * Set a temporary password (DEC-0042, AC-T-UI): for when email is not set up
 * or the person cannot use it. The person's sessions end, and at the next
 * sign-in they use this password once, then choose their own. The server
 * refuses an owner and the administrator's own account; this panel never
 * offers it for the administrator's own account. A password the server made
 * shows once with Copy.
 */
export function PersonTemporaryPassword({
  person,
  eligible,
}: {
  person: AccessUser;
  /** The last accepted security read admits actions on this person. */
  eligible: boolean;
}) {
  const id = useId();
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [source, setSource] = useState<Source>("generated");
  const [typed, setTyped] = useState("");
  const [lengthError, setLengthError] = useState("");
  const [pending, setPending] = useState(false);
  const [shown, setShown] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [failure, setFailure] = useErrorText();
  const alive = useRef(false);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  const name = personName(person);

  function start() {
    setSource("generated");
    setTyped("");
    setLengthError("");
    setFailure("");
    setShown(null);
    setNotice("");
    setOpen(true);
  }

  function close() {
    if (pending) return;
    setShown(null);
    setTyped("");
    setOpen(false);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    const password = source === "typed" ? typed : null;
    if (password !== null && (password.length < 12 || password.length > 128)) {
      setLengthError("Use 12 to 128 characters.");
      document.getElementById(`${id}-password`)?.focus();
      return;
    }
    setPending(true);
    setFailure("");
    try {
      const result = await setPersonTemporaryPassword(person.id, password);
      if (!alive.current) return;
      setTyped("");
      if (result.temporary_password) setShown(result.temporary_password);
      else {
        setOpen(false);
        setNotice(
          `Temporary password set for ${name}. Their sessions ended, and they choose a new password at their next sign-in.`,
        );
      }
      void afterPersonSecurityChange(client, person.id).catch(() => {});
    } catch (caught) {
      if (!alive.current) return;
      setFailure(temporaryPasswordFailure(caught), caught);
      if (caught instanceof ApiError && caught.status === 401)
        requestSessionRecheck();
    } finally {
      if (alive.current) setPending(false);
    }
  }

  return (
    <section
      aria-labelledby={`${id}-title`}
      className="border-t pt-4"
      data-section="temporary-password"
    >
      <h4 id={`${id}-title`} className="font-medium">
        Temporary password
      </h4>
      <p className="text-muted-foreground mt-1 text-sm">
        For when they cannot use email. Their sessions end, and at the next
        sign-in they choose their own password.
      </p>
      <div className="mt-3">
        <DisabledReason
          reason={
            eligible
              ? null
              : "This person is not eligible for security actions."
          }
        >
          <Button
            className="min-h-11 w-full sm:w-auto"
            variant="outline"
            onClick={start}
          >
            <KeyRound aria-hidden="true" />
            Set a temporary password
          </Button>
        </DisabledReason>
      </div>
      {notice ? (
        <Alert role="status" variant="success" className="mt-3">
          {notice}
        </Alert>
      ) : null}

      <Dialog open={open} onOpenChange={(next) => (next ? null : close())}>
        <DialogContent className="access-ui slim-ui max-w-lg">
          {shown ? (
            <>
              <DialogHeader>
                <DialogTitle>Temporary password for {name}</DialogTitle>
                <DialogDescription>
                  Their sessions ended. Give them this password in person or by
                  phone; at their next sign-in they choose their own.
                </DialogDescription>
              </DialogHeader>
              <div className="mt-4">
                <OneTimeSecret
                  label="Temporary password"
                  value={shown}
                  copyLabel="Copy password"
                >
                  It shows only now. If it is lost, set a new one.
                </OneTimeSecret>
              </div>
              <DialogFooter>
                <Button className="min-h-11" onClick={close}>
                  Done
                </Button>
              </DialogFooter>
            </>
          ) : (
            <form noValidate onSubmit={submit}>
              <DialogHeader>
                <DialogTitle>Set a temporary password for {name}?</DialogTitle>
                <DialogDescription>
                  Their sessions end on every device. At their next sign-in they
                  use this password once, then choose their own.
                </DialogDescription>
              </DialogHeader>
              <div className="mt-4 flex flex-col gap-3">
                <p id={`${id}-source`} className="text-sm font-medium">
                  Password
                </p>
                <RadioGroup
                  aria-labelledby={`${id}-source`}
                  value={source}
                  onValueChange={(value) => {
                    if (value === "generated" || value === "typed") {
                      setSource(value);
                      setLengthError("");
                    }
                  }}
                  disabled={pending}
                  className="gap-1"
                >
                  {sources.map((choice) => (
                    <label
                      key={choice.value}
                      className="hover:bg-tint-hover flex min-h-11 cursor-pointer items-start gap-3 rounded-md px-2 py-2 xl:min-h-8 xl:py-1.5"
                    >
                      <RadioGroupItem
                        value={choice.value}
                        className="mt-0.5"
                        aria-labelledby={`${id}-${choice.value}`}
                        aria-describedby={`${id}-${choice.value}-line`}
                      />
                      <span className="min-w-0">
                        <span
                          id={`${id}-${choice.value}`}
                          className="block text-sm font-medium"
                        >
                          {choice.label}
                        </span>
                        <span
                          id={`${id}-${choice.value}-line`}
                          className="text-muted-foreground block text-xs"
                        >
                          {choice.line}
                        </span>
                      </span>
                    </label>
                  ))}
                </RadioGroup>
                {source === "typed" ? (
                  <TextField
                    id={`${id}-password`}
                    label="Temporary password"
                    type="text"
                    autoComplete="off"
                    spellCheck={false}
                    maxLength={128}
                    value={typed}
                    error={lengthError || null}
                    disabled={pending}
                    onChange={(value) => {
                      setTyped(value);
                      setLengthError("");
                    }}
                  />
                ) : null}
                {failure ? (
                  <Alert
                    role="alert"
                    variant="destructive"
                    reference={failure.reference}
                  >
                    {failure.message}
                  </Alert>
                ) : null}
              </div>
              <DialogFooter>
                <Button
                  type="button"
                  variant="ghost"
                  className="min-h-11"
                  disabled={pending}
                  onClick={close}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  variant="destructive"
                  className="min-h-11"
                  pending={pending}
                  pendingLabel="Setting…"
                >
                  Set temporary password
                </Button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </section>
  );
}
