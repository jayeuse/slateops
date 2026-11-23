"use client";

import { useId } from "react";
import { useQuery } from "@tanstack/react-query";
import { Check, Copy } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useAdmittedWorkspaceScope } from "@/components/systems/shared/runtime/workspace-identity";

import { authMeOptions } from "../adapters/access-queries";
import { useCopyText } from "./one-time-secret";

/**
 * The inviting organization's name from the shell's identity read, or null
 * when it is unknown or belongs to another organization than the admitted one
 * (never a name left from before a switch).
 */
export function useInvitingOrganizationName(): string | null {
  const admittedOrganizationId = useAdmittedWorkspaceScope()?.org_id ?? null;
  const identity = useQuery({ ...authMeOptions(), enabled: false });
  const current = identity.data?.currentOrganization;
  return current &&
    (admittedOrganizationId === null ||
      current.orgId === admittedOrganizationId)
    ? current.name
    : null;
}

/**
 * The ready-to-send invitation message (REQ-0024 addition 5), shown as the
 * person will read it, with one button that copies all of it.
 */
export function InvitationMessageCopy({ message }: { message: string }) {
  const id = useId();
  const [copy, copyText] = useCopyText();
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <label htmlFor={id} className="text-sm font-medium">
        Message to send
      </label>
      <Textarea
        id={id}
        readOnly
        value={message}
        className="min-h-24 resize-none"
        onFocus={(event) => event.currentTarget.select()}
      />
      <Button
        type="button"
        className="min-h-11 w-full sm:w-auto sm:self-start"
        onClick={() => copyText(message)}
      >
        {copy === "copied" ? (
          <Check aria-hidden="true" />
        ) : (
          <Copy aria-hidden="true" />
        )}
        {copy === "copied" ? "Copied" : "Copy invitation message"}
      </Button>
      <span role="status" className="sr-only">
        {copy === "copied" ? "Copied." : ""}
      </span>
      {copy === "failed" ? (
        <p role="alert" className="text-danger-text text-sm">
          Copy did not work. Select the text and copy it yourself.
        </p>
      ) : null}
    </div>
  );
}
