"use client";

import { MailWarning } from "lucide-react";

import { GuardedWorkspaceLink } from "@/components/workspace-navigation-guard";

/**
 * The administrator's email line (DEC-0042, AC-E1), shown by
 * ShellAccountChecks while email is not set up. It holds no live region:
 * it appears after the page and stays.
 */
export default function EmailSetupNoticeLine() {
  return (
    <div
      data-slot="email-setup-notice"
      className="border-border bg-card text-foreground flex min-h-10 flex-wrap items-center gap-x-2 border-b px-4 py-1 text-sm sm:px-5"
    >
      <MailWarning
        aria-hidden="true"
        className="text-muted-foreground size-4 shrink-0"
      />
      <p className="min-w-0">
        Email is not set up. Invitations and password emails cannot be sent.
      </p>
      <GuardedWorkspaceLink
        href="/manage?view=email"
        className="text-action-text inline-flex min-h-11 items-center font-medium underline underline-offset-4 xl:min-h-8"
      >
        How to set up email
      </GuardedWorkspaceLink>
    </div>
  );
}
