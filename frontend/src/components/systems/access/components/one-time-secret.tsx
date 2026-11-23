"use client";

import { useEffect, useId, useState } from "react";
import { Check, Copy } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

// How long "Copied" stays on the button.
const COPIED_MILLISECONDS = 4000;

type CopyState = "idle" | "copied" | "failed";

/**
 * One copy button's state: "copied" for a few seconds after a copy, or
 * "failed" when the browser refused it.
 */
export function useCopyText(): [CopyState, (text: string) => void] {
  const [copy, setCopy] = useState<CopyState>("idle");
  useEffect(() => {
    if (copy !== "copied") return;
    const timer = window.setTimeout(() => setCopy("idle"), COPIED_MILLISECONDS);
    return () => window.clearTimeout(timer);
  }, [copy]);
  function copyText(text: string) {
    const copied = navigator.clipboard?.writeText(text);
    if (!copied) {
      setCopy("failed");
      return;
    }
    copied.then(() => setCopy("copied")).catch(() => setCopy("failed"));
  }
  return [copy, copyText];
}

/**
 * A value the server shows once (DEC-0042): an invitation link or a
 * temporary password. It sits in a read-only field the person can select,
 * with Copy beside it, and the lines under it say what the value does. The
 * copy result is spoken once; a failed copy asks the person to select it.
 */
export function OneTimeSecret({
  label,
  value,
  copyLabel,
  children,
}: {
  label: string;
  value: string;
  copyLabel: string;
  /** What the value does and how long it works, under the field. */
  children: React.ReactNode;
}) {
  const id = useId();
  const [copy, copyText] = useCopyText();
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      <div className="flex min-w-0 flex-col gap-2 sm:flex-row">
        <Input
          id={id}
          readOnly
          value={value}
          aria-describedby={`${id}-about`}
          className="min-h-11 min-w-0 flex-1 font-mono"
          onFocus={(event) => event.currentTarget.select()}
        />
        <Button
          type="button"
          variant="outline"
          className="min-h-11 shrink-0"
          onClick={() => copyText(value)}
        >
          {copy === "copied" ? (
            <Check aria-hidden="true" />
          ) : (
            <Copy aria-hidden="true" />
          )}
          {copy === "copied" ? "Copied" : copyLabel}
        </Button>
      </div>
      <span role="status" className="sr-only">
        {copy === "copied" ? "Copied." : ""}
      </span>
      {copy === "failed" ? (
        <p role="alert" className="text-danger-text text-sm">
          Copy did not work. Select the text and copy it yourself.
        </p>
      ) : null}
      <div id={`${id}-about`} className="text-muted-foreground text-sm">
        {children}
      </div>
    </div>
  );
}
